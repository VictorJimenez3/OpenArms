"""Two-vessel admission uses actual candidate replays and cannot survive STOP."""
import asyncio
import copy
import json

import pytest

from agentic.openarms_lab.contracts import SkillDefinition
from agentic.openarms_lab.evaluation import _PinnedPlanner
from agentic.openarms_lab.runtime import Lab
from agentic.openarms_lab.skills import SkillRegistry, compute_skill_hash
from agentic.openarms_lab.two_vessel_backend import TwoVesselBackend
from agentic.openarms_lab.two_vessel_configuration import CONDITIONS, EXPERIMENT
from agentic.openarms_lab.two_vessel_evaluation import SUITE, TwoVesselSkillEvaluator
from agentic.openarms_lab.two_vessel_scene import TwoVesselSceneService
from agentic.tests.test_two_vessel_runtime import DEFINITION


def record(definition=None):
    definition = SkillDefinition.model_validate(definition or DEFINITION)
    return {**definition.model_dump(mode='json'), 'version': compute_skill_hash(definition), 'status': 'task_validated'}


@pytest.mark.asyncio
async def test_real_candidate_admitted_and_all_frozen_cases_retained(tmp_path):
    evaluator = TwoVesselSkillEvaluator(tmp_path/'evidence')
    candidate = record()
    frozen_candidate = copy.deepcopy(candidate)
    result = await evaluator.evaluate_candidate('requesting-session', candidate, None)
    assert candidate == frozen_candidate
    assert result['passed'], result['reasons']
    assert all(result['regression_gates'].values())
    assert result['baseline_recovered'] == 0 and result['candidate_recovered'] == 1
    assert result['metrics']['initial_admission'] and not result['metrics']['substantive_improvement']
    cases = result['metrics']['cases']['candidate']
    assert [r['case'] for r in cases] == SUITE['positive']+SUITE['negative']
    assert cases[0]['observed']['features']['receiver_appearance'] == 'water_appearance'
    assert all(r['executions']==0 and not r['recovered'] for r in cases[1:])
    assert all(row['control_passed'] for row in result['metrics']['controls'].values())
    frozen = json.loads((tmp_path/'evidence'/result['evaluation_id']/'frozen-inputs.json').read_text())
    assert frozen['candidate'] == candidate and frozen['unchanged_baseline'] is None
    registry = SkillRegistry(tmp_path/'registry.json')
    version = registry.validate_for_task('task', SkillDefinition.model_validate(DEFINITION))
    decision = registry.record_evaluation(candidate['skill_id'], version, result)
    assert decision['status'] == 'promoted'
    assert registry.match('pour water from A to C').skill_version == version


@pytest.mark.asyncio
async def test_actual_wrong_outcome_fails_and_unsupported_condition_never_runs(tmp_path):
    evaluator = TwoVesselSkillEvaluator(tmp_path)
    wrong = copy.deepcopy(DEFINITION)
    wrong['outcome_checks'].append({'feature':'sample_cup_held', 'expected':True})
    result = await evaluator.evaluate_candidate('s',record(wrong),None)
    assert not result['passed'] and not result['regression_gates']['outcome']
    nominal = result['metrics']['cases']['candidate'][0]
    assert nominal['executions'] == 1 and not nominal['recovered']
    unsupported = copy.deepcopy(DEFINITION)
    unsupported['parameter_schema']['condition']['enum'] = ['water','vinegar']
    result = await evaluator.evaluate_candidate('s',record(unsupported),None)
    assert not result['passed'] and result['metrics']['cases'] == {}
    assert any('Only one complete water' in reason for reason in result['reasons'])


@pytest.mark.asyncio
async def test_equivalent_revision_rejected_by_measured_gain_gate(tmp_path, monkeypatch):
    evaluator = TwoVesselSkillEvaluator(tmp_path)
    # This test isolates promotion arithmetic; the real renderer cases run above.
    async def cases(folder, definition, bindings, case):
        return {'case':case,'bindings':bindings,'recovered':case=='nominal',
                'executions':1 if case=='nominal' else 0, 'observed':None,
                'control_passed':case in SUITE['controls']}
    monkeypatch.setattr(evaluator,'_case',cases)
    baseline = record()
    changed = copy.deepcopy(DEFINITION); changed['name'] = 'Renamed water pour'
    result = await evaluator.evaluate_candidate('s',record(changed),baseline)
    assert not result['passed'] and result['baseline_recovered'] == result['candidate_recovered'] == 1
    assert result['baseline_hash'] == baseline['version']
    assert any('No measured' in reason for reason in result['reasons'])


@pytest.mark.asyncio
async def test_stop_revokes_live_evaluation_without_promotion(tmp_path):
    completed_replay = asyncio.Event()
    class PausedEvaluator(TwoVesselSkillEvaluator):
        async def _case(self,*args,**kwargs):
            result = await super()._case(*args,**kwargs)
            completed_replay.set()
            await asyncio.Event().wait()
            return result
    evaluator = PausedEvaluator(tmp_path/'evaluation')
    scene = TwoVesselSceneService(tmp_path/'scene')
    lab = Lab(tmp_path/'lab',expert=_PinnedPlanner(DEFINITION,{'condition':'water'}),perception=scene,
              backend_factory=lambda:TwoVesselBackend(scene), evaluator=evaluator,
              experiment=EXPERIMENT,conditions=CONDITIONS,expert_timeout=120)
    evaluation = None
    try:
        sid = (await lab.create())['session_id']
        handle = await lab.start_task(sid,'Pour water from A into C.')
        await asyncio.wait_for(asyncio.shield(lab.workers[handle['task_id']]),30)
        pending = lab.snapshot(sid)['pending']
        exact = (sid,pending['request_id'],pending['proposal_version'])
        await lab.present(*exact);await lab.confirm(*exact)
        await asyncio.wait_for(asyncio.shield(lab.workers[handle['task_id']]),60)
        task = lab.snapshot(sid)['tasks'][-1]
        assert task['status']=='completed'
        plan=task['plan']
        evaluation=asyncio.create_task(lab.evaluate_candidate(sid,plan['skill_id'],plan['skill_version']))
        await asyncio.wait_for(completed_replay.wait(),60)
        await lab.stop(sid)
        with pytest.raises(asyncio.CancelledError):
            await evaluation
        assert not lab.registry.data['active'] and not lab.registry.data['evaluations']
        assert not list((tmp_path/'evaluation').glob('*/receipt.json'))
    finally:
        if evaluation and not evaluation.done():
            evaluation.cancel()
            await asyncio.gather(evaluation,return_exceptions=True)
        await lab.shutdown()
