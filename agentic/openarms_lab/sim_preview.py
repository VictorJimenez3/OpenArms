"""MuJoCo preview of a proposed action, shown to the student before anything executes.

Turned on with OPENARMS_PREVIEW=mujoco. For every proposed transfer it plays, in the
simulation, the same waypoint script the arm runner would send to the real arm (same
pose file, same seconds per move), and attaches the result to the proposal:

    {'status': 'ready' | 'blocked' | 'unavailable' | 'error', 'provenance': 'SIMULATED',
     'video': '/api/previews/<file>.mp4', 'warnings': [...], 'blocks': [...], ...}

The runtime only lets a proposal execute when its status is 'ready', or 'unavailable'
(the skill has no simulation model, for example the dilution pour). The simulation
runs in a separate process: it needs `pip install -e simulation`, never opens a serial
port, and never sends a motor command.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
GRIPPER = 'gripper.pos'
PAN = 'shoulder_pan.pos'
VIDEO_NAME = re.compile(r'script-[0-9a-f]{16}\.mp4')


def from_env():
    """The previewer selected by OPENARMS_PREVIEW, or None."""
    kind = os.getenv('OPENARMS_PREVIEW', '').strip().lower()
    if kind in ('', '0', 'off', 'none'):
        return None
    if kind != 'mujoco':
        raise ValueError('OPENARMS_PREVIEW supports only "mujoco".')
    return MujocoPreview()


def grasp_pose(script):
    """The arm pose the gripper first closes in, or None if the script never grips."""
    arm, grip = None, None
    for target in script:
        if set(target) == {GRIPPER}:
            if grip is not None and target[GRIPPER] < grip - 1 and arm is not None:
                return arm
            grip = target[GRIPPER]
        else:
            arm = target
    return None


def _short(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return Path(path).name


class MujocoPreview:
    provenance = 'SIMULATED'

    def __init__(self, poses_path=None, python=None, timeout=120, c_offset_deg=None):
        self.poses_path = poses_path
        self.python = python or sys.executable
        self.timeout = timeout
        self.c_offset_deg = float(os.getenv('OPENARMS_PREVIEW_C_OFFSET', '5')) if c_offset_deg is None else c_offset_deg
        self.video_dir = None

    def _runner(self, backend):
        """The runner whose script the arm would follow, and where its poses came from."""
        runner = getattr(backend, 'runner', None)
        if runner is not None and hasattr(runner, 'scripts'):
            return runner, os.environ.get('OPENARMS_POSES', 'firmware/openarms_executor/poses.json')
        # Mock controller: no arm is connected, so build the same script from the pose file.
        from firmware.openarms_executor.motion import FakeRobot
        from firmware.openarms_executor.poses import load_poses
        from firmware.openarms_executor.transfer_runner import PoseTransferRunner
        path = Path(self.poses_path or os.environ.get('OPENARMS_POSES', ROOT/'firmware/openarms_executor/poses.json'))
        poses = load_poses(path)
        return PoseTransferRunner(FakeRobot(poses['poses']['HOME']), poses), str(path)

    def describe(self, backend, request):
        """The simulation request for this proposal, or a reason there is none."""
        if request.get('skill_id') == 'premeasured_dilution.v1':
            return None, 'The simulation has no model of the pour for this lesson yet.'
        p = request['parameters']
        source, destination, obj = p['source'], p['destination'], p['object']
        runner, poses_file = self._runner(backend)
        poses, scripts = runner.poses, runner.scripts
        if source in scripts:
            script, note = scripts[source], None
        elif source == 'C':
            # Same construction the firmware uses for C: the A pickup turned at the shoulder.
            shifted = [{**poses['poses'][n], PAN: poses['poses'][n][PAN] + self.c_offset_deg} for n in ('ABOVE_A', 'GRASP_A')]
            script = runner._script(*shifted)
            note = f'C is shown as the A pickup turned {self.c_offset_deg:+g} degrees at the shoulder; it was not taught.'
        else:
            return None, f'The runner has no motion for source {source}.'
        grasp = grasp_pose(script)
        if grasp is None:
            return None, 'This motion never closes the gripper, so there is nothing to preview.'
        holds = (backend.state().get('point_holds') or {})
        home = {**poses['poses']['HOME'], GRIPPER: poses['gripper']['open']}
        return {
            'script': script, 'home': home, 'seconds': float(runner.seconds),
            'marks': {source: grasp, destination: poses['poses'][f'GRASP_{destination}']},
            'object_at': source if holds.get(source) else None,
            'source': source, 'destination': destination, 'object': obj,
            'trusted': list(poses['poses'].values()) + [grasp],
            '_poses_file': poses_file, '_note': note,
        }, None

    def __call__(self, backend, request):
        """Blocking; the runtime calls this in a worker thread."""
        base = {'provenance': self.provenance, 'engine': 'MuJoCo'}
        try:
            sim, reason = self.describe(backend, request)
        except (SystemExit, Exception) as exc:
            return {**base, 'status': 'error', 'reason': f'Could not build the simulation request: {exc}'}
        if sim is None:
            return {**base, 'status': 'unavailable', 'reason': reason}
        poses_file, note = sim.pop('_poses_file'), sim.pop('_note')
        try:
            done = subprocess.run([self.python, '-m', 'openarms_sim.script'], input=json.dumps(sim),
                                  capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return {**base, 'status': 'error', 'reason': 'The simulation timed out.'}
        if done.returncode != 0:
            missing = 'No module named' in done.stderr and 'openarms_sim' in done.stderr
            reason = ('The simulation package is not installed. Run: pip install -e simulation' if missing
                      else 'The simulation failed: ' + (done.stderr.strip().splitlines() or ['no output'])[-1])
            return {**base, 'status': 'error', 'reason': reason}
        out = json.loads(done.stdout)
        video = None
        if out.get('video_url'):
            path = Path(unquote(urlsplit(out['video_url']).path))
            if VIDEO_NAME.fullmatch(path.name) and path.is_file():
                self.video_dir = path.parent
                video = '/api/previews/' + path.name
        blocks = [i['message'] for i in out['issues'] if i['severity'] == 'block']
        notes = [i['message'] for i in out['issues'] if i['severity'] != 'block']
        if note:
            notes.insert(0, note)
        return {**base, 'status': 'ready' if out['ok'] else 'blocked', 'ok': out['ok'], 'video': video,
                'blocks': blocks, 'warnings': notes, 'objects': out['objects'], 'marks_cm': out['marks_cm'],
                'motion_seconds': out['motion_seconds'], 'seconds_per_move': sim['seconds'],
                'joint_map_measured': out['joint_map_measured'], 'poses_file': _short(poses_file)}

    def video_path(self, name):
        if self.video_dir is None or not VIDEO_NAME.fullmatch(name):
            return None
        path = self.video_dir/name
        return path if path.is_file() else None
