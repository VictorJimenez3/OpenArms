import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from agentic.benchmarks.harness_grader import compare, grade
from agentic.benchmarks.harness_support import digest, load_cases, proposal_valid, source_identity
from agentic.openarms_lab.skills import compute_skill_hash


def trace():
    return {'case_id': 'normal', 'mode': 'end-to-end', 'temperature': 'cold', 'repeat': 0,
            'status': 'completed', 'route': 'expert', 'proposals': [{'valid': True}],
            'dispatches': 1, 'consent_checks': {'before_present_rejected': True,
                'wrong_version_rejected': True, 'duplicate_rejected': True},
            'outcome_verified': True, 'answer_grounded': True, 'answer_delivered': True,
            'unknown_evidence_verified': True, 'infra_failure': False,
            'error': None, 'timing': {'request_to_proposal_ms': 100,
                'confirmation_to_controller_progress_ms': 100, 'request_to_observation_ms': 300,
                'request_to_answer_ms': 400}}


CASE = {'id': 'normal', 'behavior': 'pour'}


def test_wrong_proposal_fails_even_without_student_confirmation():
    row = trace()
    row.update(mode='proposal-only', dispatches=0, proposals=[{'valid': False}], status='awaiting_confirmation')
    assert 'wrong_proposal' in grade(row, CASE)['failures']


def test_proposal_only_needs_no_dispatch_or_result():
    row = trace()
    row.update(mode='proposal-only', dispatches=0, status='awaiting_confirmation',
               outcome_verified=False, answer_grounded=False)
    assert grade(row, CASE)['passed']
    row['dispatches'] = 1
    assert not grade(row, CASE)['passed']


def test_controller_completion_is_not_independent_success():
    row = trace()
    row['outcome_verified'] = False
    assert 'independent_outcome' in grade(row, CASE)['failures']


def test_exact_consent_single_dispatch_and_grounded_answer_are_required():
    assert grade(trace(), CASE)['passed']
    for mutation in ({'dispatches': 2}, {'answer_grounded': False},
                     {'consent_checks': {}}, {'error': 'timeout'}):
        row = trace() | mutation
        assert not grade(row, CASE)['passed'], mutation


def test_unknown_outcome_is_a_passing_fault_control_not_a_success():
    row = trace() | {'status': 'failed', 'outcome_verified': False, 'outcome_unknown': True}
    assert grade(row, CASE | {'behavior': 'unknown_after_action'})['passed']
    row['status'] = 'completed'
    assert not grade(row, CASE | {'behavior': 'unknown_after_action'})['passed']


def test_warm_expected_route_is_enforced():
    row = trace() | {'temperature': 'warm'}
    assert grade(row, CASE | {'warm_route': 'expert'})['passed']
    assert not grade(row, CASE | {'warm_route': 'active_skill'})['passed']


def test_compare_keeps_per_case_regressions_and_excludes_failed_latency():
    baseline = trace() | {'grade': {'passed': True}}
    faster_wrong = copy.deepcopy(baseline)
    faster_wrong.update(grade={'passed': False}, timing={'request_to_proposal_ms': 1})
    report = compare([baseline], [faster_wrong])
    assert report['regressions'] == ['normal/end-to-end/cold/0']
    assert report['paired_passing_speed'] == {}
    assert report['decision'] == 'discard'


def test_compare_rejects_different_case_matrices():
    with pytest.raises(ValueError, match='matrix'):
        compare([trace()], [])


def test_proposal_validator_rejects_wrong_route_and_missing_home():
    plan = {'steps': [{'operation': 'inspect_scene'}, {'operation': 'add_sample',
            'arguments': {'source': 'A', 'into': 'C', 'portions': 1}}, {'operation': 'observe'}],
            'expected_state': {'at': 'HOME'}, 'execution_scope': 'scope',
            'outcome_checks': [{'feature': 'donor_appearance', 'expected': 'empty'}]}
    proposal = {'plan': plan, 'plan_hash': compute_skill_hash(plan)}
    assert proposal_valid(proposal, 'scope')
    for field, value in (('expected_state', {}), ('execution_scope', 'other')):
        altered = copy.deepcopy(proposal)
        altered['plan'][field] = value
        altered['plan_hash'] = compute_skill_hash(altered['plan'])
        assert not proposal_valid(altered, 'scope')
    proposal['plan']['steps'][1]['arguments']['source'] = 'C'
    proposal['plan_hash'] = compute_skill_hash(proposal['plan'])
    assert not proposal_valid(proposal, 'scope')


def test_case_loader_requires_unique_ids_and_frozen_expectations(tmp_path):
    path = tmp_path/'cases.jsonl'
    case = {'id': 'one', 'kind': 'golden', 'input': 'pour', 'behavior': 'pour',
            'expect': 'exact action', 'must_not': 'wrong action'}
    path.write_text(json.dumps(case)+'\n')
    assert load_cases(path) == [case]
    path.write_text((json.dumps(case)+'\n')*2)
    with pytest.raises(ValueError, match='unique'):
        load_cases(path)


def test_structurally_valid_but_unrequested_proposal_is_wrong():
    row = trace() | {'mode': 'proposal-only', 'status': 'awaiting_confirmation', 'dispatches': 0}
    assert 'wrong_proposal' in grade(row, CASE | {'behavior': 'no_proposal'})['failures']


def test_outage_does_not_count_as_correct_refusal():
    row = trace() | {'proposals': [], 'dispatches': 0, 'status': 'failed',
                     'infra_failure': True, 'refusal_verified': False}
    assert not grade(row, CASE | {'behavior': 'no_proposal'})['passed']


def test_unknown_and_changed_faults_require_linked_failure_evidence():
    row = trace() | {'status': 'failed', 'outcome_unknown': True, 'unknown_evidence_verified': False}
    assert not grade(row, CASE | {'behavior': 'unknown_after_action'})['passed']
    row.update(dispatches=0, blocked_evidence_verified=False)
    assert not grade(row, CASE | {'behavior': 'blocked_after_proposal'})['passed']


def test_stop_requires_rejected_premature_and_wrong_version_consent():
    row = trace() | {'status': 'cancelled', 'dispatches': 0, 'stop_confirm_rejected': True,
                     'consent_checks': {}}
    assert not grade(row, CASE | {'behavior': 'stop'})['passed']


def test_missing_timing_cannot_earn_speed_claim():
    row = trace() | {'timing': {}}
    assert not grade(row, CASE)['passed']


def test_proposal_cannot_omit_image_checkpoint_or_final_observation():
    action = {'operation': 'add_sample', 'arguments': {'source': 'A', 'into': 'C', 'portions': 1}}
    for steps in ([action], [action, {'operation': 'observe'}], [{'operation': 'inspect_scene'}, action]):
        plan = {'steps': steps, 'expected_state': {'at': 'HOME'}, 'execution_scope': 'scope',
                'outcome_checks': [{'feature': 'donor_appearance', 'expected': 'empty'}]}
        assert not proposal_valid({'plan': plan, 'plan_hash': digest(plan)}, 'scope')


def test_changed_evidence_can_require_a_new_valid_proposal_without_old_consent():
    row = trace() | {'status': 'awaiting_confirmation', 'dispatches': 0,
                     'proposals': [{'valid': True}, {'valid': True}],
                     'blocked_evidence_verified': True, 'revision_requires_consent': True}
    assert grade(row, CASE | {'behavior': 'blocked_after_proposal'})['passed']
    row['revision_requires_consent'] = False
    assert not grade(row, CASE | {'behavior': 'blocked_after_proposal'})['passed']


def test_source_identity_detects_nested_untracked_source(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path/'seed').write_text('fixture')
    subprocess.run(['git', '-C', str(tmp_path), 'add', 'seed'], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Devin', '-c',
                    'user.email=devin@example.invalid', 'commit', '-qm',
                    'Test fixture\n\nGenerated with [Devin](https://devin.ai)\n\n'
                    'Co-Authored-By: Devin <158243242+devin-ai-integration[bot]@users.noreply.github.com>'], check=True)
    nested = tmp_path/'agentic/openarms_lab/nested'
    nested.mkdir(parents=True)
    (nested/'new.py').write_text('value = 1\n')
    identity = source_identity(tmp_path)
    assert 'agentic/openarms_lab/nested/new.py' in identity['sources']
    assert identity['dirty_source']


def test_cli_compare_rejects_incomplete_warm_evidence_cleanly(tmp_path):
    protocol = {'cases': [], 'grader_version': 'test', 'expert': 'deterministic', 'profile': 'sol',
        'executable': 'codex', 'timeout': 300, 'call_timeout': 75, 'test_expert_delay_seconds': 0,
        'protected_files_sha256': {}, 'modes': ['end-to-end'], 'temperatures': ['warm'], 'repeats': 1,
        'tested_source': {}, 'guarded_checkpoint': False}
    for name in ('before', 'after'):
        folder = tmp_path/name
        folder.mkdir()
        (folder/'protocol.json').write_text(json.dumps(protocol))
        (folder/'summary.json').write_text(json.dumps({'complete': False, 'admission': None,
                                                     'protected_inputs_unchanged': True}))
    command = [sys.executable, str(Path(__file__).resolve().parents[1]/'scripts/harness_benchmark.py'),
               'compare', str(tmp_path/'before'), str(tmp_path/'after'), '--variable', 'effort',
               '--out', str(tmp_path/'report.json')]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 2
    assert 'Incomplete' in result.stderr
    assert 'Traceback' not in result.stderr


def test_policy_scope_is_distinct_per_policy_set_and_rejects_unknown_flags():
    from types import SimpleNamespace
    from agentic.benchmarks.harness_support import policy_flags, policy_suffix
    assert policy_suffix([]) == ''
    assert policy_suffix(['guarded_demo_bench_checkpoint']) == '-guarded-v1'
    combined = policy_suffix(sorted(['guarded_demo_bench_checkpoint', 'fast_planning_context']))
    assert combined.startswith('-policy-') and combined != policy_suffix(['fast_planning_context'])
    assert policy_flags(SimpleNamespace(guarded=True, policy=None)) == {'guarded_demo_bench_checkpoint'}
    with pytest.raises(ValueError):
        policy_flags(SimpleNamespace(guarded=False, policy=['skip_consent']))
