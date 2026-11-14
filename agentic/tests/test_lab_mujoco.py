"""Real metered-dropper renderer coverage and adapter failure boundaries."""
import asyncio
import hashlib
import os
import re
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from agentic.openarms_lab import mujoco_process
from agentic.openarms_lab.mujoco_backend import MujocoBackend
from agentic.openarms_lab.mujoco_scene import MujocoSceneService
from simulation.lab_demos.ph import HEIGHT, WIDTH


async def quiet_progress(_phase):
    pass


@pytest.fixture
def session(tmp_path):
    scene = MujocoSceneService(tmp_path)
    backend = MujocoBackend(scene)
    backend.bind_session('session-a')
    backend.prepare()
    return scene, backend


@pytest.fixture
def real_simulator():
    pytest.importorskip('mujoco')


@pytest.mark.asyncio
@pytest.mark.parametrize(('condition', 'color'), [('vinegar', 'pink'), ('water', 'purple'), ('baking_soda', 'blue')])
async def test_real_prepared_sample_render_and_independent_observation(session, real_simulator, condition, color):
    scene, backend = session
    sid = backend.session_id
    metadata = {'scene_id': 'indicator_ph_metered_dropper', 'scene_version': 2,
                'source_revision': '16a975e', 'control_mode': 'mujoco_position_actuator_feedback'}
    assert metadata.items() <= backend.capabilities().items()
    for view in ('secondary', 'primary'):
        before = await scene.observe(sid, {'view': view})
        assert before['features'] == {'readable': True, 'color': 'purple'}
        assert before['scene']['fresh'] and abs(time.time() - before['scene']['captured_at']) < 10
        assert before['scene']['width'] == WIDTH and before['scene']['height'] == HEIGHT
        assert before['scene']['motion_seconds'] == 0
        assert metadata.items() <= before['scene'].items()
        located = await scene.localize_objects(sid, before['evidence_id'], ['A', 'C', 'other'])
        assert located['verified_labels'] == ['A', 'C']
        assert all(not item['geometry_valid'] and item['provenance'] == 'SIMULATED'
                   for item in located['detections'])
    assert backend.state()['simulation']['frame_name'] == before['evidence_id'] + '.png'
    phases, hashes = [], set()

    async def progress(phase):
        state = backend.state()['simulation']
        assert state['status'] == 'running' and state['video_name'] is None
        phases.append(phase)
        hashes.add(state['frame_evidence']['sha256'])

    receipt = await backend.execute_step('confirmed-request', {'condition_id': condition}, progress)
    assert receipt['status'] == 'completed' and receipt['controller_completed']
    assert receipt['backend'] == 'mujoco' and receipt['provenance'] == 'SIMULATED'
    assert receipt['physical_execution'] is False and backend.state()['at'] == 'HOME'
    assert phases == ['prepare_source', 'approach_paddle', 'press_paddle', 'paddle_engaged',
                      'dispense_drop', 'indicator_response', 'release_paddle', 'return_home']
    assert len(hashes) >= 4
    sim = receipt['simulation']
    assert metadata.items() <= sim.items()
    assert sim['frame_count'] > 100 and 4 < sim['motion_seconds'] < 21
    assert sim['dose_count'] == 1 and len(sim['joint_names']) == 6
    converged = [event for event in sim['trace'] if event['event'] == 'motion_converged']
    assert [event['target'] for event in converged] == ['ABOVE_A', 'GRASP_A', 'ABOVE_A', 'HOME']
    assert all(event['max_joint_error_rad'] < .015 and event['max_joint_speed_rad_s'] < .08
               and event['elapsed_seconds'] <= 5 for event in converged)
    assert any(abs(force) > .1 for event in converged for force in event['actuator_force'])
    engagement = next(event for event in sim['trace'] if event['event'] == 'paddle_engagement')
    release = next(event for event in sim['trace'] if event['event'] == 'dose_released')
    delivery = next(event for event in sim['trace'] if event['event'] == 'dose_delivered')
    assert engagement['geometric_engagement'] and engagement['engagement_distance_m'] < .014
    assert engagement['simulation_seconds'] <= release['simulation_seconds'] < delivery['simulation_seconds']
    assert delivery['dose_ml'] == .12
    assert re.fullmatch(r'[0-9a-f]{32}\.mp4', sim['video_name'])
    assert (tmp := scene.artifact_dir / sid / sim['video_name']).stat().st_size > 1000
    assert b'ftyp' in tmp.read_bytes()[:32]
    assert sim['frame_evidence']['sha256'] == hashlib.sha256(
        (scene.artifact_dir / sid / sim['frame_name']).read_bytes()).hexdigest()
    for view in ('primary', 'secondary'):
        # An erroneous controller success/status/color cannot determine pixels.
        observed = await scene.observe(sid, {'view': view, 'controller_completed': False,
                                            'status': 'failed', 'color': 'orange'})
        assert observed['evidence_id'] not in (before['evidence_id'], sim['frame_evidence']['evidence_id'])
        assert observed['scene']['captured_at'] >= sim['frame_evidence']['captured_at']
        assert observed['features'] == {'readable': True, 'color': color}
        assert observed['provenance'] == 'SIMULATED'
        assert observed['scene']['motion_seconds'] == sim['motion_seconds']
        if view == 'primary':
            # Separate GL contexts can round a few edge pixels differently.
            final_pixels = cv2.imread(str(scene.folder(sid) / sim['frame_name']))
            restored_pixels = cv2.imread(observed['images'][0]['path'])
            assert np.mean(np.any(final_pixels != restored_pixels, axis=2)) < .001

    with pytest.raises(ValueError, match='fresh MuJoCo trial'):
        await backend.execute_step('another', {'condition_id': 'vinegar'}, quiet_progress)
    backend.prepare()
    with pytest.raises(ValueError, match='already consumed'):
        await backend.execute_step('confirmed-request', {'condition_id': 'vinegar'}, quiet_progress)


@pytest.mark.asyncio
async def test_disabled_dose_keeps_receiver_and_paddle_evidence(session, real_simulator):
    scene, backend = session
    sid = backend.session_id
    before = await scene.observe(sid, {})
    before_secondary = await scene.observe(sid, {'view': 'secondary'})
    # The disabled-action control is private to the subprocess.
    control = await mujoco_process.run_worker(scene.folder(sid), {
        'kind': 'execute', 'condition': 'vinegar', 'action_enabled': False,
        'video_name': '.0123456789abcdef0123456789abcdef.mp4',
    })
    assert control['ok'] is False and control['dose_count'] == 0
    assert control['state']['dose_count'] == 0
    engagement = next(event for event in control['trace'] if event['event'] == 'paddle_engagement')
    assert engagement['geometric_engagement'] and not engagement['action_enabled']
    assert not any(event['event'] in ('dose_released', 'dose_delivered') for event in control['trace'])
    assert [event['target'] for event in control['trace'] if event['event'] == 'motion_converged'] == [
        'ABOVE_A', 'GRASP_A', 'ABOVE_A', 'HOME']
    scene.finish(sid, control['state'])
    after = await scene.observe(sid, {'color': 'pink'})
    assert before['features'] == after['features'] == {'readable': True, 'color': 'purple'}
    assert after['scene']['motion_seconds'] == control['motion_seconds']
    after_secondary = await scene.observe(sid, {'view': 'secondary'})
    assert after_secondary['features'] == before_secondary['features'] == before['features']
    before_pixels = cv2.imread(before['images'][0]['path'])
    after_pixels = cv2.imread(after['images'][0]['path'])
    np.testing.assert_array_equal(before_pixels[510:532, 726:747], after_pixels[510:532, 726:747])


def test_actuator_nonconvergence_and_geometric_miss_do_not_dose(real_simulator):
    from simulation.lab_demos.ph.run import Apparatus

    stalled = Apparatus()
    stalled.model.actuator_forcerange[:] = 0
    with pytest.raises(RuntimeError, match='failed to converge within'):
        stalled.execute('vinegar', lambda _: None)
    assert stalled.doses == 0
    assert stalled.data.time <= 5.001

    moved_paddle = Apparatus()
    moved_paddle.pad.pos[0] += .05
    with pytest.raises(RuntimeError, match='did not geometrically engage'):
        moved_paddle.execute('vinegar', lambda _: None)
    assert moved_paddle.doses == 0


@pytest.mark.asyncio
async def test_frame_ownership_integrity_and_unknown(session, real_simulator, monkeypatch):
    scene, backend = session
    sid = backend.session_id
    still = await scene.inspect_scene(sid)
    evidence_id = still['evidence_id']
    with pytest.raises(ValueError, match='not owned'):
        await scene.localize_objects('other-session', evidence_id, ['source'])
    path = Path(still['images'][0]['path'])
    path.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='changed'):
        await scene.localize_objects(sid, evidence_id, ['source'])

    original = scene.inspect_scene

    async def obscure(session_id, view):
        result = await original(session_id, view)
        if view == 'primary':
            # Retain a valid PNG whose pixels do not show the receiver.
            record, _ = scene.frames[sid, result['evidence_id']]
            raw = cv2.imencode('.png', np.zeros((HEIGHT, WIDTH, 3), np.uint8))[1].tobytes()
            Path(record['path']).write_bytes(raw)
            record['sha256'] = hashlib.sha256(raw).hexdigest()
            result['images'][0]['sha256'] = record['sha256']
        return result

    monkeypatch.setattr(scene, 'inspect_scene', obscure)
    unknown = await scene.observe(sid, {'controller_completed': True})
    assert unknown['status'] == 'unknown' and unknown['features'] == {'readable': False}
    recovered = await scene.observe(sid, {'fallback_view': 'secondary'})
    assert recovered['features'] == {'readable': True, 'color': 'purple'}
    assert [image['evidence_id'] for image in recovered['images']] == recovered['attempts']


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel_task', [False, True])
async def test_stop_or_cancel_reaps_real_renderer(session, real_simulator, monkeypatch, cancel_task):
    scene, backend = session
    pids = []
    spawn = asyncio.create_subprocess_exec

    async def record_process(*args, **kwargs):
        proc = await spawn(*args, **kwargs)
        pids.append(proc.pid)
        return proc

    monkeypatch.setattr(mujoco_process.asyncio, 'create_subprocess_exec', record_process)
    rendering = asyncio.Event()

    async def progress(_phase):
        if backend.state()['simulation']['frame_count'] > 0:
            rendering.set()
            await asyncio.sleep(60)

    task = asyncio.create_task(backend.execute_step('confirmed', {'condition_id': 'vinegar'}, progress))
    try:
        await asyncio.wait_for(rendering.wait(), 20)
        if cancel_task:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
        else:
            await asyncio.wait_for(backend.stop(), 2)
            assert (await asyncio.wait_for(task, 2))['status'] == 'stopped'
        await asyncio.wait_for(backend.wait_idle(), 2)
        assert len(pids) == 1
        with pytest.raises(ProcessLookupError):
            os.kill(pids[0], 0)
        sim = backend.state()['simulation']
        assert sim['status'] == 'stopped' and sim['video_name'] is None
        assert not list((scene.artifact_dir / backend.session_id).glob('*.mp4'))
        with pytest.raises(RuntimeError, match='fresh trial'):
            await scene.inspect_scene(backend.session_id)
    finally:
        await backend.stop()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_unsupported_steps_and_renderer_failure(session, monkeypatch):
    import agentic.openarms_lab.mujoco_backend as adapter

    async def unavailable(*args, **kwargs):
        raise RuntimeError('MuJoCo worker exited before producing evidence.')

    _scene, backend = session
    for operation in ('mock_pick_up', 'mock_put_down', 'mock_pour'):
        with pytest.raises(ValueError, match='complete prepared'):
            await backend.execute_step('request', {}, quiet_progress, operation=operation)
    assert backend.executions == 0
    with pytest.raises(ValueError):
        await backend.execute_step('request', {'condition_id': 'water', 'destination': 'D'}, quiet_progress)
    monkeypatch.setattr(adapter, 'run_worker', unavailable)
    receipt = await backend.execute_step('request', {'condition_id': 'water'}, quiet_progress)
    assert receipt['status'] == 'failed' and not receipt['controller_completed']
    assert receipt['simulation']['video_name'] is None and backend.state()['at'] == 'UNKNOWN'
    await asyncio.wait_for(backend.wait_idle(), 1)
