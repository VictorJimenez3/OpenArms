"""Conversational replies and clarification retain their task context."""
import asyncio
import copy
from pathlib import Path

import pytest
from agentic.openarms_lab.runtime import Lab
from agentic.openarms_lab.scene import SceneService
from agentic.openarms_lab.simulated_backend import SceneBackend
from agentic.openarms_lab.simulation_evaluation import simulation_scope
from agentic.tests.test_task_evidence_review import DEFINITION


class ClarifyingExpert:
    def __init__(self):
        self.contexts = []

    async def run(self, context, **_):
        self.contexts.append(copy.deepcopy(context))
        clarify = len(self.contexts) == 1
        return {'kind': 'clarification' if clarify else 'plan',
                'summary': 'Which prepared sample should I test?' if clarify else 'Prepared sample plan',
                'payload': {} if clarify else {'skill_definition': copy.deepcopy(DEFINITION),
                                               'bindings': {'condition': 'water'}},
                'provider': 'TEST_FAKE', 'model': 'TEST_FAKE', 'calls': 1,
                'usage': {}, 'elapsed_ms': 1, 'tool_receipts': []}


@pytest.mark.asyncio
async def test_thanks_is_conversation_and_how_about_starts_real_task(tmp_path):
    scene, expert = SceneService(tmp_path / 'images'), ClarifyingExpert()
    lab = Lab(tmp_path / 'data', expert=expert, perception=scene,
              backend_factory=lambda: SceneBackend(scene, delay=0))
    try:
        sid = (await lab.create())['session_id']
        for text in ('Thanks', 'Hello', 'Okay'):
            await lab.converse(sid, text)
        assert lab.get(sid)['tasks'] == [] and expert.contexts == []
        await lab.converse(sid, 'How about testing a prepared sample with indicator?')
        first = lab.get(sid)['tasks'][-1]
        await asyncio.wait_for(asyncio.shield(lab.workers[first['task_id']]), 5)
        assert first['status'] == 'needs_clarification'
        assert expert.contexts[0]['request'].startswith('How about testing')
        await lab.converse(sid, 'water')
        second = lab.get(sid)['tasks'][-1]
        await asyncio.wait_for(asyncio.shield(lab.workers[second['task_id']]), 5)
        context = expert.contexts[-1]
        assert context['clarification'] == {'task_id': first['task_id'], 'request': first['request'],
                                           'question': first['summary'], 'answer': 'water'}
        assert second['status'] == 'awaiting_confirmation'
        assert lab.backends[sid].executions == 0
        assert not lab.get(sid)['pending']['student_confirmed']
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_cancel_clears_unanswered_clarification(tmp_path):
    scene, expert = SceneService(tmp_path / 'images'), ClarifyingExpert()
    lab = Lab(tmp_path / 'data', expert=expert, perception=scene,
              backend_factory=lambda: SceneBackend(scene, delay=0))
    try:
        sid = (await lab.create())['session_id']
        handle = await lab.start_task(sid, 'Test a prepared sample')
        await asyncio.wait_for(asyncio.shield(lab.workers[handle['task_id']]), 5)
        await lab.converse(sid, 'cancel')
        assert lab.get(sid)['tasks'][-1]['status'] == 'cancelled'
        handle = await lab.start_task(sid, 'Test prepared water')
        await asyncio.wait_for(asyncio.shield(lab.workers[handle['task_id']]), 5)
        assert expert.contexts[-1]['clarification'] is None
    finally:
        await lab.shutdown()


@pytest.mark.parametrize('suffix', ['models/so101/so101_new_calib.xml', 'config/setups/block/poses.json'])
def test_simulator_configuration_changes_invalidate_admission(monkeypatch, suffix):
    before, read = simulation_scope(), Path.read_bytes
    def changed(path):
        value = read(path)
        return value + b'changed-config' if path.as_posix().endswith(suffix) else value
    monkeypatch.setattr(Path, 'read_bytes', changed)
    assert simulation_scope() != before


@pytest.mark.asyncio
async def test_spoken_condition_answer_resumes_clarification_in_one_mutation(tmp_path):
    from agentic.openarms_lab.voice_controls import VoiceControls
    scene, expert = SceneService(tmp_path/'images'), ClarifyingExpert()
    lab = Lab(tmp_path/'data', expert=expert, perception=scene,
              backend_factory=lambda: SceneBackend(scene, delay=0))
    try:
        sid = (await lab.create())['session_id']
        handle = await lab.start_task(sid, 'Test a prepared sample')
        await asyncio.wait_for(asyncio.shield(lab.workers[handle['task_id']]), 5)
        async def callback(name, args):
            return await lab.tool(sid, name, args)
        controls = VoiceControls(lambda: lab.snapshot(sid), callback)
        controls.input('water', finished=True)
        await lab.tool(sid, '_record_transcript', {'role':'user', 'text':'water',
                       'turn_id':controls.turn_id, 'final':True})
        await controls.dispatch('choose_condition', {'condition_id':'water'})
        task = lab.get(sid)['tasks'][-1]
        await asyncio.wait_for(asyncio.shield(lab.workers[task['task_id']]), 5)
        assert task['status'] == 'awaiting_confirmation'
        assert task['clarification']['task_id'] == handle['task_id']
        assert expert.contexts[-1]['clarification']['answer'] == 'water'
        assert controls.consumed and lab.backends[sid].executions == 0
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_status_question_leaves_clarification_open_for_the_next_turn(tmp_path):
    scene, expert = SceneService(tmp_path / 'images'), ClarifyingExpert()
    lab = Lab(tmp_path / 'data', expert=expert, perception=scene,
              backend_factory=lambda: SceneBackend(scene, delay=0))
    try:
        sid = (await lab.create())['session_id']
        first = await lab.start_task(sid, 'Test a prepared sample')
        await asyncio.wait_for(asyncio.shield(lab.workers[first['task_id']]), 5)

        status = await lab.converse(sid, 'What are you waiting for?', 'status-question')
        assert len(status['tasks']) == len(expert.contexts) == 1
        assert status['tasks'][0]['status'] == 'needs_clarification'
        assert 'which prepared sample' in status['messages'][-1]['text'].lower()
        duplicate = await lab.converse(sid, 'What are you waiting for?', 'status-question')
        assert duplicate['revision'] == status['revision']

        await lab.converse(sid, 'The water one, please.')
        second = lab.get(sid)['tasks'][-1]
        await asyncio.wait_for(asyncio.shield(lab.workers[second['task_id']]), 5)
        assert expert.contexts[-1]['clarification']['task_id'] == first['task_id']
        assert expert.contexts[-1]['clarification']['answer'] == 'The water one, please.'
        assert second['status'] == 'awaiting_confirmation'
        assert lab.backends[sid].executions == 0
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_sample_correction_regenerates_proposal_and_requires_fresh_consent(tmp_path):
    from agentic.openarms_lab.runtime import LabError
    from agentic.tests.test_task_loop import TestExpert, TestPerception

    lab = Lab(tmp_path, expert=TestExpert(), perception=TestPerception())
    try:
        sid = (await lab.create())['session_id']
        await lab.converse(sid, 'Test the prepared vinegar sample.')
        await asyncio.wait_for(asyncio.shield(lab.workers[lab.get(sid)['tasks'][-1]['task_id']]), 5)
        first = lab.snapshot(sid)['pending']
        await lab.present(sid, first['request_id'], first['proposal_version'])

        corrected = await lab.converse(sid, 'Actually, use water instead.', 'correction')
        assert corrected['pending'] is None and len(corrected['tasks']) == 2
        assert corrected['requests'][-1]['status'] == 'cancelled'
        assert (await lab.converse(sid, 'Actually, use water instead.', 'correction'))['tasks'][-1]['task_id'] == corrected['tasks'][-1]['task_id']
        await asyncio.wait_for(asyncio.shield(lab.workers[corrected['tasks'][-1]['task_id']]), 5)
        second = lab.snapshot(sid)['pending']
        assert second['condition_id'] == 'water'
        assert second['proposal_version'] != first['proposal_version']
        assert not second['presented'] and not second['student_confirmed']
        with pytest.raises(LabError, match='Stale'):
            await lab.confirm(sid, first['request_id'], first['proposal_version'])
        assert lab.backends[sid].executions == 0
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_progress_and_science_questions_answer_while_confirmation_executes(tmp_path):
    from agentic.openarms_lab.backends import MockBackend
    from agentic.tests.test_task_loop import TestExpert, TestPerception

    entered, release = asyncio.Event(), asyncio.Event()

    class PausedBackend(MockBackend):
        async def execute_step(self, request_id, arguments, progress, **options):
            entered.set()
            await release.wait()
            return await super().execute_step(request_id, arguments, progress, **options)

    expert = TestExpert()
    backend = PausedBackend(delay=0)
    lab = Lab(tmp_path, expert=expert, perception=TestPerception(unknown=False),
              backend_factory=lambda: backend)
    try:
        sid = (await lab.create())['session_id']
        await lab.converse(sid, 'Test the prepared vinegar sample.')
        task_id = lab.get(sid)['tasks'][-1]['task_id']
        await asyncio.wait_for(asyncio.shield(lab.workers[task_id]), 5)
        proposal = lab.snapshot(sid)['pending']
        exact = {k: proposal[k] for k in ('request_id', 'proposal_version')}
        await lab.present(sid, **exact)
        await lab.confirm(sid, **exact)
        await asyncio.wait_for(entered.wait(), 5)
        expert_calls = len(expert.contexts)

        status = await lab.converse(sid, 'How is it going?')
        assert 'action hasn’t started' in status['messages'][-1]['text']
        science = await lab.converse(sid, 'What is the water control for?')
        assert 'comparison' in science['messages'][-1]['text']
        assert [t['task_id'] for t in science['tasks']] == [task_id]
        assert len(expert.contexts) == expert_calls
        assert science['requests'][-1]['status'] == 'executing'

        release.set()
        await asyncio.wait_for(asyncio.shield(lab.workers[task_id]), 5)
        assert backend.executions == 1
        completed = lab.snapshot(sid)
        assert completed['tasks'][0]['status'] == 'completed'
        await lab.converse(sid, 'Stop.')
        after_stop = await lab.converse(sid, 'What happened to the test?')
        assert after_stop['trial']['state'] == completed['trial']['state']
        assert after_stop['observations'] == completed['observations']
        assert after_stop['messages'][-1]['text'] == completed['observations'][-1]['text']
        stop = next(e['data'] for e in reversed(after_stop['notebook']) if e['kind'] == 'stop_requested')
        assert stop['effect'] == 'idle'
    finally:
        release.set()
        await lab.shutdown()


@pytest.mark.asyncio
async def test_repetition_preserves_pending_plan_and_action_questions_can_plan(tmp_path):
    from agentic.tests.test_task_loop import TestExpert, TestPerception

    expert = TestExpert()
    lab = Lab(tmp_path, expert=expert, perception=TestPerception())
    try:
        sid = (await lab.create())['session_id']
        await lab.converse(sid, 'Will you pick up cup A?')
        tasks = lab.get(sid)['tasks']
        assert len(tasks) == 1
        await asyncio.wait_for(asyncio.shield(lab.workers[tasks[0]['task_id']]), 5)
        proposal = lab.snapshot(sid)['pending']
        for question in ('Can you repeat that?', 'Could you say that again?', 'Tell me more.'):
            snapshot = await lab.converse(sid, question)
            assert len(snapshot['tasks']) == 1
            assert snapshot['pending']['request_id'] == proposal['request_id']
            assert proposal['summary'] in snapshot['messages'][-1]['text']
        assert len(expert.contexts) == 1

        await lab.converse(sid, 'Do the water test.')
        tasks = lab.get(sid)['tasks']
        assert len(tasks) == 2
        assert tasks[-1]['request'] == 'Do the water test.'
    finally:
        await lab.shutdown()


def test_text_conversation_describes_only_active_water_fixture():
    from agentic.openarms_lab.conversation import conversation_reply

    state = {'experiment': {'id': 'two_vessel_water'},
             'trial': {'trial_id': 'trial'}, 'observations': [],
             'capabilities': {'action_description': 'pour one premeasured water portion from A into C, return donor to A and return HOME'}}
    assert state['capabilities']['action_description'] in conversation_reply('What can you do?', state)
    answer = conversation_reply('What will the indicator color be?', state)
    assert 'water-only' in answer.lower() and 'indicator' in answer.lower()
    assert 'purple' not in answer.lower()
