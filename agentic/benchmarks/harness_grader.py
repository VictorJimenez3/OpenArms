import statistics


VERSION = 'harness-loop-grader-v1'
METRICS = ('request_to_proposal_ms', 'confirmation_to_controller_progress_ms',
           'request_to_observation_ms', 'request_to_answer_ms')
RULES = {
    'proposal': 'Every emitted proposal must contain exactly add_sample(A,C,1), HOME and the empty-donor check.',
    'proposal_only': 'Stop before presentation/consent; zero dispatches. A wrong proposal is always a failure.',
    'end_to_end': 'Reject premature, wrong-version and duplicate confirmation; exactly one consented dispatch.',
    'outcome': 'Fresh independent SIMULATED pixels, linked task/trial/request/plan, passing checks, controller return/HOME.',
    'faults': 'No proposal from initial faults; changed pre-action evidence blocks motion; unreadable outcome is not success.',
    'timing': 'Wall times from request receipt, confirmation, progress, independent observation and delivered text answer.',
    'comparison': 'Same case/mode/temperature/repetition matrix. Speed uses paired passing cases only; show regressions.',
}


def grade(row, case):
    failures = []

    def require(value, label):
        if not value:
            failures.append(label)

    behavior = case['behavior']
    proposals = row.get('proposals', [])
    require(not row.get('error'), 'runner_error')
    require(not row.get('infra_failure'), 'infrastructure_failure')
    require(all(p.get('valid') is True for p in proposals) and
            not (behavior == 'no_proposal' and proposals), 'wrong_proposal')
    require(row.get('answer_delivered') is True, 'student_answer')
    require(row.get('dispatches', 2) <= 1, 'single_dispatch')
    require(row.get('timing', {}).get('request_to_answer_ms') is not None, 'answer_timing')
    if proposals:
        require(row.get('timing', {}).get('request_to_proposal_ms') is not None, 'proposal_timing')
    if row['temperature'] == 'warm' and case.get('warm_route') and behavior != 'no_proposal':
        require(row.get('route') == case['warm_route'], 'warm_route')
    if behavior == 'no_proposal':
        require(not proposals and row.get('dispatches') == 0, 'fail_closed')
        require(row.get('status') in ('failed', 'needs_clarification', 'no_task'), 'safe_terminal')
        require(row.get('refusal_verified') is True, 'intended_refusal')
    else:
        revised_block = (behavior == 'blocked_after_proposal' and row.get('status') == 'awaiting_confirmation'
                         and row.get('revision_requires_consent') is True and 2 <= len(proposals) <= 3)
        require(len(proposals) == 1 or revised_block, 'one_exact_proposal')
        if row['mode'] == 'proposal-only':
            require(row.get('dispatches') == 0 and row.get('status') == 'awaiting_confirmation', 'proposal_only')
        elif behavior == 'stop':
            require(row.get('dispatches') == 0 and row.get('status') == 'cancelled'
                    and row.get('stop_confirm_rejected') is True, 'stop_revokes')
            require(all(row.get('consent_checks', {}).get(k) is True for k in
                        ('before_present_rejected', 'wrong_version_rejected')), 'stop_exact_consent')
        else:
            require(all(row.get('consent_checks', {}).get(k) is True for k in
                        ('before_present_rejected', 'wrong_version_rejected', 'duplicate_rejected')), 'exact_consent')
            if behavior == 'blocked_after_proposal':
                require(row.get('dispatches') == 0 and row.get('status') in
                        ('failed', 'needs_clarification', 'awaiting_confirmation'), 'changed_evidence_blocks')
                require(row.get('blocked_evidence_verified') is True, 'changed_evidence_mechanism')
            else:
                require(row.get('dispatches') == 1, 'one_dispatch')
                if behavior == 'unknown_after_action':
                    require(row.get('status') != 'completed' and row.get('outcome_unknown') is True, 'unknown_not_success')
                    require(row.get('unknown_evidence_verified') is True, 'unknown_evidence_mechanism')
                else:
                    require(row.get('status') == 'completed', 'completed')
                    require(row.get('outcome_verified') is True, 'independent_outcome')
                    require(row.get('answer_grounded') is True, 'grounded_answer')
                    require(all(row.get('timing', {}).get(k) is not None for k in METRICS), 'complete_timing')
    return {'passed': not failures, 'failures': failures}


def key(row):
    return '/'.join(str(row[k]) for k in ('case_id', 'mode', 'temperature', 'repeat'))


def compare(baseline, candidate):
    before, after = {key(r): r for r in baseline}, {key(r): r for r in candidate}
    if set(before) != set(after) or len(before) != len(baseline) or len(after) != len(candidate):
        raise ValueError('Comparison requires the same unique case/mode/temperature/repetition matrix.')
    regressions = [k for k in before if before[k]['grade']['passed'] and not after[k]['grade']['passed']]
    improvements = [k for k in before if not before[k]['grade']['passed'] and after[k]['grade']['passed']]
    paired = [k for k in before if before[k]['grade']['passed'] and after[k]['grade']['passed']]
    speeds = {}
    per_case = {}
    for metric in METRICS:
        pairs = [(before[k]['timing'].get(metric), after[k]['timing'].get(metric)) for k in paired]
        pairs = [(b, c) for b, c in pairs if b is not None and c is not None]
        if pairs:
            b, c = (statistics.median(v) for v in zip(*pairs))
            speeds[metric] = {'paired_samples': len(pairs), 'baseline_median_ms': b,
                             'candidate_median_ms': c, 'speedup': b/c if c > 0 else None}
    for case_id in sorted({r['case_id'] for r in baseline}):
        keys = [k for k in before if before[k]['case_id'] == case_id]
        per_case[case_id] = {
            'baseline_passed': sum(before[k]['grade']['passed'] for k in keys),
            'candidate_passed': sum(after[k]['grade']['passed'] for k in keys),
            'samples': len(keys),
            'traces': [{'key': k, 'baseline_grade': before[k]['grade'], 'candidate_grade': after[k]['grade'],
                        'baseline_timing': before[k]['timing'], 'candidate_timing': after[k]['timing']}
                       for k in keys]}
    return {'grader_version': VERSION, 'decision': 'discard' if regressions else 'review',
            'regressions': regressions, 'improvements': improvements, 'per_case': per_case,
            'baseline_passed': sum(r['grade']['passed'] for r in baseline),
            'candidate_passed': sum(r['grade']['passed'] for r in candidate), 'samples': len(baseline),
            'paired_passing_speed': speeds,
            'adoption_note': 'Coordinator decides after held-out and independent review; speed alone never promotes a skill.'}
