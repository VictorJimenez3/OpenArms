import copy
import pytest

from openarms_lab.contracts import SkillDefinition
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
