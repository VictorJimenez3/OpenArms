"""Integration regressions for the actual Lab task and Codex tool boundary."""
import asyncio
import copy
import json
import time
import uuid
from pathlib import Path

import pytest

from openarms_lab.codex_expert import CodexExpert
from openarms_lab.contracts import SkillDefinition
from openarms_lab.runtime import Lab
from openarms_lab.scene import SceneService
from openarms_lab.simulated_backend import SceneBackend


DEFINITION = {
    'skill_id': 'sample_color', 'name': 'Prepared sample inspection',
    'intent': 'Test a prepared sample and observe its qualitative color',
    'parameter_schema': {'condition': {'type': 'string', 'enum': ['vinegar', 'water']}},
    'retrieval_examples': ['test prepared {condition}'],
    'preconditions': {'fresh_scene': True, 'labels': ['receiver']},
    'steps': [{'operation': 'inspect_scene'},
              {'operation': 'mock_prepared_sample', 'arguments': {'condition_id': '$condition'}},
              {'operation': 'observe'}],
    'expected_state': {'at': 'HOME'},
    'outcome_checks': [{'feature': 'readable', 'expected': True}],
    'limitations': ['Synthetic fixture only.'],
}


def draft():
    return {'skill_definition': copy.deepcopy(DEFINITION), 'bindings': {'condition': 'vinegar'}}


def reply(kind='plan', payload=None, *, tool=None, arguments=None):
    return {'raw': json.dumps({'kind': kind, 'tool_name': tool,
                               'arguments_json': json.dumps(arguments or {}),
                               'payload_json': json.dumps(payload or {}),
                               'summary': 'Test expert decision.'})}


def seed_version(lab, definition, *, active):
    version = lab.registry.validate_for_task('setup', SkillDefinition.model_validate(definition))
    lab.registry.record_evaluation(definition['skill_id'], version, {
        'evaluation_id': uuid.uuid4().hex, 'suite_hash': 'a' * 64,
        'candidate_hash': version, 'baseline_hash': lab.registry.data['active'].get(definition['skill_id']),
        'regression_gates': dict.fromkeys(('routing', 'outcome', 'unknown', 'consent', 'stop'), True),
        'artifact_hashes': ['b' * 64], 'reasons': ['Test setup'], 'passed': active, 'candidate_recovered': 1, 'baseline_recovered': 0,
    })
    return version


async def settle(lab, sid, handle):
    worker = lab.workers.get(handle['task_id'])
    if worker is not None:
        await asyncio.wait_for(asyncio.shield(worker), 5)
    snapshot = lab.snapshot(sid)
    return snapshot, next(t for t in snapshot['tasks'] if t['task_id'] == handle['task_id'])


async def confirm(lab, sid, request):
    args = (sid, request['request_id'], request['proposal_version'])
    await lab.present(*args)
    await lab.confirm(*args)


@pytest.fixture
async def make_lab(tmp_path):
    labs = []

    async def make(transport, *, scene_class=SceneService, backend_class=SceneBackend):
        scene = scene_class(tmp_path / 'frames')
        expert = CodexExpert(tmp_path / 'expert', artifact_roots=[scene.artifact_dir],
                             transport=transport, max_calls=7)
        lab = Lab(tmp_path / 'lab', expert=expert, perception=scene,
                  backend_factory=lambda: backend_class(scene, delay=0))
        labs.append(lab)
        sid = (await lab.create())['session_id']
        return lab, sid, scene

    yield make
    for lab in labs:
        await lab.shutdown()


async def test_final_plan_repairs_malformed_rejected_and_label_refresh_failure(make_lab):
    class RefreshOnce(SceneService):
        async def localize_objects(self, sid, evidence_id, labels):
            if not getattr(self, 'failed', False):
                self.failed = True
                raise OSError('camera device failed')
            return await super().localize_objects(sid, evidence_id, labels)

    repaired = draft()
    repaired['skill_definition']['steps'][-1]['arguments'] = {'fallback_view': 'secondary'}
    calls = []

    async def transport(prompt, *_):
        calls.append(prompt)
        plan_calls = len(calls)
        assert not lab.snapshot(sid)['requests']
        assert lab.registry.data['validations'].keys() == {'setup'}
        if plan_calls == 1:
            return reply(payload={'skill_definition': {'skill_id': 'malformed'}})
        if plan_calls == 2:
            assert 'Field required' in prompt
            return reply(payload=draft())
        if plan_calls == 3:
            assert 'because it was rejected' in prompt
        if plan_calls == 4:
            assert 'Independent image refresh failed (OSError)' in prompt
        return reply(payload=repaired)

    lab, sid, _ = await make_lab(transport, scene_class=RefreshOnce)
    rejected = seed_version(lab, DEFINITION, active=False)
    snapshot, task = await settle(lab, sid, await lab.start_task(sid, 'Try a prepared sample.'))
    assert len(calls) == 4
    assert task['status'] == 'awaiting_confirmation'
    assert snapshot['pending']['skill_version'] != rejected
    assert not snapshot['pending']['student_confirmed']
    assert lab.registry.list() == []
    assert lab.backends[sid].executions == 0


class ObscureAfterAction(SceneBackend):
    async def execute_step(self, *args, **kwargs):
        result = await super().execute_step(*args, **kwargs)
        self.scene_service.world(self.session_id).occluded_primary = True
        return result


async def recorded_failure(lab, sid):
    pinned = seed_version(lab, DEFINITION, active=True)
    handle = await lab.start_task(sid, 'Test prepared vinegar')
    snapshot, _ = await settle(lab, sid, handle)
    await confirm(lab, sid, snapshot['pending'])
    _, task = await settle(lab, sid, handle)
    assert task['observations'][-1]['status'] == 'unknown'
    assert task['plan']['skill_version'] == pinned
    await lab.prepare(sid)
    return task, pinned


async def test_improvement_repair_preserves_baseline_id_domain_and_expectations(make_lab):
    def edit(**fields):
        plan = draft()
        plan['skill_definition'].update(fields)
        return plan

    drafts = [edit(skill_id='replacement'), edit(parameter_schema={
        'condition': {'type': 'string', 'enum': ['vinegar']}}),
        edit(intent='Only try vinegar.'), edit(expected_state={}),
        edit(outcome_checks=[{'feature': 'color', 'expected': 'pink'}]),
        edit(name='Switch the binding') | {'bindings': {'condition': 'water'}}, draft()]
    drafts[-1]['skill_definition']['steps'][-1]['arguments'] = {'fallback_view': 'secondary'}
    errors = ['pinned baseline skill ID', 'baseline parameter domain', 'baseline intent',
              'baseline outcome or final-state expectations', 'baseline outcome or final-state expectations',
              'bound action for the original request']
    count = 0

    async def transport(prompt, *_):
        nonlocal count
        if '"phase": "execution_feedback"' in prompt:
            return reply('complete', {'continue': True})
        if count:
            assert errors[count - 1] in prompt
        selected = drafts[count]
        count += 1
        return reply('revision', selected)

    lab, sid, _ = await make_lab(transport, backend_class=ObscureAfterAction)
    prior, pinned = await recorded_failure(lab, sid)
    snapshot, task = await settle(lab, sid, await lab.start_improvement(sid, prior['task_id'], 'Try the other view.'))
    assert task['status'] == 'awaiting_confirmation', task.get('summary')
    assert task['improvement']['baseline_plan']['skill_id'] == DEFINITION['skill_id']
    assert task['improvement']['baseline_plan']['skill_version'] == pinned
    assert snapshot['pending']['skill_id'] == DEFINITION['skill_id']
    assert snapshot['pending']['skill_version'] != pinned
    assert lab.registry.get(DEFINITION['skill_id'])['version'] == pinned
    assert len(lab.registry.data['versions']) == 2


@pytest.mark.parametrize('change_at', ['before_validation', 'after_validation'])
async def test_baseline_change_during_planning_blocks_proposal(make_lab, change_at):
    repaired = draft()
    repaired['skill_definition']['steps'][-1]['arguments'] = {'fallback_view': 'secondary'}
    other = DEFINITION | {'name': 'Concurrent version'}

    async def transport(prompt, *_):
        if '"phase": "execution_feedback"' in prompt:
            return reply('complete', {'continue': True})
        if 'active baseline changed' in prompt:
            return reply('clarification')
        if change_at == 'before_validation':
            seed_version(lab, other, active=True)
        return reply('revision', repaired)

    lab, sid, _ = await make_lab(transport, backend_class=ObscureAfterAction)
    prior, pinned = await recorded_failure(lab, sid)
    if change_at == 'after_validation':
        run = lab.expert.run

        async def intervening(*args, **kwargs):
            result = await run(*args, **kwargs)
            assert result['tool_receipts'][-1]['result']['valid']
            seed_version(lab, other, active=True)
            return result

        lab.expert.run = intervening
    snapshot, task = await settle(lab, sid, await lab.start_improvement(sid, prior['task_id'], 'Try the other view.'))
    assert snapshot['pending'] is None
    assert lab.registry.get(DEFINITION['skill_id'])['version'] != pinned
    assert len(lab.registry.data['versions']) == 2
    if change_at == 'after_validation':
        assert task['status'] == 'failed' and 'active baseline changed' in task['summary']
    else:
        assert task['status'] == 'needs_clarification'
        assert 'active baseline changed' in task['expert_runs'][-1]['tool_receipts'][-1]['result']['error']


async def test_codex_receives_replan_limit_and_can_clarify(make_lab):
    revision = {'steps': [{'operation': 'inspect_scene'}]}
    limit_seen = []

    async def transport(prompt, *_):
        if 'Replan limit reached' in prompt:
            limit_seen.append(True)
            return reply('clarification')
        return reply('revision' if '"phase": "execution_feedback"' in prompt else 'plan', revision)

    lab, sid, _ = await make_lab(transport)
    handle = await lab.start_task(sid, 'Inspect the scene.')
    for _ in range(3):
        snapshot, task = await settle(lab, sid, handle)
        assert task['status'] == 'awaiting_confirmation'
        await confirm(lab, sid, snapshot['pending'])
    snapshot, task = await settle(lab, sid, handle)
    assert task['status'] == 'needs_clarification'
    assert limit_seen == [True]
    assert task['replans'] == 2
    assert len(snapshot['requests']) == 3
    assert lab.backends[sid].executions == 0


@pytest.mark.parametrize('tamper, error', [
    ('camera', 'detections do not match'),
    ('new_id', 'original task frame'),
    ('changing_bytes', 'bytes changed'),
    ('different_hash', 'original task frame'),
    ('detection_id', 'detections do not match'),
    ('detection_timestamp', 'detections do not match'),
])
async def test_localize_cannot_rebind_evidence(make_lab, tamper, error):
    class BadLocalization(SceneService):
        async def localize_objects(self, sid, evidence_id, labels):
            found = await super().localize_objects(sid, evidence_id, labels)
            if tamper == 'camera':
                found['detections'][0]['camera_id'] = 'unbound-camera'
            elif tamper == 'new_id':
                found['evidence_id'] = uuid.uuid4().hex
            elif tamper == 'changing_bytes':
                Path(self.frames[sid, evidence_id]['path']).write_bytes(b'corrupted')
            elif tamper == 'different_hash':
                found['images'] = [self.frames[sid, evidence_id] | {'sha256': '0' * 64}]
            elif tamper == 'detection_id':
                found['detections'][0]['frame_id'] = uuid.uuid4().hex
            else:
                found['detections'][0]['timestamp_s'] = 123
            return found

    async def transport(prompt, *_):
        if error in prompt:
            return reply('clarification')
        return reply(payload=draft())

    lab, sid, _ = await make_lab(transport, scene_class=BadLocalization)
    snapshot, task = await settle(lab, sid, await lab.start_task(sid, 'Try a prepared sample.'))
    # If the attached file changed after the first Codex call, the adapter
    # itself also refuses to send its bytes to another model call.
    assert task['status'] == ('failed' if tamper == 'changing_bytes' else 'needs_clarification')
    if tamper != 'changing_bytes':
        assert error in task['expert_runs'][-1]['tool_receipts'][-1]['result']['error']
    assert len(task['evidence']) == 1
    assert not next(iter(task['evidence'].values()))['verified_labels']
    assert snapshot['pending'] is None
    assert not lab.registry.data['versions']


@pytest.mark.parametrize('tamper, error', [
    ('clock', 'Unix producer clock'),
    ('timestamp', 'timestamps do not match'),
    ('stale', 'timestamp is stale'),
    ('future', 'future-dated'),
    ('pre_execution', 'predates execution'),
    ('frame_id', 'image identities'),
    ('bytes', 'bytes changed'),
    ('hash', 'frame owned by this session'),
    ('session', 'frame owned by this session'),
    ('fallback', 'attempts do not match'),
])
async def test_tampered_outcome_is_unknown_even_after_successful_execution(make_lab, tamper, error):
    class TamperOutcome(SceneService):
        async def observe(self, sid, inputs):
            assert inputs == {'view': 'primary', 'fallback_view': 'secondary'}
            if tamper == 'pre_execution':
                # Replay a genuine processor-owned image that the task has
                # never seen; it was captured before the simulator action.
                frame = self.before | {'status': 'observed', 'observer_version': 'test',
                                       'features': {'readable': True}}
            elif tamper == 'session':
                frame = await super().observe(str(uuid.uuid4()), inputs)
            else:
                if tamper == 'fallback':
                    self.world(sid).occluded_primary = True
                frame = await super().observe(sid, inputs)
            if tamper == 'clock':
                # A claimed provenance must not change the producer contract.
                frame['scene']['clock'] = 'recorded_video'
                frame['scene']['provenance'] = frame['provenance'] = frame['images'][0]['provenance'] = 'RECORDED'
            elif tamper == 'timestamp':
                frame['scene']['captured_at'] -= 1
            elif tamper in ('stale', 'future'):
                now = time.time()
                frame['scene']['captured_at'] = frame['images'][0]['captured_at'] = now + (
                    -300 if tamper == 'stale' else 20)
                # Model an incorrect timestamp in the producer's own index.
                self.frames[sid, frame['evidence_id']]['captured_at'] = frame['scene']['captured_at']
            elif tamper == 'frame_id':
                frame['scene']['frame_id'] = uuid.uuid4().hex
            elif tamper == 'bytes':
                Path(frame['images'][0]['path']).write_bytes(b'tampered')
            elif tamper == 'hash':
                frame['images'] = [frame['images'][0] | {'sha256': '0' * 64}]
            elif tamper == 'fallback':
                frame['attempts'].reverse()
            return frame

    async def transport(prompt, *_):
        if '"phase": "execution_feedback"' in prompt:
            return reply('complete', {'continue': True})
        payload = draft()
        payload['skill_definition']['steps'][-1]['arguments'] = {'fallback_view': 'secondary'}
        return reply(payload=payload)

    lab, sid, scene = await make_lab(transport, scene_class=TamperOutcome)
    scene.before = await scene.inspect_scene(sid)
    handle = await lab.start_task(sid, 'Try a prepared sample.')
    snapshot, task = await settle(lab, sid, handle)
    await confirm(lab, sid, snapshot['pending'])
    _, task = await settle(lab, sid, handle)
    assert task['execution'][0]['controller_completed']
    observation = task['observations'][-1]
    assert task['status'] == 'failed'
    assert 'UNKNOWN' in task['summary']
    assert observation['status'] == 'unknown'
    assert observation['provenance'] == 'UNKNOWN'
    assert not observation['features'] and not observation['evidence']
    assert error in observation['reason']


@pytest.mark.asyncio
@pytest.mark.parametrize('text', [
    'Test prepared vinegar and then test prepared water.',
    'Test prepared vinegar and measure the temperature.',
    'Do not test prepared vinegar.',
])
async def test_expert_cannot_propose_only_the_first_action(make_lab, text):
    async def transport(prompt, *_):
        if 'Ask for each action separately.' in prompt or 'no partial action was approved' in prompt:
            response = json.loads(reply('reject', {})['raw'])
            response['summary'] = 'Ask for each supported action separately.'
            return {'raw': json.dumps(response)}
        return reply(payload=draft())

    lab, sid, _ = await make_lab(transport)
    handle = await lab.start_task(sid, text)
    state, task = await settle(lab, sid, handle)
    assert task['status'] == 'failed'
    assert 'separately' in task['summary']
    assert state['pending'] is None and lab.backends[sid].executions == 0


@pytest.mark.asyncio
async def test_expert_cannot_substitute_an_explicitly_requested_sample(make_lab):
    async def transport(prompt, *_):
        if 'differs from the requested sample' in prompt:
            water = draft()
            water['bindings']['condition'] = 'water'
            return reply(payload=water)
        return reply(payload=draft())

    lab, sid, _ = await make_lab(transport)
    handle = await lab.start_task(sid, 'Test the prepared water sample.')
    state, task = await settle(lab, sid, handle)
    assert task['status'] == 'awaiting_confirmation'
    assert state['pending']['plan']['bindings'] == {'condition': 'water'}
    assert lab.backends[sid].executions == 0


@pytest.mark.asyncio
async def test_post_dispatch_revision_cannot_drop_the_approved_outcome_check(make_lab):
    async def transport(prompt, *_):
        if '"phase": "execution_feedback"' in prompt:
            if 'must preserve the approved outcome checks' in prompt:
                return reply('complete', {'continue': True})
            if 'checkpoint_failed' not in prompt:
                return reply('complete', {'continue': True})
            return reply('revision', {'steps': [{'operation': 'observe', 'arguments': {'view': 'secondary'}}],
                                      'outcome_checks': [{'feature': 'readable', 'expected': True}]})
        payload = draft()
        payload['skill_definition']['outcome_checks'].append({'feature': 'color', 'expected': 'purple'})
        return reply(payload=payload)

    lab, sid, _ = await make_lab(transport)
    handle = await lab.start_task(sid, 'Run a prepared sample with a checked outcome.')
    state, _ = await settle(lab, sid, handle)
    await confirm(lab, sid, state['pending'])
    state, task = await settle(lab, sid, handle)
    assert task['status'] == 'failed'
    assert 'outcome check failed' in task['summary']
    assert task['observations'][-1]['checks'] == {'readable': True, 'color': False}
    assert state['pending'] is None and lab.backends[sid].executions == 1


@pytest.mark.asyncio
async def test_observation_revision_does_not_clear_controller_failure(make_lab):
    class FailedAction(SceneBackend):
        async def execute_step(self, request_id, arguments, progress, **options):
            receipt = await super().execute_step(request_id, arguments, progress, **options)
            return {**receipt, 'status': 'failed', 'controller_completed': False,
                    'reason': 'The controller did not verify its return to HOME.'}

    async def transport(prompt, *_):
        if '"phase": "execution_feedback"' not in prompt:
            return reply(payload=draft())
        if 'did not verify its return' in prompt and '"view": "secondary"' not in prompt:
            return reply('revision', {'steps': [{'operation': 'observe', 'arguments': {'view': 'secondary'}}],
                                      'outcome_checks': [{'feature': 'readable', 'expected': True}]})
        return reply('complete', {'continue': True})

    lab, sid, _ = await make_lab(transport, backend_class=FailedAction)
    handle = await lab.start_task(sid, 'Run a prepared sample and inspect its result.')
    state, _ = await settle(lab, sid, handle)
    await confirm(lab, sid, state['pending'])
    state, _ = await settle(lab, sid, handle)
    await confirm(lab, sid, state['pending'])
    state, task = await settle(lab, sid, handle)
    assert task['status'] == 'failed'
    assert 'did not verify its return' in task['summary']
    assert task['observations'][-1]['status'] == 'observed'
    assert lab.backends[sid].executions == 1


async def test_recorded_still_can_be_localized_without_inventing_live_freshness(make_lab):
    class RecordedStill:
        def __init__(self, folder):
            self.folder = folder
            self.inner = SceneService(folder)

        async def inspect_scene(self, sid, view):
            receipt = await self.inner.inspect_scene(sid, view)
            receipt['scene'].update(clock='video_offset_seconds', captured_at=12.5)
            receipt['images'][0]['captured_at'] = 12.5
            return receipt

        async def localize_objects(self, sid, evidence_id, labels):
            return {'evidence_id': evidence_id, 'verified_labels': labels}

    fid = ''

    async def transport(prompt, *_):
        nonlocal fid
        if not fid:
            fid = next(iter(lab.get(sid)['tasks'][-1]['evidence']))
            return reply(tool='localize_objects', kind='tool_call', arguments={'evidence_id': fid, 'labels': ['receiver']})
        if 'fresh scene is required' in prompt:
            return reply(payload={'steps': [{'operation': 'localize_objects',
                                            'arguments': {'evidence_id': fid, 'labels': ['receiver']}}],
                                  'evidence_ids': [fid], 'preconditions': {'labels': ['receiver']}})
        assert '"verified_labels": ["receiver"]' in prompt
        return reply(payload=draft())

    lab, sid, scene = await make_lab(transport)
    lab.perception = RecordedStill(scene.artifact_dir)
    snapshot, task = await settle(lab, sid, await lab.start_task(sid, 'Locate the fixture in the recording.'))
    assert task['status'] == 'awaiting_confirmation'
    assert snapshot['pending']['plan']['steps'][0]['operation'] == 'localize_objects'
    assert task['evidence'][fid]['images'][0]['captured_at'] == 12.5
    assert task['scene']['clock'] == 'video_offset_seconds'
    assert lab.backends[sid].executions == 0


async def test_movement_after_expert_checkpoint_cannot_dispatch(make_lab):
    async def transport(prompt, *_):
        if '"phase": "execution_feedback"' in prompt:
            scene.world(sid).source_offset = 35
            return reply('complete', {'continue': True})
        return reply(payload=draft())

    lab, sid, scene = await make_lab(transport)
    handle = await lab.start_task(sid, 'Try a prepared sample.')
    snapshot, _ = await settle(lab, sid, handle)
    await confirm(lab, sid, snapshot['pending'])
    _, task = await settle(lab, sid, handle)
    assert lab.backends[sid].executions == 0
    assert not task['dispatched_action']


@pytest.mark.parametrize('fault, reason', [
    ({'source_missing': True}, 'source vessel is missing'),
    ({'receiver_missing': True}, 'receiver vessel is missing'),
    ({'vessels_swapped': True}, 'receiver vessel is out of dock C'),
    ({'receiver_offset': 20}, 'Vessel position or camera registration changed'),
    ({'camera_offset': 12}, 'fixture registration could not be verified'),
    ({'base_offset': -12}, 'fixture registration could not be verified'),
])
async def test_warm_dispatch_checks_changes_since_the_presented_scene(make_lab, fault, reason):
    async def transport(*_):
        pytest.fail('Warm skill called the expert with no expert configured.')

    lab, sid, scene = await make_lab(transport)
    lab.expert = None
    # The robot validates required fixture identities even if the skill
    # definition does not declare camera preconditions.
    seed_version(lab, DEFINITION | {'preconditions': {}}, active=True)
    handle = await lab.start_task(sid, 'Test prepared vinegar')
    snapshot, task = await settle(lab, sid, handle)
    assert task['route'] == 'active_skill'
    proposal = snapshot['pending']
    binding = sid, proposal['request_id'], proposal['proposal_version']
    await lab.present(*binding)
    for name, value in fault.items():
        setattr(scene.world(sid), name, value)
    await lab.confirm(*binding)
    snapshot, task = await settle(lab, sid, handle)
    assert snapshot['pending'] is None
    assert task['status'] == 'failed' and reason in task['summary']
    assert not task['dispatched_action'] and task['expert_runs'] == []
    assert lab.backends[sid].executions == 0


async def test_replayed_frame_after_expert_checkpoint_cannot_dispatch(make_lab):
    async def transport(prompt, *_):
        if '"phase": "execution_feedback"' in prompt:
            async def replay(_sid, _view):
                return captured
            scene.inspect_scene = replay
            return reply('complete', {'continue': True})
        return reply(payload=draft())

    lab, sid, scene = await make_lab(transport)
    # This prior frame has a valid hash and was never seen by the task.
    captured = await scene.inspect_scene(sid)
    handle = await lab.start_task(sid, 'Try a prepared sample.')
    snapshot, _ = await settle(lab, sid, handle)
    await confirm(lab, sid, snapshot['pending'])
    _, task = await settle(lab, sid, handle)
    assert task['status'] == 'failed'
    assert 'timestamp is stale' in task['summary']
    assert not task['dispatched_action'] and lab.backends[sid].executions == 0


async def test_unchanged_warm_dispatch_binds_one_motion_and_later_observation(make_lab):
    async def transport(*_):
        pytest.fail('A clear fixture should take the warm path.')

    lab, sid, _ = await make_lab(transport)
    version = seed_version(lab, DEFINITION, active=True)
    handle = await lab.start_task(sid, 'Test prepared vinegar')
    snapshot, task = await settle(lab, sid, handle)
    proposal = snapshot['pending']
    assert proposal['skill_version'] == version
    assert proposal['metrics']['model_calls'] == 0
    presented_id = proposal['plan']['scene_frame_id']
    binding = sid, proposal['request_id'], proposal['proposal_version']
    await confirm(lab, sid, proposal)
    with pytest.raises(ValueError, match='Stale'):
        await lab.confirm(*binding)
    snapshot, task = await settle(lab, sid, handle)
    assert task['status'] == 'completed' and task['expert_runs'] == []
    assert task['dispatched_action'] and lab.backends[sid].executions == 1
    execution, = task['execution']
    observation, = task['observations']
    checkpoint_id = next(item['receipt']['evidence_id'] for item in task['feedback'] if item['type'] == 'perception')
    dispatch_id = execution['dispatch_evidence_id']
    observed_id, = observation['evidence']
    assert len({presented_id, checkpoint_id, dispatch_id, observed_id}) == 4
    assert task['evidence'][dispatch_id]['verified_labels'] == ['receiver', 'source']
    assert (snapshot['requests'][0]['confirmed_at'] < task['evidence'][dispatch_id]['scene']['captured_at']
            < execution['execution_finished_at'] < task['evidence'][observed_id]['scene']['captured_at'])
    assert observation['features']['color'] == 'pink'


@pytest.mark.parametrize('late_failure', [False, True])
async def test_stop_during_dispatch_capture_discards_result_without_motion(make_lab, late_failure):
    class PausedDispatchCapture(SceneService):
        def __init__(self, folder):
            super().__init__(folder)
            self.count = 0
            self.capturing = asyncio.Event()
            self.release = asyncio.Event()
            self.returned = asyncio.Event()

        async def inspect_scene(self, sid, view='primary'):
            self.count += 1
            if self.count != 3:
                return await super().inspect_scene(sid, view)
            self.capturing.set()
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                # A capture adapter may deliver late after cancelled I/O.
                await self.release.wait()
            try:
                if late_failure:
                    raise OSError('Camera failed after STOP')
                return await super().inspect_scene(sid, view)
            finally:
                self.returned.set()

    async def transport(*_):
        pytest.fail('Warm skill called the expert.')

    lab, sid, scene = await make_lab(transport, scene_class=PausedDispatchCapture)
    seed_version(lab, DEFINITION, active=True)
    handle = await lab.start_task(sid, 'Test prepared vinegar')
    snapshot, _ = await settle(lab, sid, handle)
    proposal = snapshot['pending']
    await confirm(lab, sid, proposal)
    await asyncio.wait_for(scene.capturing.wait(), 2)
    stopped = await lab.stop(sid)
    scene.release.set()
    await asyncio.wait_for(scene.returned.wait(), 2)
    snapshot, task = await settle(lab, sid, handle)
    assert snapshot['generation'] == stopped['generation'] > proposal['generation']
    assert snapshot['scene'] == stopped['scene']
    assert task['status'] == 'cancelled' and not task['dispatched_action']
    assert len(task['evidence']) == 2
    assert lab.backends[sid].executions == 0
