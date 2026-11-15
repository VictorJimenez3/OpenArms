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
async def test_claude_reads_the_latest_harness_loop_results_on_every_pour(tmp_path, monkeypatch):
    notes = tmp_path / 'harness-loop-progress.md'
    notes.write_text('# Loop\nRound 7: pours tipped 95 degrees landed in the dish.')
    reply = ('simulate_pour', {'source': 'A', 'into': 'C', 'why': ''})
    bench = pour_lane(tmp_path, monkeypatch, reply, reply, reply)
    bench.harness_notes = notes
    s = await bench.request('pour the beaker into the dish')
    sent = bench.pour_client.calls[0]['system']
    assert '<harness_loop_results>' in sent and 'Round 7: pours tipped 95 degrees' in sent and 'the camera wins' in sent
    assert s['pending']['harness_notes']['sha256'] and any('read the harness loop results' in m['text'] for m in s['log'])
    notes.write_text('Round 8: lower the grasp by 1 cm.' + 'x' * 20000)  # the loop writes on; the next decision sees it, trimmed
    await bench.request('pour the beaker into the dish')
    sent = bench.pour_client.calls[1]['system']
    assert 'Round 8' in sent and 'Round 7' not in sent and 'middle of the file left out' in sent and len(sent) < 20000
    notes.unlink()
    s = await bench.request('pour the beaker into the dish')
    assert '<harness_loop_results>' not in bench.pour_client.calls[2]['system']
    assert any('were not read' in m['text'] for m in s['log'])


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


# ---- pours on the arm: replaying a pour recorded on the real arm ------------------------------------

TAKE = {'poses': {name: {'shoulder_pan.pos': pan, 'shoulder_lift.pos': lift, 'elbow_flex.pos': 60.0, 'wrist_flex.pos': -90.0, 'wrist_roll.pos': roll}
                  for name, (pan, lift, roll) in {'HOME': (-16, -89, -90), 'ABOVE_A': (5, 40, -90), 'GRASP_A': (5, 55, -90),
                                                  'ABOVE_C': (-17, 38, -90), 'TIP_C': (-17, 32, -1)}.items()},
        'gripper': {'open': 93.0, 'cup': 18.0}}


def replay_lane(tmp_path, monkeypatch, *, beaker=(22.0, 7.9), found=('beaker', 'dish'), real=False, answers=None):
    import json
    take = tmp_path/'take.json'
    take.write_text(json.dumps(TAKE))
    (tmp_path/'take.layout.json').write_text(json.dumps({'beaker': [22.3, 7.6], 'dish': [5.8, 7.6]}))
    asked = []
    def ask(q):
        asked.append(q)
        return answers.pop(0) if answers else 'n'
    robot = None
    if real:
        robot = Connected()
        robot._inner.pos.update(TAKE['poses']['HOME'])
    bench = BenchLane(tmp_path/'bench', poses_path=POSES, seconds=.02, previewer=Preview(), ask=ask, robot=robot, pour_poses=take)
    bench.asked = asked
    monkeypatch.setattr('agentic.openarms_lab.bench_lane.ClaudePlanner.available', staticmethod(lambda: False))
    bench.seen = {'positions': {'beaker': beaker, 'dish': (5.8, 7.6)}, 'arm_cm': (17.0, 36.0), 'frame': None,
                  'from_camera': list(found), 'notes': [], 'source': 'overhead camera 1'}
    bench.overhead_index = 1
    monkeypatch.setattr(bench, '_overhead_blocking', lambda: dict(bench.seen))
    monkeypatch.setattr(bench, '_simulate_pour_blocking', lambda *a: {'status': 'ready', 'provenance': 'SIMULATED', 'video': None, 'blocks': [], 'warnings': []})
    return bench


@pytest.mark.asyncio
async def test_a_recorded_pour_is_replayed_when_the_camera_sees_the_containers_where_it_was_recorded(tmp_path, monkeypatch):
    bench = replay_lane(tmp_path, monkeypatch)
    await bench.look_all()
    s = await bench.request('pour the beaker into the dish')
    assert s['pending']['executable'] is True and s['pending']['camera_confirmed'] == ['beaker', 'dish']
    assert 'replays the recorded joint positions, not the simulated ones' in s['log'][-1]['text']
    s = await bench.request('execute')
    assert s['last_result']['status'] == 'completed' and s['last_result']['provenance'] == 'MOCK' and s['pending'] is None and s['armed']
    receipt = next((tmp_path/'bench/pour-receipts').iterdir()).read_text()
    assert '"status": "executed"' in receipt and '"steps_done": ["pick", "pour", "return_cup", "home"]' in receipt


@pytest.mark.asyncio
async def test_a_blocked_simulation_only_warns_when_the_recording_is_replayed(tmp_path, monkeypatch):
    bench = replay_lane(tmp_path, monkeypatch)
    monkeypatch.setattr(bench, '_simulate_pour_blocking', lambda *a: {'status': 'blocked', 'provenance': 'SIMULATED', 'video': None,
                                                                       'blocks': ['The gripper would hit the table.'], 'warnings': []})
    await bench.look_all()
    s = await bench.request('pour the beaker into the dish')
    assert s['pending']['preview']['status'] == 'blocked' and s['pending']['sim_block_overridden'] is True
    assert 'WARNING (not blocking)' in s['log'][-1]['text'] and 'hit the table' in s['log'][-1]['text']
    s = await bench.request('execute')
    assert s['last_result']['status'] == 'completed' and s['pending'] is None


@pytest.mark.asyncio
async def test_a_recorded_pour_is_not_started_when_a_container_moves_after_the_look(tmp_path, monkeypatch):
    bench = replay_lane(tmp_path, monkeypatch)
    bench._shift = fake_shift([])
    # In place at the look, moved while the preview played: the look just before starting catches it.
    bench.seen['positions']['beaker'] = (22.3, 7.6)
    await bench.look_all()
    s = await bench.request('pour it in')
    assert s['pending']['executable'] is True
    bench.seen['positions']['beaker'] = (25.0, 7.6)
    s = await bench.request('execute')
    assert s['last_result'] is None and s['pending'] is None and 'Not started: the bench changed since the look' in s['log'][-1]['text']


def fake_shift(calls, *, error_mm=1.0, pan_per_cm=2.0):
    """Stands in for openarms_sim.shift: turns the pan by pan_per_cm for each cm of x."""
    def shift(poses, shift_cm, limits=None):
        calls.append(shift_cm)
        out = {n: {**p, 'shoulder_pan.pos': p['shoulder_pan.pos'] + pan_per_cm * shift_cm.get(n, (0,))[0]} for n, p in poses.items()}
        return {'poses': out, 'error_mm': {n: error_mm for n in poses}, 'turn_deg': {n: 0.5 for n in poses},
                'joint_change_deg': {n: {'shoulder_pan': pan_per_cm * shift_cm.get(n, (0,))[0]} for n in poses},
                'grasp_cm': {n: [20.0, 8.0, 3.0] for n in poses}}
    return shift


@pytest.mark.asyncio
async def test_a_container_a_little_off_its_recorded_spot_gets_a_corrected_pour(tmp_path, monkeypatch):
    calls = []
    bench = replay_lane(tmp_path, monkeypatch, beaker=(20.2, 8.5))          # 2.3 cm off (22.3, 7.6)
    bench._shift = fake_shift(calls)
    await bench.look_all()
    s = await bench.request('pour the beaker into the dish')
    assert s['pending']['executable'] is True and s['pending']['shift'] == {'beaker': (-2.1, 0.9)}
    assert calls == [{'ABOVE_A': (-2.1, 0.9), 'GRASP_A': (-2.1, 0.9)}]       # the dish stands where it was: its poses are kept
    assert s['pending']['pour_poses']['poses']['GRASP_A']['shoulder_pan.pos'] == pytest.approx(5 - 4.2)
    assert s['pending']['pour_poses']['poses']['TIP_C'] == TAKE['poses']['TIP_C']
    assert 'the recording is corrected: the beaker by (-2.1, +0.9) cm' in s['log'][-1]['text']
    s = await bench.request('execute')
    assert s['last_result']['status'] == 'completed'
    receipt = next((tmp_path/'bench/pour-receipts').iterdir()).read_text()
    assert '"corrected_poses"' in receipt and '"moved": "the beaker by (-2.1, +0.9) cm"' in receipt


@pytest.mark.asyncio
async def test_a_correction_the_model_cannot_fully_reach_only_warns_but_the_calibrated_range_still_refuses(tmp_path, monkeypatch):
    bench = replay_lane(tmp_path, monkeypatch, beaker=(16.0, 10.0))         # 6.7 cm off
    bench._shift = fake_shift([], error_mm=12.0)
    await bench.look_all()
    s = await bench.request('pour it in')
    assert s['pending']['executable'] is True
    assert 'WARNING (not blocking)' in s['log'][-1]['text'] and '12 mm short' in s['log'][-1]['text'] and '6.7 cm off' in s['log'][-1]['text']
    bench._shift = fake_shift([], pan_per_cm=40.0)                          # the pan would leave its calibrated range
    s = await bench.request('pour it in')
    assert s['pending']['executable'] is False and "leaves the arm's calibrated range" in s['pending']['why_not_executable']
    bench.seen['positions']['beaker'] = (20.2, 8.5)
    bench._shift = fake_shift([])
    await bench.look_all()
    s = await bench.request('pour it in')
    assert s['pending']['executable'] is True
    bench.seen['positions']['beaker'] = (21.8, 8.5)                         # moved 1.6 cm after the correction was made
    s = await bench.request('execute')
    assert s['last_result'] is None and 'the beaker moved 1.6 cm from where the pour was set up for' in s['log'][-1]['text']


@pytest.mark.asyncio
async def test_the_real_arm_pours_only_after_the_operator_agrees_and_from_the_recordings_home(tmp_path, monkeypatch):
    bench = replay_lane(tmp_path, monkeypatch, found=('dish',), real=True, answers=['n'])
    await bench.look_all()
    await bench.request('pour it in')
    s = await bench.request('execute')
    assert 'did NOT find the beaker' in bench.asked[0] and 'operator declined' in s['log'][-1]['text']
    assert s['last_result'] is None and bench._robot._inner.sent == []
    bench._robot._inner.pos['shoulder_lift.pos'] = -70.0                # not at the recording's HOME, and the operator says no
    await bench.request('pour it in')
    s = await bench.request('execute')
    assert "not at the recording's HOME (off: shoulder_lift +19°) and the operator did not move it back" in s['log'][-1]['text']
    assert 'Move it slowly back to HOME' in bench.asked[1] and bench._robot._inner.sent == []


@pytest.mark.asyncio
async def test_the_arm_is_brought_back_to_home_first_when_the_operator_agrees(tmp_path, monkeypatch):
    monkeypatch.setattr('agentic.openarms_lab.bench_lane.HOMING_MIN_S', .05)
    monkeypatch.setattr('agentic.openarms_lab.bench_lane.HOMING_DEG_PER_S', 1e4)
    bench = replay_lane(tmp_path, monkeypatch, real=True, answers=['y', 'n'])  # yes to going home, no to the pour itself
    bench._robot._inner.pos['shoulder_lift.pos'] = -70.0
    await bench.look_all()
    await bench.request('pour it in')
    s = await bench.request('execute')
    sent = bench._robot._inner.sent
    assert sent and sent[-1]['shoulder_lift.pos'] == TAKE['poses']['HOME']['shoulder_lift.pos'] and 'gripper.pos' not in sent[-1]
    assert bench._robot._inner.pos['shoulder_lift.pos'] == TAKE['poses']['HOME']['shoulder_lift.pos']
    assert any('Moving the arm back to the recording' in m['text'] for m in s['log'])
    assert 'Arm at HOME, path clear' in bench.asked[1] and 'operator declined this pour' in s['log'][-1]['text']


@pytest.mark.asyncio
async def test_without_a_usable_recording_a_pour_stays_simulation_only(tmp_path, monkeypatch):
    bench = replay_lane(tmp_path, monkeypatch)
    (tmp_path/'take.layout.json').unlink()
    bench.taught_pour = None
    bench._load_taught_pour(tmp_path/'take.json')
    await bench.look_all()
    s = await bench.request('pour it in')
    assert s['pending']['executable'] is False and 'take.json cannot be used' in s['pending']['why_not_executable']


@pytest.mark.asyncio
async def test_page_only_confirmation_starts_the_real_arm_without_a_terminal_question(tmp_path):
    asked = []
    bench = BenchLane(tmp_path, poses_path=POSES, seconds=.02, previewer=Preview(), ask=lambda q: asked.append(q) or 'n',
                      robot=Connected(), terminal_confirm=False)
    await bench.request('move the mandarin from A to B')
    s = await bench.request('execute')
    assert asked == [] and s['last_result']['status'] == 'completed' and s['last_result']['arm'] == 'real'
    assert not any('terminal' in m['text'] for m in s['log'])


def ruler_lane(tmp_path, monkeypatch, *looks, real=False, answers=None, reach=None, places=None):
    """A ruler bench whose top-down camera reports the mandarin at each of `looks` in turn (the last repeats)."""
    asked, looks = [], list(looks)
    def ask(q):
        asked.append(q)
        return (answers or ['y']).pop(0)
    bench = BenchLane(tmp_path, poses_path=POSES, seconds=.02, previewer=Preview(), ask=ask, robot=Connected() if real else None,
                      overhead_index=1, ruler_mode=True, reach=reach, places=places)
    def overhead():
        at = looks.pop(0) if len(looks) > 1 else looks[0]
        return {'positions': {'beaker': None, 'dish': None}, 'arm_cm': (17.0, 36.0), 'frame': '/api/bench/frame/frame-0123456789abcdef.jpg',
                'from_camera': [], 'notes': [], 'source': 'overhead camera 1', 'mandarin': at}
    monkeypatch.setattr(bench, '_overhead_blocking', overhead)
    monkeypatch.setattr('agentic.openarms_lab.bench_lane.ClaudePlanner.available', staticmethod(lambda: False))
    bench.asked = asked
    return bench


@pytest.mark.asyncio
async def test_on_a_ruler_bench_the_mandarin_is_picked_up_where_the_camera_sees_it(tmp_path, monkeypatch):
    bench = ruler_lane(tmp_path, monkeypatch, (20.5, 10.5), real=True)   # 3 cm from A's nominal (22, 8)
    assert bench.state()['mode'] == 'rulers' and 'Look now' in bench.state()['log'][0]['text']
    s = await bench.request('move the mandarin from A to B')
    assert s['pending'] is None and 'Press Look now first' in s['log'][-1]['text']
    s = await bench.look_all()
    assert s['object_at'] == 'A' and s['object_cm'] == (20.5, 10.5) and '(20.5, 10.5)' in s['camera']['text']
    s = await bench.request('move the mandarin from A to B')
    plan = s['pending']
    assert plan['preview']['status'] == 'ready' and plan['ruler']['mandarin'] == [20.5, 10.5]
    assert plan['ruler']['places'] == {'A': [20.5, 10.5], 'B': [8.0, 8.0]}   # A is where it was seen, not A's nominal spot
    assert any('not been recorded on the real arm' in m['text'] for m in s['log'])
    # The simulation and the arm get the same solved poses, and none of the taught station poses.
    taught, solved = load_poses(POSES)['poses'], bench.arm.runner.poses['poses']
    assert solved['HOME'] == taught['HOME'] and solved['GRASP_A'] != taught['GRASP_A']
    sim = bench.previewer.calls[-1]['sim']
    assert sim['marks'] == {n: solved[f'GRASP_{n}'] for n in 'AB'} and sim['trusted'] == [taught['HOME']]
    assert solved['GRASP_A'] in sim['script'] and solved['ABOVE_B'] in sim['script'] and taught['GRASP_A'] not in sim['script']
    sent = []
    send = bench._robot._inner.send_action
    bench._robot._inner.send_action = lambda action: sent.append(dict(action)) or send(action)
    monkeypatch.setattr(bench, '_overhead_blocking', lambda: {'positions': {}, 'arm_cm': (17.0, 36.0), 'frame': None, 'from_camera': [],
                                                               'notes': [], 'mandarin': (20.9, 10.2) if not sent else (9.0, 9.5)})
    s = await bench.request('execute')
    done = s['last_result']
    assert done['status'] == 'completed' and done['provenance'] == 'REAL' and 'from B' in done['text'], done
    reached = lambda pose: any(all(abs(a.get(j, 1e9) - v) < 0.01 for j, v in pose.items()) for a in sent)  # noqa: E731
    assert reached(solved['GRASP_A']) and reached(solved['GRASP_B']) and not reached(taught['GRASP_A'])
    assert s['object_at'] == 'B' and len(bench.asked) == 1


@pytest.mark.asyncio
async def test_a_ruler_move_does_not_start_if_the_mandarin_moved_or_cannot_be_seen_or_reached(tmp_path, monkeypatch):
    bench = ruler_lane(tmp_path, monkeypatch, (20.5, 10.5), (14.0, 12.0), real=True)
    await bench.look_all()
    await bench.request('move the mandarin from A to B')
    s = await bench.request('execute')                       # the second look sees it 6.7 cm away
    assert s['last_result'] is None and s['pending'] is None and bench.asked == []
    assert 'Not started' in s['log'][-1]['text'] and '(14.0, 12.0)' in s['log'][-1]['text']

    gone = ruler_lane(tmp_path/'gone', monkeypatch, None)
    await gone.look_all()
    s = await gone.request('move the mandarin from A to B')
    assert s['pending'] is None and 'does not see the mandarin' in s['log'][-1]['text']

    far = ruler_lane(tmp_path/'far', monkeypatch, (29.0, 2.0),
                     reach=lambda places: {'poses': {f'{k}_{n}': dict(load_poses(POSES)['poses']['ABOVE_A']) for n in places for k in ('GRASP', 'ABOVE')},
                                           'unreachable': ['A']})
    await far.look_all()
    s = await far.request('move the mandarin from A to B')
    assert s['pending'] is None and 'cannot reach the mandarin at (29, 2) cm' in s['log'][-1]['text']


@pytest.mark.asyncio
async def test_a_ruler_move_names_the_place_the_mandarin_is_nearest_and_takes_a_typed_spot(tmp_path, monkeypatch):
    bench = ruler_lane(tmp_path, monkeypatch, (9.0, 9.0))     # nearest B
    s = await bench.look_all()
    assert s['object_at'] == 'B'
    s = await bench.request('move the mandarin from A to B')
    assert s['pending'] is None and 'nearest B' in s['log'][-2]['text']   # the validator then refuses: nothing is at A
    s = await bench.request('move the mandarin to 20, 12')
    assert s['pending']['ruler']['places'] == {'A': [20.0, 12.0], 'B': [9.0, 9.0]}
    assert s['pending']['summary'].lower().startswith('move the mandarin from b to a')
    s = await bench.request('execute')                         # stand-in arm: nothing real moved, and it says so
    assert s['last_result']['provenance'] == 'MOCK' and s['last_result']['status'] == 'completed'


def test_ruler_bench_settings(tmp_path, monkeypatch):
    from agentic.openarms_lab.bench_lane import from_env
    monkeypatch.setenv('OPENARMS_BENCH', '1')
    monkeypatch.setenv('OPENARMS_OVERHEAD_PHOTO', 'outputs/camera/none.jpg')
    for name in ('OPENARMS_CAMERA', 'OPENARMS_FOLLOWER_PORT', 'OPENARMS_PLACES', 'OPENARMS_BENCH_STATIONS'):
        monkeypatch.delenv(name, raising=False)
    bench = from_env(tmp_path)
    assert bench.state()['mode'] == 'rulers' and bench.state()['places'] == {'A': [22.0, 8.0], 'B': [8.0, 8.0]}
    monkeypatch.setenv('OPENARMS_PLACES', 'a=20,10; B=6,12')
    assert from_env(tmp_path/'named').state()['places'] == {'A': [20.0, 10.0], 'B': [6.0, 12.0]}
    monkeypatch.setenv('OPENARMS_PLACES', 'A=20')
    with pytest.raises(BenchError):
        from_env(tmp_path/'bad')
    monkeypatch.delenv('OPENARMS_PLACES')
    monkeypatch.setenv('OPENARMS_BENCH_STATIONS', '1')
    assert from_env(tmp_path/'both').state()['mode'] == 'stations'


def test_a_picture_whose_rulers_are_hidden_uses_the_last_grid_lined_up_with_it(tmp_path):
    import json
    import cv2
    import numpy as np
    from firmware.openarms_camera import bench as camera_bench
    photo = ROOT / 'outputs/camera/look_now.jpg'  # the team's own photo; not in the repository
    if not photo.exists():
        pytest.skip('bench photo not on this machine')
    lane = BenchLane(tmp_path/'bench', poses_path=POSES, seconds=.02, previewer=Preview(), overhead_photo=str(photo))
    first = lane._overhead_blocking()
    assert first['from_camera'] and not any('could not be read' in n for n in first['notes'])
    image = cv2.imread(str(photo))
    H = np.array(json.loads((tmp_path/'bench/overhead_reference.json').read_text())['H'])
    hidden = camera_bench.to_cm(np.linalg.inv(H), [(-4, -1), (1, -1), (1, 32), (-4, 32)]).astype(np.int32)
    cv2.fillPoly(image, [hidden], (40, 40, 40))                       # the left ruler covered
    h, w = image.shape[:2]
    R = cv2.getRotationMatrix2D((w / 2, h / 2), 3, 1.0)
    R[0, 2] += 40                                                     # and the camera nudged
    cv2.imwrite(str(tmp_path/'nudged.jpg'), cv2.warpAffine(image, R, (w, h)))
    lane.overhead_photo = str(tmp_path/'nudged.jpg')
    second = lane._overhead_blocking()
    assert any('the grid of the last picture whose rulers were read' in n for n in second['notes'])
    assert 'beaker' in second['from_camera']
    assert np.hypot(*np.subtract(second['positions']['beaker'], first['positions']['beaker'])) < 0.6
    (tmp_path/'bench/overhead_reference.json').unlink()               # nothing to carry over: not calibrated, as before
    third = lane._overhead_blocking()
    assert any(n.startswith('NOT CALIBRATED') and 'no earlier grid' in n for n in third['notes'])


# ---- Claude writes the pour file: replay the recording, or improve it --------------------------------

def claude_replay_lane(tmp_path, monkeypatch, motion, *, beaker=(22.3, 7.6)):
    import json
    bench = replay_lane(tmp_path, monkeypatch, beaker=beaker)
    calls = []
    bench._shift = fake_shift(calls)
    bench.pour_client = PourClaude(('simulate_pour', {'source': 'A', 'into': 'C', 'why': 'Beaker into dish.', 'motion': motion}))
    bench.shift_calls = calls
    return bench, json


@pytest.mark.asyncio
async def test_claude_can_keep_the_recording_and_the_pour_file_it_runs_is_saved(tmp_path, monkeypatch):
    bench, json = claude_replay_lane(tmp_path, monkeypatch, {'choice': 'replay', 'why': 'The grip lands on the beaker.'})
    await bench.look_all()
    s = await bench.request('pour the beaker into the dish')
    p = s['pending']
    assert p['executable'] is True and p['made_by'] == 'recording'
    system = bench.pour_client.calls[0]['system']
    assert 'take.json' in system and 'prefer it' in system and 'motion' in bench.pour_client.calls[0]['tools'][0]['input_schema']['properties']
    assert 'Carry height' in system and 'at least 8 cm above the table' in system and 'Never lower ABOVE_A or ABOVE_C' in system
    saved = json.loads((tmp_path/'bench/pours'/f"pour-{p['request_id'][:8]}.json").read_text())
    assert saved['poses'] == TAKE['poses'] and saved['made_by'] == 'recording' and saved['recorded_on_real_arm'] is True
    layout = json.loads((tmp_path/'bench/pours'/f"pour-{p['request_id'][:8]}.layout.json").read_text())
    assert layout['beaker'] == [22.3, 7.6] and layout['dish'] == [5.8, 7.6]
    assert any('Claude kept the recorded motion: The grip lands on the beaker.' in m['text'] for m in s['log'])


@pytest.mark.asyncio
async def test_what_the_real_arm_met_is_kept_and_shown_to_claude_at_a_nearby_spot(tmp_path, monkeypatch):
    bench, json = claude_replay_lane(tmp_path, monkeypatch, {'choice': 'replay', 'why': ''})
    bench.real_arm = True
    r = {'request_id': 'abcd1234-0000', 'positions': {'beaker': [22.0, 7.9], 'dish': [5.8, 7.6]}, 'pour_file': 'p.json',
         'made_by': 'recording', 'motion': {'choice': 'replay'}}
    said = bench._record_lesson(r, {'status': 'executed'}, [
        {'pose': 'GRASP_A', 'off': {'shoulder_lift.pos': -3.7}, 'raised': {'shoulder_lift.pos': -3.7}}])
    assert 'GRASP_A' in said and 'stopped high' in said and 'raised' in said
    bench._record_lesson({**r, 'positions': {'beaker': [5.0, 6.0], 'dish': [25.0, 10.0]}},
                         {'status': 'failed', 'failed_step': 'pick', 'reason': 'did not reach target'}, [])
    assert bench._record_lesson(r, {'status': 'executed'}, []) == ''  # a clean run teaches nothing
    await bench.look_all()
    await bench.request('pour the beaker into the dish')
    system = bench.pour_client.calls[0]['system']
    assert 'What the real arm met on earlier pours' in system and 'it likely met the table' in system
    assert 'raise GRASP_A' in system and 'beaker at (5.0, 6.0)' not in system  # the far-away failure is not this spot


@pytest.mark.asyncio
async def test_claude_can_improve_the_recording_and_execute_runs_claudes_file(tmp_path, monkeypatch):
    motion = {'choice': 'improve', 'moves_cm': {'GRASP_A': [1.0, 0.0, -0.5]}, 'tip_deg': 100, 'why': 'Grip lower and tip further.'}
    bench, json = claude_replay_lane(tmp_path, monkeypatch, motion)
    await bench.look_all()
    s = await bench.request('pour the beaker into the dish')
    p = s['pending']
    assert p['executable'] is True and p['made_by'] == 'claude'
    assert bench.shift_calls[-1] == {'GRASP_A': (1.0, 0.0, -0.5)}
    assert p['pour_poses']['poses']['GRASP_A']['shoulder_pan.pos'] == pytest.approx(5 + 2.0)
    assert p['pour_poses']['poses']['TIP_C']['wrist_roll.pos'] == pytest.approx(-90 + 100)   # recorded tip turns the roll up by 89
    saved = json.loads((tmp_path/'bench/pours'/f"pour-{p['request_id'][:8]}.json").read_text())
    assert saved['poses'] == p['pour_poses']['poses'] and saved['made_by'] == 'claude' and saved['recorded_on_real_arm'] is False
    assert saved['motion']['why'] == 'Grip lower and tip further.'
    assert "Claude's changes to take.json" in s['log'][-1]['text'] and 'never been run on the real arm' in s['log'][-1]['text']
    s = await bench.request('execute')
    assert s['last_result']['status'] == 'completed'
    receipt = next((tmp_path/'bench/pour-receipts').iterdir()).read_text()
    assert '"made_by": "claude"' in receipt and f"pour-{p['request_id'][:8]}.json" in receipt


@pytest.mark.asyncio
async def test_a_claude_change_out_of_bounds_is_not_used_and_the_recording_runs(tmp_path, monkeypatch):
    motion = {'choice': 'improve', 'moves_cm': {'TIP_C': [0, 0, 8]}, 'why': 'Much higher.'}
    bench, json = claude_replay_lane(tmp_path, monkeypatch, motion)
    await bench.look_all()
    s = await bench.request('pour the beaker into the dish')
    assert s['pending']['executable'] is True and s['pending']['made_by'] == 'recording' and s['pending']['pour_poses'] is None
    assert any("Claude's change was not used (Claude asked to move TIP_C by more than 3 cm.)" in m['text'] for m in s['log'])
    bench.pour_client = PourClaude(('simulate_pour', {'source': 'A', 'into': 'C', 'why': '', 'motion': {'choice': 'improve', 'tip_deg': 170, 'why': 'x'}}))
    s = await bench.request('pour the beaker into the dish')
    assert s['pending']['made_by'] == 'recording' and any('170 degrees' in m['text'] for m in s['log'])


# ---- the operator's questions in the panel ---------------------------------------------------------

@pytest.mark.asyncio
async def test_the_real_arm_asks_the_operator_in_the_panel_and_only_yes_starts_it(tmp_path, monkeypatch):
    import asyncio
    from agentic.openarms_lab.bench_lane import PanelAsk
    bench = replay_lane(tmp_path, monkeypatch, real=True)
    ask = PanelAsk(timeout=5)
    bench.ask = bench.panel_ask = ask
    bench.answer_where = 'in the panel (Yes / No)'
    await bench.look_all()
    await bench.request('pour it in')
    run = asyncio.ensure_future(bench.request('execute'))
    for _ in range(200):
        await asyncio.sleep(.01)
        if bench.state()['question']:
            break
    q = bench.state()['question']
    assert q and 'Arm at HOME, path clear, room in the dish?' in q['text'] and 'y/n' not in q['text']
    assert any('answer in the panel (Yes / No)' in m['text'] for m in bench.state()['log'])
    with pytest.raises(BenchError, match='no longer open'):
        bench.answer('stale', True)
    bench.answer(q['id'], False)
    s = await run
    assert 'operator declined' in s['log'][-1]['text'] and bench._robot._inner.sent == [] and s['question'] is None
    # Stop answers an open question No.
    await bench.request('pour it in')
    run = asyncio.ensure_future(bench.request('execute'))
    for _ in range(200):
        await asyncio.sleep(.01)
        if bench.state()['question']:
            break
    await bench.stop()
    s = await run
    assert 'operator declined' in ' '.join(m['text'] for m in s['log'][-3:]) and bench._robot._inner.sent == []


def test_panel_ask_times_out_as_no():
    from agentic.openarms_lab.bench_lane import PanelAsk
    assert PanelAsk(timeout=.05)('Go? y/n> ') == 'n'


def test_harness_notes_default_to_victors_in_repo_results(monkeypatch):
    from agentic.openarms_lab import bench_lane
    monkeypatch.delenv('OPENARMS_HARNESS_NOTES', raising=False)
    assert bench_lane._harness_notes_path() == str(bench_lane.DEFAULT_HARNESS_NOTES)
    assert bench_lane.DEFAULT_HARNESS_NOTES.is_file()
    monkeypatch.setenv('OPENARMS_HARNESS_NOTES', 'off')
    assert bench_lane._harness_notes_path() is None
    monkeypatch.setenv('OPENARMS_HARNESS_NOTES', '/tmp/x.md')
    assert bench_lane._harness_notes_path() == '/tmp/x.md'
