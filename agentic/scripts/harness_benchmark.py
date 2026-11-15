import argparse
import asyncio
import copy
import fcntl
import importlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'agentic/benchmarks'))
from harness_grader import RULES, VERSION, compare, grade
from harness_support import (DEFINITION, policy_flags, digest, file_hash, load_cases, make_lab,
    measurements, observed_result, proposal_valid, save, settled, source_identity)

BASELINE = '47a00c1dcf95c8d0077a5007ff825b4c5de7737e'


async def rejected(lab, exact):
    LabError = importlib.import_module('openarms_lab.runtime').LabError
    try:
        await lab.confirm(*exact)
    except LabError:
        return True
    return False


async def admission(args, folder):
    if args.admission:
        source = args.admission.resolve()
        metadata = json.loads((source/'metadata.json').read_text())
        lab, scene, scope = make_lab(folder/'validation', args, deterministic=True)
        try:
            SkillDefinition = importlib.import_module('openarms_lab.contracts').SkillDefinition
            expected = digest(SkillDefinition.model_validate(DEFINITION).model_dump(mode='json'))
            registry = json.loads((source/'registry.json').read_text())
            decision = json.loads((source/'decision.json').read_text())
            if (metadata['scope'] != scope or file_hash(source/'registry.json') != metadata['registry_sha256']
                    or decision['status'] != 'promoted' or decision['candidate_hash'] != expected
                    or metadata['skill_version'] != expected
                    or registry['active'] != {DEFINITION['skill_id']: expected}
                    or registry['versions'][expected]['status'] != 'active'
                    or digest(registry['versions'][expected]['definition']) != expected):
                raise ValueError('Admission does not match the current execution policy/source scope.')
        finally:
            await lab.shutdown()
        return source/'registry.json', metadata
    lab, scene, scope = make_lab(folder, args, deterministic=True)
    try:
        sid = (await lab.create())['session_id']
    except Exception:
        await lab.shutdown()
        raise
    try:
        await lab.converse(sid, DEFINITION['retrieval_examples'][0].replace('{source}', 'A').replace('{into}', 'C'),
                           'admission-seed')
        state = await settled(lab, sid, args.timeout)
        pending = state['pending']
        if not pending or not proposal_valid(pending, scope):
            raise ValueError('Admission seed did not produce the exact supported proposal.')
        exact = (sid, pending['request_id'], pending['proposal_version'])
        await lab.present(*exact)
        await lab.confirm(*exact)
        state = await settled(lab, sid, args.timeout)
        if not observed_result(state):
            raise ValueError('Admission seed did not independently succeed.')
        plan = state['tasks'][-1]['plan']
        decision = await lab.evaluate_candidate(sid, plan['skill_id'], plan['skill_version'])
        save(folder/'decision.json', decision)
        if decision['status'] != 'promoted':
            raise ValueError('Existing setup-scoped evaluator refused benchmark seed admission.')
        shutil.copyfile(folder/'sessions/task-skills.json', folder/'registry.json')
        metadata = {'scope': scope, 'skill_version': plan['skill_version'],
                    'registry_sha256': file_hash(folder/'registry.json'),
                    'seed_provenance': 'DETERMINISTIC_TEST_EXPERT_WITH_REAL_SIMULATOR_AND_EXISTING_EVALUATOR',
                    'admission_is_not_harness_improvement': True}
        save(folder/'metadata.json', metadata)
        return folder/'registry.json', metadata
    finally:
        save(folder/'state.json', lab.snapshot(sid))
        await lab.shutdown()


async def run_case(args, case, mode, temperature, repeat, seed, metadata, folder):
    try:
        return await _run_case(args, case, mode, temperature, repeat, seed, metadata, folder)
    except Exception as exc:
        row = {'case_id': case['id'], 'mode': mode, 'temperature': temperature, 'repeat': repeat,
               'error': f'{type(exc).__name__}: {exc}', 'status': 'setup_error', 'dispatches': 0,
               'proposals': [], 'timing': {}, 'grade': {'passed': False, 'failures': ['setup_error']}}
        save(folder/'result.json', row)
        print(json.dumps(row), flush=True)
        return row


async def _run_case(args, case, mode, temperature, repeat, seed, metadata, folder):
    folder.mkdir(parents=True, exist_ok=False)
    if temperature == 'warm':
        (folder/'sessions').mkdir()
        shutil.copyfile(seed, folder/'sessions/task-skills.json')
    lab, scene, scope = make_lab(folder, args)
    try:
        sid = (await lab.create())['session_id']
    except Exception:
        await lab.shutdown()
        raise
    row = {'case_id': case['id'], 'input': case['input'], 'mode': mode, 'temperature': temperature,
           'repeat': repeat, 'execution_scope': scope, 'proposals': [], 'consent_checks': {},
           'dispatches': 0, 'outcome_verified': False, 'answer_grounded': False, 'answer_delivered': False,
           'error': None, 'timing': {}, 'trace': str(folder/'state.json'),
           'expert_configuration': lab.expert.describe(), 'evidence_provenance': 'SIMULATED',
           'model_source': 'LIVE_MODEL' if args.expert == 'live' else 'DETERMINISTIC_TEST_EXPERT'}
    started = time.perf_counter()
    try:
        row['registry_before_sha256'] = digest(lab.registry.data)
        row['admitted_skill_version'] = metadata['skill_version'] if temperature == 'warm' else None
        row['registry_match_before'] = lab.registry.match(case['input']) is not None
        row['phase_coverage'] = 'proposal_prefix_only' if mode == 'proposal-only' else 'full_case'
        fault = case.get('fault')
        if fault == 'stale_before':
            scene.fault = fault
        elif fault == 'missing_before':
            scene.variant = 'missing'
        elif fault in ('occluded_after', 'stale_after'):
            scene.after_fault = fault
        started = time.perf_counter()
        await lab.converse(sid, case['input'], f'{case["id"]}-{mode}-{temperature}-{repeat}')
        row['acknowledgment_ms'] = (time.perf_counter()-started)*1000
        state = lab.snapshot(sid)
        if state['tasks']:
            state = await settled(lab, sid, args.timeout)
        save(folder/'before-consent.json', state)
        pending = state['pending']
        if pending and mode == 'end-to-end' and proposal_valid(pending, scope) and case['behavior'] != 'no_proposal':
            exact = (sid, pending['request_id'], pending['proposal_version'])
            row['consent_checks']['before_present_rejected'] = await rejected(lab, exact)
            await lab.present(*exact)
            row['consent_checks']['wrong_version_rejected'] = await rejected(
                lab, (sid, pending['request_id'], pending['proposal_version']+1))
            if case['behavior'] == 'stop':
                await lab.stop(sid)
                row['stop_confirm_rejected'] = await rejected(lab, exact)
            else:
                if fault in ('camera_shift_after_proposal', 'missing_after_proposal'):
                    scene.variant = 'camera_shift' if fault.startswith('camera') else 'missing'
                await lab.confirm(*exact)
                row['consent_checks']['duplicate_rejected'] = await rejected(lab, exact)
                await settled(lab, sid, args.timeout)
        state = lab.snapshot(sid)
        task = state['tasks'][-1] if state['tasks'] else None
        if task:
            row.update(status=task['status'], route=task['route'], summary=task.get('summary'),
                       replans=task['replans'], expert_runs=task['expert_runs'])
            row['proposals'] = [{'request_id': r['request_id'], 'plan_hash': r['plan_hash'],
                                 'valid': proposal_valid(r, scope), 'plan': r['plan']}
                                for r in state['requests']]
            row['outcome_verified'] = observed_result(state)
            row['outcome_unknown'] = bool(task['observations'] and task['observations'][-1]['status'] == 'unknown')
            if task['status'] == 'completed' and task['observations']:
                answer = await lab.converse(sid, 'What happened?', 'result-answer')
                row['answer_grounded'] = answer['messages'][-1]['text'] == task['observations'][-1]['text']
                row['answer'] = answer['messages'][-1]['text']
            else:
                row['answer'] = (pending['summary'] if pending and mode == 'proposal-only' else
                                 task.get('summary') or task.get('reason'))
            row['answer_delivered'] = bool(row.get('answer'))
            answered = time.perf_counter()
            row['timing'] = measurements(lab, task['task_id'], started, answered,
                                         pending['request_id'] if pending else None)
            simulation = lab.backends[sid].state().get('simulation') or {}
            row['simulated_motion_seconds'] = simulation.get('motion_seconds')
            row['controller_elapsed_ms'] = next((r.get('elapsed_ms') for r in task['execution']
                                                 if r.get('controller_completed')), None)
            row['model_calls'] = sum(r.get('calls') or 0 for r in task['expert_runs'])
            row['test_expert_invocations'] = len(task['expert_runs']) if args.expert == 'deterministic' else 0
            row['usage'] = {}
            for run in task['expert_runs']:
                for name, value in (run.get('usage') or {}).items():
                    if type(value) in (int, float):
                        row['usage'][name] = row['usage'].get(name, 0)+value
            row['cost_usd'] = None
            row['cost_note'] = 'CLI account usage; no reliable dollar cost reported.'
            row['guarded_checkpoints'] = sum(f['type'] == 'deterministic_checkpoint' for f in task['feedback'])
            codes = [e['data'].get('code') for e in state['notebook']
                     if e['kind'] == 'task_status' and e['data'].get('task_id') == task['task_id']]
            row['failure_codes'] = [code for code in codes if code]
            row['infra_failure'] = any(code not in ('invalid_task',) for code in row['failure_codes'])
            invalid_frames = [f for f in scene.fault_frames if
                f['scene'].get('fixture_registration_valid') is False or not f['scene'].get('fresh')
                or f.get('pixel_ready') is False]
            row['refusal_verified'] = (task['status'] in ('failed', 'needs_clarification') and
                not row['infra_failure'] and (not fault or bool(invalid_frames)))
            confirmed = next((r for r in state['requests'] if r.get('student_confirmed')), None)
            row['blocked_evidence_verified'] = bool(confirmed and any(
                f['delivered_at'] > confirmed['confirmed_at'] for f in invalid_frames)
                and any(f['type'] in ('checkpoint_failed', 'precondition_failed') for f in task['feedback']))
            observation = task['observations'][-1] if task['observations'] else None
            controller = next((r for r in task['execution'] if r.get('controller_completed')), None)
            row['unknown_evidence_verified'] = bool(observation and controller and confirmed
                and observation['status'] == 'unknown'
                and all(observation[k] == controller[k] for k in ('request_id', 'task_id', 'trial_id', 'plan_hash'))
                and observation['request_id'] == confirmed['request_id']
                and any(f['delivered_at'] > controller['execution_finished_at'] and
                        (f['variant'] == 'occluded' or f['fault'] == 'stale_after') for f in scene.fault_frames)
                and 'unknown' in (task.get('summary') or '').lower())
        else:
            row.update(status='no_task', route=None, expert_runs=[], model_calls=0)
            row['answer'] = state['messages'][-1]['text']
            row['answer_delivered'] = bool(row['answer'])
            row['timing'] = {'request_to_answer_ms': (time.perf_counter()-started)*1000}
        row['dispatches'] = lab.backends[sid].executions
        row['revision_requires_consent'] = bool(state.get('pending') and
            not state['pending']['student_confirmed'] and not state['pending']['presented'])
        row['grade'] = grade(row, case)
    except Exception as exc:
        row.update(error=f'{type(exc).__name__}: {exc}', status='runner_error')
        row['grade'] = grade(row, case)
    finally:
        save(folder/'state.json', lab.snapshot(sid))
        save(folder/'clock-events.json', lab.clock_events)
        save(folder/'fault-frames.json', scene.fault_frames)
        row['dispatches'] = lab.backends[sid].executions
        row['grade'] = grade(row, case)
        save(folder/'result.json', row)
        await lab.shutdown()
    print(json.dumps({k: row.get(k) for k in ('case_id', 'mode', 'temperature', 'repeat', 'status',
          'route', 'dispatches', 'model_calls', 'grade', 'timing')}), flush=True)
    return row


async def run(args):
    sys.path[:0] = [str(args.target/'agentic'), str(args.target)]
    identity = source_identity(args.target)
    if args.revision and identity['revision'] != args.revision:
        raise ValueError('Target HEAD is not the pinned --revision.')
    if identity['dirty_source'] and not args.allow_dirty_source:
        raise ValueError('Pinned source is dirty; commit the candidate or explicitly --allow-dirty-source with hash pinning.')
    cases = load_cases(args.cases)
    if args.select:
        selected = set(args.select.split(','))
        if not selected.issubset({c['id'] for c in cases}):
            raise ValueError('Unknown selected case.')
        cases = [c for c in cases if c['id'] in selected]
    modes, temperatures = args.modes.split(','), args.temperatures.split(',')
    if set(modes)-{'proposal-only', 'end-to-end'} or set(temperatures)-{'cold', 'warm'}:
        raise ValueError('Unknown mode or temperature.')
    matrix = [(r, c, m, t) for r in range(args.repeats) for c in cases for m in modes for t in temperatures
              if c['behavior'] != 'stop' or m == 'end-to-end']
    count = len(matrix)
    args.policy = sorted(policy_flags(args))
    args.expert_executable = args.executable
    if args.expert == 'live' and count > args.max_live_tasks:
        raise ValueError('Live batch exceeds explicit --max-live-tasks budget.')
    args.out.mkdir(parents=True, exist_ok=False)
    if args.service_tier != 'standard':
        if args.expert != 'live':
            raise ValueError('Service tier applies only to live Codex experts.')
        wrapper = args.out/'codex-service-tier'
        wrapper.write_text('#!/bin/sh\nexec ' + json.dumps(args.executable) +
                           ' -c \'service_tier="' + args.service_tier + '"\' "$@"\n')
        wrapper.chmod(0o755)
        args.expert_executable = str(wrapper)
    protected = [ROOT/'agentic/benchmarks/harness_grader.py', ROOT/'agentic/benchmarks/harness_support.py',
                 Path(__file__), args.cases]
    hashes = {str(p): file_hash(p) for p in protected}
    protocol = {'version': 'openarms-harness-loop-v1', 'baseline_revision': BASELINE,
                'tested_source': identity, 'target': str(args.target), 'cases': cases,
                'case_file_sha256': file_hash(args.cases), 'protected_files_sha256': hashes,
                'grader_version': VERSION, 'scoring_rules': RULES,
                'expert': args.expert, 'profile': args.expert_profile, 'effort': args.reasoning_effort,
                'executable': args.executable, 'timeout': args.timeout, 'call_timeout': args.call_timeout,
                'guarded_checkpoint': 'guarded_demo_bench_checkpoint' in args.policy, 'policies': args.policy,
                'service_tier': args.service_tier,
                'service_tier_note': 'Requested Codex tier; CLI warns and omits unsupported tiers; served tier is not reported.',
                'test_expert_delay_seconds': args.test_expert_delay,
                'modes': modes, 'temperatures': temperatures, 'repeats': args.repeats, 'planned_samples': count,
                'approval': 'SCRIPTED_TEST_STUDENT', 'physical_hardware_used': False,
                'learning_sequence': ['freeze', 'baseline', 'diagnose_trace', 'one_change', 'same_cases',
                                      'heldout', 'independent_review', 'coordinator_keep_or_discard'],
                'command': sys.argv, 'started_at': time.time()}
    save(args.out/'protocol.json', protocol)
    save(args.out/'scoring-rules.json', RULES)
    rows, metadata, batch_error = [], None, None
    try:
        seed, metadata = await admission(args, args.out/'admission') if 'warm' in temperatures else (None, {'skill_version': None})
        for repeat, case, mode, temperature in matrix:
            folder = args.out/f'{case["id"]}-{mode}-{temperature}-{repeat}'
            row = await run_case(args, case, mode, temperature, repeat, seed, metadata, folder)
            rows.append(row)
            save(args.out/'results.json', rows)
            if args.expert == 'live' and any(code in ('authentication', 'quota', 'unavailable', 'unsupported_model')
                                            for code in row.get('failure_codes', [])):
                batch_error = 'Live expert dependency failed; stopped without fallback.'
                break
    except Exception as exc:
        batch_error = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        unchanged = source_identity(args.target) == identity and all(file_hash(p) == h for p, h in hashes.items())
        save(args.out/'summary.json', {'samples': len(rows), 'planned_samples': count,
             'passed': sum(r['grade']['passed'] for r in rows), 'complete': len(rows) == count,
             'batch_error': batch_error,
             'protected_inputs_unchanged': unchanged, 'admission': metadata, 'finished_at': time.time(),
             'model_calls': sum(r.get('model_calls', 0) for r in rows),
             'false_proposals': sum('wrong_proposal' in r['grade']['failures'] for r in rows)})
        manifest = {str(p.relative_to(args.out)): file_hash(p) for p in sorted(args.out.rglob('*')) if p.is_file()}
        save(args.out/'artifact-manifest.json', manifest)
        if not unchanged:
            raise ValueError('Source or protected protocol changed during evaluation; evidence is invalid.')


def main():
    parser = argparse.ArgumentParser(description='Pinned, hardware-free OpenArms harness benchmark.')
    commands = parser.add_subparsers(dest='command', required=True)
    runner = commands.add_parser('run')
    runner.add_argument('--out', type=Path, required=True)
    runner.add_argument('--target', type=Path, default=ROOT)
    runner.add_argument('--revision', help='Require this exact HEAD; otherwise record and pin current clean HEAD.')
    runner.add_argument('--allow-dirty-source', action='store_true')
    runner.add_argument('--cases', type=Path, default=ROOT/'agentic/benchmarks/cases.jsonl')
    runner.add_argument('--select')
    runner.add_argument('--modes', default='proposal-only,end-to-end')
    runner.add_argument('--temperatures', default='cold,warm')
    runner.add_argument('--repeats', type=int, choices=range(1, 6), default=2)
    runner.add_argument('--expert', choices=['deterministic', 'live'], default='deterministic')
    runner.add_argument('--expert-profile', choices=['sol', 'astra', 'opus', 'sonnet'], default='sol')
    runner.add_argument('--reasoning-effort', choices=['low', 'medium', 'high', 'xhigh'], default='medium')
    runner.add_argument('--executable', default='/Users/victor/.local/bin/codex')
    runner.add_argument('--timeout', type=float, default=300)
    runner.add_argument('--call-timeout', type=float, default=75)
    runner.add_argument('--max-live-tasks', type=int, default=8)
    runner.add_argument('--test-expert-delay', type=float, default=0)
    runner.add_argument('--admission', type=Path)
    runner.add_argument('--guarded', action='store_true')
    runner.add_argument('--policy', action='append', choices=['guarded_demo_bench_checkpoint', 'fast_planning_context',
                                                              'guarded_demo_bench_completion'])
    runner.add_argument('--service-tier', choices=['standard', 'priority'], default='standard')
    comparison = commands.add_parser('compare')
    comparison.add_argument('baseline', type=Path)
    comparison.add_argument('candidate', type=Path)
    comparison.add_argument('--out', type=Path, required=True)
    comparison.add_argument('--variable', choices=['effort', 'checkpoint', 'tier', 'policy'], required=True)
    args = parser.parse_args()
    if args.command == 'compare':
        before, after = [json.loads((p/'protocol.json').read_text()) for p in (args.baseline, args.candidate)]
        for field in ('cases', 'grader_version', 'expert', 'profile', 'executable', 'timeout',
                      'call_timeout', 'test_expert_delay_seconds', 'protected_files_sha256',
                      'modes', 'temperatures', 'repeats'):
            if before[field] != after[field]:
                parser.error(f'Incomparable protocol field: {field}')
        for protocol in (before, after):
            protocol.setdefault('service_tier', 'standard')
            protocol.setdefault('policies', ['guarded_demo_bench_checkpoint'] if protocol['guarded_checkpoint'] else [])
        if args.variable != 'tier' and before['service_tier'] != after['service_tier']:
            parser.error('Only a tier comparison may change the service tier.')
        if args.variable == 'tier' and (any(before[k] != after[k] for k in ('tested_source', 'policies', 'effort'))
                                        or before['service_tier'] == after['service_tier']):
            parser.error('Tier comparison must change only the requested service tier.')
        if args.variable == 'policy':
            source_maps = [{p: h for p, h in protocol['tested_source']['sources'].items()
                            if not p.startswith('simulation/config/setups/demo_live/')}
                           for protocol in (before, after)]
            changed = {p for p in source_maps[0] if source_maps[0][p] != source_maps[1].get(p)}
            if (source_maps[0].keys() != source_maps[1].keys() or before['effort'] != after['effort']
                    or any(not p.startswith('agentic/openarms_lab/') for p in changed)
                    or not set(before['policies']) < set(after['policies'])):
                parser.error('Policy comparison must add opt-in policies with runtime-only source changes and fixed expert settings.')
        if args.variable == 'effort' and any(before[k] != after[k] for k in ('tested_source', 'guarded_checkpoint')):
            parser.error('Effort comparison must keep source and checkpoint policy fixed.')
        if args.variable == 'checkpoint' and before['effort'] != after['effort']:
            parser.error('Checkpoint comparison must keep effort fixed.')
        if args.variable == 'checkpoint':
            source_maps = [{p: h for p, h in protocol['tested_source']['sources'].items()
                            if not p.startswith('simulation/config/setups/demo_live/')}
                           for protocol in (before, after)]
            if source_maps[0].keys() != source_maps[1].keys():
                parser.error('Checkpoint experiment cannot add or remove runtime source files.')
            changed = {p for p in source_maps[0] if source_maps[0][p] != source_maps[1][p]}
            if changed != {'agentic/openarms_lab/task_loop.py'} or before['guarded_checkpoint'] or not after['guarded_checkpoint']:
                parser.error('Checkpoint experiment must change only TaskLoop and enable the guarded policy.')
        summaries = [json.loads((p/'summary.json').read_text()) for p in (args.baseline, args.candidate)]
        if any(not s['complete'] or not s['protected_inputs_unchanged'] for s in summaries):
            parser.error('Incomplete or changed-source evidence cannot be compared.')
        if 'warm' in before['temperatures'] and summaries[0]['admission']['skill_version'] != summaries[1]['admission']['skill_version']:
            parser.error('Warm comparison requires equivalent admitted skill definitions.')
        for folder in (args.baseline, args.candidate):
            summary = json.loads((folder/'summary.json').read_text())
            if not summary['complete'] or not summary['protected_inputs_unchanged']:
                parser.error('Incomplete or changed-source evidence cannot be compared.')
        report = compare(*[json.loads((p/'results.json').read_text()) for p in (args.baseline, args.candidate)])
        report.update(baseline=str(args.baseline), candidate=str(args.candidate),
                      baseline_source=before['tested_source'], candidate_source=after['tested_source'],
                      baseline_effort=before['effort'], candidate_effort=after['effort'],
                      baseline_tier=before['service_tier'], candidate_tier=after['service_tier'],
                      baseline_policies=before['policies'], candidate_policies=after['policies'],
                      grader_version=before['grader_version'],
                      comparison_engine_sha256=file_hash(ROOT/'agentic/benchmarks/harness_grader.py'),
                      excluded_nonexecution_config='simulation/config/setups/demo_live/ is ignored and unused by demo_bench.')
        if args.out.exists():
            parser.error('Refusing to overwrite a comparison.')
        save(args.out, report)
        print(json.dumps({k: v for k, v in report.items() if k not in ('per_case', 'baseline_source', 'candidate_source')}, indent=2))
    else:
        args.target, args.out, args.cases = args.target.resolve(), args.out.resolve(), args.cases.resolve()
        if args.timeout <= 0 or args.call_timeout <= 0 or args.test_expert_delay < 0:
            parser.error('Invalid time budget.')
        lock = ROOT/'.devin/harness-loop/simulator.lock'
        lock.parent.mkdir(parents=True, exist_ok=True)
        with lock.open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                parser.error('Coordinator simulator owner is already running a benchmark.')
            asyncio.run(run(args))


if __name__ == '__main__':
    main()
