"""The real bench inside the lab app: look, plan, simulate, then move the real arm.

Turned on with OPENARMS_BENCH=1. It sits beside the pH investigation and does not go
through its task loop. The steps are:

    1. LOOK      the Look now button: a fixed webcam and plain OpenCV say which station the
                 object is on (firmware/openarms_camera). A command plans from the most recent
                 look and takes no picture itself. Without a camera the app tracks it instead.
    2. PLAN      fixed patterns, then Claude, turn the text into steps from the saved
                 positions; the agent validator decides what is allowed (free_plan.py).
    3. SIMULATE  the same joint targets are played in MuJoCo and shown (sim_preview.py).
    4. EXECUTE   only after "execute", and on the real arm only after the bench operator
                 answers y in the server terminal. PoseArm sends the same targets.
    5. CHECK     the camera looks again. The result is REAL only when the picture agrees
                 with the plan; otherwise it says what the camera saw, or UNKNOWN.

Settings (environment):
    OPENARMS_BENCH=1               turn the lane on
    OPENARMS_FOLLOWER_PORT=...     the real arm; without it a stand-in robot is used
    OPENARMS_CAMERA=1              webcam index; without it there is no camera check
    OPENARMS_POSES=path            pose file (default firmware/openarms_executor/poses.json)
    OPENARMS_SECONDS=3             seconds per move (default 3)
    OPENARMS_BENCH_OBJECT_AT=A     where the object starts when there is no camera
    OPENARMS_OVERHEAD_CAMERA=1     webcam looking straight down at the two rulers (for pours)
    OPENARMS_OVERHEAD_PHOTO=path   a saved overhead photo to use in place of that webcam
    OPENARMS_SIDE_CAMERA=0         webcam watching the bench from the side; shown in the panel, never measured from

Pours ("pour the beaker into the container") are SIMULATION ONLY. The overhead picture is read
with firmware/openarms_camera/bench.py: the two red rulers give centimetres, the beaker and the
container are placed where the picture shows them, the simulation's demo bench is rebuilt there
and the pour is played. No poses have been taught for the beaker on the real arm, so a pour
cannot be executed from here.
"""
from __future__ import annotations

import asyncio
import copy
import os
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import json
import re
import shutil
import subprocess
import sys

from .free_plan import SKILL, ClaudePlanner, FreePlans, PlanProblem, repeat_requested
from .sim_preview import MujocoPreview

ROOT = Path(__file__).resolve().parents[2]
OBJECT = 'mandarin'
EXECUTE_WORDS = {'execute', 'execute it', 'run it', 'run it for real', 'do it for real', 'go ahead', 'confirm', 'yes'}


POUR_WORDS = re.compile(r"\b(?:pour|tip|empty|dump|mix|add|dilute)\b")
SETUPS = ROOT / 'simulation/config/setups'
PIECE_OF = {'A': 'beaker', 'C': 'dish'}
POUR_TOOLS = [
    {'name': 'simulate_pour',
     'description': 'Set up and play a simulated pour. Never moves the real arm.',
     'input_schema': {'type': 'object', 'additionalProperties': False, 'required': ['source', 'into', 'why'], 'properties': {
         'source': {'type': 'string', 'description': 'Station letter of the container the arm picks up and tips.'},
         'into': {'type': 'string', 'description': 'Station letter of the container that receives it.'},
         'why': {'type': 'string', 'description': 'Two or three plain sentences for the student: what you understood, what the camera '
                                                  'showed, and what you expect the simulation to show. No markdown.'}}}},
    {'name': 'cannot_do',
     'description': 'Use when the request is not a pour you can set up with what is on the bench.',
     'input_schema': {'type': 'object', 'additionalProperties': False, 'required': ['reason'], 'properties': {
         'reason': {'type': 'string', 'description': 'One or two plain sentences for the student.'}}}},
]
POUR_SYSTEM = """You help a student run a pouring experiment with a small robot arm. You decide what the student \
wants poured into what, from their words and from what an overhead camera found on the bench. A simulation then plays it. \
Nothing you do moves the real arm.

On the bench (positions in centimetres, read off two rulers by the camera):
{bench}
Camera: {camera}
The arm's base is at {arm} cm. In the simulation the pour works when both containers stand side by side about \
30 cm in front of the arm; a receiver that sits between the arm and the cup blocks it.

Only a "source" container can be picked up and tipped; only a "receiver" can be poured into. Words like "this", "that", \
"the cup", "the bowl" refer to what is on the bench. Always answer with exactly one tool call and no other text: \
simulate_pour, or cannot_do."""


class BenchError(ValueError):
    """Shown to the student as-is."""


def from_env(data_dir: Path):
    if os.getenv('OPENARMS_BENCH', '').strip().lower() in ('', '0', 'off', 'false', 'no'):
        return None
    camera = os.getenv('OPENARMS_CAMERA', '').strip()
    return BenchLane(
        data_dir / 'bench', port=os.getenv('OPENARMS_FOLLOWER_PORT') or None,
        camera_index=int(camera) if camera else None,
        seconds=float(os.getenv('OPENARMS_SECONDS', '3')),
        object_at=os.getenv('OPENARMS_BENCH_OBJECT_AT', 'A').strip().upper() or 'A',
        planner=ClaudePlanner() if ClaudePlanner.available() else None,
        overhead_index=int(os.environ['OPENARMS_OVERHEAD_CAMERA']) if os.getenv('OPENARMS_OVERHEAD_CAMERA', '').strip() else None,
        overhead_photo=os.getenv('OPENARMS_OVERHEAD_PHOTO') or None,
        side_index=int(os.environ['OPENARMS_SIDE_CAMERA']) if os.getenv('OPENARMS_SIDE_CAMERA', '').strip() else None)


class _Arm:
    """What free_plan.FreePlans expects of a backend: state, a runner with a robot, and poses."""
    mode = 'physical'

    def __init__(self, robot, poses, seconds, holds):
        self.runner = SimpleNamespace(robot=robot, poses=poses, seconds=seconds)
        self._state = {'at': 'HOME', 'holding': None, 'armed': True, 'gripper': None, 'point_holds': dict(holds)}
        self._executing = False

    def state(self):
        return copy.deepcopy(self._state)


class BenchLane:
    def __init__(self, data_dir: Path, *, port=None, camera_index=None, camera=None, regions=None, regions_path=None,
                 poses_path=None, seconds=3.0, object_at='A', planner=None, previewer=None, ask=input, robot=None,
                 overhead_index=None, overhead_photo=None, pour_client=None, side_index=None, side_camera=None):
        from firmware.openarms_executor.poses import load_poses
        self.data_dir = Path(data_dir)
        self.frames = self.data_dir / 'frames'
        self.frames.mkdir(parents=True, exist_ok=True)
        self.port, self.seconds = port, float(seconds)
        self.poses_path = Path(poses_path or os.environ.get('OPENARMS_POSES', ROOT / 'firmware/openarms_executor/poses.json'))
        self.poses = load_poses(self.poses_path)
        self.real_arm = port is not None or robot is not None and not _is_fake(robot)
        self._robot = robot
        # The stand-in needs no operator; the real arm always asks in the server terminal.
        self.free = FreePlans(self.poses_path, seconds=self.seconds, planner=planner,
                              ask=ask if self.real_arm else (lambda _q: 'y'))
        self.previewer = previewer if previewer is not None else MujocoPreview(self.poses_path)
        self.camera = camera
        if camera is None and camera_index is not None:
            from firmware.openarms_camera.stations import Camera
            self.camera = Camera(camera_index)
        self._regions, self._regions_path = regions, regions_path
        stations = sorted(n[6:] for n in self.poses['poses'] if n.startswith('GRASP_') and f'ABOVE_{n[6:]}' in self.poses['poses'])
        if object_at not in stations:
            raise BenchError(f'The object cannot start at {object_at}; the pose file has stations {stations}.')
        self.stations = stations
        self.arm = _Arm(None, self.poses, self.seconds, {s: OBJECT if s == object_at else None for s in stations})
        self.pending = None
        self.busy = None  # what the lane is doing right now, for the page
        self.log = []
        self.sight = {'status': 'no_camera' if self.camera is None else 'not_looked',
                      'text': 'No camera is configured; the app tracks the object itself.' if self.camera is None else 'The camera has not looked yet.',
                      'frame': None, 'at': None}
        self.last_result = None
        self.last_instruction = None
        # Pours: an overhead view of the rulers (a webcam, or a saved photo standing in for it).
        self.overhead_index, self.overhead_photo = overhead_index, overhead_photo
        self.pour_client = pour_client  # an Anthropic client for tests; the real one is made on first use
        # A side view for people to watch. Nothing is measured from it.
        self.side_camera = side_camera
        if side_camera is None and side_index is not None:
            from firmware.openarms_camera.stations import Camera
            self.side_camera = Camera(side_index)
        self.side = {'frame': None, 'text': '' if self.side_camera else None, 'time': None}
        if self.camera is None and (overhead_index is not None or overhead_photo):
            # Say what the panel will look at, instead of "no camera", before the first picture is taken.
            source = f'the saved photo {Path(overhead_photo).name}' if overhead_photo else f'camera {overhead_index}'
            self.sight = {'status': 'overhead_ready', 'frame': None, 'at': None,
                          'text': f'Top-down view: {source}. Press Look now, or ask for a pour, to read the bench from it.'}
        self._lock = asyncio.Lock()
        self._run = None
        # What the most recent Look now saw. Commands plan from these; they do not take a new picture.
        self.overhead_seen = None
        self.station_sight = None
        self._say('assistant', f"Real bench ready ({'real arm' if self.real_arm else 'stand-in arm, nothing will move'}). "
                               f"Stations: {', '.join(stations)}. Try: move the {OBJECT} from A to B.")

    # ---- small helpers ---------------------------------------------------------------

    def _say(self, role, text):
        self.log.append({'time': time.time(), 'role': role, 'text': text})
        del self.log[:-60]

    def regions(self):
        if self._regions is not None:
            return self._regions
        from firmware.openarms_camera.stations import load_regions
        return load_regions(self._regions_path)

    def _robot_now(self):
        if self._robot is None:
            if self.port:
                from firmware.openarms_executor.robot import connect
                self._robot = connect(False, self.port)
            else:
                from firmware.openarms_executor.motion import FakeRobot
                self._robot = FakeRobot(self.poses['poses']['HOME'])
        self.arm.runner.robot = self._robot
        return self._robot

    def _side_blocking(self):
        import cv2
        try:
            image = self.side_camera.read()
        except OSError as exc:
            return {'frame': self.side.get('frame'), 'text': f'The side camera gave no picture ({exc}).', 'time': time.time()}
        name = f'frame-{uuid.uuid4().hex[:16]}.jpg'
        cv2.imwrite(str(self.frames / name), image)
        return {'frame': '/api/bench/frame/' + name, 'text': 'Side view, for watching only.', 'time': time.time()}

    async def look_all(self):
        """The Look now button: refresh every view that is configured."""
        await self.look_side()
        if self.overhead_index is not None or self.overhead_photo:
            seen = await asyncio.to_thread(self._overhead_blocking)
            seen['time'] = time.time()
            self.overhead_seen = seen
            self._show_overhead(seen)
        if self.camera is not None:
            await self.look()
        return self.state()

    def _show_overhead(self, seen):
        where = '; '.join(f"the {n} at {tuple(seen['positions'][n])} cm" for n in ('beaker', 'dish') if seen['positions'].get(n))
        self.sight = {'status': 'overhead', 'frame': seen['frame'], 'at': None, 'time': time.time(),
                      'text': (f"From {seen['source']}: " if seen.get('source') else '') + where + '. ' + ' '.join(seen['notes'])}
        return where

    async def look_side(self):
        """Refreshes the side picture, if a side camera is configured."""
        if self.side_camera is not None:
            self.side = await asyncio.to_thread(self._side_blocking)
        return self.side

    def _set_holds(self, station):
        """The object is on `station` (or nowhere the app knows, if None)."""
        holds = {s: OBJECT if s == station else None for s in self.stations}
        self.arm._state['point_holds'] = dict(holds)
        if self.free._arm is not None and not self.arm._executing:
            self.free._arm._state['point_holds'] = dict(holds)

    def where(self):
        return next((s for s, h in self.arm._state['point_holds'].items() if h), None)

    def state(self):
        return {'enabled': True, 'arm': 'real' if self.real_arm else 'stand-in', 'stations': self.stations,
                'object': OBJECT, 'object_at': self.where(), 'armed': self.arm._state['armed'], 'busy': self.busy,
                'camera': dict(self.sight), 'side': dict(self.side), 'pending': copy.deepcopy(self.pending), 'last_result': copy.deepcopy(self.last_result),
                'log': list(self.log[-30:]), 'poses_file': _short(self.poses_path), 'seconds_per_move': self.seconds,
                'planner': 'claude' if self.free.planner else 'patterns only'}

    # ---- 1. look -----------------------------------------------------------------------

    def _look_blocking(self):
        import cv2
        from firmware.openarms_camera.stations import annotate, where
        regions = self.regions()
        if regions is None:
            return {'status': 'not_marked', 'frame': None, 'at': None,
                    'text': 'The camera is connected but the stations are not marked yet. '
                            'Run: python -m firmware.openarms_camera mark --camera N'}
        try:
            image = self.camera.read()
            seen = where(image, regions)
        except (OSError, ValueError) as exc:
            return {'status': 'error', 'frame': None, 'at': None, 'text': f'The camera check failed: {exc}'}
        name = f'frame-{uuid.uuid4().hex[:16]}.jpg'
        cv2.imwrite(str(self.frames / name), annotate(image, regions, seen))
        return {'status': seen['status'], 'frame': '/api/bench/frame/' + name, 'at': seen['station'], 'text': seen['text']}

    async def look(self, *, apply=True):
        """Takes a picture. With apply, the camera's answer replaces the tracked position."""
        if self.camera is None:
            return self.sight
        sight = await asyncio.to_thread(self._look_blocking)
        sight['time'] = time.time()
        self.sight = self.station_sight = sight
        if apply and sight['status'] in ('at_station', 'elsewhere', 'not_seen') and not self.arm._executing:
            if sight['at'] is None or sight['at'] in self.stations:
                self._set_holds(sight['at'])
        return sight

    # ---- pours: overhead picture -> bench in centimetres -> simulation ------------------------------

    def _overhead_blocking(self):
        """Reads the bench from the overhead view. Positions fall back to the last known ones."""
        import cv2
        from firmware.openarms_camera import bench
        known = bench.read_bench()
        out = {'positions': {k: known[k] for k in ('beaker', 'dish')}, 'arm_cm': known['arm_cm'], 'frame': None,
               'from_camera': [], 'notes': []}
        if self.overhead_photo:
            image = cv2.imread(str(self.overhead_photo))
            source = f'the saved photo {Path(self.overhead_photo).name}'
        elif self.overhead_index is not None:
            from firmware.openarms_camera.stations import Camera
            try:
                image = Camera(self.overhead_index).read()
            except OSError as exc:
                image, out['notes'] = None, [f'The overhead camera gave no picture ({exc}).']
            source = f'overhead camera {self.overhead_index}'
        else:
            out['notes'].append('No overhead camera is configured, so the last known positions are used.')
            return out
        if image is None:
            out['notes'].append(f'Could not read {source}; the last known positions are used.')
            return out
        out['source'] = source
        cv2.imwrite(str(self.data_dir / 'last_overhead_raw.jpg'), image)  # the untouched picture, for re-testing detection
        try:
            H, error = bench.ruler_mapping(image)
        except ValueError as exc:
            # Show what the camera actually sees, so it can be re-aimed.
            name = f'frame-{uuid.uuid4().hex[:16]}.jpg'
            cv2.imwrite(str(self.frames / name), image)
            out['frame'] = '/api/bench/frame/' + name
            dark = ' The picture is almost black: is the lens covered or facing the table?' if image.mean() < 25 else ''
            out['notes'].append(f'NOT CALIBRATED: the two rulers are not readable in this picture ({exc}).{dark} '
                                'Both rulers must be fully in view from above. The last known positions are used.')
            return out
        flat = bench.flatten(image, H)
        pieces = bench.find_pieces(flat, known['arm_cm'])
        for name in ('beaker', 'dish'):
            if name in pieces:
                out['positions'][name] = pieces[name]['cm']
                out['from_camera'].append(name)
                if pieces[name]['note']:
                    out['notes'].append(f"The {name} was found by its raised rim, so its position may be 1 to 3 cm out.")
            else:
                out['notes'].append(f'The camera did not find the {name}; its last known position is used.')
        if error > 0.5:
            out['notes'].append(f'The rulers fit loosely ({error:.1f} cm), so positions may be a centimetre or more off.')
        name = f'frame-{uuid.uuid4().hex[:16]}.jpg'
        cv2.imwrite(str(self.frames / name), bench.draw(flat, pieces, known['arm_cm']))
        out['frame'] = '/api/bench/frame/' + name
        return out

    @staticmethod
    def _bench_stations():
        import yaml
        raw = yaml.safe_load((SETUPS / 'demo/bench.yaml').read_text())
        return {name: {'kind': s['kind'], 'contents': s.get('contents') or {}} for name, s in raw['stations'].items()}

    def _decide_pour(self, text, seen):
        """(source, into, why). Claude decides when it is available; otherwise the one pour the bench allows."""
        stations = self._bench_stations()
        sources = [n for n, s in stations.items() if s['kind'] == 'source']
        receivers = [n for n, s in stations.items() if s['kind'] == 'receiver']
        fallback = (sources[0], receivers[0], f'The bench has one cup to pour ({sources[0]}) and one container to pour into ({receivers[0]}).')
        client = self.pour_client
        if client is None and ClaudePlanner.available():
            client = ClaudePlanner().client
        if client is None:
            return fallback
        from agentic.openarms_agent.brain import MODEL
        lines = []
        for name, s in stations.items():
            piece = PIECE_OF.get(name, name)
            where = seen['positions'].get(piece)
            how = 'seen by the camera' if piece in seen['from_camera'] else 'last known position, not seen this time'
            holds = ', '.join(s['contents']) or 'empty'
            lines.append(f"- station {name}: the {piece}, a {s['kind']}, at {where} ({how}); holds {holds}")
        system = POUR_SYSTEM.format(bench='\n'.join(lines), camera=' '.join(seen['notes']) or 'both containers were found.',
                                    arm=seen['arm_cm'])
        try:
            resp = client.messages.create(model=MODEL, max_tokens=800, system=system, tools=POUR_TOOLS,
                                          messages=[{'role': 'user', 'content': text}])
        except Exception as exc:
            return (*fallback[:2], fallback[2] + f' (The planning model was unavailable: {type(exc).__name__}.)')
        use = next((b for b in resp.content if b.type == 'tool_use'), None)
        if use is None:
            said = ' '.join(b.text for b in resp.content if b.type == 'text').strip()
            raise BenchError(said or 'I could not turn that into a pour.')
        if use.name == 'cannot_do':
            raise BenchError(str(use.input.get('reason') or 'I could not turn that into a pour.'))
        source, into = str(use.input.get('source', '')).upper(), str(use.input.get('into', '')).upper()
        if source not in sources or into not in receivers:
            raise BenchError(f'Only {", ".join(sources)} can be poured, into {", ".join(receivers)}.')
        return source, into, str(use.input.get('why') or '').strip()

    def _simulate_pour_blocking(self, positions, source, into):
        """Rebuilds the simulation bench at these positions and plays the pour. Returns a preview dict."""
        from firmware.openarms_camera import bench
        live = SETUPS / 'demo_live'  # a working copy, so looking at the bench never edits the committed layout
        live.mkdir(exist_ok=True)
        shutil.copy(SETUPS / 'demo/bench.yaml', live / 'bench.yaml')
        bench.write_bench(positions, live / 'bench.yaml')
        solved = subprocess.run([sys.executable, '-m', 'openarms_sim.ik', '--setup', 'demo_live'], capture_output=True, text=True, timeout=120)
        if solved.returncode:
            return {'status': 'error', 'provenance': 'SIMULATED', 'reason': (solved.stderr.strip().splitlines() or ['could not solve the arm poses'])[-1]}
        unreachable = [line.split()[0] for line in solved.stdout.splitlines() if 'cannot reach' in line]
        plan = {'plan_id': 'pour', 'steps': [{'action': 'add_sample', 'args': {'source': source, 'into': into, 'portions': 1}}]}
        ran = subprocess.run([sys.executable, '-m', 'openarms_sim', '--setup', 'demo_live', '--plan', json.dumps(plan), '--no-cache'],
                             capture_output=True, text=True, timeout=180)
        try:
            out = json.loads(ran.stdout[:ran.stdout.rindex('}') + 1])
        except ValueError:
            return {'status': 'error', 'provenance': 'SIMULATED', 'reason': (ran.stderr.strip().splitlines() or ['the simulation printed no result'])[-1]}
        blocks = [i['message'] for i in out['issues'] if i['severity'] == 'block']
        if unreachable:
            blocks.insert(0, f"The simulated arm cannot reach {', '.join(unreachable)} from where it stands.")
        notes = [i['message'] for i in out['issues'] if i['severity'] != 'block']
        video = None
        if out.get('video_url'):
            self._sim_videos = Path(out['video_url'].removeprefix('file://')).parent
            video = '/api/bench/preview/' + Path(out['video_url']).name
        predicted = next((p for p in out.get('predicted', []) if p['station'] == into), None)
        return {'status': 'blocked' if blocks else 'ready', 'provenance': 'SIMULATED', 'engine': 'MuJoCo', 'video': video,
                'blocks': blocks, 'warnings': notes, 'predicted': predicted, 'motion_seconds': out.get('motion_seconds')}

    async def _pour_request(self, text):
        """The pour path: take the bench as the last Look now saw it, decide, rebuild the simulation, play it."""
        self.pending = None
        seen = self.overhead_seen
        if seen is None:
            if self.overhead_index is not None or self.overhead_photo:
                self._say('assistant', 'Press Look now first. I plan from the most recent look, and there has not been one yet.')
                return self.state()
            seen = await asyncio.to_thread(self._overhead_blocking)  # no overhead view at all: the last known positions
            seen['time'] = time.time()
        where = self._show_overhead(seen)
        self._say('assistant', f"Using the look from {_ago(seen['time'])}. " + self.sight['text'])
        self.busy = 'deciding'
        try:
            source, into, why = await asyncio.to_thread(self._decide_pour, text, seen)
        except BenchError as exc:
            self.busy = None
            self._say('assistant', str(exc))
            return self.state()
        if why:
            self._say('assistant', why)
        r = {'request_id': str(uuid.uuid4()), 'skill_id': 'simulated_pour.v1', 'parameters': {'source': source, 'into': into},
             'summary': f'Pour the {PIECE_OF.get(source, source)} ({source}) into the {PIECE_OF.get(into, into)} ({into})',
             'planner': 'claude' if (self.pour_client or ClaudePlanner.available()) else 'bench layout',
             'preview': {'status': 'running', 'provenance': 'SIMULATED'}, 'executable': False,
             'why_not_executable': 'Simulation only: no poses have been taught on the real arm for the beaker and the container.',
             'positions': {k: list(v) for k, v in seen['positions'].items() if v}}
        self.pending, self.last_instruction = r, text
        self.busy = 'building the simulation'
        self._say('assistant', f"Setting up the simulation with {where}, then playing: {r['summary']}.")
        try:
            out = await asyncio.to_thread(self._simulate_pour_blocking, seen['positions'], source, into)
        except Exception as exc:
            out = {'status': 'error', 'provenance': 'SIMULATED', 'reason': f'{type(exc).__name__}: {exc}'}
        self.busy = None
        if self.pending is not r:
            return self.state()
        r['preview'] = out
        if out['status'] == 'ready':
            p = out.get('predicted') or {}
            seeing = f"the {PIECE_OF.get(into, into)} turns {p.get('color')}" + (f" with {' and '.join(p['observations'])}" if p.get('observations') else '') if p else 'the pour goes in'
            self._say('assistant', f'Simulation finished (SIMULATED): the pour goes in, and {seeing}. '
                                   'This is a simulation only; the real arm has not been taught this pour.')
        elif out['status'] == 'blocked':
            self._say('assistant', 'The simulation shows a problem with this layout (SIMULATED): ' + ' '.join(out['blocks'][:3])
                      + ' Try standing the two containers side by side about 30 cm in front of the arm, then ask again.')
        else:
            self._say('assistant', 'The simulation did not run: ' + str(out.get('reason', 'unknown error')))
        return self.state()

    # ---- 2 and 3. plan, then simulate ------------------------------------------------------

    async def request(self, text):
        text = text.strip()
        if not text:
            raise BenchError('Type what the arm should do.')
        word = ''.join(c for c in text.lower() if c.isalpha() or c == ' ').strip()
        if word in EXECUTE_WORDS:
            if self.pending is None:
                self._say('user', text)
                self._say('assistant', 'There is no simulated plan waiting. Ask for an action first.')
                return self.state()
            try:
                return await self.execute(self.pending['request_id'], said=text)
            except BenchError as exc:  # typed "execute": answer in the log, like any other reply
                self._say('assistant', str(exc))
                return self.state()
        async with self._lock:
            if self.arm._executing:
                raise BenchError('The arm is moving. Wait or press Stop.')
            self._say('user', text)
            self.pending = None
            if repeat_requested(text):
                if not self.last_instruction:
                    self._say('assistant', 'There is no earlier command to repeat yet.')
                    return self.state()
                text = self.last_instruction
            if POUR_WORDS.search(text.lower()):
                return await self._pour_request(text)
            sight = self.station_sight or self.sight
            if self.camera is not None:
                if self.station_sight is None:
                    self._say('assistant', 'Press Look now first. I plan from the most recent look, and there has not been one yet.')
                    return self.state()
                self._say('assistant', f"Using the look from {_ago(sight['time'])}. " + sight['text'])
            self.busy = 'planning'
            try:
                steps = self.free.parse(text, self.arm)
                planner, added = 'patterns', ''
                if not steps:
                    planned = await asyncio.to_thread(self.free.plan_with_agent, text, self.arm, self.last_instruction)
                    if planned is None:
                        raise PlanProblem("I did not understand that. Try: move the mandarin from A to B, or: go to above B, then return home.")
                    steps, added, _calls = planned
                    planner = 'claude'
                self.free.validate(self.arm, steps)
            except PlanProblem as exc:
                self.busy = None
                self._say('assistant', str(exc))
                return self.state()
            summary = self.free.summary(steps, OBJECT) + (f' ({added})' if added else '')
            r = {'request_id': str(uuid.uuid4()), 'skill_id': SKILL, 'parameters': {'steps': steps}, 'summary': summary,
                 'planner': planner, 'preview': {'status': 'running', 'provenance': 'SIMULATED'},
                 'object_at': self.where(), 'camera_at_plan': sight.get('at') if self.camera is not None else None}
            self.pending, self.last_instruction = r, text
            self.busy = 'simulating'
            self._say('assistant', f'I understood: {summary}. Simulating it first. Nothing real has moved.')
            try:
                sim = self.free.sim_request(self.arm, steps, OBJECT)
                out = await asyncio.to_thread(self.previewer, self.arm, {'request_id': r['request_id'], 'skill_id': SKILL,
                                                                        'parameters': r['parameters'], 'sim': sim})
            except Exception as exc:
                out = {'status': 'error', 'provenance': 'SIMULATED', 'reason': f'{type(exc).__name__}: {exc}'}
            if out.get('video'):
                out['video'] = out['video'].replace('/api/previews/', '/api/bench/preview/')
            self.busy = None
            if self.pending is not r:
                return self.state()  # cancelled while simulating
            r['preview'] = out
            target = 'the real arm' if self.real_arm else 'the stand-in arm'
            if out['status'] == 'ready':
                ends = [f"the {o['name']} ends at {o['at']}" if o.get('at') else f"the {o['name']} is off its marks" for o in out.get('objects', [])]
                self._say('assistant', f"Simulation finished (SIMULATED): {' and '.join(ends) or 'the plan completes'}. "
                                       f"Watch it, then type execute to run it on {target}.")
            elif out['status'] == 'blocked':
                self._say('assistant', 'The simulation stopped this plan (SIMULATED): ' + ' '.join(out.get('blocks') or ['it did not complete.'])
                          + ' It will not be executed.')
            else:
                self._say('assistant', 'The simulation did not run: ' + str(out.get('reason', 'unknown error')) + ' Nothing will be executed without it.')
            return self.state()

    async def cancel(self):
        if self.arm._executing:
            raise BenchError('The arm is moving. Use Stop.')
        if self.pending is not None:
            self.pending = None
            self._say('assistant', 'Cancelled. Nothing moved.')
        return self.state()

    # ---- 4 and 5. execute, then check ---------------------------------------------------------

    async def execute(self, request_id, *, said=None):
        async with self._lock:
            if said:
                self._say('user', said)
            r = self.pending
            if r is None or r['request_id'] != request_id:
                raise BenchError('That plan is no longer current. Ask again.')
            if r.get('executable') is False:
                raise BenchError(r.get('why_not_executable') or 'This plan can only be simulated.')
            if r['preview'].get('status') != 'ready':
                raise BenchError('The simulation has not cleared this plan, so it will not be executed.')
            if not self.arm._state['armed']:
                raise BenchError('The arm is disarmed after a stop or fault. Check the bench and restart the server.')
            steps = r['parameters']['steps']
            # The bench may have changed while the student watched the preview.
            if self.camera is not None:
                self.busy = 'looking'
                sight = await self.look()
                if sight['status'] in ('at_station', 'elsewhere', 'not_seen') and sight['at'] != r['object_at']:
                    self.pending, self.busy = None, None
                    self._say('assistant', f"Not started: the plan was made with the object at {r['object_at'] or 'no station'}, "
                                           f"but now {sight['text'][0].lower() + sight['text'][1:]} Ask again.")
                    return self.state()
            try:
                self.free.validate(self.arm, steps)
            except PlanProblem as exc:
                self.pending, self.busy = None, None
                self._say('assistant', f'Not started: {exc}')
                return self.state()
            self.pending = None
            self.busy = 'waiting for the operator' if self.real_arm else 'executing'
            await asyncio.to_thread(self._robot_now)
            if self.real_arm:
                self._say('assistant', 'Waiting for the bench operator to answer y in the server terminal.')
            ok, why = await self.free.authorize(self.arm, r)
            if not ok:
                self.busy = None
                self._say('assistant', f'Not started: {why}')
                return self.state()
            self.busy = 'executing'
            self._say('assistant', f"Running on {'the real arm' if self.real_arm else 'the stand-in arm'}. Stop is available.")
            self._run = asyncio.ensure_future(self.free.execute(self.arm, r, _no_progress))
            try:
                done = await self._run
            except Exception as exc:
                done = {'status': 'failed', 'reason': f'{type(exc).__name__}: {exc}', 'expected': None}
                self.arm._state['armed'] = False
            finally:
                self._run = None
            self.busy = 'checking'
            result = {'request_id': r['request_id'], 'summary': r['summary'], 'status': done['status'], 'reason': done.get('reason'),
                      'arm': 'real' if self.real_arm else 'stand-in'}
            expected = next((s for s, h in (done.get('expected') or {}).items() if h), None)
            if done['status'] != 'completed':
                self.arm._state['armed'] = False
                result.update(provenance='UNKNOWN', text=f"The run ended: {done['status']}. {done.get('reason') or ''} "
                                                         'Where the object is now is unknown; check the bench and restart the server.')
            elif self.camera is None or not self.real_arm:
                result.update(provenance='UNKNOWN' if self.real_arm else 'MOCK',
                              text=('The arm finished. No camera is configured, so the result is not independently checked.' if self.real_arm
                                    else f"The stand-in arm finished; nothing real moved. The app now assumes the object is at {expected or 'no station'}."))
            else:
                sight = await self.look(apply=False)
                if sight['status'] == 'at_station' and sight['at'] == expected:
                    result.update(provenance='REAL', text=f'The arm finished, and the camera sees the object at {expected}, as planned.')
                    self._set_holds(expected)
                elif sight['status'] in ('at_station', 'elsewhere', 'not_seen'):
                    result.update(provenance='REAL', text=f"The arm finished, but the plan put the object at {expected or 'no station'} and "
                                                          f"{sight['text'][0].lower() + sight['text'][1:]}")
                    self._set_holds(sight['at'])
                else:
                    result.update(provenance='UNKNOWN', text=f"The arm finished. {sight['text']} The result is not confirmed.")
                result['frame'] = sight.get('frame')
            await self.look_side()
            self.last_result = result
            self.busy = None
            self._say('assistant', f"{result['text']} ({result['provenance']})")
            return self.state()

    async def stop(self):
        """Stops a run in progress. The arm finishes its current move, then holds, and is disarmed."""
        if self.arm._executing or self._run is not None:
            self.free.stop()
            self.arm._state['armed'] = False
            self._say('assistant', 'Stop requested. The arm finishes its current move and holds there.')
        self.pending = None
        return self.state()

    def file(self, kind, name):
        """A saved camera frame or preview video, by exact generated name only."""
        import re
        if kind == 'frame' and re.fullmatch(r'frame-[0-9a-f]{16}\.jpg', name):
            path = self.frames / name
            return path if path.is_file() else None
        if kind == 'preview':
            folder = getattr(self, '_sim_videos', None)
            if folder is not None and re.fullmatch(r'[0-9a-f]{16}\.mp4', name) and (folder / name).is_file():
                return folder / name  # a pour preview
            return self.previewer.video_path(name) if hasattr(self.previewer, 'video_path') else None
        return None


def _ago(when):
    seconds = max(0, int(time.time() - when))
    return f'{seconds} seconds ago' if seconds < 90 else f'{seconds // 60} minutes ago'


async def _no_progress(_phase):
    return None


def _is_fake(robot):
    return any(base.__name__ == 'FakeRobot' for base in type(robot).__mro__)


def _short(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return Path(path).name
