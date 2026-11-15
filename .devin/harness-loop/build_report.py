import hashlib
import json
import re
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'outputs'
PYTHON = '/Users/victor/OpenArms/device-expert-smoke/.venv-lab/bin/python'
NAMES = ['live-medium-development', 'live-low-development', 'deterministic-baseline-v2',
         'deterministic-checkpoint-v2', 'heldout-deterministic-baseline', 'heldout-deterministic-checkpoint',
         'live-checkpoint-baseline', 'live-checkpoint-candidate', 'heldout-live-baseline', 'heldout-live-checkpoint']


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe(name):
    folder = OUT/name
    summary, protocol, rows = [read(folder/file) for file in ('summary.json', 'protocol.json', 'results.json')]
    if not summary['complete'] or not summary['protected_inputs_unchanged']:
        raise ValueError('Incomplete evidence: '+name)
    groups = {}
    for row in rows:
        key = '/'.join(row[k] for k in ('case_id', 'mode', 'temperature'))
        groups.setdefault(key, []).append(row)
    metrics = {}
    for key, group in groups.items():
        metrics[key] = {'passed': sum(r['grade']['passed'] for r in group), 'samples': len(group)}
        for metric in ('request_to_proposal_ms', 'confirmation_to_controller_progress_ms',
                       'request_to_observation_ms', 'request_to_answer_ms'):
            values = [r['timing'][metric] for r in group if r['timing'].get(metric) is not None]
            if values:
                metrics[key][metric] = {'median': statistics.median(values), 'min': min(values), 'max': max(values)}
    return {'path': str(folder), 'summary': summary, 'protocol_sha256': sha(folder/'protocol.json'),
            'artifact_manifest_sha256': sha(folder/'artifact-manifest.json'),
            'revision': protocol['tested_source']['revision'], 'source_sha256': protocol['tested_source']['source_tree_sha256'],
            'expert': protocol['expert'], 'requested_profile': protocol['profile'], 'requested_effort': protocol['effort'],
            'guarded': protocol['guarded_checkpoint'], 'groups': metrics,
            'actual_models_reported': sorted({run['actual_model'] for r in rows for run in r.get('expert_runs', [])
                                              if run.get('actual_model')}),
            'guarded_checkpoint_count': sum(r.get('guarded_checkpoints', 0) for r in rows),
            'live_model_calls': sum(r.get('model_calls', 0) for r in rows),
            'traces': [r['trace'] for r in rows if 'trace' in r]}


runs = {name: describe(name) for name in NAMES}
comparisons = {name: read(OUT/name) for name in (
    'live-effort-development-comparison.json', 'checkpoint-deterministic-comparison.json',
    'checkpoint-heldout-comparison.json', 'checkpoint-live-comparison.json', 'checkpoint-heldout-live-comparison.json')}
candidate_test_log = (OUT/'candidate-full-suite.log').read_text()
test_result = re.findall(r'(\d+) passed.*?in ([\d.]+)s', candidate_test_log)
if not test_result:
    raise ValueError('Candidate full-suite result is missing.')
heldout_live = runs['heldout-live-checkpoint']
report = {
    'result': 'Retain guarded checkpoint as an isolated opt-in candidate; preserve all defaults.',
    'baseline': {'branch': 'victor/integration-device-expert', 'revision': '47a00c1dcf95c8d0077a5007ff825b4c5de7737e'},
    'candidate': {'branch': 'victor/harness-checkpoint-pinned-47a00c1',
                  'revision': '0287c6e35f36c2f690ccbb6104bf146e1570aa61',
                  'worktree': '/Users/victor/OpenArms/harness-checkpoint-v2',
                  'api': 'Lab.guarded_demo_bench_checkpoint = True; default False',
                  'scope_policy': 'content-derived demo-bench scope plus -guarded-v1; separately re-admitted'},
    'coordinator': {'worktree': str(ROOT), 'branch': 'victor/harness-loop-pinned-47a00c1',
                    'requirement_ids': ['D1', 'D3', 'D4', 'R2', 'R4', 'R6'], 'issue': 19,
                    'simulator_registry_owner': 'coordinator only', 'pushed_or_merged': False},
    'reproduce': {
        'cwd': str(ROOT),
        'benchmark': f'PYTHONPATH=agentic:. {PYTHON} agentic/scripts/harness_benchmark.py run --out outputs/harness-run-unique',
        'candidate': f'PYTHONPATH=agentic:. {PYTHON} agentic/scripts/harness_benchmark.py run --out outputs/harness-candidate-unique --target /Users/victor/OpenArms/harness-checkpoint-v2 --revision 0287c6e35f36c2f690ccbb6104bf146e1570aa61 --guarded',
        'live': '--expert live --expert-profile sol --reasoning-effort medium --executable /Users/victor/.local/bin/codex',
        'compare': f'PYTHONPATH=agentic:. {PYTHON} agentic/scripts/harness_benchmark.py compare BASELINE_DIR CANDIDATE_DIR --variable checkpoint --out outputs/comparison-unique.json',
        'cases': 'agentic/benchmarks/cases.jsonl', 'scoring': 'agentic/benchmarks/harness_grader.py',
        'heldout': '.devin/harness-loop/heldout.jsonl', 'fresh_output_required': True},
    'loop': [
        {'stage': 'freeze', 'evidence': 'Per-run protocol.json contains inputs/expectations, protected hashes, tested sources, configuration and matrix.'},
        {'stage': 'baseline', 'evidence': 'Pinned runtime baseline; full 686-test suite; real live expert and simulator runs.'},
        {'stage': 'diagnose', 'finding': 'Cold fresh inspection always requested expert execution feedback before a separate deterministic dispatch check; live pre-action wait dominates confirmation-to-progress.'},
        {'stage': 'candidate_1', 'change': 'Sol medium to low only, same prompt/template and scene.',
         'decision': 'Discard global effort change: 4/4 correct proposals each, aggregate 1.09x but unfamiliar D03 regressed about 16%; two repetitions are insufficient for a global change.'},
        {'stage': 'candidate_2', 'change': 'Skip only ordinary first demo inspection expert checkpoint when exact approved plan and fresh unchanged evidence pass deterministic guards.',
         'decision': 'Retain isolated opt-in: matched live and deterministic cases, separately scoped admission and held-out evaluation; no default enablement.'},
        {'stage': 'heldout', 'evidence': 'Four unseen-by-optimizer cases; deterministic 32/32 per variant; live H01 two repeats per variant.',
         'live_candidate_passed': heldout_live['summary']['passed']},
        {'stage': 'review', 'reviewer': 'built-in independent reviewer 52871d6d; raw live trace, exact consent, one dispatch, fresh linked observation and post-action expert run checked.'}],
    'runs': runs, 'comparisons': comparisons,
    'verification': {'baseline_full_suite': '686 passed in 307.97s',
                     'benchmark_tests': '19 passed', 'candidate_focused': '65 passed in 4.64s',
                     'candidate_full_suite': {'passed': int(test_result[-1][0]), 'seconds': float(test_result[-1][1]),
                                              'log': str(OUT/'candidate-full-suite.log')},
                     'known_warnings': ['pytest-asyncio unset fixture-loop scope', 'existing Test* helper classes have constructors']},
    'retained_failures': {
        'initial_deterministic_batch': 'outputs/deterministic-baseline-development: 60/76 before runner instrumentation corrections; all original evidence retained.',
        'repairs': ['Restored simulator final state ignores view variant; harness now occludes captured post-action pixels and rehashes evidence before ingestion.',
                    'STOP exposes task reason rather than summary; runner records actual reason.',
                    'Missing donor leaves camera markers registered; grader mechanism now uses independent pixel readiness.',
                    'Valid revised proposals are allowed only with fresh pending consent; incomplete batches rejected; nested/untracked sources detected; target imports isolated.'],
        'expectations_changed': False,
        'frozen_runner_versions': ['outputs/runner-v1-snapshot', 'outputs/runner-v2-snapshot'],
        'source_comparison_exception': 'Ignored simulation/config/setups/demo_live config was created by baseline tests; selected demo setup never consumes it. Raw identities retained; only this nonexecution path is excluded.'},
    'delegation': {
        'full_sessions': [
            {'worker': 'worker-f36eecb6e918', 'responsibility': 'candidate implementation', 'session_id': None,
             'status': 'workspace_trust blocked before creation', 'open_resume': None},
            {'worker': 'worker-a378b9ac3b50', 'responsibility': 'independent review', 'session_id': None,
             'status': 'workspace_trust blocked before creation; interactive trust job-2f34de53e1c7 opened at user request',
             'open_resume': None},
            {'worker': 'worker-37e3af00af12', 'responsibility': 'final independent evidence review',
             'session_id': 'lucky-brook', 'status': 'initial real review succeeded; same-session follow-up job-ea8f008f07b5',
             'open_resume': 'python3 /Users/victor/.config/devin/skills/local-devin-sessions/scripts/local_sessions.py open worker-37e3af00af12',
             'raw_resume': 'cd /Users/victor/OpenArms/harness-evidence-review-v2 && /Users/victor/.local/share/local-devin-sessions/runtime/3000.12.57/bin/devin --permission-mode auto --respect-workspace-trust true --resume lucky-brook'}],
        'built_in_workers': [
            {'id': '02b84299', 'responsibility': 'isolated candidate implementation; no grader/held-out access', 'status': 'completed'},
            {'id': '52871d6d', 'responsibility': 'independent protocol and evidence review', 'status': 'completed initial review; final live update separate'},
            {'id': '08f0666c', 'responsibility': 'bounded evidence-schema compatibility review', 'status': 'completed'}],
        'full_session_blocker': 'Resolved by human exact-worktree trust and exit; initial denied read/shell calls were not bypassed. Real reviewer still completed via native read tools.',
        'launcher': '/Users/victor/.config/devin/skills/local-devin-sessions/scripts/local_sessions.py'},
    'limits': ['Small non-randomized live batch; no statistical confidence claim.',
               'Requested gpt-6.1-sol; actual_model null and identity unverified when provider omits telemetry.',
               'No 2x/4x service-tier support established; none tested or projected.',
               'Cost USD unavailable; actual calls and token/cache counts remain in raw traces.',
               'No injected expert delay used in measured runs; deterministic expert model_calls=0.',
               'One fixed simulated A-to-C motion only; no new experiment transfer or D4 product-completion claim.',
               'Primary/secondary name one overview; pixel donor appearance is not measured delivery volume, chemistry or physical qualification.',
               'HOME/return controller facts remain distinct from independent pixel observations.',
               'Scripted exact consent and delivered text, not human approval latency or audible voice.',
               'Bit-identical-image guard is conservative; changed, uncertain or nonordinary evidence retains escalation.',
               'Do not tune on the next multi-choice experiment before running a frozen harness baseline.']}
path = ROOT/'agentic/benchmarks/first_loop_report.json'
if path.exists():
    raise FileExistsError(path)
path.write_text(json.dumps(report, indent=2)+'\n')
print(path)
