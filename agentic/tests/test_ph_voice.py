"""Transport/consent regressions; deliberately no provider, microphone or hardware."""
import asyncio
import base64
import array
import time
from types import SimpleNamespace as NS
import pytest
from agentic.openarms_lab.voice_controls import VoiceControls
from agentic.openarms_lab.live import GeminiBridge


@pytest.fixture
def state():
    return {'generation': 0, 'pending': {'request_id': 'r1', 'proposal_version': 'v1', 'presented': True, 'summary': 'Add the vinegar sample.'}, 'requests': [], 'observations': []}


@pytest.mark.asyncio
async def test_completed_confirm_executes_without_waiting_for_model_and_tool_does_not_repeat(state):
    calls = []
    async def callback(name, args):
        calls.append((name, args))
        state['pending'] = None
        return state
    controls = VoiceControls(lambda: state, callback)
    controls.input('Con')
    assert await controls.complete_control() is None
    controls.input('firm.', finished=True)
    await controls.complete_control()
    await controls.dispatch('student_confirm', {'request_id': 'r1', 'proposal_version': 'v1'})
    assert len(calls) == 1
    assert calls[0][1]['_voice_consent']['turn_id'] == controls.turn_id


@pytest.mark.asyncio
@pytest.mark.parametrize('text', ['do not confirm', 'confirm but change it', 'maybe yes', 'cancel and confirm'])
async def test_mixed_or_negated_speech_cannot_confirm(state, text):
    async def callback(*args):
        pytest.fail('Consent was manufactured')
    controls = VoiceControls(lambda: state, callback)
    controls.input(text, finished=True)
    with pytest.raises(ValueError):
        await controls.dispatch('student_confirm', {'request_id': 'r1', 'proposal_version': 'v1'})


@pytest.mark.asyncio
async def test_presentation_must_precede_utterance_not_only_tool_call(state):
    state['pending']['presented'] = False
    controls = VoiceControls(lambda: state, lambda *_: None)
    controls.input('confirm')
    state['pending']['presented'] = True
    controls.input('', finished=True)
    with pytest.raises(ValueError):
        await controls.complete_control()


@pytest.mark.asyncio
async def test_new_version_disconnect_and_repeated_consent_rejected(state):
    controls = VoiceControls(lambda: state, lambda *_: None)
    controls.input('confirm', finished=True)
    state['generation'] += 1
    with pytest.raises(ValueError):
        await controls.complete_control()


@pytest.mark.asyncio
async def test_pcm_end_closes_optional_asr_finished_and_binds_at_audio_onset(state):
    calls, events = [], []
    async def callback(name, args):
        calls.append((name, args))
        return state
    async def emit(event): events.append(event)
    bridge = GeminiBridge(lambda: state, callback, emit)
    bridge.ready = True
    state['pending']['presented'] = False
    await bridge.audio(base64.b64encode(array.array('h', [1000]*1600).tobytes()).decode())
    state['pending']['presented'] = True
    bridge.controls.input('Confirm.')  # provider omitted optional finished flag
    bridge.last_transcription = time.monotonic()
    for _ in range(7): await bridge.audio(base64.b64encode(bytes(3200)).decode())
    await bridge.input_boundary
    assert bridge.controls.finished.is_set()
    assert any(name == '_record_transcript' and args['final'] for name, args in calls)
    assert not any(name == 'student_confirm' for name, _ in calls)
    assert any(event['type'] == 'error' for event in events)


@pytest.mark.asyncio
async def test_pcm_boundary_unblocks_completed_request_without_model_consent(state):
    calls = []
    async def callback(name, args):
        calls.append((name, args))
        return state
    async def emit(event): pass
    bridge = GeminiBridge(lambda: state, callback, emit)
    bridge.ready = True
    await bridge.audio(base64.b64encode(array.array('h', [1000]*1600).tobytes()).decode())
    bridge.controls.input('Please inspect the scene.')
    bridge.last_transcription = time.monotonic()
    waiting = asyncio.create_task(bridge.controls.dispatch('request_action', {'text':'Please inspect the scene.'}))
    await bridge.end_audio()
    await waiting
    assert len([name for name, _ in calls if name == 'request_action']) == 1
    assert not any(name == 'student_confirm' for name, _ in calls)


@pytest.mark.asyncio
async def test_only_completed_matching_playback_ack_presents_audio(state):
    calls, sent = [], []
    async def callback(name, args): calls.append((name, args))
    async def emit(msg): sent.append(msg)
    bridge = GeminiBridge(lambda: state, callback, emit)
    bridge.replies['a'] = {'complete': False, 'proposal': {'request_id': 'r1', 'proposal_version': 'v1'}}
    await bridge.played('a')
    assert not calls
    bridge.replies['b'] = {'complete': True, 'proposal': {'request_id': 'r1', 'proposal_version': 'v1'}}
    await bridge.played('b')
    await bridge.played('b')
    assert len(calls) == 1
    assert calls[0][0] == '_present_audio'
    bridge.replies['c'] = {'complete': True, 'proposal': {'request_id': 'r1', 'proposal_version': 'v1'}}
    await bridge.interrupt('c')
    await bridge.played('c')
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_audio_bounds_mute_and_overflow_drop_stale_inputs(state):
    sent = []
    async def emit(msg): sent.append(msg)
    bridge = GeminiBridge(lambda: state, lambda *_: None, emit)
    bridge.ready = True
    with pytest.raises(ValueError): await bridge.audio('not base64')
    with pytest.raises(ValueError): await bridge.audio(base64.b64encode(b'x' * 6402).decode())
    await bridge.audio(base64.b64encode(b'\0\0' * 1600).decode())
    assert bridge.incoming.qsize() == 1
    await bridge.mute(True)
    assert all(item[0] != 'audio' for item in list(bridge.incoming._queue))
    await bridge.audio(base64.b64encode(b'\0\0' * 1600).decode())
    assert all(item[0] != 'audio' for item in list(bridge.incoming._queue))


@pytest.mark.asyncio
async def test_missing_provider_keeps_application_session_alive(state, monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    sent, calls = [], []
    async def emit(msg): sent.append(msg)
    async def callback(*args): calls.append(args)
    await GeminiBridge(lambda: state, callback, emit).run()
    assert sent[-1]['status'] == 'unavailable'
    assert not calls

@pytest.mark.asyncio
async def test_speech_captured_during_assistant_playback_cannot_be_consent(state):
    playing = True
    controls = VoiceControls(lambda: state, lambda *_: None, lambda: not playing)
    controls.input('confirm')
    playing = False
    controls.input('', finished=True)
    with pytest.raises(ValueError):
        await controls.complete_control()


@pytest.mark.asyncio
async def test_background_observations_use_correlated_nonblocking_tool_responses(state):
    state['pending'] = None
    responses = []
    received = asyncio.Event()
    async def tool_response(**kwargs):
        responses.extend(kwargs['function_responses'])
        received.set()
    async def callback(*_):
        pytest.fail('The event subscription must not execute a lab action')
    async def emit(*_):
        pass
    bridge = GeminiBridge(lambda: state, callback, emit)
    session = NS(send_tool_response=tool_response)
    task = asyncio.create_task(bridge._tool(session, NS(id='watch-1', name='watch_lab_events', args={})))
    await asyncio.wait_for(received.wait(), .2)
    received.clear()
    state['messages'] = [{'role': 'assistant', 'text': 'Still working.'}]
    await bridge.state_changed()
    assert bridge.state_updates.empty()  # No transcript -> event -> speech feedback loop.
    state['observations'] = [{'provenance': 'SIMULATED', 'color': 'pink', 'evidence_id': 'frame-2'}]
    await bridge.state_changed()
    await asyncio.wait_for(received.wait(), .2)
    assert len(responses) == 2
    assert all(r.id == 'watch-1' and r.will_continue for r in responses)
    assert responses[-1].response['state']['observations'][0]['evidence_id'] == 'frame-2'
    assert responses[-1].scheduling.value == 'WHEN_IDLE'
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert bridge.watcher_id is None


async def test_playback_ack_does_not_trigger_another_proposal_reply(state):
    async def callback(*args): return state
    async def emit(*args): pass
    state['pending']['presented'] = False
    bridge = GeminiBridge(lambda: state, callback, emit)
    await bridge.state_changed()
    bridge.state_updates.get_nowait()
    state['pending']['presented'] = True
    await bridge.state_changed()
    assert bridge.state_updates.empty()
    state['voice_control'] = {'accepted': False, 'reason': 'Fresh confirmation required.', 'turn_id': 'turn-2'}
    await bridge.state_changed()
    assert bridge.state_updates.get_nowait()['voice_control']['accepted'] is False
