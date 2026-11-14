"""Completed student input controls the canonical mock task, never model arguments."""
import asyncio
import time

import pytest

from agentic.openarms_lab.backends import MockBackend
from agentic.openarms_lab.runtime import Lab, LabError
from agentic.openarms_lab.voice_controls import VoiceControls
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


@pytest.mark.parametrize('text', ['Thanks!', 'Why does cabbage indicator turn pink?'])
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
