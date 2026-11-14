"""Real HTTP/WebSocket fixtures for pH sessions, access, and connection ownership."""
import asyncio
import time
import pytest
from fastapi.testclient import TestClient
from agentic.openarms_lab.app import create_app
from agentic.openarms_lab.runtime import Lab
from agentic.openarms_lab.scene import SceneService
from agentic.openarms_lab.simulated_backend import SceneBackend
from agentic.tests.test_task_loop import TestExpert


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENARMS_BACKEND', 'mock')
    monkeypatch.delenv('OPENARMS_DEMO_TOKEN', raising=False)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    scene = SceneService(tmp_path/'images')
    lab = Lab(tmp_path/'data', expert=TestExpert(), perception=scene,
              backend_factory=lambda: SceneBackend(scene, delay=0))
    with TestClient(create_app(lab, access_path=tmp_path / 'access.db')) as client:
        yield client


def new_session(client):
    response = client.post('/api/sessions')
    assert response.status_code == 200, response.text
    data = response.json()
    return data, {'Authorization': 'Bearer ' + data['access_token']}


def hello(ws, session, cid='client-1'):
    ws.send_json({'type': 'hello', 'protocol_version': 1, 'connection_id': cid, 'access_token': session['access_token']})
    assert ws.receive_json()['type'] == 'hello'
    assert ws.receive_json()['type'] == 'state'
    assert ws.receive_json()['status'] == 'connected'


def test_session_grants_are_isolated_and_absent_from_snapshots(client):
    a, ah = new_session(client)
    b, bh = new_session(client)
    url = '/api/sessions/' + a['session_id']
    assert client.get(url).status_code == 401
    assert client.get(url, headers=bh).status_code == 401
    data = client.get(url, headers=ah).json()
    assert 'access_token' not in data
    assert a['access_token'] not in str(data)
    assert client.get('/api/sessions', headers=ah).status_code in (404, 405)


def test_complete_pH_flow_and_presentation_gate_over_http(client):
    session, headers = new_session(client)
    url = '/api/sessions/' + session['session_id']
    def post(path, body):
        return client.post(url + '/' + path, json=body, headers=headers)
    assert post('request', {'text': 'Test the prepared vinegar sample.'}).status_code == 200
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        snap = client.get(url, headers=headers).json()
        if snap['pending']:
            break
        time.sleep(.01)
    pending = snap['pending']
    assert pending
    assert not snap['prediction']
    frame = snap['scene_images'][0]
    assert 'path' not in frame
    assert client.get(frame['artifact_url']).status_code == 401
    image = client.get(frame['artifact_url'], headers=headers)
    assert image.status_code == 200 and image.content.startswith(b'\x89PNG')
    _, wrong_headers = new_session(client)
    assert client.get(frame['artifact_url'], headers=wrong_headers).status_code == 401
    binding = {k: pending[k] for k in ('request_id', 'proposal_version')}
    assert post('confirm', binding).status_code == 409
    assert post('present', {**binding, 'channel': 'audio'}).status_code == 400
    assert post('present', {**binding, 'channel': 'text'}).status_code == 200
    assert post('confirm', binding).status_code == 200
    assert post('confirm', binding).status_code == 409
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        snap = client.get(url, headers=headers).json()
        if snap['observations']:
            break
        time.sleep(.02)
    assert snap['observations']
    assert snap['observations'][-1]['provenance'] == 'SYNTHETIC'
    assert snap['observations'][-1]['features']['color'] == 'pink'
    assert post('reflection', {'text': 'The reference pink color supports acidic.'}).status_code == 200
    assert post('prepare', {}).status_code == 200


def test_socket_hello_heartbeat_voice_failure_and_text_fallback(client):
    session, headers = new_session(client)
    url = '/api/sessions/' + session['session_id']
    with client.websocket_connect(url + '/live') as ws:
        hello(ws, session)
        ws.send_json({'type': 'ping', 'seq': 7})
        assert ws.receive_json() == {'type': 'pong', 'seq': 7}
        ws.send_json({'type': 'start_voice'})
        assert ws.receive_json()['status'] == 'unavailable'
        ws.send_json({'type': 'text', 'text': 'Choose vinegar', 'client_request_id': 'a'})
        while True:
            message = ws.receive_json()
            if message['type'] == 'state' and message['state']['trial']['condition_id'] == 'vinegar':
                break
        ws.send_json({'type': 'stop'})
        while ws.receive_json()['type'] != 'state':
            pass


def test_connection_replacement_does_not_let_old_cleanup_disconnect_new_owner(client):
    session, headers = new_session(client)
    url = '/api/sessions/' + session['session_id']
    with client.websocket_connect(url + '/live') as first:
        hello(first, session, 'one')
        with client.websocket_connect(url + '/live') as second:
            hello(second, session, 'two')
            second.send_json({'type': 'ping', 'seq': 2})
            assert second.receive_json()['type'] == 'pong'
            assert client.get(url, headers=headers).json()['connected'] is True


def test_remote_creation_requires_pairing_and_cross_origin_mutations_fail(client, monkeypatch):
    monkeypatch.setenv('OPENARMS_ALLOWED_HOSTS', 'demo.example')
    assert client.post('/api/sessions', headers={'Host': 'demo.example'}).status_code == 403
    monkeypatch.setenv('OPENARMS_DEMO_TOKEN', 'a-test-pairing-code')
    assert client.post('/api/sessions', headers={'Host': 'demo.example'}).status_code == 401
    assert client.post('/api/sessions', headers={'Host': 'demo.example', 'Authorization': 'Bearer a-test-pairing-code'}).status_code == 200
    assert client.post('/api/sessions', headers={'Origin': 'https://unrelated.example'}).status_code == 403
