"""openarms_sim demo bench through the shared consent, task and evidence loop."""
import asyncio
import copy
from pathlib import Path

import numpy as np
import pytest

from agentic.openarms_lab.runtime import Lab, LabError
from agentic.openarms_lab.demo_bench import (ACTION_CHECKS, DemoBenchBackend, DemoBenchSceneService, anchors, read_pixels)
from agentic.openarms_lab.demo_bench_worker import run_worker
from agentic.openarms_lab import two_vessel_scene

DEFINITION = {
    'skill_id': 'demo_bench_pour', 'name': 'Pour beaker A into container C',
    'intent': 'Pour the beaker at A into the container at C once, return it to A and go HOME',
    'retrieval_examples': ['pour the beaker from {source} into {into}'],
    'parameter_schema': {'source': {'type': 'string', 'enum': ['A']}, 'into': {'type': 'string', 'enum': ['C']}},
    'preconditions': {'fresh_scene': True, 'labels': ['source', 'receiver']},
    'steps': [{'operation': 'inspect_scene'},
              {'operation': 'add_sample', 'arguments': {'source': '$source', 'into': '$into'}},
              {'operation': 'observe'}],
    'expected_state': {'at': 'HOME'},
    'outcome_checks': [{'feature': 'donor_appearance', 'expected': 'empty'},
                       {'feature': 'sample_cup_station', 'expected': 'A'}],
    'limitations': ['SIMULATED demo bench motion only; no physical or chemistry qualification.'],
}


class PourExpert:
    """Deterministic planner, explicitly not a live provider qualification."""
    def __init__(self, definition=DEFINITION):
        self.contexts = []
        self.definition = definition

    async def run(self, context, *, tool_handler, **_):
        self.contexts.append(copy.deepcopy(context))
        if context['phase'] == 'planning':
            await tool_handler('localize_objects', {
                'evidence_id': context['images'][0]['evidence_id'], 'labels': ['source', 'receiver']})
            return {'kind': 'plan', 'summary': 'Pour A into C, return the beaker and go HOME.',
                    'payload': {'skill_definition': self.definition, 'bindings': {'source': 'A', 'into': 'C'}},
                    'provider': 'TEST_FAKE', 'model': 'deterministic-pour-planner', 'calls': 1,
                    'usage': {}, 'elapsed_ms': 1, 'tool_receipts': []}
        return {'kind': 'complete', 'summary': 'Check the independent overview.', 'payload': {'continue': True},
                'provider': 'TEST_FAKE', 'model': 'deterministic-pour-planner', 'calls': 1,
                'usage': {}, 'elapsed_ms': 1, 'tool_receipts': []}


def make_lab(tmp_path, expert=None):
    scene = DemoBenchSceneService(tmp_path/'frames')
    return scene, Lab(tmp_path/'lab', expert=expert or PourExpert(), perception=scene,
                      backend_factory=lambda: DemoBenchBackend(scene), execution_scope='demo-bench-test')


async def settled(lab, handle):
    await asyncio.wait_for(asyncio.shield(lab.workers[handle['task_id']]), 90)


@pytest.mark.asyncio
async def test_demo_bench_full_consent_single_dispatch_and_independent_outcome(tmp_path):
    scene, lab = make_lab(tmp_path)
    try:
        sid = (await lab.create())['session_id']
        handle = await lab.start_task(sid, 'Pour the beaker from A into C, then return it to A and go HOME.')
        await settled(lab, handle)
        snapshot = lab.snapshot(sid)
        assert snapshot['tasks'][-1]['status'] == 'awaiting_confirmation', snapshot['tasks'][-1]['summary']
        proposal = snapshot['pending']
        exact = (sid, proposal['request_id'], proposal['proposal_version'])
        backend = lab.backends[sid]
        with pytest.raises(LabError):
            await lab.confirm(*exact)  # Not yet presented to the student.
        assert backend.executions == 0
        await lab.present(*exact)
        await lab.confirm(*exact)
        await settled(lab, handle)
        task = lab.snapshot(sid)['tasks'][-1]
        assert task['status'] == 'completed', task['summary']
        assert backend.executions == 1
        outcome = task['observations'][-1]
        assert outcome['provenance'] == 'SIMULATED'
        assert outcome['features']['donor_appearance'] == 'empty'
        sim = backend.state()['simulation']
        assert sim['status'] == 'completed' and sim['setup'] == 'demo' and 20 < sim['motion_seconds'] < 30
        assert sim['dose_count'] == 1 and sim['returned_to_dock'] and sim['home_reached']
        assert (scene.folder(sid)/sim['video_name']).stat().st_size > 1000
        observed_id = outcome['evidence'][-1]
        assert observed_id != sim['frame_evidence']['evidence_id']
        assert scene.frames[sid, observed_id][0]['captured_at'] > sim['frame_evidence']['captured_at']
        with pytest.raises(LabError, match='consumed'):
            await lab.confirm(*exact)
        assert backend.executions == 1
        await lab.prepare(sid)
        reset = await scene.observe(sid, {'controller_completed': True})
        assert reset['features']['donor_appearance'] == 'liquid_visible'
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_demo_bench_stop_revokes_pending_confirmation(tmp_path):
    _scene, lab = make_lab(tmp_path)
    try:
        sid = (await lab.create())['session_id']
        handle = await lab.start_task(sid, 'Pour the beaker from A into C.')
        await settled(lab, handle)
        proposal = lab.snapshot(sid)['pending']
        exact = (sid, proposal['request_id'], proposal['proposal_version'])
        await lab.present(*exact)
        await lab.stop(sid)
        assert lab.snapshot(sid)['pending'] is None
        with pytest.raises(LabError):
            await lab.confirm(*exact)
        assert lab.backends[sid].executions == 0
    finally:
        await lab.shutdown()


class DirectActionExpert(PourExpert):
    async def run(self, context, **kwargs):
        if context['phase'] != 'planning':
            return await super().run(context, **kwargs)
        self.contexts.append(copy.deepcopy(context))
        operation, arguments = {
            'Pick up the beaker.': ('pick', {'station': 'A'}),
            'Pick up the receiver.': ('pick', {'station': 'A'}),
            'Pour it into the receiver.': ('pour', {'into': 'C', 'portions': 1}),
            'Put the beaker back.': ('return_cup', {'station': 'A'}),
        }[context['request']]
        return {'kind': 'plan', 'summary': operation, 'payload': {
            'steps': [{'operation': 'inspect_scene'}, {'operation': operation, 'arguments': arguments},
                      {'operation': 'observe'}],
            'outcome_checks': ACTION_CHECKS[operation],
        }, 'provider': 'TEST_FAKE', 'model': 'deterministic-action-planner', 'calls': 1,
            'usage': {}, 'elapsed_ms': 1, 'tool_receipts': []}


@pytest.mark.asyncio
@pytest.mark.parametrize('experiment', ['volcano', 'potions', 'lava_lamp'])
async def test_distinct_beaker_actions_preserve_the_simulated_pose_until_the_next_confirmed_command(tmp_path, monkeypatch, experiment):
    monkeypatch.setenv('OPENARMS_DEMO_EXPERIMENT', experiment)
    _scene, lab = make_lab(tmp_path, DirectActionExpert())
    try:
        sid = (await lab.create())['session_id']
        backend = lab.backends[sid]
        trial_id = lab.snapshot(sid)['trial']['trial_id']
        observations = set()

        async def request_action(text):
            handle = await lab.start_task(sid, text)
            await settled(lab, handle)
            return handle, lab.snapshot(sid)

        rejected, state = await request_action('Pick up the receiver.')
        assert state['pending'] is None
        assert state['tasks'][-1]['task_id'] == rejected['task_id']
        assert state['tasks'][-1]['status'] in ('failed', 'needs_clarification')
        assert backend.executions == 0

        for count, (request, operation, position, holding) in enumerate([
            ('Pick up the beaker.', 'pick', 'LIFT_A', 'sample_cup'),
            ('Pour it into the receiver.', 'pour', 'ABOVE_C', 'sample_cup'),
            ('Put the beaker back.', 'return_cup', 'HOME', None),
        ], start=1):
            handle, state = await request_action(request)
            proposal = state['pending']
            assert proposal, state['tasks'][-1]['summary']
            assert [step['operation'] for step in proposal['plan']['steps']] == ['inspect_scene', operation, 'observe']
            assert backend.executions == count - 1
            key = (sid, proposal['request_id'], proposal['proposal_version'])
            await lab.present(*key)
            await lab.confirm(*key)
            await settled(lab, handle)

            state = lab.snapshot(sid)
            task = state['tasks'][-1]
            assert task['status'] == 'completed', task['summary']
            assert backend.executions == count
            assert state['trial']['trial_id'] == trial_id
            assert (state['state']['at'], state['state']['holding']) == (position, holding)
            outcome = task['observations'][-1]
            assert outcome['provenance'] == 'SIMULATED'
            assert all(outcome['checks'].values())
            assert outcome['features']['sample_cup_held'] is (holding is not None)
            assert outcome['features']['donor_appearance'] == ('liquid_visible' if operation == 'pick' else 'empty')
            assert outcome['evidence'][-1] not in observations
            observations.add(outcome['evidence'][-1])
        assert state['state']['cup_portions'] == 0 and state['state']['receiver_portions'] == 1
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_stop_during_a_resumed_pour_cancels_the_worker(tmp_path):
    scene, lab = make_lab(tmp_path, DirectActionExpert())
    try:
        sid = (await lab.create())['session_id']
        backend = lab.backends[sid]

        async def plan_and_confirm(text):
            task = await lab.start_task(sid, text)
            await settled(lab, task)
            state = lab.snapshot(sid)
            proposal = state['pending']
            assert proposal, state['tasks'][-1]['summary']
            key = (sid, proposal['request_id'], proposal['proposal_version'])
            await lab.present(*key)
            await lab.confirm(*key)
            return task, key

        task, _ = await plan_and_confirm('Pick up the beaker.')
        await settled(lab, task)
        assert backend.state()['holding'] == 'sample_cup'

        started = asyncio.Event()
        worker = backend.worker

        async def paused_worker(folder, command, progress):
            async def mark_started(message):
                started.set()
                await asyncio.Future()

            return await worker(folder, command, mark_started)

        backend.worker = paused_worker
        _, key = await plan_and_confirm('Pour it into the receiver.')
        await asyncio.wait_for(started.wait(), 30)
        stopped = await lab.stop(sid)
        assert stopped['pending'] is None
        assert stopped['tasks'][-1]['status'] == 'cancelled'
        assert backend.state()['simulation']['status'] == 'stopped'
        assert backend.executions == 2
        with pytest.raises(LabError):
            await lab.confirm(*key)
        with pytest.raises(RuntimeError, match='fresh trial'):
            await scene.inspect_scene(sid)
        assert backend.executions == 2
    finally:
        await lab.shutdown()


@pytest.mark.parametrize(('text', 'reason'), [
    ('Pour the beaker from station B into C.', 'from A'),
    ('Pour the beaker from A into receiver B.', 'into C'),
    ('Pour two portions from A to C.', 'one premeasured portion'),
    ('Pour 5 mL from A to C.', 'one premeasured portion'),
    ('Pour from A into C, then return the beaker to C.', 'return the donor to A'),
    ('Pour the vinegar from A into C.', 'only the prepared beaker'),
    ('Add baking soda into C.', 'only the prepared beaker'),
    ('Pour from A into C twice.', 'one premeasured portion from A into C only'),
    ('Pour all of the beaker at A into C.', 'one premeasured portion from A into C only'),
    ('Pour the right container into the left one.', 'one premeasured portion from A into C only'),
    ('Pour the beaker at C onto A.', 'from A'),
    ('Pour B into C.', 'from A'),
    ('Pour from A into C three times.', 'one premeasured portion from A into C only'),
    ('Pour 100 g from A into C.', 'one premeasured portion from A into C only'),
    ('Pour from A into C and leave it at C.', 'return the donor to A'),
])
@pytest.mark.asyncio
async def test_demo_bench_unsupported_request_never_becomes_the_nominal_pour(tmp_path, text, reason):
    _scene, lab = make_lab(tmp_path)
    try:
        sid = (await lab.create())['session_id']
        handle = await lab.start_task(sid, text)
        await settled(lab, handle)
        state = lab.snapshot(sid)
        assert state['pending'] is None
        assert state['tasks'][-1]['status'] == 'failed'
        assert reason in state['tasks'][-1]['summary']
        assert lab.backends[sid].executions == 0
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_demo_bench_plan_must_check_the_donor_reading(tmp_path):
    # A check on a feature the pour never changes cannot stand in for the observer's verdict.
    weak = {**DEFINITION, 'outcome_checks': [{'feature': 'sample_cup_station', 'expected': 'A'}]}
    _scene, lab = make_lab(tmp_path, PourExpert(weak))
    try:
        sid = (await lab.create())['session_id']
        handle = await lab.start_task(sid, 'Pour the beaker from A into C.')
        await settled(lab, handle)
        state = lab.snapshot(sid)
        assert state['pending'] is None
        assert 'donor_appearance' in state['tasks'][-1]['summary']
        assert lab.backends[sid].executions == 0
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_demo_bench_pixel_observer_fails_closed_on_fault_views(tmp_path):
    frames = {}
    for variant in ('nominal', 'camera_shift', 'missing', 'swapped', 'occluded'):
        result = await run_worker(tmp_path, {'kind': 'capture', 'variant': variant, 'generation': 0})
        frames[variant] = two_vessel_scene.fixture._pixels(result['raw_frame'])
    anchor = anchors(frames['nominal'])
    assert read_pixels(frames['nominal'], anchor)['donor'] == 'liquid_visible'
    for variant in ('camera_shift', 'missing', 'swapped', 'occluded'):
        assert read_pixels(frames[variant], anchor)['ready'] is False, variant
    marker_only = frames['missing'].copy()
    x, y = np.rint(anchor['A'] + (-13, -90)).astype(int)
    marker_only[y-3:y+3, x-3:x+3] = (255, 0, 255)
    assert not read_pixels(marker_only, anchor)['ready']
    backend = DemoBenchBackend(DemoBenchSceneService(tmp_path/'s'))
    backend.bind_session('s'); backend.prepare()
    for operation, arguments in (('mock_prepared_sample', {'condition_id': 'water'}),
                                 ('add_sample', {'source': 'C', 'into': 'A'}),
                                 ('add_sample', {'source': 'A', 'into': 'C', 'portions': 2})):
        with pytest.raises(ValueError):
            backend.check_step(operation, arguments)


@pytest.mark.asyncio
async def test_demo_bench_skill_admitted_in_its_own_setup_scope(tmp_path):
    from agentic.openarms_lab.contracts import SkillDefinition
    from agentic.openarms_lab.demo_bench import DemoBenchSkillEvaluator, execution_scope
    from agentic.openarms_lab.skills import SkillRegistry, compute_skill_hash
    definition = SkillDefinition.model_validate(DEFINITION)
    candidate = {**definition.model_dump(mode='json'), 'version': compute_skill_hash(definition), 'status': 'task_validated'}
    result = await DemoBenchSkillEvaluator(tmp_path/'evidence').evaluate_candidate('s', candidate, None)
    assert result['passed'], result['reasons']
    cases = result['metrics']['cases']['candidate']
    assert cases[0]['recovered'] and all(r['executions'] == 0 and not r['recovered'] for r in cases[1:])
    assert all(row['control_passed'] for row in result['metrics']['controls'].values())
    assert result['metrics']['source_scope'] == execution_scope() and execution_scope().startswith('demo-bench-')
    registry = SkillRegistry(tmp_path/'registry.json')
    version = registry.validate_for_task('task', definition)
    assert registry.record_evaluation(candidate['skill_id'], version, result)['status'] == 'promoted'


def test_app_defaults_mujoco_to_demo_bench_with_its_own_scope(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from agentic.openarms_lab.app import create_app
    monkeypatch.setenv('OPENARMS_EXECUTION', 'mujoco')
    monkeypatch.delenv('OPENARMS_SCENE', raising=False)
    monkeypatch.setenv('OPENARMS_DATA_DIR', str(tmp_path/'application'))
    monkeypatch.delenv('OPENARMS_DEMO_TOKEN', raising=False)
    with TestClient(create_app()) as client:
        assert client.get('/api/health').json()['experiment_id'] == 'demo_bench_pour'
        session = client.post('/api/sessions').json()
        assert session['execution_scope'].startswith('demo-bench-')
        assert session['capabilities']['physical_execution'] is False
        assert session['capabilities']['evaluator_available'] is True


@pytest.mark.parametrize('source', ['simulation/config/setups/demo/bench.yaml', 'simulation/config/setups/demo/poses.json',
                                    'agentic/openarms_lab/demo_bench.py', 'agentic/openarms_lab/task_loop.py'])
def test_demo_bench_scope_changes_with_setup_revision(monkeypatch, source):
    from agentic.openarms_lab.demo_bench import execution_scope
    before, read = execution_scope(), Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes', lambda p: read(p) + b'changed' if p.as_posix().endswith(source) else read(p))
    assert execution_scope() != before
