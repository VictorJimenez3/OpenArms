"""Simulation evidence and consent checks through the shared lab runtime."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from agentic.openarms_lab.app import create_app
from agentic.openarms_lab.mujoco_backend import MujocoBackend
from agentic.openarms_lab.mujoco_scene import MujocoSceneService
from agentic.openarms_lab.runtime import Lab, LabError
from agentic.openarms_lab.scene import SceneService
from agentic.openarms_lab.simulated_backend import SceneBackend
from agentic.tests.test_task_loop import TestExpert as ExpertFixture


async def wait_for_status(lab, sid, expected):
    async with asyncio.timeout(10):
        while True:
            snapshot = lab.snapshot(sid)
            status = snapshot['tasks'][-1]['status']
            if status == expected:
                return snapshot
            assert status not in ('failed', 'cancelled', 'needs_clarification'), snapshot['tasks'][-1]
            await asyncio.sleep(.01)


@pytest.mark.asyncio
async def test_shared_runtime_inspects_before_expert_and_only_dispatches_presented_proposal_once(tmp_path):
    # This scenario uses the existing synthetic regression environment for speed.
    scene = SceneService(tmp_path / 'synthetic-frames')
    expert = ExpertFixture()
    lab = Lab(tmp_path, backend_factory=lambda: SceneBackend(scene, delay=0), expert=expert, perception=scene)
    try:
        sid = (await lab.create())['session_id']
        await lab.choose_condition(sid, 'vinegar')
        await lab.prediction(sid, 'The receiver will appear pink.')
        await lab.start_task(sid, 'Test the prepared sample.', client_request_id='request')
        proposed = await wait_for_status(lab, sid, 'awaiting_confirmation')
        pending = proposed['pending']
        binding = sid, pending['request_id'], pending['proposal_version']
        planning = expert.contexts[0]
        assert planning['scene']['fresh'] and planning['images'][0]['provenance'] == 'SYNTHETIC'
        assert lab.backends[sid].executions == 0
        with pytest.raises(LabError, match='presented'):
            await lab.confirm(*binding)
        await lab.present(*binding)
        await lab.confirm(*binding)
        done = await wait_for_status(lab, sid, 'completed')
        with pytest.raises(LabError, match='Stale'):
            await lab.confirm(*binding)
        assert lab.backends[sid].executions == 1
        outcome = done['observations'][-1]
        assert outcome['features']['color'] == 'pink'
        assert outcome['evidence'] != [planning['images'][0]['evidence_id']]
        assert outcome['provenance'] == 'SYNTHETIC'
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_corrected_condition_revokes_simulation_consent(tmp_path):
    scene = SceneService(tmp_path / 'synthetic-frames')
    lab = Lab(tmp_path, backend_factory=lambda: SceneBackend(scene, delay=0), expert=ExpertFixture(), perception=scene)
    try:
        sid = (await lab.create())['session_id']
        await lab.choose_condition(sid, 'vinegar')
        await lab.start_task(sid, 'Test the prepared sample.', client_request_id='old')
        pending = (await wait_for_status(lab, sid, 'awaiting_confirmation'))['pending']
        binding = sid, pending['request_id'], pending['proposal_version']
        await lab.present(*binding)
        await lab.choose_condition(sid, 'water')
        assert lab.snapshot(sid)['pending'] is None
        with pytest.raises(LabError, match='Stale'):
            await lab.confirm(*binding)
        assert lab.backends[sid].executions == 0
    finally:
        await lab.shutdown()


def test_existing_block_preview_checks_position_and_rejects_empty_source():
    pytest.importorskip('mujoco')
    from openarms_sim import preview

    plan = {'steps': [{'action': 'move_block', 'args': {'from': 'A', 'to': 'B'}}]}
    moved = preview(plan, setup='block', render=False)
    assert moved['ok'] and moved['motion_seconds'] > 0
    assert moved['objects'] == [{'name': 'block', 'at': 'B', 'started_at': 'A', 'moved': True}]
    blocked = preview(plan, setup='block', objects={'block': 'C'}, render=False)
    assert not blocked['ok']
    assert any(issue['code'] == 'missed_grasp' for issue in blocked['issues'])
    assert blocked['objects'][0]['at'] == 'C'


def test_real_simulation_png_and_mp4_use_shared_authenticated_session_routes(tmp_path, monkeypatch):
    pytest.importorskip('mujoco')
    monkeypatch.delenv('OPENARMS_DEMO_TOKEN', raising=False)
    scene = MujocoSceneService(tmp_path / 'mujoco-frames')
    lab = Lab(tmp_path / 'data', perception=scene, expert=ExpertFixture(),
              backend_factory=lambda: MujocoBackend(scene))
    with TestClient(create_app(lab, access_path=tmp_path / 'access.sqlite3'), base_url='http://localhost') as client:
        own = client.post('/api/sessions').json()
        other = client.post('/api/sessions').json()
        sid = own['session_id']
        base = f'/api/sessions/{sid}'
        headers = {'Authorization': 'Bearer ' + own['access_token']}
        other_headers = {'Authorization': 'Bearer ' + other['access_token']}

        state = client.get(base, headers=headers).json()
        image = state['scene_images'][0]
        assert image['provenance'] == 'SIMULATED'
        fid, url = image['evidence_id'], image['artifact_url']
        assert client.get(url).status_code == 401
        assert client.get(url, headers=other_headers).status_code == 401
        png = client.get(url, headers=headers)
        assert png.status_code == 200 and png.headers['content-type'] == 'image/png'
        assert png.content.startswith(b'\x89PNG\r\n\x1a\n')
        other_base = f"/api/sessions/{other['session_id']}"
        assert client.get(f'{other_base}/evidence/{fid}', headers=other_headers).status_code == 404

        assert client.post(base + '/condition', json={'condition_id': 'vinegar'}, headers=headers).status_code == 200
        client.portal.call(lab.start_task, sid, 'Test the prepared sample.')
        pending = client.portal.call(wait_for_status, lab, sid, 'awaiting_confirmation')['pending']
        binding = {key: pending[key] for key in ('request_id', 'proposal_version')}
        assert lab.backends[sid].executions == 0
        assert client.post(base + '/confirm', json=binding, headers=headers).status_code == 409
        assert client.post(base + '/present', json={**binding, 'channel': 'text'}, headers=headers).status_code == 200
        assert client.post(base + '/confirm', json=binding, headers=headers).status_code == 200
        client.portal.call(wait_for_status, lab, sid, 'completed')
        done = client.get(base, headers=headers).json()
        assert done['observations'][-1]['features'] == {'readable': True, 'color': 'pink'}
        assert done['observations'][-1]['provenance'] == 'SIMULATED'
        assert lab.backends[sid].executions == 1
        simulation = done['state']['simulation']
        assert simulation['source_revision'] == '16a975e' and simulation['dose_count'] == 1
        assert simulation['frame_url'] != url
        assert client.get(simulation['frame_url'], headers=headers).status_code == 200
        assert client.get(simulation['video_url']).status_code == 401
        assert client.get(simulation['video_url'], headers=other_headers).status_code == 401
        video = client.get(simulation['video_url'], headers=headers)
        assert video.status_code == 200 and video.headers['content-type'] == 'video/mp4'
        assert b'ftyp' in video.content[:32]
        name = simulation['video_url'].rsplit('/', 1)[1]
        assert client.get(f'{other_base}/media/{name}', headers=other_headers).status_code == 404
