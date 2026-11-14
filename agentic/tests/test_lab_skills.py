"""Independent validation and durable lifecycle of the single task registry."""
import copy

import pytest

from agentic.openarms_lab.contracts import PlanDraft, SkillDefinition
from agentic.openarms_lab.skills import SkillRegistry
from agentic.tests.test_task_loop import DEFINITION, HASH, TestEvaluator as FakeEvaluator, draft


def test_empty_registry_and_candidate_scope(tmp_path):
    path = tmp_path / 'task-skills.json'
    registry = SkillRegistry(path)
    assert registry.list() == []
    plan = PlanDraft.model_validate(draft())
    compiled = registry.compile(plan, task_id='first')
    assert compiled['steps'][1]['arguments']['condition_id'] == 'vinegar'
    version = registry.validate_for_task('first', plan.skill_definition)
    assert version == compiled['skill_version']
    with pytest.raises(ValueError):
        registry.authorize('second', 'sample_color', version)
    registry.authorize('first', 'sample_color', version, consume=True)
    restored = SkillRegistry(path)
    with pytest.raises(ValueError):
        restored.authorize('first', 'sample_color', version)
    assert restored.match('Run prepared water') is None


@pytest.mark.parametrize('bad_binding', ['bleach', 1, True, ['water']])
def test_binding_type_enum_and_extent(tmp_path, bad_binding):
    registry = SkillRegistry(tmp_path / 'skills.json')
    data = draft()
    data['bindings']['condition'] = bad_binding
    with pytest.raises(ValueError):
        registry.compile(PlanDraft.model_validate(data))


def test_unsupported_route_and_no_observation_fail_closed(tmp_path):
    registry = SkillRegistry(tmp_path / 'skills.json')
    data = draft()
    data['skill_definition']['steps'][1]['arguments']['source'] = 'B'
    with pytest.raises(ValueError):
        registry.compile(PlanDraft.model_validate(data))
    data = draft()
    data['skill_definition']['steps'].pop()
    with pytest.raises(ValueError, match='independent observation'):
        registry.compile(PlanDraft.model_validate(data))


@pytest.mark.asyncio
async def test_evaluation_reject_preserves_exact_baseline(tmp_path):
    path = tmp_path / 'task-skills.json'
    registry = SkillRegistry(path)
    base = SkillDefinition.model_validate(DEFINITION)
    old = registry.validate_for_task('first', base)
    first = await FakeEvaluator().evaluate_candidate('session', registry.get('sample_color', old), None)
    assert registry.record_evaluation('sample_color', old, first)['status'] == 'promoted'
    revised = copy.deepcopy(DEFINITION)
    revised['steps'][-1]['arguments'] = {'view': 'secondary'}
    new = registry.validate_for_task('second', SkillDefinition.model_validate(revised))
    candidate = registry.get('sample_color', new)
    baseline = registry.get('sample_color')
    bad = await FakeEvaluator(passed=False).evaluate_candidate('session', candidate, baseline)
    bad['evaluation_id'] = 'rejected-revision'
    with pytest.raises(ValueError, match='exact candidate'):
        registry.record_evaluation('sample_color', new, {**bad, 'baseline_hash': HASH})
    result = registry.record_evaluation('sample_color', new, bad)
    assert result['status'] == 'rejected'
    assert result['rollback_target'] == old
    restored = SkillRegistry(path)
    assert restored.get('sample_color') == baseline
    assert restored.get('sample_color', new)['status'] == 'rejected'
    assert restored.match('run prepared water').skill_version == old
    assert restored.match('do not run prepared water') is None
    assert restored.evaluation_decisions(new) == [result]


def test_persisted_definition_hash_mismatch_fails_closed(tmp_path):
    path = tmp_path / 'task-skills.json'
    registry = SkillRegistry(path)
    registry.validate_for_task('first', SkillDefinition.model_validate(DEFINITION))
    path.write_text(path.read_text().replace('Prepared sample inspection', 'Modified title'))
    with pytest.raises(ValueError, match='hash mismatch'):
        SkillRegistry(path)
