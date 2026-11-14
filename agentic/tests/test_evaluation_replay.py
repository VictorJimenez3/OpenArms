import copy
import json
import pytest

from openarms_lab.contracts import SkillDefinition
from openarms_lab import evaluation
from openarms_lab.evaluation import SyntheticSkillEvaluator
from openarms_lab.skills import compute_skill_hash


def definition(fallback=False):
    value = SkillDefinition.model_validate({
        'skill_id': 'prepared_color', 'name': 'Prepared sample color',
        'intent': 'Observe the simulated prepared sample color.',
        'retrieval_examples': ['test prepared {sample}', 'check prepared {sample}'],
        'parameter_schema': {'sample': {'type': 'string', 'enum': ['vinegar', 'water']}},
        'preconditions': {'fresh_scene': True},
        'steps': [{'operation': 'inspect_scene'},
                  {'operation': 'mock_prepared_sample', 'arguments': {'condition_id': '$sample'}},
                  {'operation': 'observe', 'arguments': {'view': 'primary', **({'fallback_view': 'secondary'} if fallback else {})}}],
        'outcome_checks': [{'feature': 'readable', 'expected': True}],
        'limitations': ['Synthetic fixture; no physical success or measured pH.'],
    })
    return {**value.model_dump(mode='json'), 'version': compute_skill_hash(value), 'status': 'task_validated'}


@pytest.mark.asyncio
async def test_frozen_replay_detects_real_gain_and_rejects_label_only_revision(tmp_path):
    evaluator = SyntheticSkillEvaluator(tmp_path)
    baseline = definition()
    admitted = await evaluator.evaluate_candidate('test-session', baseline, None)
    assert admitted['passed'], admitted
    assert admitted['candidate_recovered'] == 6
    assert admitted['regression_gates'] == dict.fromkeys(['routing', 'outcome', 'unknown', 'consent', 'stop'], True)
    baseline['status'] = 'active'
    original = copy.deepcopy(baseline)
    revision = definition(True)
    improved = await evaluator.evaluate_candidate('test-session', revision, baseline)
    assert improved['passed'], improved
    assert (improved['baseline_recovered'], improved['candidate_recovered']) == (6, 8)
    assert baseline == original
    label_only = definition()
    label_only['name'] = 'New improved label'
    label_only['version'] = compute_skill_hash(SkillDefinition.model_validate({
        key: value for key, value in label_only.items() if key not in ('version', 'status')}))
    rejected = await evaluator.evaluate_candidate('test-session', label_only, baseline)
    assert not rejected['passed']
    assert rejected['baseline_recovered'] == rejected['candidate_recovered']


@pytest.mark.asyncio
async def test_improvement_cannot_raise_score_by_dropping_a_condition(tmp_path):
    baseline, candidate = definition(), definition(True)
    candidate['parameter_schema']['sample']['enum'] = ['vinegar']
    evaluator = SyntheticSkillEvaluator(tmp_path)
    with pytest.raises(ValueError, match='baseline parameter domain'):
        await evaluator.evaluate_candidate('test-session', candidate, baseline)


@pytest.mark.asyncio
async def test_improvement_must_preserve_existing_conversational_invocations(tmp_path):
    baseline, candidate = definition(), definition(True)
    candidate['retrieval_examples'] = ['a different request {sample}']
    evaluator = SyntheticSkillEvaluator(tmp_path)
    receipt = await evaluator.evaluate_candidate('test-session', candidate, baseline)
    assert not receipt['passed'] and not receipt['regression_gates']['routing']


@pytest.mark.asyncio
async def test_readable_outcome_during_controller_failure_does_not_count_as_recovered(tmp_path, monkeypatch):
    class FailedController(evaluation.SceneBackend):
        async def execute_step(self, *args, **kwargs):
            receipt = await super().execute_step(*args, **kwargs)
            return {**receipt, 'status': 'failed', 'controller_completed': False,
                    'reason': 'Return to HOME failed.'}

    monkeypatch.setattr(evaluation, 'SceneBackend', FailedController)
    receipt = await SyntheticSkillEvaluator(tmp_path).evaluate_candidate('test-session', definition(), None)
    comparison = json.loads((tmp_path / receipt['metrics']['artifact']).read_text())
    clear = next(case for case in comparison['cases']['candidate'] if case['case'] == 'clear')
    assert clear['observed']['status'] == 'observed'
    assert clear['executions'] == 1
    assert not clear['recovered']
    assert receipt['candidate_recovered'] == 0
    assert not receipt['regression_gates']['outcome']
    assert not receipt['passed']
