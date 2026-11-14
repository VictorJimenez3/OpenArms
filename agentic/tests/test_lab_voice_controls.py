"""Completed student input controls the canonical mock task, never model arguments."""
import asyncio
import time

import pytest

from agentic.openarms_lab.backends import MockBackend
from agentic.openarms_lab.runtime import Lab, LabError
from agentic.openarms_lab.voice_controls import VoiceControls
from agentic.openarms_lab.live import GeminiBridge
from agentic.tests.test_task_loop import TestExpert, TestPerception


@pytest.fixture
async def voice_lab(tmp_path):
    backend = MockBackend(delay=0)
    lab = Lab(tmp_path, expert=TestExpert(), perception=TestPerception(unknown=False),
              backend_factory=lambda: backend)
    sid = (await lab.create())['session_id']
    controls = VoiceControls(lambda: lab.snapshot(sid), lambda n, a: lab.tool(sid, n, a))
    try:
        yield lab, sid, controls, backend
    finally:
        await lab.shutdown()


async def wait_for_task(lab, task_id):
    worker = lab.workers.get(task_id)
    if worker:
        await asyncio.wait_for(asyncio.shield(worker), 2)


async def propose(voice_lab, *, presented=False):
    lab, sid, controls, _ = voice_lab
    text = 'Test the prepared vinegar sample.'
    controls.input(text, finished=True)
    await lab.tool(sid, '_record_transcript',
                   {'role': 'user', 'text': text, 'turn_id': controls.turn_id, 'final': True})
    task = await controls.dispatch('request_action', {'text': text})
    assert task['status'] == 'queued'
    await wait_for_task(lab, task['task_id'])
    pending = lab.snapshot(sid)['pending']
    assert pending['turn_id'] == controls.turn_id
    exact = {k: pending[k] for k in ('request_id', 'proposal_version')}
    if presented:
        await lab.present(sid, **exact)
    return task['task_id'], exact


async def say(controls, text):
    controls.input(text, finished=True)
    return await controls.complete_control()


@pytest.mark.parametrize('phrase', ['Please stop now.', 'Stop now, please.', 'Please stop.'])
@pytest.mark.parametrize('channel', ['voice', 'text'])
async def test_polite_stop_revokes_pending_work_on_both_channels(voice_lab, phrase, channel):
    lab, sid, controls, backend = voice_lab
    await propose(voice_lab, presented=True)
    generation = lab.snapshot(sid)['generation']
    if channel == 'voice':
        await say(controls, phrase)
    else:
        await lab.converse(sid, phrase)
    state = lab.snapshot(sid)
    assert state['generation'] > generation
    assert state['pending'] is None and backend.executions == 0
    assert state['tasks'][0]['status'] == 'cancelled'


@pytest.mark.parametrize('phrase', ['Do not stop.', 'What if I ask you to stop?',
                                  'Say please stop now.', '"Please stop now."', 'Stap.'])
async def test_stop_discussion_and_misrecognition_are_not_controls(voice_lab, phrase):
    lab, sid, controls, _ = voice_lab
    generation = lab.snapshot(sid)['generation']
    await say(controls, phrase)
    assert lab.snapshot(sid)['generation'] == generation


@pytest.mark.parametrize('correction', ['Actually, use water instead.', 'Actually, test the prepared water sample.'])
async def test_completed_correction_precedes_fast_confirmation_without_model_tool(voice_lab, correction):
    lab, sid, _, backend = voice_lab
    await lab.choose_condition(sid, 'vinegar')
    _, old = await propose(voice_lab, presented=True)
    async def emit(_):
        pass
    bridge = GeminiBridge(lambda: lab.snapshot(sid), lambda n, a: lab.tool(sid, n, a), emit)
    bridge.controls.input(correction)
    await bridge._finish_transcript()
    bridge.controls.input('Confirm.')
    await bridge._finish_transcript()
    state = lab.snapshot(sid)
    original = next(r for r in state['requests'] if r['request_id'] == old['request_id'])
    assert original['status'] == 'cancelled' and not original['student_confirmed']
    assert backend.executions == 0
    assert len(state['tasks']) == 2
    assert state['trial']['condition_id'] == 'water'
    await wait_for_task(lab, state['tasks'][-1]['task_id'])
    pending = lab.snapshot(sid)['pending']
    assert pending and pending['condition_id'] == 'water'
    assert pending['plan']['bindings']['condition'] == 'water'
    assert not pending['student_confirmed']


async def test_completed_stop_applies_before_slow_transcript_delivery(voice_lab):
    lab, sid, _, _ = voice_lab
    entered, release = asyncio.Event(), asyncio.Event()
    async def emit(frame):
        if frame.get('type') == 'transcript' and frame.get('final'):
            entered.set()
            await release.wait()
    bridge = GeminiBridge(lambda: lab.snapshot(sid), lambda n, a: lab.tool(sid, n, a), emit)
    generation = lab.snapshot(sid)['generation']
    bridge.controls.input('Please stop now.')
    finish = asyncio.create_task(bridge._finish_transcript())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        bridge.controls.begin_input()
        assert lab.snapshot(sid)['generation'] > generation
    finally:
        release.set()
        await finish


@pytest.mark.parametrize('name,arguments', [('record_prediction', {'text':'I predict pink.'}),
                                           ('prepare_next_trial', {})])
async def test_waiting_voice_mutation_cannot_cross_stop(voice_lab, name, arguments):
    lab, sid, _, _ = voice_lab
    lock = lab._lock(sid)
    await lock.acquire()
    generation = lab.snapshot(sid)['generation']
    stop = asyncio.create_task(lab.stop(sid))
    await asyncio.sleep(0)
    mutation = asyncio.create_task(lab.tool(sid, name, {**arguments, '_voice_generation':generation}))
    await asyncio.sleep(0)
    lock.release()
    await stop
    with pytest.raises(LabError, match='Stale voice generation'):
        await mutation


async def test_completed_explicit_voice_action_starts_task_without_model_tool(voice_lab):
    lab, sid, _, backend = voice_lab
    async def emit(_):
        pass
    bridge = GeminiBridge(lambda: lab.snapshot(sid), lambda n, a: lab.tool(sid, n, a), emit)
    bridge.controls.input('Please test the prepared vinegar sample and check the indicator color.')
    await bridge._finish_transcript()
    state = lab.snapshot(sid)
    assert len(state['tasks']) == 1 and backend.executions == 0


async def test_completed_reset_recovers_session_requiring_prepare(voice_lab):
    lab, sid, _, _ = voice_lab
    lab.get(sid)['requires_prepare'] = True
    async def emit(_):
        pass
    bridge = GeminiBridge(lambda:lab.snapshot(sid),lambda n,a:lab.tool(sid,n,a),emit)
    bridge.controls.input('Please prepare a new trial.')
    await bridge._finish_transcript()
    assert lab.snapshot(sid)['requires_prepare'] is False
    assert not lab.snapshot(sid)['tasks']


@pytest.mark.parametrize('text', ['Can you test another sample after this one?', 'Please prepare a new trial.'])
async def test_completed_question_and_reset_do_not_queue_another_expert(voice_lab, text):
    lab, sid, _, _ = voice_lab
    _, old = await propose(voice_lab, presented=True)
    async def emit(_):
        pass
    bridge = GeminiBridge(lambda: lab.snapshot(sid), lambda n, a: lab.tool(sid,n,a),emit)
    bridge.controls.input(text)
    await bridge._finish_transcript()
    state = lab.snapshot(sid)
    assert len(state['tasks']) == 1
    if text.startswith('Can'):
        assert state['pending']['request_id'] == old['request_id']
    else:
        assert state['pending'] is None


async def test_new_pcm_cannot_cancel_completed_stop_waiting_for_lock(voice_lab):
    import base64
    lab, sid, _, _ = voice_lab
    entered = asyncio.Event()
    async def callback(name, args):
        if name == 'stop_lab':
            entered.set()
        return await lab.tool(sid,name,args)
    async def emit(_):
        pass
    bridge = GeminiBridge(lambda:lab.snapshot(sid),callback,emit)
    bridge.ready = True
    bridge.controls.input('Please stop now.')
    bridge.last_transcription = time.monotonic()-1
    lock=lab._lock(sid)
    await lock.acquire()
    bridge._end_speech()
    timer=bridge.input_boundary
    try:
        await asyncio.wait_for(entered.wait(),2)
        await bridge.audio(base64.b64encode(b'\xff\x1f'*1600).decode())
    finally:
        lock.release()
    await asyncio.gather(timer,return_exceptions=True)
    assert any(e['kind']=='stop_requested' for e in lab.snapshot(sid)['notebook'])


async def test_voice_cancel_then_completed_confirmation_executes_new_task_once(voice_lab):
    lab, sid, controls, backend = voice_lab
    controls.input('I predict pink.', finished=True)
    await controls.dispatch('record_prediction', {'text': 'I predict pink.'})
    assert not lab.snapshot(sid)['tasks']

    _, first = await propose(voice_lab, presented=True)
    await say(controls, 'Cancel.')
    assert lab.snapshot(sid)['pending'] is None
    assert not backend.executions

    task_id, exact = await propose(voice_lab, presented=True)
    controls.input('Confirm.', finished=True)
    with pytest.raises(ValueError, match='current proposal'):
        await controls.dispatch('student_confirm', first)
    with pytest.raises(ValueError, match='current proposal'):
        await controls.dispatch('student_confirm', {**exact, 'proposal_version': first['proposal_version']})
    await controls.complete_control()
    await controls.dispatch('student_confirm', exact)
    await wait_for_task(lab, task_id)

    snap = lab.snapshot(sid)
    assert [r['status'] for r in snap['requests']] == ['cancelled', 'completed']
    assert snap['requests'][-1]['student_confirmed']
    assert snap['requests'][-1]['result']['physical_execution'] is False
    assert backend.executions == 1 and snap['observations'][-1]['provenance'] == 'SYNTHETIC'
    controls.input('Confirm.', finished=True)
    # A later turn cannot use the old tool receipt.
    with pytest.raises(ValueError, match='current proposal'):
        await controls.dispatch('student_confirm', exact)
    assert backend.executions == 1


@pytest.mark.parametrize('utterance', ['yes but use water', 'do not confirm', 'I predict yes',
                                      'say confirm', '“confirm”', 'confirm?', ''])
async def test_model_cannot_invent_student_consent(voice_lab, utterance):
    lab, sid, controls, backend = voice_lab
    _, exact = await propose(voice_lab, presented=True)
    controls.input(utterance, finished=True)
    fake = {**exact, '_voice_consent': {**exact, 'text': 'yes', 'turn_id': controls.turn_id}}
    with pytest.raises(ValueError):
        await controls.dispatch('student_confirm', fake)
    pending = lab.snapshot(sid)['pending']
    assert pending['request_id'] == exact['request_id'] and not pending['student_confirmed']
    assert not backend.executions


async def test_confirmation_requires_new_completed_utterance_after_presentation(voice_lab):
    lab, sid, controls, backend = voice_lab
    task_id, exact = await propose(voice_lab)
    controls.input('Yes, ', finished=False)
    await lab.present(sid, **exact)
    controls.input('confirm.', finished=True)
    with pytest.raises(ValueError, match='current proposal'):
        await controls.complete_control()
    assert not backend.executions

    controls.input('Con', finished=False)
    attempt = asyncio.create_task(controls.dispatch('student_confirm', exact))
    try:
        await asyncio.sleep(0)
        assert not attempt.done()
        assert await controls.complete_control() is None
        assert not backend.executions and not lab.snapshot(sid)['pending']['student_confirmed']
        controls.input('firm.', finished=True)
        await asyncio.wait_for(attempt, 2)
    finally:
        if not attempt.done():
            attempt.cancel()
            await asyncio.gather(attempt, return_exceptions=True)
    await wait_for_task(lab, task_id)
    assert backend.executions == 1


@pytest.mark.parametrize('revocation', ['expiry', 'stop', 'disconnect'])
async def test_stale_disconnected_and_stop_consent_rejected(voice_lab, monkeypatch, revocation):
    lab, sid, controls, backend = voice_lab
    _, exact = await propose(voice_lab, presented=True)
    controls.input('confirm', finished=True)
    if revocation == 'expiry':
        import agentic.openarms_lab.voice_controls as voice
        monkeypatch.setattr(voice, 'time', type('Clock', (), {'monotonic': lambda: time.monotonic() + 31}))
    else:
        await lab.stop(sid, disconnect=(revocation == 'disconnect'))

    with pytest.raises(ValueError, match='current proposal'):
        await controls.dispatch('student_confirm', exact)
    if revocation != 'expiry':
        with pytest.raises(LabError, match='Stale|disconnected'):
            await lab.confirm(sid, **exact)
    assert not backend.executions


async def test_voice_action_waits_for_final_correlated_student_transcript(voice_lab):
    lab, sid, controls, backend = voice_lab
    text = 'Test the prepared water sample.'
    controls.input(text, finished=True)
    args = {'text': text}
    with pytest.raises(LabError, match='completed user turn'):
        await controls.dispatch('request_action', args)
    controls.input(text, finished=True)
    await lab.tool(sid, '_record_transcript',
                   {'role': 'assistant', 'text': text, 'turn_id': controls.turn_id, 'final': True})
    with pytest.raises(LabError, match='completed user turn'):
        await controls.dispatch('request_action', args)
    assert lab.snapshot(sid)['tasks'] == []
    assert not backend.executions


async def test_provider_integral_float_uses_server_version_and_concurrent_confirm_is_once(voice_lab):
    lab, sid, controls, backend = voice_lab
    task_id, exact = await propose(voice_lab, presented=True)
    entered, release = asyncio.Event(), asyncio.Event()
    original = controls.callback
    seen = []
    async def delayed(name, args):
        if name == 'student_confirm':
            seen.append(args)
            entered.set()
            await release.wait()
        return await original(name, args)
    controls.callback = delayed
    controls.input('Confirm.', finished=True)
    provider = asyncio.create_task(controls.dispatch('student_confirm', {
        **exact, 'proposal_version': float(exact['proposal_version'])}))
    await entered.wait()
    deterministic = asyncio.create_task(controls.dispatch('student_confirm', exact))
    await asyncio.sleep(0)
    assert not deterministic.done()
    release.set()
    await asyncio.gather(provider, deterministic)
    await wait_for_task(lab, task_id)
    assert len(seen) == backend.executions == 1
    assert type(seen[0]['proposal_version']) is int
    assert type(seen[0]['_voice_consent']['proposal_version']) is int
    with pytest.raises(ValueError):
        await controls.dispatch('student_confirm', {**exact, 'proposal_version': True})


@pytest.mark.parametrize('name', ['request_action', 'start_task'])
async def test_mutation_uses_completed_transcript_and_claims_turn_once(voice_lab, name):
    lab, sid, controls, _ = voice_lab
    text = 'How about testing the prepared vinegar and checking the indicator?'
    controls.input(text, finished=True)
    await lab.tool(sid, '_record_transcript',
                   {'role': 'user', 'text': text, 'turn_id': controls.turn_id, 'final': True})
    with pytest.raises(ValueError, match='verbatim'):
        await controls.dispatch(name, {'text': 'Test the prepared water sample.'})
    assert not lab.snapshot(sid)['tasks']

    alt = 'start_task' if name == 'request_action' else 'request_action'
    results = await asyncio.gather(
        controls.dispatch(name, {'text': text.lower().rstrip('?'), '_tool_call_id': 'a'}),
        controls.dispatch(alt, {'text': text, '_tool_call_id': 'b'}),
        return_exceptions=True)
    accepted = [result for result in results if isinstance(result, dict)]
    rejected = [result for result in results if isinstance(result, ValueError)]
    assert len(accepted) == len(rejected) == 1
    assert 'already used' in str(rejected[0])
    snapshot = await controls.dispatch('get_lab_state', {})
    assert len(snapshot['tasks']) == 1
    assert snapshot['tasks'][0]['request'] == text
    assert snapshot['tasks'][0]['turn_id'] == controls.turn_id


@pytest.mark.parametrize('text', ['Thanks!', 'Why does indicator turn pink?'])
async def test_conversation_is_not_a_task_even_if_model_quotes_it(voice_lab, text):
    lab, sid, controls, _ = voice_lab
    controls.input(text, finished=True)
    with pytest.raises(ValueError, match='conversational'):
        await controls.dispatch('request_action', {'text': text})
    assert not (await controls.dispatch('get_lab_state', {}))['tasks']


async def test_correction_keeps_its_own_turn_without_granting_task_consent(voice_lab):
    lab, sid, controls, backend = voice_lab
    _, proposal = await propose(voice_lab, presented=True)
    text = 'Actually, use water instead.'
    controls.input(text, finished=True)
    await lab.tool(sid, '_record_transcript',
                   {'role': 'user', 'text': text, 'turn_id': controls.turn_id, 'final': True})
    await controls.dispatch('choose_condition', {'condition_id': 'water'})
    assert lab.snapshot(sid)['trial']['condition_id'] == 'water'
    with pytest.raises(ValueError):
        await controls.dispatch('start_task', {'text': text})
    with pytest.raises(ValueError):
        await controls.dispatch('student_confirm', proposal)
    assert not backend.executions


async def test_waiting_mutation_cannot_inherit_a_later_turn(voice_lab):
    lab, sid, controls, _ = voice_lab
    controls.input('Test the prepared ')
    stale_id = controls.turn_id
    task = asyncio.create_task(controls.dispatch('request_action', {'text': 'Test the prepared vinegar.'},
                                                 turn_id=stale_id))
    await asyncio.sleep(0)
    controls.revoke()
    controls.input('Test the prepared vinegar.', finished=True)
    with pytest.raises(ValueError, match='revoked'):
        await task
    assert not lab.snapshot(sid)['tasks']


@pytest.mark.parametrize(('text', 'name', 'arguments'), [
    ('Can you tell me what you are doing?', 'request_action', {'text': 'Can you tell me what you are doing?'}),
    ('Can you repeat that?', 'request_action', {'text': 'Can you repeat that?'}),
    ('Could you say that again?', 'request_action', {'text': 'Could you say that again?'}),
    ('Tell me more.', 'request_action', {'text': 'Tell me more.'}),
    ('What would happen with water?', 'choose_condition', {'condition_id': 'water'}),
    ('I prefer vinegar.', 'choose_condition', {'condition_id': 'water'}),
    ('How long will this take?', 'prepare_next_trial', {}),
    ('What if I ask you to stop?', 'stop_lab', {}),
])
async def test_voice_question_and_mismatched_choice_cannot_mutate(voice_lab, text, name, arguments):
    lab, sid, controls, backend = voice_lab
    controls.input(text, finished=True)
    await lab.tool(sid, '_record_transcript',
                   {'role': 'user', 'text': text, 'turn_id': controls.turn_id, 'final': True})
    before = lab.snapshot(sid)
    with pytest.raises(ValueError):
        await controls.dispatch(name, arguments)
    assert lab.snapshot(sid)['revision'] == before['revision']
    assert not backend.executions
