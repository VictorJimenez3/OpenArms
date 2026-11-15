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
    OPENARMS_POUR_POSES=path       a pour recorded on the real arm (teleop_record --capture); lets a pour be executed
    OPENARMS_BENCH_STATIONS=1      use the older taught A/B joint poses for the mandarin even when a top-down view is configured
    OPENARMS_PLACES="A=22,8;B=8,8" where the named places are, in ruler centimetres (ruler bench; these are the defaults)
    OPENARMS_BENCH_CONFIRM=page    Execute on the page starts the real arm at once. The default, terminal, also asks the
                                   bench operator for y in the server terminal (and, in a pour, that the lifted cup is held)

Pours ("pour the beaker into the container"): the overhead picture is read with
firmware/openarms_camera/bench.py: the two red rulers give centimetres, the beaker and the
container are placed where the picture shows them, the simulation's demo bench is rebuilt there
and the pour is played. The simulated joint targets are never sent to the real arm.

A pour can be EXECUTED only by replaying a recording made on the real arm (OPENARMS_POUR_POSES).
Beside that file sits NAME.layout.json, {"beaker": [x, y], "dish": [x, y]}: where the two stood,
in ruler centimetres, when the pour was recorded. When the camera sees a container more than
CORRECT_FROM_CM from there, the recorded poses at that container are corrected for the offset
(simulation/openarms_sim/shift.py): the model works out how each joint must change to move the recorded
grip that far, and only that change is added to the recording. A large offset, or a correction the model
cannot fully reach, is a warning, not a refusal; only the arm's calibrated joint range (with
LIMIT_MARGIN_DEG to spare) is enforced. It looks again before starting, and the
containers must still be where the correction was made for. A piece the camera cannot find is not
corrected and is left to the bench operator to check by eye.

The mandarin on a ruler bench ("move the mandarin from A to B"): with a top-down view configured, the
taught joint poses in the pose file are not used for A and B. Look now finds the mandarin in ruler
centimetres. The place it is nearest to is where it "is", and that place's poses are solved for the spot
the camera saw, not the place's nominal spot; the other places are solved at their own coordinates
(simulation/openarms_sim/reach.py). The plan is simulated with those poses and execute sends the same
poses to the arm. HOME and the gripper values still come from the pose file, recorded on the real arm.
These poses come from the model through config/joint_map.yaml, which is not measured, so the real
gripper can be a couple of centimetres off; the solved poses have never been recorded on the real arm.
"""
from __future__ import annotations

import asyncio
import copy
import math
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
POUR_SKILL = 'simulated_pour.v1'
CORRECT_FROM_CM = 0.5  # closer than this to where the pour was recorded, the recording is replayed as it is
WARN_CORRECTION_CM = 4.0  # an offset larger than this is corrected, with a warning that the model is less sure that far
SAME_BENCH_CM = 1.0  # at Execute, the camera must see each container this close to where the correction was made for
CORRECTION_ERROR_MM = 5.0  # the model must reach the corrected spot this closely
CORRECTION_AIM_DEG = 3.0  # ... without the gripper's tilt or roll changing more than this
CORRECTION_JOINT_DEG = 25.0  # no joint may change more than this from the recording
LIMIT_MARGIN_DEG = 3.0  # a corrected pose stays this far inside each joint's calibrated range
POSE_PIECE = {'ABOVE_A': 'beaker', 'GRASP_A': 'beaker', 'ABOVE_C': 'dish', 'TIP_C': 'dish'}
DEFAULT_PLACES = {'A': (22.0, 8.0), 'B': (8.0, 8.0)}  # ruler centimetres
MOVED_CM = 1.5  # the mandarin may be this far from where the plan was made and the plan still stands
DELIVERED_CM = 4.0  # after a move, the camera must see the mandarin this close to the place it was sent to
APART_CM = 6.0  # a place closer than this to the mandarin is not somewhere to move it to
_TO_POINT = re.compile(r"\bto\s*\(?\s*(\d+(?:\.\d+)?)\s*(?:,|\s)\s*(\d+(?:\.\d+)?)\s*\)?(?:\s*cm)?")
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
    rulers = any(os.getenv(k, '').strip() for k in ('OPENARMS_OVERHEAD_CAMERA', 'OPENARMS_OVERHEAD_PHOTO', 'OPENARMS_POUR_POSES'))
    keep_stations = camera or os.getenv('OPENARMS_BENCH_STATIONS', '').strip().lower() in ('1', 'on', 'true', 'yes')
    return BenchLane(
        data_dir / 'bench', port=os.getenv('OPENARMS_FOLLOWER_PORT') or None,
        camera_index=int(camera) if camera else None,
        seconds=float(os.getenv('OPENARMS_SECONDS', '3')),
        object_at=os.getenv('OPENARMS_BENCH_OBJECT_AT', 'A').strip().upper() or 'A',
        planner=ClaudePlanner() if ClaudePlanner.available() else None,
        overhead_index=int(os.environ['OPENARMS_OVERHEAD_CAMERA']) if os.getenv('OPENARMS_OVERHEAD_CAMERA', '').strip() else None,
        overhead_photo=os.getenv('OPENARMS_OVERHEAD_PHOTO') or None,
        side_index=int(os.environ['OPENARMS_SIDE_CAMERA']) if os.getenv('OPENARMS_SIDE_CAMERA', '').strip() else None,
        pour_poses=os.getenv('OPENARMS_POUR_POSES') or None,
        terminal_confirm=os.getenv('OPENARMS_BENCH_CONFIRM', 'terminal').strip().lower() != 'page',
        ruler_mode=bool(rulers and not keep_stations), places=_places(os.getenv('OPENARMS_PLACES', '')))


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
                 overhead_index=None, overhead_photo=None, pour_client=None, side_index=None, side_camera=None,
                 pour_poses=None, terminal_confirm=True, ruler_mode=False, places=None, reach=None, shift=None):
        from firmware.openarms_executor.poses import load_poses
        self.data_dir = Path(data_dir)
        self.frames = self.data_dir / 'frames'
        self.frames.mkdir(parents=True, exist_ok=True)
        self.port, self.seconds = port, float(seconds)
        self.poses_path = Path(poses_path or os.environ.get('OPENARMS_POSES', ROOT / 'firmware/openarms_executor/poses.json'))
        self.poses = load_poses(self.poses_path)
        self.real_arm = port is not None or robot is not None and not _is_fake(robot)
        self._robot = robot
        # The stand-in needs no operator. The real arm asks in the server terminal, unless the person who started the
        # server chose page-only confirmation: then Execute on the page (local machine only) is the one authorization.
        self.terminal_confirm = bool(terminal_confirm) and self.real_arm
        self.ask = ask if self.terminal_confirm else (lambda _q: 'y')
        self.free = FreePlans(self.poses_path, seconds=self.seconds, planner=planner, ask=self.ask)
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
        # A pour recorded on the real arm, and where the containers stood for it. Without one, pours are simulation only.
        self.taught_pour, self._pour_arm = None, None
        self.no_taught_pour = 'Simulation only: no pour recorded on the real arm is configured (OPENARMS_POUR_POSES).'
        if pour_poses:
            self._load_taught_pour(Path(pour_poses))
        # Ruler bench: everything is placed by the rulers in the top-down picture. The mandarin is picked up where the
        # camera sees it, with arm poses solved for that spot; the taught A/B joint poses from an earlier bench are not used.
        self.ruler_mode = bool(ruler_mode)
        self.places = dict(places or DEFAULT_PLACES)
        self._reach = reach or _reach_blocking  # solves arm poses for places in ruler centimetres
        self._shift = shift or _shift_blocking  # corrects recorded poses for a container that stands a little off
        self.ruler_plan = None  # what the solved poses in use were made for
        ready = f"Real bench ready ({'real arm' if self.real_arm else 'stand-in arm, nothing will move'}). "
        if self.ruler_mode:
            self.stations = sorted(self.places)
            self.arm._state['point_holds'] = {s: None for s in self.stations}
            spots = ', '.join(f'{n} at ({x:g}, {y:g}) cm' for n, (x, y) in sorted(self.places.items()))
            self._say('assistant', ready + f'Everything is placed by the rulers in the top-down picture. Places: {spots}. Press Look now, '
                                           f'then try: move the {OBJECT} from A to B, or: pour the beaker into the dish.')
        else:
            self._say('assistant', ready + f"Stations: {', '.join(stations)}. Try: move the {OBJECT} from A to B.")

    # ---- small helpers ---------------------------------------------------------------

    def _load_taught_pour(self, path):
        from firmware.openarms_executor.poses import load_poses
        from firmware.openarms_executor.pour_once import bench_limits, preflight
        try:
            poses = load_poses(path)
            preflight(poses, bench_limits())
            layout = json.loads(path.with_suffix('.layout.json').read_text())
            at = {piece: (float(layout[piece][0]), float(layout[piece][1])) for piece in ('beaker', 'dish')}
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            self.no_taught_pour = f'Simulation only: the recorded pour {path.name} cannot be used ({type(exc).__name__}: {exc}).'
            return
        self.taught_pour = {'path': path, 'poses': poses, 'at': at}

    def _taught_pour_fits(self, seen, source, into):
        """(why the recorded pour cannot be replayed on this bench, or None; the pieces the camera confirmed;
        {piece: (dx, dy) cm} for each piece far enough off that the recording is corrected for it)."""
        if self.taught_pour is None:
            return self.no_taught_pour, [], {}
        if (source, into) != ('A', 'C'):
            return 'Simulation only: the pour recorded on the real arm is the beaker into the dish.', [], {}
        confirmed, shift = [], {}
        for piece in ('beaker', 'dish'):
            if piece not in seen['from_camera']:
                continue
            (x, y), (tx, ty) = seen['positions'][piece], self.taught_pour['at'][piece]
            off = math.hypot(x - tx, y - ty)
            if off > CORRECT_FROM_CM:
                shift[piece] = (round(x - tx, 2), round(y - ty, 2))
            confirmed.append(piece)
        return None, confirmed, shift

    def _corrected_pour_blocking(self, shift):
        """The recorded pour with its poses at each shifted container corrected: (pose file dict, what changed)."""
        from firmware.openarms_executor.pour_once import bench_limits, preflight
        taught = self.taught_pour['poses']
        shift_cm = {name: shift[piece] for name, piece in POSE_PIECE.items() if piece in shift}
        limits = bench_limits()  # the real arm's calibrated range; the model's own joint limits are narrower in places
        # The correction keeps LIMIT_MARGIN_DEG inside it, so no servo is driven onto the end of its range.
        inside = {j: (lo + LIMIT_MARGIN_DEG, hi - LIMIT_MARGIN_DEG) for j, (lo, hi) in limits.items()}
        out = self._shift({name: taught['poses'][name] for name in shift_cm}, shift_cm, inside)
        poses = copy.deepcopy(taught)
        problems = [f'the {piece} is {math.hypot(*d):.1f} cm off, and the correction is surest within {WARN_CORRECTION_CM:g} cm'
                    for piece, d in shift.items() if math.hypot(*d) > WARN_CORRECTION_CM]
        for name in shift_cm:
            err, aim = out['error_mm'].get(name, 0.0), out['turn_deg'].get(name, 0.0)
            biggest = max((abs(v) for v in out['joint_change_deg'].get(name, {}).values()), default=0.0)
            if err > CORRECTION_ERROR_MM or aim > CORRECTION_AIM_DEG:
                problems.append(f'{name} would be {err:.0f} mm short with the gripper turned {aim:.0f} degrees')
            elif biggest > CORRECTION_JOINT_DEG:
                problems.append(f'{name} would need a joint to change {biggest:.0f} degrees')
            poses['poses'][name] = out['poses'][name]
        try:
            preflight(poses, limits)
        except ValueError as exc:
            raise BenchError(f'Simulation only: the corrected pour leaves the arm\'s calibrated range ({exc}).') from None
        moved = ', '.join(f'the {piece} by ({dx:+.1f}, {dy:+.1f}) cm' for piece, (dx, dy) in shift.items())
        changes = {name: out['joint_change_deg'][name] for name in shift_cm}
        return poses, {'moved': moved, 'joint_change_deg': changes, 'error_mm': out['error_mm'], 'warnings': problems}

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
        if self.ruler_mode:
            m = seen.get('mandarin')
            where = (f"the {OBJECT} at {tuple(m)} cm" if m else f'no {OBJECT} in view') + ('; ' + where if where else '')
            if not self.arm._executing:
                self._set_holds(self._nearest_place(m) if m else None)
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
        return {'enabled': True, 'mode': 'rulers' if self.ruler_mode else 'stations', 'object_cm': (self.overhead_seen or {}).get('mandarin'),
                'places': {k: list(v) for k, v in self.places.items()} if self.ruler_mode else None, 'arm': 'real' if self.real_arm else 'stand-in', 'stations': self.stations,
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
               'from_camera': [], 'notes': [], 'mandarin': None}
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
        # The untouched picture, for re-testing detection; written whole, then put in place, so it is never cut off.
        cv2.imwrite(str(self.data_dir / 'last_overhead_raw.part.jpg'), image)
        os.replace(self.data_dir / 'last_overhead_raw.part.jpg', self.data_dir / 'last_overhead_raw.jpg')
        H, error, unread = None, None, None
        try:
            H, error = bench.ruler_mapping(image)
        except ValueError as exc:
            unread = str(exc)
        if H is not None and error <= 1.0:
            self._save_overhead_reference(image, H, error)
        elif H is None:
            # Rulers hidden (a hand, the arm), glare, or a crooked view: carry over the mapping of the last picture whose
            # rulers were read, lined up with this one by what both show of the table.
            try:
                H, error, note = self._carry_overhead_reference(image)
                out['notes'].append(f'The rulers could not be read in this picture ({unread}), so {note}')
            except (OSError, ValueError, KeyError, TypeError) as exc:
                unread += f'; and no earlier grid could be lined up with it ({exc})'
        if H is None:
            # Show what the camera actually sees, so it can be re-aimed.
            name = f'frame-{uuid.uuid4().hex[:16]}.jpg'
            cv2.imwrite(str(self.frames / name), image)
            out['frame'] = '/api/bench/frame/' + name
            dark = ' The picture is almost black: is the lens covered or facing the table?' if image.mean() < 25 else ''
            out['notes'].append(f'NOT CALIBRATED: the two rulers are not readable in this picture ({unread}).{dark} '
                                'Both rulers must be in view from above. The last known positions are used.')
            return out
        flat = bench.flatten(image, H)
        # Measured on the camera's own picture, so nothing is cropped or resampled; the flattened one is only drawn.
        pieces = bench.find_pieces_raw(image, H, known['arm_cm'])
        mandarin = bench.find_mandarin(flat, known['arm_cm']) if self.ruler_mode else None
        if mandarin:
            out['mandarin'] = mandarin['cm']
            # The fruit is round and about the dish's size, so the circle search takes it for a container.
            pieces = {n: p for n, p in pieces.items() if math.dist(p['cm'], mandarin['cm']) > 4.0}
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
        cv2.imwrite(str(self.frames / name), bench.draw(flat, pieces, known['arm_cm'], mandarin, self.places if self.ruler_mode else None))
        out['frame'] = '/api/bench/frame/' + name
        return out

    def _save_overhead_reference(self, image, H, error):
        """Keeps the last picture whose rulers were read, and its mapping, for pictures where they cannot be."""
        import cv2
        reference = self.data_dir / 'overhead_reference.jpg'
        cv2.imwrite(str(self.data_dir / 'overhead_reference.part.jpg'), image)
        os.replace(self.data_dir / 'overhead_reference.part.jpg', reference)
        reference.with_suffix('.json').write_text(json.dumps({'H': [list(map(float, r)) for r in H], 'error_cm': float(error),
                                                              'time': time.time()}))

    def _carry_overhead_reference(self, image):
        """(H, fit error, note) from the saved reference picture, lined up with this one. Raises when it cannot be."""
        import cv2
        import numpy as np
        from firmware.openarms_camera import bench
        reference = self.data_dir / 'overhead_reference.jpg'
        saved = json.loads(reference.with_suffix('.json').read_text())
        earlier = cv2.imread(str(reference))
        if earlier is None:
            raise ValueError('there is no earlier picture whose rulers were read')
        H, matched, shift = bench.carry_mapping(earlier, np.array(saved['H']), image)
        return H, float(saved['error_cm']), (
            f"the grid of the last picture whose rulers were read ({_ago(saved['time'])}) is used, lined up with this one by "
            f"{matched} matching features (the camera moved about {shift:.0f} px). Positions may be about a centimetre further off.")

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
        notes = [i['message'] for i in out['issues'] if i['severity'] != 'block']
        if unreachable:
            # Only a warning: the real arm replays a recording, not these solved poses, and the solver's miss here
            # is a few millimetres from the model's wrist limit with a level gripper.
            notes.insert(0, f"The simulated arm only nearly reaches {', '.join(unreachable)} (a few millimetres short); "
                            "the real arm replays the recorded pour, so this does not stop Execute.")
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
        why_not, confirmed, shift = self._taught_pour_fits(seen, source, into)
        poses, correction = None, None
        if why_not is None and shift:
            self.busy = 'correcting the recorded pour'
            try:
                poses, correction = await asyncio.to_thread(self._corrected_pour_blocking, shift)
            except BenchError as exc:
                why_not = str(exc)
            except Exception as exc:
                why_not = f'Simulation only: the recorded pour could not be corrected ({type(exc).__name__}: {exc}).'
        r = {'request_id': str(uuid.uuid4()), 'skill_id': POUR_SKILL, 'parameters': {'source': source, 'into': into},
             'summary': f'Pour the {PIECE_OF.get(source, source)} ({source}) into the {PIECE_OF.get(into, into)} ({into})',
             'planner': 'claude' if (self.pour_client or ClaudePlanner.available()) else 'bench layout',
             'preview': {'status': 'running', 'provenance': 'SIMULATED'}, 'executable': why_not is None,
             'why_not_executable': why_not, 'camera_confirmed': confirmed, 'shift': shift if why_not is None else {},
             'pour_poses': poses, 'correction': correction,
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
            target = 'the real arm' if self.real_arm else 'the stand-in arm'
            self._say('assistant', f'Simulation finished (SIMULATED): the pour goes in, and {seeing}. ' + (
                f"Type execute to replay the pour recorded on the real arm ({self.taught_pour['path'].name}) on {target}. "
                + ('The arm replays the recorded joint positions, not the simulated ones.' if not r['correction'] else
                   f"The containers stand off their recorded spots, so the recording is corrected: {r['correction']['moved']}. "
                   'The model worked out how much each joint must change to move the recorded grip that far; the arm replays the '
                   'recording with those changes, which are checked against its calibrated range. The model is not exactly the '
                   'real arm, so watch the first grasp and keep Stop at hand.'
                   + (' WARNING (not blocking): ' + '; '.join(r['correction']['warnings']) + '. The grasp may land off the container.' if r['correction'].get('warnings') else ''))
                + ''.join(f' The camera did not find the {p}: check by eye that it stands on its recorded spot first.'
                          for p in ('beaker', 'dish') if p not in confirmed) if why_not is None else
                'This is a simulation only; the real arm has not been taught this pour.' if self.taught_pour is None else why_not))
        elif out['status'] == 'blocked':
            self._say('assistant', 'The simulation shows a problem with this layout (SIMULATED): ' + ' '.join(out['blocks'][:3])
                      + ' Try standing the two containers side by side about 30 cm in front of the arm, then ask again.')
        else:
            self._say('assistant', 'The simulation did not run: ' + str(out.get('reason', 'unknown error')))
        return self.state()

    # ---- the mandarin on a ruler bench: camera position -> solved arm poses ------------------------

    def _nearest_place(self, cm):
        return min(self.places, key=lambda n: math.dist(self.places[n], cm))

    async def _ruler_setup(self, text):
        """Solves the arm poses for the mandarin where the last look saw it and for the other places, and makes
        them the poses the plan, the simulation and the arm use. Returns the command, with a typed position
        ("to 10, 12") turned into a place letter. Raises BenchError with what to tell the student."""
        seen = self.overhead_seen
        if seen is None:
            raise BenchError('Press Look now first. I plan from the most recent look, and there has not been one yet.')
        cm = seen.get('mandarin')
        self._say('assistant', f"Using the look from {_ago(seen['time'])}. " + self.sight['text'])
        if cm is None:
            raise BenchError(f'The camera does not see the {OBJECT} in the top-down picture, so I do not know where to pick it up. '
                             'Put it inside the rulers, clear of the arm, and press Look now.')
        source = self._nearest_place(cm)
        places = {n: tuple(xy) for n, xy in self.places.items()}
        if point := _TO_POINT.search(text.lower()):
            # "move the mandarin to 10, 12": the place it is not on goes to that spot for this plan.
            target = next(n for n in sorted(places) if n != source)
            places[target] = (float(point[1]), float(point[2]))
            text = f'move the {OBJECT} from {source} to {target}'
        places[source] = tuple(cm)
        try:
            solved = await asyncio.to_thread(self._reach, places)
        except Exception as exc:
            raise BenchError(f'The arm poses could not be solved ({type(exc).__name__}: {exc}).') from exc
        from firmware.openarms_executor.pour_once import bench_limits
        limits = bench_limits()
        out = set(solved.get('unreachable') or [])
        out |= {name.split('_', 1)[1] for name, pose in solved['poses'].items()
                if any(not limits[j][0] <= v <= limits[j][1] for j, v in pose.items())}
        where = lambda n: f"{'the ' + OBJECT if n == source else n} at ({places[n][0]:g}, {places[n][1]:g}) cm"  # noqa: E731
        if source in out:
            raise BenchError(f'The arm cannot reach {where(source)} in the simulation. Move it closer to the middle of the bench and press Look now.')
        usable = {n: xy for n, xy in places.items() if n not in out}
        base = self.poses  # HOME and the gripper values: recorded on the real arm
        poses = {'poses': {'HOME': dict(base['poses']['HOME']),
                           **{name: pose for name, pose in solved['poses'].items() if name.split('_', 1)[1] in usable}},
                 'gripper': dict(base['gripper'])}
        (self.data_dir / 'ruler_poses.json').write_text(json.dumps(
            {'note': 'Solved in the simulation for the ruler positions below; not recorded on the real arm.',
             'places_cm': {n: list(xy) for n, xy in usable.items()}, 'mandarin_at': source, **poses}, indent=2) + '\n')
        self.arm.runner.poses = poses
        self.stations = sorted(usable)
        self.free._arm = None  # the next run builds its arm from these poses
        self.arm._state.update(at='HOME', holding=None)
        self.arm._state['point_holds'] = {n: OBJECT if n == source else None for n in self.stations}
        self.ruler_plan = {'mandarin': list(cm), 'source': source, 'places': {n: list(xy) for n, xy in usable.items()},
                           'tilt_deg': solved.get('tilt_deg'), 'joint_map_measured': solved.get('joint_map_measured')}
        notes = [f'The {OBJECT} is nearest {source}, so {source} is where the camera saw it: ({cm[0]:g}, {cm[1]:g}) cm.']
        notes += [f'{n} is at ({xy[0]:g}, {xy[1]:g}) cm.' for n, xy in sorted(usable.items()) if n != source]
        notes += [f'The arm cannot reach {where(n)} in the simulation, so it is left out.' for n in sorted(out)]
        notes += [f'{n} is only {math.dist(xy, cm):.1f} cm from the {OBJECT}; a move there would barely move it.'
                  for n, xy in sorted(usable.items()) if n != source and math.dist(xy, cm) < APART_CM]
        self._say('assistant', ' '.join(notes))
        if len(usable) < 2:
            raise BenchError('There is no reachable place to move it to. Name a spot, like: move the mandarin to 12, 10.')
        return text

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
            if self.ruler_mode:
                self.busy = 'solving the arm poses'
                try:
                    text = await self._ruler_setup(text)
                except BenchError as exc:
                    self.busy = None
                    self._say('assistant', str(exc))
                    return self.state()
            elif self.camera is not None:
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
                 'object_at': self.where(), 'camera_at_plan': sight.get('at') if self.camera is not None else None,
                 'ruler': copy.deepcopy(self.ruler_plan) if self.ruler_mode else None}
            self.pending, self.last_instruction = r, text
            self.busy = 'simulating'
            self._say('assistant', f'I understood: {summary}. Simulating it first. Nothing real has moved.')
            try:
                sim = self.free.sim_request(self.arm, steps, OBJECT)
                if self.ruler_mode:
                    # Only HOME was recorded on the real arm; what the solved poses touch in the simulation is not excused.
                    sim['trusted'] = [self.poses['poses']['HOME']]
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
                                       f"Watch it, then type execute to run it on {target}."
                          + (' The arm will be sent the poses solved in the simulation for these ruler positions. They have not been '
                             'recorded on the real arm and may be a couple of centimetres off, so keep a hand near Stop.'
                             if self.ruler_mode and self.real_arm else ''))
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
            if r['skill_id'] == POUR_SKILL:
                return await self._execute_pour(r)
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
            if r.get('ruler') and (self.overhead_index is not None or self.overhead_photo):
                self.busy = 'looking'
                seen = await asyncio.to_thread(self._overhead_blocking)
                seen['time'] = time.time()
                was, now = r['ruler']['mandarin'], seen.get('mandarin')
                if now is None or math.dist(was, now) > MOVED_CM:
                    self.overhead_seen = seen
                    self._show_overhead(seen)
                    self.pending, self.busy = None, None
                    self._say('assistant', f'Not started: the plan was made with the {OBJECT} at {tuple(was)} cm, but now the camera '
                                           + (f'sees it at {tuple(now)} cm.' if now else 'does not see it.') + ' Ask again.')
                    return self.state()
            try:
                self.free.validate(self.arm, steps)
            except PlanProblem as exc:
                self.pending, self.busy = None, None
                self._say('assistant', f'Not started: {exc}')
                return self.state()
            self.pending = None
            self.busy = 'waiting for the operator' if self.terminal_confirm else 'executing'
            await asyncio.to_thread(self._robot_now)
            if self.terminal_confirm:
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
            elif r.get('ruler') and self.real_arm and (self.overhead_index is not None or self.overhead_photo):
                seen = await asyncio.to_thread(self._overhead_blocking)
                seen['time'] = time.time()
                self.overhead_seen = seen
                self._show_overhead(seen)
                now, goal = seen.get('mandarin'), r['ruler']['places'].get(expected) if expected else None
                if now is not None and goal is not None and math.dist(now, goal) <= DELIVERED_CM:
                    result.update(provenance='REAL', text=f'The arm finished, and the camera sees the {OBJECT} at {tuple(now)} cm, '
                                                          f'{math.dist(now, goal):.1f} cm from {expected}.')
                elif now is not None:
                    result.update(provenance='REAL', text=f"The arm finished, but the camera sees the {OBJECT} at {tuple(now)} cm"
                                                          + (f', {math.dist(now, goal):.1f} cm from {expected} where the plan put it.' if goal else '.'))
                else:
                    result.update(provenance='UNKNOWN', text=f'The arm finished, but the camera does not see the {OBJECT} now. The result is not confirmed.')
                result['frame'] = seen.get('frame')
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

    async def _execute_pour(self, r):
        """Replays the pour recorded on the real arm. Called by execute, with the lock held."""
        from agentic.openarms_agent.runner import run
        from agentic.openarms_agent.validator import validate
        from firmware.openarms_executor.poses import ARM_JOINTS
        from firmware.openarms_executor.pour_once import PLAN, STATIONS, ObservedPour
        from firmware.openarms_executor.transfer_runner import HOME_TOL
        taught, confirmed = self.taught_pour, r['camera_confirmed']

        def not_started(why):
            self.pending, self.busy = None, None
            self._say('assistant', f'Not started: {why}')
            return self.state()

        # The bench may have changed while the student watched the preview.
        if self.overhead_index is not None or self.overhead_photo:
            self.busy = 'looking'
            seen = await asyncio.to_thread(self._overhead_blocking)
            seen['time'] = time.time()
            self.overhead_seen = seen
            self._show_overhead(seen)
            why_not, confirmed, shift = self._taught_pour_fits(seen, 'A', 'C')
            if why_not:
                return not_started('the bench changed since the look. ' + why_not.removeprefix('Simulation only: '))
            planned = r.get('shift') or {}
            for piece in ('beaker', 'dish'):
                was, now = planned.get(piece, (0.0, 0.0)), shift.get(piece, (0.0, 0.0))
                if piece in confirmed and math.dist(was, now) > SAME_BENCH_CM:
                    return not_started(f'the bench changed since the look: the {piece} moved {math.dist(was, now):.1f} cm from where '
                                       'the pour was set up for. Ask again.')
            confirmed = [p for p in confirmed if p in r['camera_confirmed']]
        self.pending = None
        self.busy = 'waiting for the operator' if self.terminal_confirm else 'executing'
        pour_poses = r.get('pour_poses') or taught['poses']
        home = pour_poses['poses']['HOME']
        try:
            if self.real_arm:
                robot = await asyncio.to_thread(self._robot_now)
            else:
                from firmware.openarms_executor.motion import FakeRobot
                robot = FakeRobot(home)
            start = await asyncio.to_thread(robot.get_observation)
        except Exception as exc:
            return not_started(f'the arm did not answer ({type(exc).__name__}: {exc}).')
        off = [j.removesuffix('.pos') for j in ARM_JOINTS if abs(float(start[j]) - home[j]) > HOME_TOL]
        if off:
            return not_started(f"the arm is not at the recording's HOME (off: {', '.join(off)}). Move it there and ask again.")
        missing = [p for p in ('beaker', 'dish') if p not in confirmed]
        checked = (('The camera sees both containers on their recorded spots.' if not r.get('correction') else
                    f"The recording is corrected for the camera's view: {r['correction']['moved']}.") if not missing else
                   f"The camera did NOT find the {' or the '.join(missing)}: check by eye that it stands on its recorded spot.")
        if self.terminal_confirm:
            self._say('assistant', 'Waiting for the bench operator to answer y in the server terminal.')
        elif missing and self.real_arm:
            self._say('assistant', checked)
        answer = await asyncio.to_thread(self.ask, f"\nPour {r['request_id'][:8]}: replay {taught['path'].name}"
                                                   f"{' (corrected)' if r.get('correction') else ''} on the real arm.\n"
                                                   f"{checked}\nArm at HOME, path clear, room in the dish? y/n> ")
        if answer.strip().lower() not in ('y', 'yes'):
            return not_started('the bench operator declined this pour.')

        receipts = self.data_dir / 'pour-receipts'
        receipts.mkdir(exist_ok=True)
        receipt = receipts / f"pour-{r['request_id'][:8]}.jsonl"

        def note(event, **details):
            with receipt.open('a') as f:
                f.write(json.dumps({'time': time.time(), 'event': event, **details}) + '\n')

        note('request', backend='physical' if self.real_arm else 'fake', poses=str(taught['path']), camera_confirmed=confirmed,
             correction=r.get('correction'), corrected_poses=r['pour_poses']['poses'] if r.get('pour_poses') else None)
        note('start_pose', joints=start)
        arm = ObservedPour(robot, pour_poses, note=note, fake=not self.real_arm)
        verdict = validate(PLAN, arm.state(), STATIONS)
        if not verdict['ok']:
            return not_started(verdict['reason'])

        def lift_failed():  # as in pour_once: once the cup is lifted, a person confirms it is held before it is carried
            if not arm.state()['holding'] or arm.state()['at'] != 'A':
                return False
            held = self.ask('Is the cup securely lifted and clear of the table? y/n> ').strip().lower() in ('y', 'yes')
            note('cup_held_observed', confirmed=held)
            return not held

        self.busy = 'executing'
        self._say('assistant', f"Replaying the recorded pour on {'the real arm' if self.real_arm else 'the stand-in arm'}. Stop is available."
                  + (' After the lift, the operator confirms in the terminal that the cup is held.' if self.terminal_confirm else ''))
        self._pour_arm, self.arm._executing = arm, True
        self._run = asyncio.ensure_future(asyncio.to_thread(run, PLAN, arm, lift_failed))
        try:
            done = await self._run
        except Exception as exc:
            done = {'status': 'failed', 'reason': f'{type(exc).__name__}: {exc}'}
        finally:
            self._run, self._pour_arm, self.arm._executing = None, None, False
        note('result', **done)
        ok = done['status'] == 'executed'
        result = {'request_id': r['request_id'], 'summary': r['summary'], 'status': 'completed' if ok else done['status'],
                  'reason': done.get('reason'), 'arm': 'real' if self.real_arm else 'stand-in'}
        if not ok:
            self.arm._state['armed'] = False
            result.update(provenance='UNKNOWN', text=f"The pour ended: {done['status']}. {done.get('reason') or ''} The cup may still be in "
                                                     'the gripper; check the bench and restart the server.')
        elif self.real_arm:
            result.update(provenance='UNKNOWN', text='The arm replayed the recorded pour and is back at HOME. Nothing here measures '
                                                     'whether the liquid went in; look at the bench.')
        else:
            result.update(provenance='MOCK', text='The stand-in arm replayed the recorded pour; nothing real moved.')
        await self.look_side()
        self.last_result = result
        self.busy = None
        self._say('assistant', f"{result['text']} ({result['provenance']})")
        return self.state()

    async def stop(self):
        """Stops a run in progress. The arm finishes its current move, then holds, and is disarmed."""
        if self.arm._executing or self._run is not None:
            self.free.stop()
            if self._pour_arm is not None:
                self._pour_arm._stopped = True  # the pour's own thread sees this, ends the move and holds the arm there
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


def _places(text):
    """'A=22,8;B=8,8' -> {'A': (22.0, 8.0), 'B': (8.0, 8.0)}; empty text gives the defaults."""
    out = {}
    for part in filter(None, (p.strip() for p in text.split(';'))):
        try:
            name, xy = part.split('=')
            x, y = (float(v) for v in xy.split(','))
        except ValueError:
            raise BenchError(f'OPENARMS_PLACES: could not read {part!r}; write it like A=22,8;B=8,8 (ruler centimetres).') from None
        if not re.fullmatch(r'[A-Za-z]', name.strip()):
            raise BenchError(f'OPENARMS_PLACES: a place is named with one letter, not {name.strip()!r}.')
        out[name.strip().upper()] = (x, y)
    if out and len(out) < 2:
        raise BenchError('OPENARMS_PLACES needs at least two places, like A=22,8;B=8,8.')
    return out or dict(DEFAULT_PLACES)


def _shift_blocking(poses, shift_cm, limits=None):
    """Recorded poses corrected for containers that stand a little off, solved in the simulation's own process (openarms_sim.shift)."""
    done = subprocess.run([sys.executable, '-m', 'openarms_sim.shift'], input=json.dumps({'poses': poses, 'shift_cm': shift_cm, 'limits_deg': limits}),
                          capture_output=True, text=True, timeout=120)
    if done.returncode:
        raise RuntimeError((done.stderr.strip().splitlines() or ['the pose correction printed nothing'])[-1])
    return json.loads(done.stdout)


def _reach_blocking(places):
    """Arm poses for these ruler positions, solved in the simulation's own process (openarms_sim.reach)."""
    done = subprocess.run([sys.executable, '-m', 'openarms_sim.reach'], input=json.dumps({'places': {n: list(xy) for n, xy in places.items()}}),
                          capture_output=True, text=True, timeout=120)
    if done.returncode:
        raise RuntimeError((done.stderr.strip().splitlines() or ['the pose solver printed nothing'])[-1])
    return json.loads(done.stdout)
