import asyncio
import copy
import hashlib
import importlib
import json
import subprocess
import time
from pathlib import Path

from PIL import Image


DEFINITION = {
    'skill_id': 'harness_benchmark.pour', 'name': 'Prepared demo pour',
    'intent': 'Pour one prepared portion from A into C, return the beaker to A and go HOME.',
    'retrieval_examples': [
        'pour the beaker from {source} into {into}, return the beaker to {source} and go HOME, then check the result.',
        'pour the beaker from {source} into {into}'],
    'parameter_schema': {'source': {'type': 'string', 'enum': ['A']},
                         'into': {'type': 'string', 'enum': ['C']}},
    'preconditions': {'fresh_scene': True, 'labels': ['source', 'receiver']},
    'steps': [{'operation': 'inspect_scene'},
              {'operation': 'add_sample', 'arguments': {'source': '$source', 'into': '$into', 'portions': 1}},
              {'operation': 'observe'}],
    'expected_state': {'at': 'HOME'},
    'outcome_checks': [{'feature': 'donor_appearance', 'expected': 'empty'}],
    'limitations': ['SIMULATED demo bench only; no physical or chemistry qualification.'],
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def proposal_valid(proposal, scope):
    plan = proposal.get('plan') or {}
    steps = plan.get('steps', [])
    actions = [s for s in steps if s['operation'] not in
               ('inspect_scene', 'localize_objects', 'observe')]
    action_index = next((i for i, s in enumerate(steps) if s['operation'] == 'add_sample'), 0)
    return bool(steps and steps[-1]['operation'] == 'observe'
                and any(s['operation'] == 'inspect_scene' for s in steps[:action_index])
                and [{**a, 'arguments': {'amount': 'all', **a['arguments']}} for a in actions] ==
                [{'operation': 'add_sample', 'arguments': {'source': 'A', 'into': 'C', 'portions': 1, 'amount': 'all'}}]
                and plan.get('expected_state', {}).get('at') == 'HOME'
                and plan.get('execution_scope') == scope and proposal.get('plan_hash') == digest(plan)
                and {'feature': 'donor_appearance', 'expected': 'empty'} in plan.get('outcome_checks', []))


def load_cases(path):
    cases = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    required = {'id', 'kind', 'input', 'behavior', 'expect', 'must_not'}
    if not cases or any(not required.issubset(c) or not all(c[k] for k in required) for c in cases):
        raise ValueError('Each case requires frozen input, expect, must_not, kind, behavior and id.')
    if len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Case IDs must be unique.')
    if any(c['behavior'] not in ('pour', 'no_proposal', 'blocked_after_proposal', 'unknown_after_action', 'stop')
           for c in cases):
        raise ValueError('Unknown case behavior.')
    return cases


def source_identity(root):
    root = Path(root).resolve()
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    config = subprocess.check_output(['git', '-C', str(root), 'ls-files', '--', 'simulation/config'], text=True).splitlines()
    paths = [*sorted((root/'agentic/openarms_lab').rglob('*.py')),
             *sorted((root/'simulation/openarms_sim').rglob('*.py')),
             *sorted((root/'bench_vision').rglob('*.py')),
             *(root/p for p in config)]
    sources = {str(p.relative_to(root)): file_hash(p) for p in paths if p.is_file()}
    dirty = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=all', '--',
        'agentic/openarms_lab', 'simulation/openarms_sim', 'simulation/config', 'bench_vision'], text=True).splitlines()
    return {'revision': head, 'source_tree_sha256': digest(sources), 'sources': sources, 'dirty_source': dirty}


class DeterministicExpert:
    provider = 'DETERMINISTIC_TEST'
    model = 'fixed-pour-test-expert-v1'
    reasoning_effort = 'none'

    def __init__(self, delay=0):
        self.delay = delay

    def describe(self):
        return {'provider': self.provider, 'requested_model': None, 'actual_model': None,
                'model': self.model, 'reasoning_effort': 'none', 'live_model': False,
                'injected_delay_seconds': self.delay}

    async def run(self, context, *, tool_handler, cancel_event=None, **kwargs):
        began = time.perf_counter()
        if self.delay:
            await asyncio.sleep(self.delay)
        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError
        planning = context['phase'] in ('planning', 'improvement')
        if planning and context.get('images'):
            await tool_handler('localize_objects', {
                'evidence_id': context['images'][0]['evidence_id'], 'labels': ['source', 'receiver']})
        return {'kind': 'plan' if planning else 'complete',
                'summary': 'Fixed test proposal; host must independently validate.' if planning else 'Test checkpoint receipt.',
                'payload': {'skill_definition': copy.deepcopy(DEFINITION), 'bindings': {'source': 'A', 'into': 'C'}}
                           if planning else {'continue': True},
                'provider': self.provider, 'model': self.model, 'requested_model': None, 'actual_model': None,
                'model_verified': False, 'reasoning_effort': 'none', 'calls': 0, 'usage': {},
                'elapsed_ms': (time.perf_counter()-began)*1000, 'tool_receipts': []}


async def settled(lab, sid, timeout=300):
    task = lab.snapshot(sid)['tasks'][-1]
    worker = lab.workers.get(task['task_id'])
    if worker:
        await asyncio.wait_for(asyncio.shield(worker), timeout)
    return lab.snapshot(sid)


POLICIES = ('guarded_demo_bench_checkpoint', 'fast_planning_context', 'guarded_demo_bench_completion')


def policy_flags(args):
    flags = set(getattr(args, 'policy', None) or [])
    if getattr(args, 'guarded', False):
        flags.add('guarded_demo_bench_checkpoint')
    if flags - set(POLICIES):
        raise ValueError('Unknown policy flag.')
    return flags


def policy_suffix(policies):
    if not policies:
        return ''
    if list(policies) == ['guarded_demo_bench_checkpoint']:
        return '-guarded-v1'
    return '-policy-' + digest(sorted(policies))[:12]


def make_lab(folder, args, *, deterministic=False):
    Lab = importlib.import_module('openarms_lab.runtime').Lab
    TaskLoop = importlib.import_module('openarms_lab.task_loop').TaskLoop
    demo = importlib.import_module('openarms_lab.demo_bench')
    CONDITIONS, EXPERIMENT = demo.CONDITIONS, demo.EXPERIMENT
    DemoBenchBackend, DemoBenchSceneService = demo.DemoBenchBackend, demo.DemoBenchSceneService
    DemoBenchSkillEvaluator, execution_scope = demo.DemoBenchSkillEvaluator, demo.execution_scope
    ConfiguredExpert = importlib.import_module('openarms_lab.expert_profiles').ConfiguredExpert

    policies = sorted(policy_flags(args))
    for flag in POLICIES:
        if flag in policies and (not hasattr(TaskLoop, flag) or type(getattr(TaskLoop, flag)) is not bool):
            raise ValueError('Target has no requested policy API: ' + flag)
        if hasattr(TaskLoop, flag):
            setattr(TaskLoop, flag, flag in policies)
    base_scope = execution_scope()
    scope = base_scope + policy_suffix(policies)

    class FaultScene(DemoBenchSceneService):
        fault = None

        def __init__(self, folder):
            super().__init__(folder)
            self.fault_frames = []

        async def inspect_scene(self, sid, view='primary'):
            result = await super().inspect_scene(sid, view)
            if getattr(self, 'occlude_observation', False):
                image = result['images'][0]
                path = Path(image['path'])
                with Image.open(path) as original:
                    Image.new('RGB', original.size, 'black').save(path, format='PNG')
                changed_hash = file_hash(path)
                image['sha256'] = changed_hash
                self.frames[sid, image['evidence_id']][0]['sha256'] = changed_hash
                self._raw[sid, image['evidence_id']]['sha256'] = changed_hash
                result['scene']['fixture_registration_valid'] = False
            if self.fault in ('stale_before', 'stale_after'):
                image = result['images'][0]
                stale = image['captured_at'] - 181
                image['captured_at'] = stale
                self.frames[sid, image['evidence_id']][0]['captured_at'] = stale
                self._raw[sid, image['evidence_id']]['captured_at'] = stale
                result['scene'].update(captured_at=stale, expires_at=stale+180, fresh=False)
            self.fault_frames.append({'evidence_id': result['evidence_id'], 'scene': copy.deepcopy(result['scene']),
                                      'fault': self.fault, 'variant': self.variant, 'delivered_at': time.time(),
                                      'pixel_ready': self._observe_pixels(sid, result['evidence_id']).get('ready')})
            return result

        async def observe(self, sid, receipt):
            if getattr(self, 'after_fault', None) == 'occluded_after':
                self.variant = 'occluded'
                self.occlude_observation = True
            elif getattr(self, 'after_fault', None) == 'stale_after':
                self.fault = 'stale_after'
            return await super().observe(sid, receipt)

    class TimedLab(Lab):
        def __init__(self, *a, **kw):
            self.clock_events = []
            super().__init__(*a, **kw)

        def _event(self, s, kind, **data):
            self.clock_events.append({'kind': kind, 'monotonic': time.perf_counter(),
                                      'wall_time': time.time(), 'data': copy.deepcopy(data)})
            return super()._event(s, kind, **data)

    class ScopedEvaluator(DemoBenchSkillEvaluator):
        pass

    ScopedEvaluator.scope = staticmethod(lambda: scope if execution_scope() == base_scope else 'source-changed')
    scene = FaultScene(folder/'scene')
    expert = DeterministicExpert(getattr(args, 'test_expert_delay', 0)) if deterministic or args.expert == 'deterministic' else (
        ConfiguredExpert(folder/'expert', artifact_roots=[scene.artifact_dir],
                         profile=args.expert_profile, reasoning_effort=args.reasoning_effort,
                         executable=getattr(args, 'expert_executable', None) or args.executable, call_timeout=args.call_timeout, task_timeout=args.timeout))
    lab = TimedLab(folder/'sessions', perception=scene, expert=expert,
                   evaluator=ScopedEvaluator(folder/'evaluations'),
                   backend_factory=lambda: DemoBenchBackend(scene), execution_scope=scope,
                   experiment=EXPERIMENT, conditions=CONDITIONS, expert_timeout=args.timeout,
                   execution_timeout=90)
    return lab, scene, scope


def observed_result(state):
    if not state.get('tasks'):
        return False
    task = state['tasks'][-1]
    if not task['observations'] or not task['execution']:
        return False
    observation = task['observations'][-1]
    controllers = [r for r in task['execution'] if r.get('controller_completed')]
    if len(controllers) != 1:
        return False
    controller = controllers[0]
    simulation = controller.get('simulation') or {}
    request = next((r for r in state['requests'] if r['request_id'] == controller['request_id']), {})
    evidence = observation.get('evidence', [])
    controller_frame = (simulation.get('frame_evidence') or {}).get('evidence_id')
    try:
        frames = [task['evidence'][fid]['scene'] for fid in evidence]
    except KeyError:
        return False
    return bool(task['status'] == request.get('status') == simulation.get('status') == 'completed'
        and controller_frame and request.get('student_confirmed')
        and request.get('presented') and request.get('presentation', {}).get('time', float('inf')) <= request['confirmed_at']
        and all(controller.get(k) == observation.get(k) == task.get(k) for k in ('task_id', 'trial_id'))
        and controller['request_id'] == observation['request_id']
        and controller['plan_hash'] == observation['plan_hash'] == request.get('plan_hash')
        and observation['status'] == 'observed' and observation['provenance'] == 'SIMULATED'
        and observation.get('source') and observation['features'].get('donor_appearance') == 'empty'
        and observation['checks'] and all(observation['checks'].values())
        and simulation.get('dose_count') == 1 and simulation.get('returned_to_dock') and simulation.get('home_reached')
        and evidence and controller_frame not in evidence
        and all(frame['captured_at'] > controller['execution_finished_at'] and frame.get('fresh')
                for frame in frames))


def measurements(lab, task_id, started, answered, request_id=None):
    events = [e for e in lab.clock_events if e['data'].get('task_id') == task_id
              and (request_id is None or e['data'].get('request_id') == request_id)]

    def first(kind, predicate=lambda e: True):
        return next((e['monotonic'] for e in events if e['kind'] == kind and predicate(e)), None)

    proposal, confirmation = first('request_proposed'), first('student_confirmed')
    progress = first('execution_progress', lambda e: bool(e['data'].get('phase')))
    observed, finished = first('observation'), first('execution_result')

    def delta(a, b):
        return (b-a)*1000 if a is not None and b is not None else None

    return {'request_to_proposal_ms': delta(started, proposal),
            'proposal_to_confirmation_ms': delta(proposal, confirmation),
            'confirmation_to_controller_progress_ms': delta(confirmation, progress),
            'controller_receipt_to_observation_ms': delta(finished, observed),
            'request_to_observation_ms': delta(started, observed),
            'request_to_answer_ms': delta(started, answered),
            'clock': 'perf_counter', 'approval': 'SCRIPTED_TEST_STUDENT_NOT_HUMAN'}
