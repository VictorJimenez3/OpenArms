"""Isolated, cancellable renderer for the openarms_sim `demo` bench; never imports a hardware executor."""
from __future__ import annotations

import functools
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

from .two_vessel_worker import _emit, run_worker as _run_worker

SETUP = 'demo'
CAMERA_ID = 'demo_bench_overview'
CONFIGURATION_ID = 'demo_bench_overview.v3'
# Share of what is still in the beaker that one complete pour moves.
FRACTIONS = {'all': 1.0, 'half': 0.5}
VARIANTS = ('nominal', 'camera_shift', 'missing', 'swapped', 'occluded')

run_worker = functools.partial(_run_worker, module='agentic.openarms_lab.demo_bench_worker')
EXPERIMENTS_FILE = Path(__file__).resolve().parents[2] / 'simulation/config/setups/demo/experiments.yaml'


def experiment_name():
    name = os.environ.get('OPENARMS_DEMO_EXPERIMENT', 'volcano').strip().lower() or 'volcano'
    if name not in experiments():
        raise ValueError(f'Unknown demo bench experiment {name!r}; known: {sorted(experiments())}.')
    return name


@functools.cache
def experiments():
    import yaml
    return yaml.safe_load(EXPERIMENTS_FILE.read_text())


def experiment_contents(name=None):
    """Station contents for the selected experiment, or None to keep setups/demo/bench.yaml as is."""
    contents = experiments()[name or experiment_name()].get('contents')
    return None if contents is None else {station: dict(values) for station, values in contents.items()}


def frame_record(path, generation, captured_at=None):
    evidence_id = Path(path).stem
    return {'evidence_id': evidence_id, 'frame_id': evidence_id, 'path': str(Path(path).resolve()),
            'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(), 'camera_id': CAMERA_ID,
            'configuration_id': CONFIGURATION_ID, 'calibration_id': CONFIGURATION_ID,
            'captured_at': time.time() if captured_at is None else captured_at, 'clock': 'unix_seconds',
            'coordinate_frame': 'overview_image', 'units': 'px', 'generation': generation, 'provenance': 'SIMULATED'}


def _action_steps(operation, command, held_source):
    if operation == 'add_sample':
        if held_source is not None or (command.get('source'), command.get('into'), command.get('portions')) != ('A', 'C', 1):
            raise ValueError('The complete pour requires the beaker at A, an empty gripper, and one portion into C.')
        return [{'action': 'add_sample', 'args': {'source': 'A', 'into': 'C', 'portions': 1}}], 'HOME'
    if operation == 'pick' and held_source is None and command.get('station', 'A') == 'A':
        return [{'action': 'pick', 'args': {'station': 'A'}}], 'LIFT_A'
    if operation == 'pour' and held_source == 'A' and command.get('into') == 'C' and command.get('portions') == 1:
        return [{'action': 'pour', 'args': {'into': 'C'}}], 'ABOVE_C'
    if operation == 'return_cup' and held_source == 'A' and command.get('station', 'A') == 'A':
        return [{'action': 'return_cup'}, {'action': 'home'}], 'HOME'
    raise ValueError('Pick only from A, pour the held beaker into C once, or return the held beaker to A.')


def _run(folder, command):
    import mujoco
    import numpy as np
    from PIL import Image

    from simulation.openarms_sim.chemistry import load_model
    from simulation.openarms_sim.config import load_bench, load_chemistry_config, load_joint_map, load_pose_file
    from simulation.openarms_sim.joints import JointMap
    from simulation.openarms_sim.motion import build_segments, expand_plan
    from simulation.openarms_sim.player import Player
    from simulation.openarms_sim.render import OVERVIEW_HEIGHT, OVERVIEW_WIDTH, VideoRecorder, camera
    from simulation.openarms_sim.scene import build_scene

    bench = load_bench(SETUP)
    jm = JointMap(load_joint_map())
    pose_file = load_pose_file(SETUP)
    jm.use_taught_gripper(pose_file.get('gripper'))
    config = load_chemistry_config()

    def player_for(scene):
        trusted = [np.array(jm.pose_to_model(pose_file['poses'][n])) for n in pose_file.get('taught', [])]
        return Player(scene, jm, config, load_model(config), strict_limits=pose_file.get('source') != 'taught',
                      trusted_poses=trusted, contents=experiment_contents(),
                      allow_simulation_only=experiments()[experiment_name()].get('simulation_only', False))

    def frame(scene, *, shifted=False):
        path = folder / (uuid.uuid4().hex + '.png')
        view = camera(scene.bench)
        if shifted:
            # The demo bench has no camera block, so render's own shift is a no-op; turn the default view here.
            view.azimuth += 10  # Clearly outside the 6 px marker tolerance.
        with mujoco.Renderer(scene.model, OVERVIEW_HEIGHT, OVERVIEW_WIDTH) as renderer:
            renderer.update_scene(scene.data, view)
            # Render a magenta fiducial fixed to the donor wall. It is visual only and
            # is occluded normally, so the independent observer can track it in pixels.
            donor = scene.body['A']
            rotation = scene.data.xmat[donor].reshape(3, 3)
            position = scene.data.xpos[donor] + rotation @ np.array([.018, -.012, .014])
            marker = renderer.scene.geoms[renderer.scene.ngeom]
            mujoco.mjv_initGeom(marker, mujoco.mjtGeom.mjGEOM_SPHERE, np.full(3, .0035), position,
                                np.eye(3).ravel(), np.array([1., 0., 1., 1.], dtype=np.float32))
            marker.emission = .25
            renderer.scene.ngeom += 1
            Image.fromarray(renderer.render()).save(path, format='PNG')
        raw = frame_record(path, command['generation'])
        return {'frame_name': path.name, 'captured_at': raw['captured_at'], 'raw_frame': raw}

    def home_scene(variant):
        scene = build_scene(bench, view_variant=variant)
        player = player_for(scene)
        if variant == 'missing':
            player.pos['A'][2] = -1.0
        if variant == 'swapped':
            player.pos['A'][:2], player.pos['C'][:2] = player.pos['C'][:2].copy(), player.pos['A'][:2].copy()
        player._apply(np.array(jm.pose_to_model(pose_file['poses']['HOME'])), jm.gripper_open_value)
        return scene

    if command['kind'] == 'capture':
        variant = command.get('variant', 'nominal')
        if variant not in VARIANTS:
            raise ValueError('Unknown demo bench view variant.')
        reference = frame(home_scene('nominal')) if command.get('reference') else None
        state = command.get('state')
        if state is None:
            result = frame(home_scene(variant), shifted=variant == 'camera_shift')
        else:
            # Restore the actual final renderer arrays; never derive pixels from a receipt or prediction.
            scene = build_scene(bench)
            for field, value in state['model'].items():
                getattr(scene.model, field)[:] = value
            for field, value in state['data'].items():
                getattr(scene.data, field)[:] = value
            mujoco.mj_forward(scene.model, scene.data)
            result = frame(scene, shifted=variant == 'camera_shift')
        _emit(kind='capture', reference=reference, motion_seconds=state['motion_seconds'] if state else 0, **result)
        return

    if command['kind'] != 'execute':
        raise ValueError('Unknown demo bench worker command.')
    amount = command.get('amount', 'all')
    if amount not in FRACTIONS or (amount != 'all' and command.get('operation', 'add_sample') != 'add_sample'):
        raise ValueError('Only the complete pour takes amount=all|half on the demo bench.')
    if not re.fullmatch(r'\.[0-9a-f]{32}\.mp4', command['video_name']):
        raise ValueError('Invalid staging video name.')

    previous = command.get('state')
    prior_player = previous['player'] if previous is not None else None
    held_source = prior_player['holding'] if prior_player is not None else None
    operation = command.get('operation', 'add_sample')
    steps, end_pose = _action_steps(operation, command, held_source)
    scene = build_scene(bench)
    player = player_for(scene)
    # What the beaker held at reset, so the state can report the share still left after half pours.
    full_amount = sum(player.contents['A'].values()) or 1.0
    start = {}
    receiver_portions = 0
    pours_done = 0
    if prior_player is not None:
        player.contents = prior_player['contents']
        player.location = prior_player['location']
        player.holding = held_source
        # The gripper must be allowed to touch the vessel as its jaws open on the return.
        player._touch_ok = held_source
        player._rel = tuple(np.array(array) for array in prior_player['grasp']) if held_source else None
        for name, mocap in scene.mocap.items():
            player.pos[name] = np.array(previous['data']['mocap_pos'][mocap])
            rotation = np.empty(9)
            mujoco.mju_quat2Mat(rotation, np.array(previous['data']['mocap_quat'][mocap]))
            player.rot[name] = rotation.reshape(3, 3)
        player._refresh_liquids()
        start = {'start_q': np.array(previous['data']['qpos'])[scene.arm_qadr],
                 'start_grip': prior_player['grip'], 'held_source': held_source}
        receiver_portions = prior_player['receiver_portions']
        pours_done = prior_player.get('pours_done', 0)
    segments = build_segments(expand_plan({'steps': steps}), pose_file['poses'], jm, bench.stations, **start)
    player._apply(segments[0].q0, segments[0].grip0)
    # The beaker's contents carry over from the saved state; half pours half of what is left.
    player.pour_fraction = FRACTIONS[amount]
    recorder = VideoRecorder(scene, folder / command['video_name'], fps=30, speed=1)
    last_phase = None
    trace = []

    def progress(player):
        nonlocal last_phase
        recorder(player)
        phase = player.step + ': ' + player.label
        if phase != last_phase:
            trace.append({'phase': phase, 'motion_seconds': player.t})
            _emit(kind='progress', phase=phase, frame_count=recorder.frames, motion_seconds=player.t,
                  **frame(scene))
            last_phase = phase

    try:
        player.run(segments, fps=30, on_frame=progress, allow_held=end_pose != 'HOME')
    finally:
        recorder.close()
    dose_count = len(player.poured)
    receiver_portions += dose_count
    pours_done += dose_count
    cup_share = round(sum(player.contents['A'].values()) / full_amount, 6)
    state = {'model': {f: getattr(scene.model, f).tolist() for f in ('geom_size', 'geom_pos', 'geom_rgba')},
             'data': {f: getattr(scene.data, f).tolist() for f in ('qpos', 'mocap_pos', 'mocap_quat')},
             'motion_seconds': player.t,
             'player': {'contents': player.contents, 'location': player.location, 'holding': player.holding,
                        'grasp': [array.tolist() for array in player._rel] if player._rel is not None else None,
                        'grip': segments[-1].grip1, 'receiver_portions': receiver_portions,
                        'pours_done': pours_done}}
    # The demo bench has no docks, so "returned" is the cup back on its mark with the gripper empty.
    returned = player.location.get('A') == 'A' and player.holding is None
    at_end_pose = np.allclose(scene.data.qpos[scene.arm_qadr], jm.pose_to_model(pose_file['poses'][end_pose]))
    home = bool(at_end_pose and end_pose == 'HOME')
    held = player.holding == 'A'
    holding_matches = returned if end_pose == 'HOME' else held
    dose_matches = dose_count == int(operation in {'add_sample', 'pour'})
    successful = not any(issue.severity == 'block' for issue in player.issues)
    _emit(kind='result', ok=bool(successful and at_end_pose and holding_matches and dose_matches),
          frame_count=recorder.frames, motion_seconds=player.t, dose_count=dose_count,
          donor_remaining=round(sum(player.contents['A'].values()), 6),
          warnings=[issue.message for issue in player.issues], state=state, trace=trace,
          returned_to_dock=returned, home_reached=home, video_name=command['video_name'],
          controller_state={'at': end_pose if at_end_pose else 'UNKNOWN', 'holding': 'sample_cup' if held else None,
                            'cup_station': 'A' if returned else None, 'cup_portions': cup_share,
                            'receiver_portions': receiver_portions, 'pours_done': pours_done}, **frame(scene))


if __name__ == '__main__':
    try:
        _run(Path(sys.argv[1]), json.loads(sys.argv[2]))
    except Exception as exc:
        _emit(kind='error', reason=f'Demo bench simulation failed ({type(exc).__name__}): {exc}')
        sys.exit(1)
