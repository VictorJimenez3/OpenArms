import asyncio
import copy
import time
from pathlib import Path

import pytest

from openarms_lab.backends import MockBackend
from openarms_lab.contracts import AddSampleArguments, PlanDraft
from openarms_lab.runtime import Lab, LabError
from openarms_lab.scene import SceneService
from openarms_lab.skills import compute_skill_hash
from openarms_lab.task_loop import CAMERA_FIELDS


class GuardedLab(Lab):
    guarded_demo_bench_checkpoint = True


DEFINITION = {
    'skill_id': 'synthetic_demo_pour', 'name': 'Synthetic demo pour',
    'intent': 'Pour the prepared sample from A into C once and return HOME',
    'parameter_schema': {},
    'retrieval_examples': ['pour the prepared sample from A into C'],
    'preconditions': {'fresh_scene': True, 'labels': ['source', 'receiver']},
    'steps': [{'operation': 'inspect_scene'},
              {'operation': 'add_sample', 'arguments': {'source': 'A', 'into': 'C', 'portions': 1}},
              {'operation': 'observe'}],
    'expected_state': {'at': 'HOME'},
    'outcome_checks': [{'feature': 'donor_appearance', 'expected': 'empty'}],
    'limitations': ['Synthetic unit-test fixture only; no simulator or physical execution.'],
}
IDENTITY = {'scene_id': 'openarms_sim_demo', 'scene_version': 1, 'setup': 'demo',
            'control_mode': 'mujoco_kinematic_add_sample'}


class SyntheticDemoScene(SceneService):
    feature_schema = {**SceneService.feature_schema, 'donor_appearance': {'enum': ['empty', 'liquid_visible']}}

    def __init__(self, root):
        super().__init__(root)
        self.captures = 0
        self.hook = None
        self.before_capture = None
        self.localize_hook = None
        self.entered = asyncio.Event()
        self.resume = asyncio.Event()
        self.block_at = None
        self.scenes = {}

    async def inspect_scene(self, sid, view='primary'):
        self.captures += 1
        if self.captures == self.block_at:
            self.entered.set()
            try:
                await self.resume.wait()
            except asyncio.CancelledError:
                await self.resume.wait()
        if self.before_capture:
            self.before_capture(self, sid)
        frame = await super().inspect_scene(sid, view)
        frame['scene'].update(IDENTITY)
        if self.hook:
            self.hook(self, sid, frame)
        self.scenes[frame['evidence_id']] = copy.deepcopy(frame['scene'])
        return frame

    async def localize_objects(self, sid, evidence_id, labels):
        result = await super().localize_objects(sid, evidence_id, labels)
        for detection in result['detections']:
            detection.update({k: self.scenes[evidence_id][k] for k in CAMERA_FIELDS})
        if self.localize_hook:
            self.localize_hook(result)
        return result

    async def observe(self, sid, arguments):
        result = await super().observe(sid, arguments)
        if result['status'] == 'observed':
            result['features']['donor_appearance'] = (
                'empty' if result['features'].get('color') == 'pink' else 'liquid_visible')
        return result


class SyntheticDemoBackend(MockBackend):
    def __init__(self, scene):
        super().__init__(delay=0)
        self.scene_service = scene
        self.session_id = None
        self.fail = False

    def bind_session(self, sid):
        self.session_id = sid

    @staticmethod
    def capabilities():
        return {**MockBackend.capabilities(), **IDENTITY, 'experiment_id': 'demo_bench_pour',
                'conditions': ['prepared'], 'supported_operations': ['add_sample'],
                'simulation_execution': True,
                'skill_admission': {'required_outcome_checks': DEFINITION['outcome_checks']}}

    def check_step(self, operation, arguments):
        if operation != 'add_sample':
            raise ValueError('Synthetic demo supports only add_sample.')
        AddSampleArguments.model_validate(arguments)

    async def execute_step(self, request_id, arguments, progress, *, operation):
        self.check_step(operation, arguments)
        if request_id in self._consumed:
            raise ValueError('Duplicate synthetic dispatch.')
        self._consumed.add(request_id)
        self.executions += 1
        await progress('synthetic_pour')
        if not self.fail:
            self.scene_service.world(self.session_id).apply_sample('vinegar')
        return {'status': 'failed' if self.fail else 'completed',
                'controller_completed': not self.fail, 'reason': 'Synthetic failure' if self.fail else None}


class SyntheticExpert:
    def __init__(self):
        self.contexts = []
        self.definition = copy.deepcopy(DEFINITION)
        self.feedback_kind = 'complete'

    async def run(self, context, **kwargs):
        self.contexts.append(copy.deepcopy(context))
        planning = context['phase'] == 'planning'
        return {'kind': 'plan' if planning else self.feedback_kind,
                'summary': 'Synthetic decision',
                'payload': {'skill_definition': self.definition} if planning else {'continue': True},
                'provider': 'SYNTHETIC', 'model': 'SYNTHETIC', 'calls': 1, 'usage': {}}

    @property
    def checkpoints(self):
        return [c for c in self.contexts if c['phase'] == 'execution_feedback']


@pytest.fixture
async def make_lab(tmp_path):
    labs = []

    async def make(lab_class=GuardedLab):
        root = tmp_path / str(len(labs))
        scene = SyntheticDemoScene(root / 'frames')
        expert = SyntheticExpert()
        lab = lab_class(root / 'lab', perception=scene, expert=expert,
                        backend_factory=lambda: SyntheticDemoBackend(scene),
                        execution_scope='synthetic-demo-scope',
                        experiment={'id': 'demo_bench_pour'},
                        conditions=[{'id': 'prepared', 'title': 'Synthetic prepared sample'}])
        labs.append(lab)
        sid = (await lab.create())['session_id']
        return lab, sid, scene, expert

    yield make
    for lab in labs:
        await lab.shutdown()


async def settle(lab, sid):
    task = lab.get(sid)['tasks'][-1]
    worker = lab.workers.get(task['task_id'])
    if worker:
        await asyncio.wait_for(asyncio.shield(worker), 3)
    return lab.snapshot(sid)['tasks'][-1]


async def proposal(lab, sid):
    await lab.start_task(sid, 'Pour the prepared sample from A into C.')
    task = await settle(lab, sid)
    assert task['status'] == 'awaiting_confirmation', task.get('summary')
    return lab.get(sid)['pending']


async def approve(lab, sid, request):
    args = (sid, request['request_id'], request['proposal_version'])
    await lab.present(*args)
    await lab.confirm(*args)


def test_opt_in_api_is_explicit_and_default_off():
    assert getattr(Lab, 'guarded_demo_bench_checkpoint', None) is False
    assert GuardedLab.guarded_demo_bench_checkpoint is True


@pytest.mark.parametrize('lab_class,expected_feedback', [(Lab, 2), (GuardedLab, 1)])
async def test_cold_checkpoint_and_post_action_feedback(make_lab, lab_class, expected_feedback):
    lab, sid, scene, expert = await make_lab(lab_class)
    request = await proposal(lab, sid)
    approved = copy.deepcopy(request['plan'])
    await approve(lab, sid, request)
    task = await settle(lab, sid)
    assert task['status'] == 'completed', task.get('summary')
    assert len(expert.checkpoints) == expected_feedback
    assert expert.checkpoints[-1]['task_context']['dispatched_action'] is True
    assert any(f['type'] == 'execution' for f in expert.checkpoints[-1]['feedback'])
    assert any(f['type'] == 'observation' for f in expert.checkpoints[-1]['feedback'])
    assert task['observations'][-1]['status'] == 'observed'
    assert task['observations'][-1]['checks'] == {'donor_appearance': True}
    assert scene.captures == 4
    assert lab.backends[sid].executions == 1
    dispatch = task['evidence'][request['result']['dispatch_evidence_id']]['scene']
    assert dispatch['captured_at'] > request['confirmed_at']
    assert request['plan'] == approved
    assert request['plan_hash'] == compute_skill_hash(approved)
    checkpoints = [f for f in task['feedback'] if f['type'] == 'deterministic_checkpoint']
    assert len(checkpoints) == (1 if lab_class is GuardedLab else 0)
    with pytest.raises(LabError):
        await lab.confirm(sid, request['request_id'], request['proposal_version'])
    await lab._execute_task(lab.get(sid), lab.get(sid)['tasks'][-1], request)
    assert lab.backends[sid].executions == 1


@pytest.mark.parametrize('lab_class', [Lab, GuardedLab])
async def test_warm_routing_stays_model_free_with_synthetic_route_stub(make_lab, monkeypatch, lab_class):
    lab, sid, scene, expert = await make_lab(lab_class)
    monkeypatch.setattr(lab.registry, 'match', lambda text: PlanDraft.model_validate(
        {'skill_definition': copy.deepcopy(DEFINITION)}))
    request = await proposal(lab, sid)
    await approve(lab, sid, request)
    task = await settle(lab, sid)
    assert task['route'] == 'active_skill'
    assert task['status'] == 'completed'
    assert not expert.contexts
    assert lab.backends[sid].executions == 1
    assert scene.captures == 4


@pytest.mark.parametrize('change', [
    'replan', 'execution', 'dispatched', 'uncertainty', 'failure', 'unavailable',
    'clarification', 'correction', 'improvement', 'other_scene', 'other_backend',
    'plan_tamper', 'task_plan_tamper', 'extra_inspection',
])
async def test_nonordinary_tasks_keep_pre_action_expert(make_lab, change):
    lab, sid, scene, expert = await make_lab()
    if change == 'extra_inspection':
        expert.definition['steps'].insert(0, {'operation': 'inspect_scene'})
    request = await proposal(lab, sid)
    task = lab.get(sid)['tasks'][-1]
    if change == 'replan':
        task['replans'] = 1
    elif change == 'execution':
        task['execution'].append({'status': 'failed'})
    elif change == 'dispatched':
        task['dispatched_action'] = True
    elif change in ('uncertainty', 'failure', 'unavailable'):
        kind = {'uncertainty': 'uncertainty', 'failure': 'checkpoint_failed',
                'unavailable': 'scene_unavailable'}[change]
        task['feedback'].append({'type': kind, 'reason': 'Synthetic uncertainty'})
    elif change in ('clarification', 'correction', 'improvement'):
        task[change] = {'synthetic': True}
    elif change == 'other_scene':
        scene.hook = lambda service, sid, frame: frame['scene'].update(scene_id='two_vessel_docks')
    elif change == 'other_backend':
        backend = lab.backends[sid]
        original = backend.capabilities()
        backend.capabilities = lambda: {**original, 'experiment_id': 'two_vessel_water'}
    await approve(lab, sid, request)
    if change == 'plan_tamper':
        request['plan']['expected_state']['at'] = 'NOT_HOME'
    elif change == 'task_plan_tamper':
        task['plan']['expected_state']['at'] = 'NOT_HOME'
    await settle(lab, sid)
    assert expert.checkpoints
    assert expert.checkpoints[0]['task_context']['dispatched_action'] is (change == 'dispatched')
    assert lab.backends[sid].executions <= 1


@pytest.mark.parametrize('stage', [2, 3])
@pytest.mark.parametrize('fault', [
    'moved', 'camera', 'unknown', 'stale', 'unreadable', 'missing', 'failed', 'uncertain',
])
async def test_checkpoint_or_dispatch_evidence_faults_escalate_or_fail_closed(make_lab, stage, fault):
    lab, sid, scene, expert = await make_lab()
    request = await proposal(lab, sid)

    def break_frame(service, session_id, frame):
        if service.captures != stage:
            return
        if fault == 'moved':
            service.world(session_id).source_offset = 4
            frame['scene']['fixture_registration_valid'] = False
        elif fault == 'camera':
            frame['scene']['camera_config_id'] = 'changed-camera'
        elif fault == 'unknown':
            frame['scene']['fixture_registration_valid'] = None
        elif fault == 'stale':
            frame['scene']['captured_at'] = time.time() - 1000
            frame['images'][0]['captured_at'] = frame['scene']['captured_at']
        elif fault == 'unreadable':
            raise OSError('Synthetic camera read failed.')
        elif fault == 'missing':
            frame['images'] = []
        elif fault == 'failed':
            frame['status'] = 'failed'
            frame['reason'] = 'Synthetic failed checkpoint.'
        elif fault == 'uncertain':
            frame['uncertainty'] = 'Synthetic unknown donor fill.'

    scene.hook = break_frame
    expert.feedback_kind = 'reject'
    await approve(lab, sid, request)
    task = await settle(lab, sid)
    assert task['status'] == 'failed', task.get('summary')
    assert lab.backends[sid].executions == 0
    assert expert.checkpoints
    assert not task['observations']


@pytest.mark.parametrize('fault', [
    'presented_receipt', 'presented_scene', 'presented_localization',
    'localization', 'detection', 'moved_box', 'image_bytes', 'missing_file',
])
async def test_uncertain_or_changed_evidence_never_uses_the_cold_skip(make_lab, fault):
    lab, sid, scene, expert = await make_lab()
    request = await proposal(lab, sid)
    if fault.startswith('presented_'):
        record = lab.get(sid)['tasks'][-1]['evidence'][request['plan']['scene_frame_id']]
        target = {'presented_receipt': record, 'presented_scene': record['scene'],
                  'presented_localization': record['localization']}[fault]
        target['uncertainty'] = 'Synthetic uncertainty'
    elif fault in ('localization', 'detection', 'moved_box'):
        def alter_localization(result):
            if fault == 'moved_box':
                result['detections'][0]['box_xyxy'][0] += 1
                result['detections'][0]['box_xyxy'][2] += 1
            else:
                target = result if fault == 'localization' else result['detections'][0]
                target['uncertainty'] = 'Synthetic uncertainty'
        scene.localize_hook = alter_localization
    else:
        def alter_image(service, session_id, frame):
            if service.captures == 2:
                path = service.artifact_dir / session_id / (frame['evidence_id'] + '.png')
                if fault == 'image_bytes':
                    path.write_bytes(b'not the captured image')
                else:
                    path.unlink()
        scene.hook = alter_image
    expert.feedback_kind = 'reject'
    await approve(lab, sid, request)
    await settle(lab, sid)
    assert expert.checkpoints
    assert expert.checkpoints[0]['task_context']['dispatched_action'] is False
    assert lab.backends[sid].executions == 0


@pytest.mark.parametrize('stage', [2, 3])
async def test_changed_pixels_with_unchanged_registered_vessels_escalate(make_lab, stage):
    lab, sid, scene, expert = await make_lab()
    request = await proposal(lab, sid)

    def change_contents(service, session_id):
        if service.captures == stage:
            service.world(session_id).color = 'blue-green'

    scene.before_capture = change_contents
    expert.feedback_kind = 'reject'
    await approve(lab, sid, request)
    await settle(lab, sid)
    assert expert.checkpoints
    assert expert.checkpoints[0]['task_context']['dispatched_action'] is False
    assert lab.backends[sid].executions == 0


@pytest.mark.parametrize('fault', ['changed', 'missing'])
async def test_presented_image_integrity_is_rechecked_before_skip(make_lab, fault):
    lab, sid, scene, expert = await make_lab()
    request = await proposal(lab, sid)
    record = lab.get(sid)['tasks'][-1]['evidence'][request['plan']['scene_frame_id']]
    path = Path(record['images'][0]['path'])
    if fault == 'changed':
        path.write_bytes(b'changed original image')
    else:
        path.unlink()
    expert.feedback_kind = 'reject'
    await approve(lab, sid, request)
    await settle(lab, sid)
    assert expert.checkpoints
    assert expert.checkpoints[0]['task_context']['dispatched_action'] is False
    assert lab.backends[sid].executions == 0


@pytest.mark.parametrize('change', ['plan', 'task_plan', 'scope'])
async def test_late_dispatch_cannot_use_changed_plan_or_scope(make_lab, change):
    lab, sid, scene, expert = await make_lab()
    request = await proposal(lab, sid)

    def change_approval(service, session_id):
        if service.captures == 3:
            if change == 'plan':
                request['plan']['expected_state']['at'] = 'NOT_HOME'
            elif change == 'task_plan':
                lab.get(sid)['tasks'][-1]['plan']['expected_state']['at'] = 'NOT_HOME'
            else:
                lab.execution_scope = 'changed-scope'

    scene.before_capture = change_approval
    expert.feedback_kind = 'reject'
    await approve(lab, sid, request)
    await settle(lab, sid)
    assert expert.checkpoints
    assert expert.checkpoints[0]['task_context']['dispatched_action'] is False
    assert lab.backends[sid].executions == 0


@pytest.mark.parametrize('stage', [2, 3])
@pytest.mark.parametrize('operation', ['cancel', 'stop', 'disconnect', 'generation'])
async def test_late_capture_cannot_restart_revoked_task(make_lab, operation, stage):
    lab, sid, scene, expert = await make_lab()
    request = await proposal(lab, sid)
    scene.block_at = stage
    await approve(lab, sid, request)
    await asyncio.wait_for(scene.entered.wait(), 2)
    if operation == 'cancel':
        await lab.cancel(sid, request['request_id'])
    elif operation == 'stop':
        await lab.stop(sid)
    elif operation == 'disconnect':
        await lab.stop(sid, disconnect=True)
    else:
        lab.get(sid)['generation'] += 1
    scene.resume.set()
    await settle(lab, sid)
    assert lab.backends[sid].executions == 0
    assert not expert.checkpoints
    with pytest.raises(LabError):
        await lab.confirm(sid, request['request_id'], request['proposal_version'])


async def test_exact_consent_and_stop_before_confirmation(make_lab):
    lab, sid, scene, expert = await make_lab()
    request = await proposal(lab, sid)
    with pytest.raises(LabError):
        await lab.confirm(sid, request['request_id'], request['proposal_version'])
    await lab.present(sid, request['request_id'], request['proposal_version'])
    with pytest.raises(LabError):
        await lab.confirm(sid, request['request_id'], request['proposal_version'] + 1)
    await lab.stop(sid)
    with pytest.raises(LabError):
        await lab.confirm(sid, request['request_id'], request['proposal_version'])
    assert lab.backends[sid].executions == 0
    assert not expert.checkpoints


@pytest.mark.parametrize('fault', ['controller', 'outcome'])
async def test_post_action_failures_still_reach_expert_and_do_not_complete(make_lab, fault):
    lab, sid, scene, expert = await make_lab()
    request = await proposal(lab, sid)
    if fault == 'controller':
        lab.backends[sid].fail = True
    else:
        def obscure_outcome(service, session_id, frame):
            if service.captures == 4:
                frame['scene']['fixture_registration_valid'] = False
        scene.hook = obscure_outcome
    await approve(lab, sid, request)
    task = await settle(lab, sid)
    assert task['status'] == 'failed'
    assert lab.backends[sid].executions == 1
    assert len(expert.checkpoints) == 1
    assert expert.checkpoints[0]['task_context']['dispatched_action'] is True
    assert any(f['type'] == 'checkpoint_failed' for f in expert.checkpoints[0]['feedback'])
