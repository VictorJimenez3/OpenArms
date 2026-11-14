"""An active mock skill must not swallow unsupported natural request clauses."""
import asyncio

import pytest

from agentic.openarms_lab.backends import MockBackend
from agentic.openarms_lab.contracts import SkillDefinition
from agentic.openarms_lab.runtime import Lab, LabError
from agentic.tests.test_task_loop import DEFINITION, TestEvaluator, TestExpert, TestPerception, decision


class ClarifyingExpert(TestExpert):
    async def run(self, context, **kwargs):
        if context['phase'] == 'planning':
            self.contexts.append(context)
            return {**decision('clarification', {}), 'summary':
                    'Measuring dilution concentration is unavailable. Which supported mock operation would you like?'}
        return await super().run(context, **kwargs)


@pytest.fixture
async def prepared_lab(tmp_path):
    backend = MockBackend(delay=0)
    expert = ClarifyingExpert()
    lab = Lab(tmp_path, expert=expert, perception=TestPerception(unknown=False),
              backend_factory=lambda: backend)
    try:
        definition = SkillDefinition.model_validate(DEFINITION)
        version = lab.registry.validate_for_task('offline-evaluation', definition)
        receipt = await TestEvaluator().evaluate_candidate('offline-evaluation', {'version': version}, None)
        assert lab.registry.record_evaluation(definition.skill_id, version, receipt)['status'] == 'promoted'
        sid = (await lab.create())['session_id']
        yield lab, backend, sid, expert, version
    finally:
        await lab.shutdown()


async def settled(lab, sid, task_id):
    worker = lab.workers.get(task_id)
    if worker:
        await asyncio.wait_for(asyncio.shield(worker), 2)
    return lab.snapshot(sid)


async def submit(lab, sid, text, entry):
    if entry == 'voice':
        turn_id = 'offline-student-utterance'
        await lab.tool(sid, '_record_transcript',
                       {'role': 'user', 'text': text, 'turn_id': turn_id, 'final': True})
        args = {'text': text, '_voice_turn_id': turn_id, '_voice_generation': lab.snapshot(sid)['generation']}
        return await lab.tool(sid, 'request_action', args)
    return (await lab.request(sid, text))['tasks'][-1]


@pytest.mark.parametrize('text', [
    'Add water from A into B then inspect the dilution.',
    'Add water from C into B and observe the dilution.',
    'Run prepared water and then measure dilution concentration.',
    'Run prepared vinegar, then add two water volumes and inspect the dilution.',
])
@pytest.mark.parametrize('entry', ['text', 'voice'])
async def test_dilution_request_reaches_expert_intact_without_running_supported_subset(prepared_lab, text, entry):
    lab, backend, sid, expert, _ = prepared_lab
    before = backend.state()
    queued = await submit(lab, sid, text, entry)
    assert queued['status'] == 'queued'
    snap = await settled(lab, sid, queued['task_id'])
    task = snap['tasks'][-1]
    assert task['route'] == 'expert' and task['status'] == 'needs_clarification'
    assert len(expert.contexts) == 1 and expert.contexts[0]['request'] == text
    assert expert.contexts[0]['capability_limits']['physical_execution'] is False
    assert 'unavailable' in task['summary']
    assert snap['pending'] is None and snap['requests'] == [] and snap['observations'] == []
    assert task['execution'] == [] and backend.state() == before and not backend.executions


async def test_unsupported_revision_revokes_previous_presented_action(prepared_lab):
    lab, backend, sid, expert, _ = prepared_lab
    before = backend.state()
    first = await submit(lab, sid, 'Run prepared water.', 'text')
    snap = await settled(lab, sid, first['task_id'])
    old = {k: snap['pending'][k] for k in ('request_id', 'proposal_version')}
    await lab.present(sid, **old)

    text = 'Run prepared water and then measure dilution concentration.'
    revision = await submit(lab, sid, text, 'text')
    snap = await settled(lab, sid, revision['task_id'])
    assert expert.contexts[-1]['request'] == text
    assert snap['tasks'][-1]['status'] == 'needs_clarification'
    assert snap['pending'] is None and snap['requests'][0]['status'] == 'cancelled'
    with pytest.raises(LabError, match='Stale'):
        await lab.confirm(sid, **old)
    assert backend.state() == before and not backend.executions


@pytest.mark.parametrize('condition', ['vinegar', 'water'])
async def test_supported_request_reuses_exact_active_version(prepared_lab, condition):
    lab, backend, sid, expert, version = prepared_lab
    handle = await submit(lab, sid, f'Run prepared {condition}.', 'text')
    snap = await settled(lab, sid, handle['task_id'])
    proposal = snap['pending']
    assert proposal['skill_version'] == version
    assert proposal['plan']['bindings'] == {'condition': condition}
    assert snap['tasks'][-1]['route'] == 'active_skill'
    assert not snap['prediction'] and not expert.contexts and not backend.executions

    exact = {k: proposal[k] for k in ('request_id', 'proposal_version')}
    await lab.present(sid, **exact)
    await lab.confirm(sid, **exact)
    snap = await settled(lab, sid, handle['task_id'])
    assert snap['tasks'][-1]['status'] == 'completed'
    assert snap['requests'][-1]['result']['physical_execution'] is False
    assert snap['observations'][-1]['provenance'] == 'SYNTHETIC'
    assert backend.executions == 1 and not expert.contexts
