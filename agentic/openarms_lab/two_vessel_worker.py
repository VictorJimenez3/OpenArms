"""Isolated, cancellable two-vessel renderer; never imports a hardware executor."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import os
from pathlib import Path
import re
import signal
import sys
import time
import uuid


async def run_worker(folder, command, on_progress=None, *, module='agentic.openarms_lab.two_vessel_worker'):
    """Own the renderer and FFmpeg process group, including launch cancellation."""
    launch = asyncio.create_task(asyncio.create_subprocess_exec(
        sys.executable, '-m', module, str(folder), json.dumps(command),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, start_new_session=True))
    process, result = None, None
    try:
        process = await asyncio.shield(launch)
        while line := await process.stdout.readline():
            message = json.loads(line)
            if message['kind'] == 'progress' and on_progress:
                await on_progress(message)
            else:
                result = message
        if await process.wait() or result is None:
            raise RuntimeError((result or {}).get('reason', 'Two-vessel renderer exited without evidence.'))
        return result
    finally:
        if process is None:
            process = await launch
        if process.returncode is None:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.communicate()


def _emit(**value):
    print(json.dumps(value, allow_nan=False), flush=True)


def _run(folder, command):
    import mujoco
    import numpy as np
    from simulation.openarms_sim import two_vessel as fixture
    from simulation.openarms_sim.chemistry import load_model
    from simulation.openarms_sim.config import load_bench, load_chemistry_config, load_joint_map, load_pose_file
    from simulation.openarms_sim.joints import JointMap
    from simulation.openarms_sim.motion import build_segments, expand_plan
    from simulation.openarms_sim.player import Player
    from simulation.openarms_sim.preview import example_plan
    from simulation.openarms_sim.render import VideoRecorder, overview_image
    from simulation.openarms_sim.scene import build_scene

    def frame(scene=None, *, nominal=False):
        path = folder / (uuid.uuid4().hex + '.png')
        if scene is None:
            raw = fixture.capture(path, variant='nominal' if nominal else command.get('variant', 'nominal'),
                                  generation=command['generation'])
        else:
            overview_image(scene, path)
            raw = fixture._frame_record(path, command['generation'], time.time())
        raw.update(evidence_id=path.stem, frame_id=path.stem)
        return {'frame_name': path.name, 'captured_at': raw['captured_at'], 'raw_frame': raw}

    if command['kind'] == 'capture':
        reference = frame(nominal=True) if command.get('reference') else None
        state = command.get('state')
        if state is None:
            result = frame()
        else:
            # Restore the actual final renderer arrays, never derive liquid pixels
            # from a controller status, condition label, or predicted outcome.
            scene = build_scene(load_bench('liquid'))
            for field, value in state['model'].items():
                getattr(scene.model, field)[:] = value
            for field, value in state['data'].items():
                getattr(scene.data, field)[:] = value
            mujoco.mj_forward(scene.model, scene.data)
            result = frame(scene)
        _emit(kind='capture', reference=reference,
              motion_seconds=state['motion_seconds'] if state else 0, **result)
        return

    if command['kind'] != 'execute' or command.get('condition') != 'water':
        raise ValueError('Only the water A-to-C motion demonstration is supported.')
    if not re.fullmatch(r'\.[0-9a-f]{32}\.mp4', command['video_name']):
        raise ValueError('Invalid staging video name.')
    bench = load_bench('liquid')
    jm = JointMap(load_joint_map())
    pose_file = load_pose_file('liquid')
    jm.use_taught_gripper(pose_file.get('gripper'))
    segments = build_segments(expand_plan(example_plan('A', 'C', setup='liquid')),
                              pose_file['poses'], jm, bench.stations)
    scene = build_scene(bench)
    config = load_chemistry_config()
    trusted = [np.array(jm.pose_to_model(pose_file['poses'][n])) for n in pose_file.get('taught', [])]
    player = Player(scene, jm, config, load_model(config), contents={'A': {'water': 1}, 'C': {}},
                    strict_limits=pose_file.get('source') != 'taught', trusted_poses=trusted)
    recorder = VideoRecorder(scene, folder / command['video_name'], fps=30, speed=1)
    last_phase = None
    trace = []

    def progress(player):
        nonlocal last_phase
        recorder(player)
        phase = player.step + ': ' + player.label
        if phase != last_phase:
            trace.append({'phase': phase, 'motion_seconds': player.t})
            _emit(kind='progress', phase=phase, frame_count=recorder.frames,
                  motion_seconds=player.t, **frame(scene))
            last_phase = phase

    try:
        player.run(segments, fps=30, on_frame=progress)
    finally:
        recorder.close()
    seconds = player.t
    state = {'model': {f: getattr(scene.model, f).tolist() for f in ('geom_size', 'geom_pos', 'geom_rgba')},
             'data': {f: getattr(scene.data, f).tolist() for f in ('qpos', 'mocap_pos', 'mocap_quat')},
             'motion_seconds': seconds}
    returned = player.location.get('A') == 'A' and player.holding is None
    home = bool(segments and segments[-1].step == 'home()')
    successful = not any(issue.severity == 'block' for issue in player.issues)
    _emit(kind='result', ok=successful and returned and home and len(player.poured) == 1,
          frame_count=recorder.frames, motion_seconds=seconds, dose_count=len(player.poured),
          warnings=[issue.message for issue in player.issues], state=state, trace=trace,
          returned_to_dock=returned, home_reached=home, video_name=command['video_name'],
          **frame(scene))


if __name__ == '__main__':
    try:
        _run(Path(sys.argv[1]), json.loads(sys.argv[2]))
    except Exception as exc:
        _emit(kind='error', reason=f'Two-vessel simulation failed ({type(exc).__name__}): {exc}')
        sys.exit(1)
