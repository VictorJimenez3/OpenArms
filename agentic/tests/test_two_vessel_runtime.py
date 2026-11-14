"""Actual rendered water pour through the shared consent, task and evidence loop."""
import asyncio
import copy
import os
from pathlib import Path

import pytest

from agentic.openarms_lab.runtime import Lab, LabError
from agentic.openarms_lab.two_vessel_backend import TwoVesselBackend
from agentic.openarms_lab.two_vessel_scene import TwoVesselSceneService
from agentic.openarms_lab import two_vessel_worker

DEFINITION = {
    'skill_id': 'two_vessel_water', 'name': 'One water pour A to C',
    'intent': 'Pour one premeasured water portion from A into C and return HOME',
    'retrieval_examples': ['pour {condition} from A to C'],
    'parameter_schema': {'condition': {'type': 'string', 'enum': ['water']}},
    'preconditions': {'fresh_scene': True, 'labels': ['source', 'receiver']},
    'steps': [{'operation': 'inspect_scene'},
              {'operation': 'mock_prepared_sample', 'arguments': {'condition_id': '$condition'}},
              {'operation': 'observe'}],
    'expected_state': {'at': 'HOME'},
    'outcome_checks': [{'feature': 'receiver_appearance', 'expected': 'water_appearance'},
                       {'feature': 'sample_cup_station', 'expected': 'A'}],
    'limitations': ['SIMULATED water motion only; no physical or kit recipe qualification.'],
}


class WaterExpert:
    """Deterministic planner, explicitly not a live provider qualification."""
    def __init__(self):
        self.contexts = []

    async def run(self, context, *, tool_handler, **_):
        self.contexts.append(copy.deepcopy(context))
        if context['phase'] == 'planning':
            await tool_handler('localize_objects', {
                'evidence_id': context['images'][0]['evidence_id'], 'labels': ['source', 'receiver']})
            return {'kind': 'plan', 'summary': 'Pour water from A to C, return donor and HOME.',
                    'payload': {'skill_definition': DEFINITION, 'bindings': {'condition': 'water'}},
                    'provider': 'TEST_FAKE', 'model': 'deterministic-water-planner', 'calls': 1,
                    'usage': {}, 'elapsed_ms': 1, 'tool_receipts': []}
        return {'kind': 'complete', 'summary': 'Check the independent overview.', 'payload': {'continue': True},
                'provider': 'TEST_FAKE', 'model': 'deterministic-water-planner', 'calls': 1,
                'usage': {}, 'elapsed_ms': 1, 'tool_receipts': []}


async def settled(lab, handle):
    await asyncio.wait_for(asyncio.shield(lab.workers[handle['task_id']]), 90)


@pytest.mark.asyncio
async def test_real_two_vessel_water_full_lab_consent_and_fresh_outcome(tmp_path):
    scene, expert = TwoVesselSceneService(tmp_path/'frames'), WaterExpert()
    lab = Lab(tmp_path/'lab', expert=expert, perception=scene,
              backend_factory=lambda: TwoVesselBackend(scene), execution_scope='two-vessel-test')
    try:
        sid = (await lab.create())['session_id']
        handle = await lab.start_task(sid, 'Pour water from A into C.')
        await settled(lab, handle)
        snapshot = lab.snapshot(sid)
        assert snapshot['tasks'][-1]['status'] == 'awaiting_confirmation', snapshot['tasks'][-1]['summary']
        proposal = snapshot['pending']
        exact = (sid, proposal['request_id'], proposal['proposal_version'])
        backend = lab.backends[sid]
        assert backend.executions == 0
        with pytest.raises(LabError):
            await lab.confirm(*exact)
        await lab.present(*exact)
        await lab.confirm(*exact)
        await settled(lab, handle)
        snapshot = lab.snapshot(sid)
        task = snapshot['tasks'][-1]
        assert task['status'] == 'completed', task['summary']
        assert backend.executions == 1
        outcome = task['observations'][-1]
        assert outcome['features']['receiver_appearance'] == 'water_appearance'
        assert outcome['features']['sample_cup_station'] == 'A'
        assert outcome['provenance'] == 'SIMULATED'
        sim = backend.state()['simulation']
        assert sim['status'] == 'completed' and 19 < sim['motion_seconds'] < 21
        assert sim['dose_count'] == 1 and sim['returned_to_dock'] and sim['home_reached']
        assert sim['frame_count'] > 500
        assert (scene.folder(sid)/sim['video_name']).stat().st_size > 1000
        # Independent capture is a new raw image, taken after final controller frame.
        observed_id = outcome['evidence'][-1]
        final_frame = scene.frames[sid, observed_id][0]
        assert observed_id != sim['frame_evidence']['evidence_id']
        assert final_frame['captured_at'] > sim['frame_evidence']['captured_at']
        assert Path(final_frame['path']).name == observed_id+'.png'
        assert expert.contexts[-1]['phase'] != 'planning'
        with pytest.raises(LabError, match='consumed'):
            await lab.confirm(*exact)
        assert backend.executions == 1
        await lab.prepare(sid)
        reset = await scene.observe(sid, {'controller_completed': True, 'color': 'purple'})
        assert reset['features']['receiver_appearance'] == 'dark_base_visible'
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_raw_registration_integrity_reset_and_water_only(tmp_path):
    scene = TwoVesselSceneService(tmp_path)
    backend = TwoVesselBackend(scene)
    backend.bind_session('s'); backend.prepare()
    for condition in ('vinegar', 'baking_soda'):
        with pytest.raises(ValueError, match='water only'):
            backend.check_step('mock_prepared_sample', {'condition_id': condition})
    for variant in ('nominal', 'camera_shift', 'missing', 'swapped', 'occluded'):
        scene.variant = variant
        frame = await scene.observe('s', {'controller_completed': True, 'receiver_appearance': 'water_appearance'})
        assert (frame['status'] == 'observed') == (variant == 'nominal')
        located = await scene.localize_objects('s', frame['evidence_id'], ['source','receiver'])
        assert located['verified_labels'] == (['source','receiver'] if variant == 'nominal' else [])
    scene.variant = 'nominal'
    frame = await scene.inspect_scene('s')
    with pytest.raises(ValueError, match='not owned'):
        await scene.localize_objects('other', frame['evidence_id'], ['source'])
    backend.prepare()
    assert not (await scene.localize_objects('s',frame['evidence_id'],['source']))['verified_labels']
    Path(frame['images'][0]['path']).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='hash changed'):
        await scene.localize_objects('s',frame['evidence_id'],['source'])


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel_task', [False, True])
async def test_stop_reaps_renderer_and_blocks_late_publication(tmp_path, monkeypatch, cancel_task):
    scene = TwoVesselSceneService(tmp_path)
    backend = TwoVesselBackend(scene)
    backend.bind_session('s'); backend.prepare()
    started = asyncio.Event()
    pids = []
    spawn = asyncio.create_subprocess_exec
    async def record(*args, **kwargs):
        proc = await spawn(*args, **kwargs); pids.append(proc.pid); return proc
    monkeypatch.setattr(two_vessel_worker.asyncio,'create_subprocess_exec',record)
    async def progress(_):
        started.set()
        await asyncio.sleep(30)
    task = asyncio.create_task(backend.execute_step('stop-test',{'condition_id':'water'},progress))
    try:
        await asyncio.wait_for(started.wait(), 30)
        if cancel_task:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)
        else:
            await asyncio.wait_for(backend.stop(),3)
            assert (await asyncio.wait_for(task,3))['status']=='stopped'
        await asyncio.wait_for(backend.wait_idle(),3)
        with pytest.raises(ProcessLookupError):
            os.kill(pids[0],0)
        assert backend.state()['simulation']['video_name'] is None
        assert not list(scene.folder('s').glob('*.mp4'))
        with pytest.raises(RuntimeError, match='fresh trial'):
            await scene.inspect_scene('s')
    finally:
        await backend.stop()
        await asyncio.gather(task,return_exceptions=True)


def test_app_selects_water_only_scene_and_isolates_admission(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from agentic.openarms_lab.app import create_app
    monkeypatch.setenv('OPENARMS_EXECUTION', 'mujoco')
    monkeypatch.setenv('OPENARMS_SCENE', 'two_vessel')
    monkeypatch.setenv('OPENARMS_DATA_DIR', str(tmp_path/'application'))
    monkeypatch.delenv('OPENARMS_DEMO_TOKEN', raising=False)
    with TestClient(create_app()) as client:
        assert client.get('/api/health').json()['experiment_id'] == 'two_vessel_water'
        session = client.post('/api/sessions').json()
        assert session['experiment']['id'] == 'two_vessel_water'
        assert [c['id'] for c in session['conditions']] == ['water']
        assert session['capabilities']['evaluator_available'] is True
        assert session['capabilities']['physical_execution'] is False
        assert session['execution_scope'].startswith('two-vessel-')
        headers = {'Authorization': 'Bearer '+session['access_token']}
        url = '/api/sessions/'+session['session_id']
        assert client.post(url+'/condition', json={'condition_id':'vinegar'}, headers=headers).status_code == 409
        assert client.post(url+'/condition', json={'condition_id':'water'}, headers=headers).status_code == 200
        assert 'pH' not in session['experiment']['description']


@pytest.mark.parametrize('source', ['simulation/config/setups/liquid/bench.yaml',
    'agentic/openarms_lab/two_vessel_evaluation.py', 'agentic/openarms_lab/runtime.py',
    'agentic/openarms_lab/evaluation.py', 'bench_vision/perception.py'])
def test_two_vessel_admission_scope_changes_with_fixture(monkeypatch, source):
    from pathlib import Path
    from agentic.openarms_lab.two_vessel_configuration import execution_scope
    before, read = execution_scope(), Path.read_bytes
    def changed(path):
        value = read(path)
        return value+b'changed' if path.as_posix().endswith(source) else value
    monkeypatch.setattr(Path, 'read_bytes', changed)
    assert execution_scope() != before


@pytest.mark.asyncio
async def test_water_experiment_history_is_passive_and_keeps_conditions(tmp_path):
    from agentic.openarms_lab.runtime import Lab
    from agentic.openarms_lab.two_vessel_configuration import EXPERIMENT, CONDITIONS
    from agentic.openarms_lab.backends import MockBackend
    lab = Lab(tmp_path, experiment=EXPERIMENT, conditions=CONDITIONS,
              backend_factory=MockBackend, execution_scope='water-test')
    sid = (await lab.create())['session_id']
    await lab.shutdown()
    def forbidden():
        raise AssertionError('History initialized a backend')
    restored = Lab(tmp_path, experiment=EXPERIMENT, conditions=CONDITIONS,
                   backend_factory=forbidden, execution_scope='water-test')
    try:
        state = restored.snapshot(sid)
        assert state['history_only'] is False
        assert [c['id'] for c in state['conditions']] == ['water']
        assert not restored.backends
    finally:
        await restored.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize('channel', ['voice', 'text', 'api'])
async def test_unsupported_correction_revokes_presented_water_before_confirm(tmp_path, channel):
    from agentic.openarms_lab.backends import MockBackend
    from agentic.openarms_lab.live import GeminiBridge
    from agentic.openarms_lab.two_vessel_configuration import EXPERIMENT, CONDITIONS
    from agentic.tests.test_task_loop import TestExpert, TestPerception
    backend = MockBackend(delay=0)
    lab = Lab(tmp_path, expert=TestExpert(), perception=TestPerception(unknown=False),
              backend_factory=lambda: backend, experiment=EXPERIMENT, conditions=CONDITIONS)
    try:
        sid = (await lab.create())['session_id']
        await lab.choose_condition(sid, 'water')
        handle = await lab.start_task(sid, 'Test prepared water')
        await settled(lab, handle)
        proposal = lab.snapshot(sid)['pending']
        await lab.present(sid, proposal['request_id'], proposal['proposal_version'])
        async def emit(_):
            pass
        bridge = GeminiBridge(lambda: lab.snapshot(sid), lambda n,a: lab.tool(sid,n,a), emit)
        revision = lab.snapshot(sid)['revision']
        if channel == 'api':
            with pytest.raises(LabError, match='supported'):
                await lab.choose_condition(sid, 'vinegar')
            assert lab.snapshot(sid)['revision'] > revision
        elif channel == 'voice':
            bridge.controls.input('Actually, use vinegar instead.')
            await bridge._finish_transcript()
        else:
            await lab.converse(sid, 'Actually, use vinegar instead.')
        bridge.controls.input('Confirm.')
        await bridge._finish_transcript()
        state = lab.snapshot(sid)
        assert state['pending'] is None and len(state['tasks']) == 1
        assert state['requests'][-1]['status'] == 'cancelled'
        assert not state['requests'][-1]['student_confirmed']
        assert backend.executions == 0
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_concurrent_stop_and_inspection_cancel_finish_worker_cleanup(tmp_path, monkeypatch):
    import agentic.openarms_lab.two_vessel_scene as adapter
    started, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    cleaned = []
    async def worker(*_args, **_kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()
            cleaned.append(True)
    monkeypatch.setattr(adapter, 'run_worker', worker)
    scene = TwoVesselSceneService(tmp_path)
    inspect = asyncio.create_task(scene.inspect_scene('s'))
    await started.wait()
    stop = asyncio.create_task(scene.cancel_captures('s'))
    try:
        await cleaning.wait()
        inspect.cancel()
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(inspect, stop, return_exceptions=True)
        assert cleaned == [True] and not scene.frames
    finally:
        release.set()
        await asyncio.gather(inspect, stop, return_exceptions=True)


@pytest.mark.asyncio
async def test_expert_receives_controller_and_observer_admission_contract(tmp_path):
    from agentic.openarms_lab.two_vessel_configuration import EXPERIMENT, CONDITIONS
    from agentic.tests.test_task_loop import TestPerception
    contexts = []
    class InspectContract:
        async def run(self, context, **_):
            contexts.append(context)
            return {'kind':'clarification', 'summary':'Inspecting the admission contract only.', 'payload':{},
                    'provider':'TEST_FAKE', 'model':'contract-test', 'calls':1,
                    'usage':{}, 'elapsed_ms':0, 'tool_receipts':[]}
    scene = TwoVesselSceneService(tmp_path/'frames')
    lab = Lab(tmp_path/'lab', expert=InspectContract(), perception=TestPerception(unknown=False),
              backend_factory=lambda: TwoVesselBackend(scene), experiment=EXPERIMENT, conditions=CONDITIONS)
    try:
        sid = (await lab.create())['session_id']
        handle = await lab.start_task(sid, 'Pour water from A to C.')
        await settled(lab, handle)
        requirements = contexts[0]['capability_limits']['skill_admission']
        assert requirements['required_expected_state'] == {'at':'HOME'}
        assert requirements['required_outcome_checks'] == [
            {'feature':'receiver_appearance', 'expected':'water_appearance'}]
        assert 'not a camera-observed feature' in requirements['expected_state_contract']
        assert 'independently' in requirements['outcome_checks_contract']
        assert not {'steps', 'bindings', 'skill_definition'}.intersection(requirements)
        assert {'inspect_scene','localize_objects','validate_plan'}.issubset(
            {tool['name'] for tool in contexts[0]['tools']})
        assert lab.backends[sid].executions == 0
    finally:
        await lab.shutdown()
