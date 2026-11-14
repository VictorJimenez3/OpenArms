"""Promotion checks proposed routes against every currently active skill."""
import copy
import uuid
from agentic.openarms_lab.contracts import SkillDefinition
from agentic.openarms_lab.skills import SkillRegistry
from agentic.tests.test_task_loop import DEFINITION


def evaluate(registry, definition):
    version = registry.validate_for_task(uuid.uuid4().hex, SkillDefinition.model_validate(definition))
    baseline = registry.data['active'].get(definition['skill_id'])
    receipt = {'evaluation_id': uuid.uuid4().hex, 'suite_hash': 'a'*64,
               'candidate_hash': version, 'baseline_hash': baseline,
               'artifact_hashes': ['b'*64], 'candidate_recovered': 3, 'baseline_recovered': 2 if baseline else 0,
               'regression_gates': dict.fromkeys(('routing', 'outcome', 'unknown', 'consent', 'stop'), True),
               'passed': True, 'reasons': ['Test evaluator result']}
    return version, registry.record_evaluation(definition['skill_id'], version, receipt)


def test_new_skill_cannot_displace_an_existing_warm_route(tmp_path):
    registry = SkillRegistry(tmp_path/'skills.json')
    original, result = evaluate(registry, copy.deepcopy(DEFINITION))
    assert result['status'] == 'promoted'
    rival = copy.deepcopy(DEFINITION)
    rival['skill_id'] = 'another_skill'
    new, result = evaluate(registry, rival)
    assert result['status'] == 'rejected'
    assert registry.match('test prepared vinegar').skill_version == original
    assert registry.get('another_skill', new)['status'] == 'rejected'
    receipt = registry.data['evaluations'][-1]
    assert not receipt['regression_gates']['active_registry_routing']
    assert receipt['metrics']['active_registry_routing']['active_versions'] == {'sample_color': original}
    assert any(not case['passed'] for case in receipt['metrics']['active_registry_routing']['cases'])


def test_revision_checks_other_skills_and_retains_original_routes(tmp_path):
    registry = SkillRegistry(tmp_path/'skills.json')
    first, _ = evaluate(registry, copy.deepcopy(DEFINITION))
    other = copy.deepcopy(DEFINITION)
    other['skill_id'] = 'other_skill'
    other['retrieval_examples'] = ['inspect other {condition}']
    second, result = evaluate(registry, other)
    assert result['status'] == 'promoted'
    changed = copy.deepcopy(DEFINITION)
    changed['retrieval_examples'].append('inspect other {condition}')
    changed['steps'][-1]['arguments'] = {'view': 'secondary'}
    _, result = evaluate(registry, changed)
    assert result['status'] == 'rejected'
    assert registry.match('inspect other water').skill_version == second
    assert registry.match('test prepared vinegar').skill_version == first
    changed['retrieval_examples'] = ['a new route {condition}']
    _, result = evaluate(registry, changed)
    assert result['status'] == 'rejected'
    changed['retrieval_examples'] = list(DEFINITION['retrieval_examples']) + ['a new route {condition}']
    revised, result = evaluate(registry, changed)
    assert result['status'] == 'promoted'
    assert registry.match('test prepared vinegar').skill_version == revised
    assert registry.match('a new route water').skill_version == revised
    assert registry.match('inspect other water').skill_version == second


def test_asr_punctuation_and_politeness_reuse_without_losing_negation(tmp_path):
    from agentic.openarms_lab.skills import _normalize
    registry = SkillRegistry(tmp_path/'skills.json')
    version, _ = evaluate(registry, copy.deepcopy(DEFINITION))
    assert registry.match('Please test. Prepared vinegar!').skill_version == version
    assert registry.match('test prepared water, please.').skill_version == version
    assert registry.match('Please do not test. Prepared vinegar!') is None
    assert _normalize('Use 1.5 mL, please.') == 'use 1.5 ml'
