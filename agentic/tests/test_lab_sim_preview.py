"""Simulation evidence and consent checks through the shared lab runtime."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from agentic.openarms_lab.app import create_app
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


def test_real_simulation_png_uses_shared_authenticated_evidence_route(tmp_path, monkeypatch):
    pytest.importorskip('mujoco')
    pytest.importorskip('openarms_sim')
    monkeypatch.delenv('OPENARMS_DEMO_TOKEN', raising=False)
    scene = MujocoSceneService(tmp_path / 'mujoco-frames')
    lab = Lab(tmp_path / 'data', perception=scene)
    with TestClient(create_app(lab, access_path=tmp_path / 'access.sqlite3'), base_url='http://localhost') as client:
        own = client.post('/api/sessions').json()
        other = client.post('/api/sessions').json()
        sid = own['session_id']
        image = client.portal.call(scene.inspect_scene, sid)
        assert image['provenance'] == 'SIMULATED'
        fid = image['evidence_id']
        url = f'/api/sessions/{sid}/evidence/{fid}'
        headers = {'Authorization': 'Bearer ' + own['access_token']}
        assert client.get(url).status_code == 401
        assert client.get(url, headers={'Authorization': 'Bearer ' + other['access_token']}).status_code == 401
        png = client.get(url, headers=headers)
        assert png.status_code == 200 and png.headers['content-type'] == 'image/png'
        assert png.content.startswith(b'\x89PNG\r\n\x1a\n')
        other_url = f"/api/sessions/{other['session_id']}/evidence/{fid}"
        assert client.get(other_url, headers={'Authorization': 'Bearer ' + other['access_token']}).status_code == 404
