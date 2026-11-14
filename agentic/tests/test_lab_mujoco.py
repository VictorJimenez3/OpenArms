"""Real Player/renderer coverage and adapter failure boundaries."""
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
    pytest.importorskip('openarms_sim')


@pytest.mark.asyncio
@pytest.mark.parametrize(('condition', 'color'), [('vinegar', 'pink'), ('water', 'purple'), ('baking_soda', 'blue')])
async def test_real_prepared_sample_render_and_independent_observation(session, real_simulator, condition, color):
    scene, backend = session
    sid = backend.session_id
    before = await scene.observe(sid, {})
    assert before['features'] == {'readable': True, 'color': 'purple'}
    assert before['scene']['fresh'] and abs(time.time() - before['scene']['captured_at']) < 10
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
    assert list(dict.fromkeys(phases)) == ['pick(A)', 'pour(C)', 'return_cup()', 'home()']
    assert len(hashes) >= 4
    sim = receipt['simulation']
    assert sim['frame_count'] > 100 and sim['motion_seconds'] > 15
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

    with pytest.raises(ValueError, match='fresh MuJoCo trial'):
        await backend.execute_step('another', {'condition_id': 'vinegar'}, quiet_progress)
    backend.prepare()
    with pytest.raises(ValueError, match='already consumed'):
        await backend.execute_step('confirmed-request', {'condition_id': 'vinegar'}, quiet_progress)


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
            raw = cv2.imencode('.png', np.zeros((480, 640, 3), np.uint8))[1].tobytes()
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
