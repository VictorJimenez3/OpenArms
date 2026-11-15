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
CONFIGURATION_ID = 'demo_bench_overview.v1'
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


def _run(folder, command):
    import mujoco
    import numpy as np
    from simulation.openarms_sim.chemistry import load_model
    from simulation.openarms_sim.config import load_bench, load_chemistry_config, load_joint_map, load_pose_file
    from simulation.openarms_sim.joints import JointMap
    from simulation.openarms_sim.motion import build_segments, expand_plan
    from simulation.openarms_sim.player import Player
    from simulation.openarms_sim.render import VideoRecorder, overview_image
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
        if shifted:
            # The demo bench has no camera block, so render's own shift is a no-op; turn the default view here.
            from PIL import Image
            from simulation.openarms_sim.render import OVERVIEW_HEIGHT, OVERVIEW_WIDTH, camera
            view = camera(scene.bench)
            view.azimuth += 10  # Clearly outside the 6 px marker tolerance.
            with mujoco.Renderer(scene.model, OVERVIEW_HEIGHT, OVERVIEW_WIDTH) as renderer:
                renderer.update_scene(scene.data, view)
                Image.fromarray(renderer.render()).save(path, format='PNG')
        else:
            overview_image(scene, path)
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
            result = frame(scene)
        _emit(kind='capture', reference=reference, motion_seconds=state['motion_seconds'] if state else 0, **result)
        return

    amounts = [*command.get('history', []), command.get('amount', 'all')]
    if (command['kind'] != 'execute' or (command.get('source'), command.get('into'), command.get('portions')) != ('A', 'C', 1)
            or any(amount not in FRACTIONS for amount in amounts) or len(amounts) > 8):
        raise ValueError('Only add_sample(source=A, into=C, portions=1, amount=all|half) is supported on the demo bench.')
    if not re.fullmatch(r'\.[0-9a-f]{32}\.mp4', command['video_name']):
        raise ValueError('Invalid staging video name.')
    plan = {'plan_id': 'demo-bench', 'steps': [{'action': 'add_sample', 'args': {'source': 'A', 'into': 'C', 'portions': 1}}]}
    segments = build_segments(expand_plan(plan), pose_file['poses'], jm, bench.stations)
    scene = build_scene(bench)
    player = player_for(scene)
    # The bench carries over between commands: replay the earlier pours of this trial, unrecorded
    # and with the same deterministic motion, so this pour starts from the state they left.
    for amount in amounts[:-1]:
        player.pour_fraction = FRACTIONS[amount]
        player.run(segments, fps=30)
    player.pour_fraction = FRACTIONS[amounts[-1]]
    replayed_seconds, replayed_pours = player.t, len(player.poured)
    recorder = VideoRecorder(scene, folder / command['video_name'], fps=30, speed=1)
    last_phase = None
    trace = []

    def progress(player):
        nonlocal last_phase
        recorder(player)
        phase = player.step + ': ' + player.label
        if phase != last_phase:
            trace.append({'phase': phase, 'motion_seconds': player.t - replayed_seconds})
            _emit(kind='progress', phase=phase, frame_count=recorder.frames, motion_seconds=player.t - replayed_seconds,
                  **frame(scene))
            last_phase = phase

    try:
        player.run(segments, fps=30, on_frame=progress)
    finally:
        recorder.close()
    state = {'model': {f: getattr(scene.model, f).tolist() for f in ('geom_size', 'geom_pos', 'geom_rgba')},
             'data': {f: getattr(scene.data, f).tolist() for f in ('qpos', 'mocap_pos', 'mocap_quat')},
             'motion_seconds': player.t - replayed_seconds}
    # The demo bench has no docks, so "returned" is the cup back on its mark with the gripper empty.
    returned = player.location.get('A') == 'A' and player.holding is None
    home = bool(segments and segments[-1].step == 'home()')
    successful = not any(issue.severity == 'block' for issue in player.issues)
    poured = len(player.poured) - replayed_pours
    _emit(kind='result', ok=successful and returned and home and poured == 1,
          frame_count=recorder.frames, motion_seconds=player.t - replayed_seconds, dose_count=poured,
          donor_remaining=round(sum(player.contents['A'].values()), 6),
          warnings=[issue.message for issue in player.issues], state=state, trace=trace,
          returned_to_dock=returned, home_reached=home, video_name=command['video_name'], **frame(scene))


if __name__ == '__main__':
    try:
        _run(Path(sys.argv[1]), json.loads(sys.argv[2]))
    except Exception as exc:
        _emit(kind='error', reason=f'Demo bench simulation failed ({type(exc).__name__}): {exc}')
        sys.exit(1)
