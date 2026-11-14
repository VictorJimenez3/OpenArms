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
        await lab.converse(sid, 'How about testing a prepared sample with cabbage indicator?')
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
