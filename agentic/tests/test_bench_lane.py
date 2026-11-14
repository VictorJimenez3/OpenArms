"""Real-bench lane: the camera decides where the object is, the plan is simulated, then the arm runs."""
import asyncio
from pathlib import Path

import cv2
import numpy as np
import pytest

from agentic.openarms_lab.bench_lane import BenchError, BenchLane
from firmware.openarms_camera.stations import mark_station
from firmware.openarms_executor.motion import FakeRobot
from firmware.openarms_executor.poses import load_poses

ROOT = Path(__file__).resolve().parents[2]
POSES = ROOT/'firmware/openarms_executor/poses.json'
SPOT = {'A': (150, 250), 'B': (450, 250), 'air': (300, 80)}


def picture(at):
    image = np.full((480, 640, 3), 40, np.uint8)
    if at:
        cv2.circle(image, SPOT[at], 30, (20, 120, 240), -1)
    return image


REGIONS = mark_station(mark_station({}, 'A', picture('A')), 'B', picture('B'))


class Webcam:
    """Shows a scripted sequence of scenes; the last one repeats."""
    def __init__(self, *scenes):
        self.scenes, self.reads = list(scenes), 0
    def read(self):
        self.reads += 1
        scene = self.scenes.pop(0) if len(self.scenes) > 1 else self.scenes[0]
        if scene == 'broken':
            raise OSError('camera 1 could not be opened')
        return picture(scene)


class Preview:
    def __init__(self, status='ready'):
        self.status, self.calls = status, []
    def __call__(self, backend, request):
        self.calls.append(request)
        sim = request['sim']
        return {'status': self.status, 'provenance': 'SIMULATED', 'video': '/api/previews/script-0123456789abcdef.mp4',
                'warnings': [], 'blocks': ['The gripper closed on nothing.'] if self.status == 'blocked' else [],
                'objects': [{'name': sim['object'], 'at': sim['expect_at']}]}
    def video_path(self, name):
        return None


class Connected:
    """Not a FakeRobot by type, so the lane treats it as the real arm."""
    def __init__(self):
        self._inner = FakeRobot(load_poses(POSES)['poses']['HOME'])
    def __getattr__(self, name):
        return getattr(self._inner, name)


def lane(tmp_path, *, camera=None, real=False, answers=None, preview=None, object_at='A'):
    asked = []
    def ask(q):
        asked.append(q)
        return (answers or ['y']).pop(0) if answers is None or answers else 'n'
    made = BenchLane(tmp_path, camera=camera, regions=REGIONS if camera else None, poses_path=POSES, seconds=.02,
                     object_at=object_at, previewer=preview or Preview(), ask=ask, robot=Connected() if real else None)
    made.asked = asked
    return made


@pytest.mark.asyncio
async def test_look_simulate_execute_and_camera_confirms(tmp_path):
    cam = Webcam('A', 'A', 'B')            # at Look now, just before running, after running
    bench = lane(tmp_path, camera=cam, real=True)
    s = await bench.request('move the mandarin from A to B')      # no look yet: nothing is planned, no picture is taken
    assert s['pending'] is None and 'Press Look now first' in s['log'][-1]['text'] and cam.reads == 0
    await bench.look_all()
    s = await bench.request('move the mandarin from A to B')
    assert s['camera']['at'] == 'A' and s['camera']['frame'].startswith('/api/bench/frame/frame-')
    assert s['pending']['summary'] == 'Move the mandarin from A to B' and s['pending']['preview']['status'] == 'ready'
    assert s['pending']['preview']['video'] == '/api/bench/preview/script-0123456789abcdef.mp4'
    assert bench.previewer.calls[0]['sim']['object_at'] == 'A' and bench.previewer.calls[0]['sim']['expect_at'] == 'B'
    assert bench.asked == [] and 'Nothing real has moved' in s['log'][-2]['text']
    s = await bench.request('execute')
    assert len(bench.asked) == 1 and 'Move the mandarin from A to B' in bench.asked[0]
    assert s['last_result']['provenance'] == 'REAL' and 'camera sees the object at B, as planned' in s['last_result']['text']
    assert s['object_at'] == 'B' and s['pending'] is None and s['armed'] and s['busy'] is None
    assert bench.file('frame', s['last_result']['frame'].rsplit('/', 1)[1]).is_file()
    assert bench.file('frame', '../access.sqlite3') is None


@pytest.mark.asyncio
async def test_the_camera_not_the_apps_memory_decides_where_the_object_is(tmp_path):
    bench = lane(tmp_path, camera=Webcam('B'), real=True, object_at='A')   # the app assumed A; the camera sees B
    await bench.look_all()
    s = await bench.request('move the mandarin from A to B')
    assert s['pending'] is None and s['object_at'] == 'B'
    assert 'nothing at A' in s['log'][-1]['text'] and 'camera sees the object at B' in s['log'][-2]['text']
    s = await bench.request('move the mandarin from B to A')
    assert s['pending']['preview']['status'] == 'ready'


@pytest.mark.asyncio
async def test_a_mismatch_after_the_run_is_reported_not_assumed(tmp_path):
    bench = lane(tmp_path, camera=Webcam('A', 'A', 'A'), real=True)        # the arm ran, but the object never left A
    await bench.look_all()
    await bench.request('move the mandarin from A to B')
    s = await bench.execute(bench.pending['request_id'])
    assert s['last_result']['provenance'] == 'REAL' and 'but the plan put the object at B' in s['last_result']['text']
    assert s['object_at'] == 'A'
    bench = lane(tmp_path/'two', camera=Webcam('A', 'A', None), real=True)  # the object is hidden afterwards
    await bench.look_all()
    await bench.request('move the mandarin from A to B')
    s = await bench.execute(bench.pending['request_id'])
    assert 'does not see the object' in s['last_result']['text'] and s['object_at'] is None


@pytest.mark.asyncio
async def test_nothing_runs_if_the_bench_changed_or_the_operator_says_no(tmp_path):
    bench = lane(tmp_path, camera=Webcam('A', 'air'), real=True)           # someone lifted the object during the preview
    await bench.look_all()
    await bench.request('move the mandarin from A to B')
    s = await bench.execute(bench.pending['request_id'])
    assert s['last_result'] is None and s['pending'] is None and 'Not started' in s['log'][-1]['text'] and bench.asked == []
    bench = lane(tmp_path/'two', camera=Webcam('A'), real=True, answers=['n'])
    await bench.look_all()
    await bench.request('move the mandarin from A to B')
    s = await bench.execute(bench.pending['request_id'])
    assert s['last_result'] is None and 'declined' in s['log'][-1]['text'] and s['object_at'] == 'A' and s['armed']


@pytest.mark.asyncio
async def test_a_blocked_or_stale_plan_cannot_execute(tmp_path):
    bench = lane(tmp_path, preview=Preview('blocked'))
    s = await bench.request('move the mandarin from A to B')
    assert 'will not be executed' in s['log'][-1]['text']
    with pytest.raises(BenchError, match='has not cleared'):
        await bench.execute(s['pending']['request_id'])
    with pytest.raises(BenchError, match='no longer current'):
        await bench.execute('something-else')
    s = await bench.request('execute')
    assert s['last_result'] is None


@pytest.mark.asyncio
async def test_stand_in_arm_without_camera_tracks_and_labels_honestly(tmp_path):
    bench = lane(tmp_path)
    assert bench.state()['arm'] == 'stand-in' and bench.state()['camera']['status'] == 'no_camera'
    await bench.request('move the mandarin from A to B')
    s = await bench.request('execute')
    assert s['last_result']['provenance'] == 'MOCK' and 'nothing real moved' in s['last_result']['text'] and s['object_at'] == 'B'
    assert bench.asked == []
    s = await bench.request('again')                                       # A is empty now
    assert s['pending'] is None and 'nothing at A' in s['log'][-1]['text']
    s = await bench.request('go to A and then B and then home after that')
    assert s['pending']['summary'] == 'Go to ABOVE_A; then go to ABOVE_B; then return to HOME'
    s = await bench.cancel()
    assert s['pending'] is None
    s = await bench.request('sing a song')
    assert 'did not understand' in s['log'][-1]['text']


@pytest.mark.asyncio
async def test_camera_trouble_is_said_plainly(tmp_path):
    bench = lane(tmp_path, camera=Webcam('broken'), real=True)
    await bench.look_all()
    s = await bench.request('move the mandarin from A to B')
    assert s['camera']['status'] == 'error' and 'could not be opened' in s['camera']['text']
    assert s['pending'] is not None           # the app falls back to its own tracking for planning
    bench = BenchLane(tmp_path/'two', camera=Webcam('A'), regions=None, regions_path=tmp_path/'none.json', poses_path=POSES,
                      seconds=.02, previewer=Preview())
    assert (await bench.look())['status'] == 'not_marked'


@pytest.mark.asyncio
async def test_stop_disarms_and_routes_are_local_only(tmp_path):
    from fastapi.testclient import TestClient
    from agentic.openarms_lab.app import create_app
    from agentic.openarms_lab.runtime import Lab
    bench = lane(tmp_path/'bench')
    with TestClient(create_app(Lab(tmp_path/'data'), access_path=tmp_path/'access.sqlite3', bench=bench)) as client:
        assert client.get('/api/bench').json()['enabled'] is True
        s = client.post('/api/bench/request', json={'text': 'move the mandarin from A to B'}).json()
        assert s['pending']['preview']['status'] == 'ready'
        assert client.post('/api/bench/execute', json={'request_id': 'nope'}).status_code == 409
        assert client.get('/api/bench/frame/..%2Fsecret').status_code == 404
        assert client.post('/api/bench/stop').json()['pending'] is None
    with TestClient(create_app(Lab(tmp_path/'data2'), access_path=tmp_path/'access2.sqlite3'), client=('10.0.0.5', 5000)) as remote:
        assert remote.get('/api/bench').json() == {'enabled': False}
    with TestClient(create_app(Lab(tmp_path/'data3'), access_path=tmp_path/'access3.sqlite3', bench=bench), client=('10.0.0.5', 5000)) as remote:
        assert remote.get('/api/bench').status_code == 403
        assert remote.post('/api/bench/request', json={'text': 'move the mandarin from A to B'}).status_code == 403


# ---- pours: overhead picture -> rebuilt simulation (simulation only) -------------------------------

class ToolCall:
    def __init__(self, name, input):
        self.type, self.name, self.input, self.id = 'tool_use', name, input, 'tu_1'


class PourClaude:
    def __init__(self, *replies):
        self.replies, self.calls, self.messages = list(replies), [], self
    def create(self, **kw):
        self.calls.append(kw)
        name, inp = self.replies.pop(0)
        return type('Resp', (), {'content': [ToolCall(name, inp)], 'usage': None})()


def pour_lane(tmp_path, monkeypatch, *replies, seen=None, sim=None):
    bench = lane(tmp_path)
    bench.pour_client = PourClaude(*replies) if replies else None
    if not replies:
        monkeypatch.setattr('agentic.openarms_lab.bench_lane.ClaudePlanner.available', staticmethod(lambda: False))
    seen = seen or {'positions': {'beaker': (4.0, 7.0), 'dish': (22.0, 4.0)}, 'arm_cm': (17.0, 35.5), 'frame': '/api/bench/frame/frame-0123456789abcdef.jpg',
                    'from_camera': ['beaker', 'dish'], 'notes': [], 'source': 'overhead camera 1'}
    bench.simulated = []
    monkeypatch.setattr(bench, '_overhead_blocking', lambda: seen)
    if sim is not False:
        def fake(positions, source, into):
            bench.simulated.append((positions, source, into))
            return sim or {'status': 'ready', 'provenance': 'SIMULATED', 'video': '/api/bench/preview/0123456789abcdef.mp4', 'blocks': [],
                           'warnings': [], 'predicted': {'station': 'C', 'color': 'red', 'observations': ['fizzing']}}
        monkeypatch.setattr(bench, '_simulate_pour_blocking', fake)
    return bench


@pytest.mark.asyncio
async def test_pour_looks_from_above_lets_claude_decide_and_rebuilds_the_simulation(tmp_path, monkeypatch):
    bench = pour_lane(tmp_path, monkeypatch, ('simulate_pour', {'source': 'a', 'into': 'C', 'why': 'This is the beaker, that is the dish.'}))
    s = await bench.request('pour this into that')
    assert bench.simulated == [({'beaker': (4.0, 7.0), 'dish': (22.0, 4.0)}, 'A', 'C')]
    assert s['pending']['summary'] == 'Pour the beaker (A) into the dish (C)' and s['pending']['planner'] == 'claude'
    assert s['pending']['preview']['status'] == 'ready' and s['pending']['executable'] is False
    assert s['camera']['status'] == 'overhead' and 'the beaker at (4.0, 7.0) cm' in s['camera']['text']
    said = [m['text'] for m in s['log'] if m['role'] == 'assistant']
    assert 'This is the beaker, that is the dish.' in said and 'turns red with fizzing' in said[-1] and 'simulation only' in said[-1]
    sent = bench.pour_client.calls[0]
    assert 'station A: the beaker, a source, at (4.0, 7.0) (seen by the camera)' in sent['system'] and sent['messages'][0]['content'] == 'pour this into that'
    # A pour cannot be run on the arm from here, by button or by word.
    with pytest.raises(BenchError, match='Simulation only'):
        await bench.execute(s['pending']['request_id'])
    s = await bench.request('execute')
    assert 'Simulation only' in s['log'][-1]['text'] and s['last_result'] is None and bench.asked == []


@pytest.mark.asyncio
async def test_pour_reports_a_blocked_layout_and_missing_camera_readings(tmp_path, monkeypatch):
    seen = {'positions': {'beaker': (4.8, 4.1), 'dish': (5.6, 12.8)}, 'arm_cm': (17.0, 35.5), 'frame': None, 'from_camera': ['dish'],
            'notes': ['The camera did not find the beaker; its last known position is used.']}
    blocked = {'status': 'blocked', 'provenance': 'SIMULATED', 'video': None, 'blocks': ['The wrist would knock the container at C.'], 'warnings': [], 'predicted': None}
    bench = pour_lane(tmp_path, monkeypatch, ('simulate_pour', {'source': 'A', 'into': 'C', 'why': ''}), seen=seen, sim=blocked)
    s = await bench.request('pour the beaker into the container')
    assert s['pending']['preview']['status'] == 'blocked' and 'knock the container' in s['log'][-1]['text'] and 'side by side' in s['log'][-1]['text']
    assert 'did not find the beaker' in s['camera']['text']
    assert 'last known position, not seen this time' in bench.pour_client.calls[0]['system']


@pytest.mark.asyncio
async def test_pour_can_be_declined_or_corrected_by_the_bench(tmp_path, monkeypatch):
    bench = pour_lane(tmp_path, monkeypatch, ('cannot_do', {'reason': 'There is nothing called milk on the bench.'}),
                      ('simulate_pour', {'source': 'C', 'into': 'A', 'why': ''}))
    s = await bench.request('pour the milk into the cup')
    assert s['pending'] is None and 'nothing called milk' in s['log'][-1]['text']
    s = await bench.request('pour the container into the beaker')        # the receiver cannot be tipped
    assert s['pending'] is None and 'Only A can be poured, into C' in s['log'][-1]['text'] and bench.simulated == []


@pytest.mark.asyncio
async def test_pour_without_claude_uses_the_one_pour_the_bench_allows_and_runs_the_real_simulation(tmp_path, monkeypatch):
    pytest.importorskip('mujoco')
    pytest.importorskip('openarms_sim')
    bench = pour_lane(tmp_path, monkeypatch, sim=False)                  # no model, the real simulation
    s = await bench.request('pour it in')
    p = s['pending']
    assert p['planner'] == 'bench layout' and p['preview']['status'] == 'ready', p['preview']
    assert p['preview']['predicted']['color'] == 'red' and p['preview']['video'].startswith('/api/bench/preview/')
    assert bench.file('preview', p['preview']['video'].rsplit('/', 1)[1]).is_file()
    assert not (ROOT / 'simulation/config/setups/demo/bench.yaml').read_text().count('demo_live')
    # mandarin commands still go the other way
    s = await bench.request('move the mandarin from A to B')
    assert s['pending']['skill_id'] != 'simulated_pour.v1'


@pytest.mark.asyncio
async def test_side_camera_is_shown_but_never_measured_from(tmp_path, monkeypatch):
    side = Webcam('air')                                   # whatever it shows must not change what the app believes
    bench = BenchLane(tmp_path, poses_path=POSES, seconds=.02, previewer=Preview(), side_camera=side)
    assert bench.state()['side'] == {'frame': None, 'text': '', 'time': None}
    await bench.look_all()
    s = await bench.request('move the mandarin from A to B')
    assert s['side']['frame'].startswith('/api/bench/frame/frame-') and bench.file('frame', s['side']['frame'].rsplit('/', 1)[1]).is_file()
    assert s['object_at'] == 'A' and s['camera']['status'] == 'no_camera' and side.reads == 1
    assert lane(tmp_path/'none').state()['side']['text'] is None   # no side camera configured
    side.scenes = ['broken']
    assert 'gave no picture' in (await bench.look_side())['text']


@pytest.mark.asyncio
async def test_look_now_reads_the_top_down_view_and_the_panel_says_what_it_will_use(tmp_path, monkeypatch):
    bench = BenchLane(tmp_path, poses_path=POSES, seconds=.02, previewer=Preview(), overhead_photo='outputs/camera/live_demo_2.jpg')
    first = bench.state()['camera']
    assert first['status'] == 'overhead_ready' and 'live_demo_2.jpg' in first['text'] and 'No camera' not in first['text']
    seen = {'positions': {'beaker': (4.8, 3.2), 'dish': (5.5, 13.0)}, 'arm_cm': (17.0, 35.5), 'frame': '/api/bench/frame/frame-0123456789abcdef.jpg',
            'from_camera': ['beaker', 'dish'], 'notes': [], 'source': 'the saved photo live_demo_2.jpg'}
    monkeypatch.setattr(bench, '_overhead_blocking', lambda: seen)
    s = await bench.look_all()
    assert s['camera']['status'] == 'overhead' and s['camera']['frame'] == seen['frame'] and 'the dish at (5.5, 13.0) cm' in s['camera']['text']
    assert s['pending'] is None and lane(tmp_path/'plain').state()['camera']['status'] == 'no_camera'


def test_a_live_top_down_picture_without_readable_rulers_is_shown_and_says_so(tmp_path):
    class Dark:
        def read(self):
            return np.zeros((240, 320, 3), np.uint8)
    bench = BenchLane(tmp_path, poses_path=POSES, seconds=.02, previewer=Preview(), overhead_index=1)
    import firmware.openarms_camera.stations as stations
    real = stations.Camera
    stations.Camera = lambda index: Dark()
    try:
        seen = bench._overhead_blocking()
    finally:
        stations.Camera = real
    assert seen['from_camera'] == [] and seen['frame'] and bench.file('frame', seen['frame'].rsplit('/', 1)[1]).is_file()
    assert 'NOT CALIBRATED' in seen['notes'][0] and 'almost black' in seen['notes'][0] and seen['source'] == 'overhead camera 1'
    assert seen['positions']['beaker'] and seen['positions']['dish']      # last known positions, clearly labelled as such


@pytest.mark.asyncio
async def test_a_pour_uses_the_last_look_now_and_takes_no_new_picture(tmp_path, monkeypatch):
    bench = pour_lane(tmp_path, monkeypatch)
    bench.overhead_index = 1
    looks = []
    first = {'positions': {'beaker': (6.0, 9.0), 'dish': (20.0, 5.0)}, 'arm_cm': (17.0, 35.5), 'frame': None,
             'from_camera': ['beaker', 'dish'], 'notes': [], 'source': 'overhead camera 1'}
    monkeypatch.setattr(bench, '_overhead_blocking', lambda: looks.append(1) or dict(first))
    s = await bench.request('pour it in')
    assert s['pending'] is None and 'Press Look now first' in s['log'][-1]['text'] and looks == []
    await bench.look_all()
    first['positions'] = {'beaker': (1.0, 1.0), 'dish': (2.0, 2.0)}      # the bench changes after the look
    s = await bench.request('pour it in')
    assert looks == [1] and bench.simulated[0][0] == {'beaker': (6.0, 9.0), 'dish': (20.0, 5.0)}
    assert any('Using the look from' in m['text'] for m in s['log'])
