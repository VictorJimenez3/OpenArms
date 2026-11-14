"""Consent and whole-app voice workflow against the real runtime, no provider/motors."""
import asyncio
import pytest
from agentic.openarms_lab.runtime import Lab, LabError
from agentic.openarms_lab.voice_controls import VoiceControls


@pytest.mark.asyncio
async def test_whole_application_voice_controls(tmp_path):
    lab = Lab(tmp_path)
    sid = (await lab.create())['session_id']
    controls = VoiceControls(lambda: lab.snapshot(sid), lambda n, a: lab.tool(sid, n, a))

    async def say(text, name, args={}):
        controls.input(text, finished=True)
        return await controls.dispatch(name, args)

    try:
        snap = await say('Choose color dilution', 'select_experiment', {'experiment_id': 'color_dilution'})
        assert len(snap['available_experiments']) == 3
        await say('It will be lighter', 'record_prediction', {'text': 'It will be lighter'})
        snap = await say('Add water from A to B', 'request_action', {'text': 'add water from A to B'})
        old = snap['pending']['request_id']
        snap = await say('Actually use C', 'request_action', {'text': 'add water from C to B'})
        current = snap['pending']['request_id']
        assert current != old
        with pytest.raises(ValueError):
            await say('Confirm', 'student_confirm', {'request_id': old})
        snap = await say('Cancel', 'cancel_request', {'request_id': current})
        assert snap['pending'] is None
        snap = await say('Use A', 'request_action', {'text': 'add water from A to B'})
        request = snap['pending']['request_id']
        snap = await say('Yes, confirm.', 'student_confirm', {'request_id': request})
        assert snap['requests'][-1]['student_confirmed']
        assert not snap['requests'][-1]['operator_authorized']
        await lab.tasks[sid]
        snap = lab.snapshot(sid)
        assert snap['requests'][-1]['status'] == 'completed'
        assert {o['provenance'] for o in snap['observations']} == {'MOCK', 'MODEL-PREDICTED'}
        qid = snap['quiz']['id']
        snap = await say('The concentration is lower', 'answer_question', {'question_id': qid, 'answer': 'The concentration is lower'})
        assert snap['quiz']['answered']
        snap = await say('Next trial', 'prepare_next_trial')
        assert snap['quiz'] is None and snap['prediction'] == ''
        await say('Choose buoyancy', 'select_experiment', {'experiment_id': 'buoyancy_trial'})
        assert lab.snapshot(sid)['experiment']['id'] == 'buoyancy_trial'
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize('utterance', ['yes but use C', 'do not confirm', 'I predict yes', 'say confirm', ''])
async def test_model_cannot_invent_student_consent(tmp_path, utterance):
    lab = Lab(tmp_path)
    sid = (await lab.create())['session_id']
    await lab.prediction(sid, 'float')
    snap = await lab.request(sid, 'test sample at A in B')
    rid = snap['pending']['request_id']
    controls = VoiceControls(lambda: lab.snapshot(sid), lambda n, a: lab.tool(sid, n, a))
    controls.input(utterance, finished=True)
    try:
        with pytest.raises(ValueError):
            await controls.dispatch('student_confirm', {'request_id': rid, '_voice_consent': {'text': 'yes', 'request_id': rid}})
        assert lab.snapshot(sid)['pending']['request_id'] == rid
        assert sid not in lab.tasks
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_confirmation_needs_later_utterance_and_is_single_use(tmp_path):
    lab = Lab(tmp_path)
    sid = (await lab.create())['session_id']
    await lab.prediction(sid, 'float')
    controls = VoiceControls(lambda: lab.snapshot(sid), lambda n, a: lab.tool(sid, n, a))
    controls.input('confirm', finished=True)
    snap = await controls.dispatch('request_action', {'text': 'test sample at A in B'})
    rid = snap['pending']['request_id']
    try:
        with pytest.raises(ValueError):
            await controls.dispatch('student_confirm', {'request_id': rid})
        controls.input('Yes, ', finished=False)
        task = asyncio.create_task(controls.dispatch('student_confirm', {'request_id': rid}))
        await asyncio.sleep(0)
        assert sid not in lab.tasks  # partial "yes" cannot approve
        controls.input('confirm.', finished=True)
        await task
        with pytest.raises(ValueError):
            await controls.dispatch('student_confirm', {'request_id': rid})
        assert len(lab.tasks) == 1
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_stale_disconnected_and_stop_consent_rejected(tmp_path):
    lab = Lab(tmp_path)
    sid = (await lab.create())['session_id']
    await lab.prediction(sid, 'float')
    snap = await lab.request(sid, 'test sample at A in B')
    rid = snap['pending']['request_id']
    controls = VoiceControls(lambda: lab.snapshot(sid), lambda n, a: lab.tool(sid, n, a))
    controls.input('confirm', finished=True)
    try:
        await lab.stop(sid, disconnect=True)
        with pytest.raises(ValueError):
            await controls.dispatch('student_confirm', {'request_id': rid})
        with pytest.raises(LabError):
            await lab.tool(sid, 'student_confirm', {'request_id': rid})
        assert sid not in lab.tasks
    finally:
        await lab.shutdown()
