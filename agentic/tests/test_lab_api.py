"""Authenticated session lifecycle and mock-only control regressions."""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agentic.openarms_lab.app import create_app
from agentic.openarms_lab.backends import MockBackend
from agentic.openarms_lab.runtime import Lab, LabError
from agentic.tests.test_task_loop import TestExpert, TestPerception, decision


def binding(proposal):
    return {key: proposal[key] for key in ('request_id', 'proposal_version')}


async def task_snapshot(lab, sid, task_id):
    worker = lab.workers.get(task_id)
    if worker is not None:
        await asyncio.wait_for(asyncio.shield(worker), 2)
    return lab.snapshot(sid)


@pytest.fixture
def client(tmp_path, monkeypatch):
    for name in ('OPENARMS_DEMO_TOKEN', 'OPENARMS_ALLOWED_HOSTS', 'GEMINI_API_KEY', 'GOOGLE_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    lab = Lab(tmp_path, expert=TestExpert(), perception=TestPerception(),
              backend_factory=lambda: MockBackend(delay=0))
    with TestClient(create_app(lab, access_path=tmp_path / 'access.db')) as client:
        yield client


def new_session(client):
    response = client.post('/api/sessions')
    assert response.status_code == 200, response.text
    session = response.json()
    return session, f"/api/sessions/{session['session_id']}", {
        'Authorization': f"Bearer {session['access_token']}"}


def hello(ws, session, connection_id):
    ws.send_json({'type': 'hello', 'protocol_version': 1,
                  'access_token': session['access_token'], 'connection_id': connection_id})
    reply = ws.receive_json()
    assert reply['type'] == 'hello' and reply['connection_id'] == connection_id
    state = ws.receive_json()
    assert state['type'] == 'state'
    assert ws.receive_json()['status'] == 'connected'
    return state['state']


def wait_state(client, url, headers, predicate):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        response = client.get(url, headers=headers)
        assert response.status_code == 200, response.text
        state = response.json()
        if predicate(state):
            return state
        time.sleep(.005)
    pytest.fail(f'Session did not reach expected state: {state["tasks"]}')


def test_api_prediction_explicit_request_and_exact_approval(client):
    assert client.get('/').status_code == 200
    assert client.get('/api/health').json()['hardware_enabled'] is False
    session, url, headers = new_session(client)
    assert client.get(url).status_code == 401

    def post(path, body, **extra_headers):
        return client.post(url + '/' + path, json=body, headers={**headers, **extra_headers})

    prediction = post('prediction', {'text': 'The sample might turn pink.'}).json()
    assert prediction['prediction'] == 'The sample might turn pink.'
    assert prediction['pending'] is None and prediction['tasks'] == []
    body = {'text': 'Test the prepared vinegar sample.', 'client_request_id': 'test-turn'}
    queued = post('request', body).json()
    assert queued['tasks'][0]['status'] == 'queued' and queued['pending'] is None
    snap = wait_state(client, url, headers, lambda s: s['pending'] is not None)
    exact = binding(snap['pending'])
    assert session['access_token'] not in str(snap)
    assert len(post('request', body).json()['tasks']) == 1
    assert post('confirm', exact, Origin='https://evil.example').status_code == 403
    assert post('confirm', exact).status_code == 409
    stale = {**exact, 'proposal_version': exact['proposal_version'] + 1}
    assert post('present', stale).status_code == 409
    assert post('present', exact).status_code == 200
    assert post('confirm', stale).status_code == 409
    assert post('confirm', exact).status_code == 200
    assert post('confirm', exact).status_code == 409
    snap = wait_state(client, url, headers, lambda s: s['tasks'][0]['status'] == 'completed')
    assert snap['requests'][0]['student_confirmed']
    assert snap['requests'][0]['result']['controller_completed'] is True
    assert snap['observations'][0]['provenance'] == 'UNKNOWN'
    assert snap['observations'][0]['value'] is None


def test_websocket_host_origin_and_hello_guards(client):
    session, url, headers = new_session(client)
    other, _, _ = new_session(client)
    for extra in ({'Host': 'evil.example'}, {'Origin': 'https://evil.example'}):
        with pytest.raises(WebSocketDisconnect) as rejected:
            with client.websocket_connect(url + '/live', headers=extra):
                pytest.fail('Unexpected upgrade from an untrusted host or origin')
        assert rejected.value.code == 1008
    correct = {'type': 'hello', 'protocol_version': 1, 'access_token': session['access_token']}
    for message in ({'type': 'ping'}, {**correct, 'protocol_version': 2},
                    {**correct, 'access_token': other['access_token']}):
        with client.websocket_connect(url + '/live') as ws:
            ws.send_json(message)
            with pytest.raises(WebSocketDisconnect) as rejected:
                ws.receive_json()
            assert rejected.value.code == 1008
    assert client.get(url, headers=headers).json()['generation'] == session['generation']


def test_default_voice_stays_disabled_even_with_legacy_keys(client, monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'not-a-real-key')
    monkeypatch.setenv('GOOGLE_API_KEY', 'not-a-real-key')
    health = client.get('/api/health').json()
    assert health['live_configured'] is False
    assert health['live_model'] is None
    assert health['voice_status'] == 'disabled_pending_replacement'
    session, url, headers = new_session(client)
    with client.websocket_connect(url + '/live') as ws:
        hello(ws, session, 'voice-disabled')
        ws.send_json({'type': 'start_voice'})
        error = ws.receive_json()
        assert error['type'] == 'status' and error['status'] == 'unavailable'
        assert 'Voice is disabled' in error['message']
        ws.send_json({'type': 'ping', 'seq': 1})
        assert ws.receive_json() == {'type': 'pong', 'seq': 1}
        assert client.post(url + '/stop', headers=headers).status_code == 200


def test_new_owner_revokes_approval_and_old_socket_cannot_stop_new_owner(client):
    session, url, headers = new_session(client)
    _, _, other_headers = new_session(client)
    with client.websocket_connect(url + '/live') as first:
        original = hello(first, session, 'original')
        assert client.post(url + '/request', headers=headers,
                           json={'text': 'Test the prepared vinegar sample.'}).status_code == 200
        snap = wait_state(client, url, headers, lambda s: s['pending'] is not None)
        exact = binding(snap['pending'])
        assert client.post(url + '/present', headers=headers, json=exact).status_code == 200
        with client.websocket_connect(url + '/live') as successor:
            current = hello(successor, session, 'successor')
            assert current['generation'] == original['generation'] + 1
            assert current['pending'] is None
            assert current['requests'][0]['status'] == 'cancelled'
            assert client.post(url + '/confirm', headers=headers, json=exact).status_code == 409
            assert client.post(url + '/stop', headers=other_headers).status_code == 401
            first.send_json({'type': 'stop'})
            for _ in range(16):
                try:
                    first.receive_json()
                except WebSocketDisconnect as exc:
                    assert exc.code == 4001
                    break
            else:
                pytest.fail('Old socket remained open')
            successor.send_json({'type': 'ping', 'seq': 9})
            assert successor.receive_json() == {'type': 'pong', 'seq': 9}
            snap = client.get(url, headers=headers).json()
            assert snap['connected'] and snap['generation'] == current['generation']
    wait_state(client, url, headers, lambda s: not s['connected'])


async def test_stop_revokes_inflight_expert_and_blocks_late_tool(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()
    cancellation, late_results = [], []

    class LateExpert:
        async def run(self, context, *, tool_handler, emit, cancel_event):
            cancellation.append(cancel_event)
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
            with pytest.raises(asyncio.CancelledError):
                await tool_handler('inspect_scene', {})
            late_results.append('rejected')
            return decision()

    backend = MockBackend(delay=0)
    lab = Lab(tmp_path, expert=LateExpert(), perception=TestPerception(),
              backend_factory=lambda: backend)
    try:
        sid = (await lab.create())['session_id']
        request = await lab.start_task(sid, 'Test the prepared vinegar sample.')
        assert request['status'] == 'queued'
        await asyncio.wait_for(entered.wait(), 2)
        worker = lab.workers[request['task_id']]
        await lab.stop(sid, disconnect=True)
        assert cancellation[0].is_set()
        release.set()
        await asyncio.wait_for(worker, 2)
        snap = lab.snapshot(sid)
        assert late_results == ['rejected']
        assert not snap['connected'] and snap['generation'] == 1
        assert snap['tasks'][0]['status'] == 'cancelled'
        assert snap['pending'] is None and snap['requests'] == []
        assert backend.executions == 0
    finally:
        release.set()
        await lab.shutdown()


async def test_runtime_tool_cancel_is_correlated_to_request(tmp_path):
    backend = MockBackend(delay=0)
    lab = Lab(tmp_path, expert=TestExpert(), perception=TestPerception(),
              backend_factory=lambda: backend)
    try:
        sid = (await lab.create())['session_id']
        for cid, text in [('earlier', 'Test the prepared vinegar sample.'),
                          ('current', 'Test the prepared water sample.')]:
            handle = await lab.tool(sid, 'start_task', {'text': text, '_tool_call_id': cid})
            snap = await task_snapshot(lab, sid, handle['task_id'])
            assert snap['pending']['task_id'] == handle['task_id']
        exact = binding(snap['pending'])
        await lab.present(sid, **exact)
        for cid in ('unknown', 'earlier'):
            await lab.tool(sid, '_cancel_tool_request', {'tool_call_id': cid})
            assert binding(lab.snapshot(sid)['pending']) == exact
        await lab.tool(sid, '_cancel_tool_request', {'tool_call_id': 'current'})
        snap = lab.snapshot(sid)
        assert snap['pending'] is None
        assert all(r['status'] == 'cancelled' for r in snap['requests'])
        with pytest.raises(LabError, match='Stale'):
            await lab.confirm(sid, **exact)
        assert backend.executions == 0
    finally:
        await lab.shutdown()


@pytest.mark.parametrize('injected', [False, True])
async def test_physical_backend_cannot_prepare_execute_or_stop(tmp_path, monkeypatch, injected):
    class ForbiddenPhysical(MockBackend):
        mode = 'physical'

        def prepare(self):
            pytest.fail('A physical backend reached preparation')

        async def execute_step(self, *args, **kwargs):
            pytest.fail('A physical backend reached execution')

        async def stop(self):
            pytest.fail('A physical backend reached STOP')

    monkeypatch.setenv('OPENARMS_BACKEND', 'physical')
    lab = Lab(tmp_path, backend_factory=ForbiddenPhysical if injected else None)
    try:
        for _ in range(2):
            with pytest.raises(LabError, match='Physical app execution|hardware-free mock'):
                await lab.create()
        assert not lab.sessions and not lab.backends
    finally:
        await lab.shutdown()


async def test_stop_during_mock_action_revokes_execution_and_prevents_observation(tmp_path):
    executing = asyncio.Event()

    class WaitingMock(MockBackend):
        async def execute_step(self, request_id, arguments, progress):
            async def signal_progress(phase):
                executing.set()
                await progress(phase)
            return await super().execute_step(request_id, arguments, signal_progress)

    backend = WaitingMock(delay=0, fault='timeout')
    lab = Lab(tmp_path, expert=TestExpert(), perception=TestPerception(),
              backend_factory=lambda: backend)
    try:
        sid = (await lab.create())['session_id']
        handle = await lab.start_task(sid, 'Test the prepared vinegar sample.')
        ready = await task_snapshot(lab, sid, handle['task_id'])
        exact = binding(ready['pending'])
        await lab.present(sid, **exact)
        await lab.confirm(sid, **exact)
        await asyncio.wait_for(executing.wait(), 2)
        await asyncio.wait_for(lab.stop(sid), 2)
        stopped = await task_snapshot(lab, sid, handle['task_id'])
        assert stopped['generation'] == ready['generation'] + 1
        assert stopped['tasks'][0]['status'] == 'cancelled'
        assert stopped['requests'][0]['status'] == 'stopped'
        assert stopped['requests'][0]['result']['status'] == 'stopped'
        assert stopped['pending'] is None and stopped['observations'] == []
        assert backend.executions == 1 and backend.state()['at'] == 'HOME'
        assert backend.state()['receiver_portions'] == 0
        with pytest.raises(LabError, match='Stale'):
            await lab.confirm(sid, **exact)
    finally:
        await lab.shutdown()
