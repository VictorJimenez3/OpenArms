"""Private subprocess entry point for the existing MuJoCo liquid Player."""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

try:
    import imageio.v2 as imageio
    import mujoco

    from openarms_sim.chemistry import load_model
    from openarms_sim.config import load_bench, load_chemistry_config, load_joint_map, load_pose_file
    from openarms_sim.joints import JointMap
    from openarms_sim.motion import build_segments, expand_plan
    from openarms_sim.player import Player
    from openarms_sim.render import HEIGHT, WIDTH, VideoRecorder, camera
    from openarms_sim.scene import build_scene
except ImportError:
    if __name__ != '__main__':
        raise
    print(json.dumps({'kind': 'error', 'reason': 'MuJoCo is unavailable. Install simulation with pip install -e simulation.'}))
    sys.exit(1)

FPS = 30


def _emit(**receipt):
    print(json.dumps(receipt), flush=True)


def _snapshot(renderer, scene, folder, view='primary'):
    view_camera = camera()
    view_camera.distance = .85
    view_camera.lookat[:] = [.23, 0, .07]
    if view == 'secondary':
        view_camera.elevation = -75
    renderer.update_scene(scene.data, view_camera)
    name = uuid.uuid4().hex + '.png'
    imageio.imwrite(folder / name, renderer.render())
    return {'frame_name': name, 'captured_at': time.time()}


def _run(folder: Path, command: dict):
    scene = build_scene(load_bench('liquid'))
    poses = load_pose_file('liquid')
    joints = JointMap(load_joint_map())
    joints.use_taught_gripper(poses.get('gripper'))
    chemistry = load_chemistry_config()
    contents = command['contents']
    if command['kind'] == 'execute':
        contents['A'] = {command['condition']: 1}
    player = Player(scene, joints, chemistry, load_model(chemistry), contents)
    player.run(build_segments([{'action': 'home'}], poses['poses'], joints, scene.bench.stations), FPS)

    renderer = mujoco.Renderer(scene.model, HEIGHT, WIDTH)
    try:
        if command['kind'] == 'capture':
            _emit(kind='capture', **_snapshot(renderer, scene, folder, command['view']))
            return
        _execute(player, renderer, folder, poses['poses'], joints, command)
    finally:
        renderer.close()


def _execute(player, renderer, folder, poses, joints, command):
    scene = player.scene
    segments = build_segments(expand_plan({
        'steps': [{'action': 'add_sample', 'args': {'source': 'A', 'into': 'C', 'portions': 1}}],
    }), poses, joints, scene.bench.stations)

    video_name = command['video_name']
    recorder = VideoRecorder(scene, folder / video_name, fps=FPS, speed=3)
    last_step = None
    last_capture = -1.0

    def on_frame(current):
        nonlocal last_step, last_capture
        recorder(current)
        if current.step != last_step or current.t - last_capture >= 2.5:
            last_step, last_capture = current.step, current.t
            _emit(kind='progress', phase=current.step, frame_count=recorder.frames,
                  motion_seconds=round(current.t, 2), **_snapshot(renderer, scene, folder))

    player.t = 0.0
    try:
        issues = player.run(segments, FPS, on_frame=on_frame)
    finally:
        recorder.close()
    warnings = [issue.message for issue in issues]
    transfer_ok = (len(player.poured) == 1 and player.poured[0]['source'] == 'A' and
                   player.poured[0]['into'] == 'C' and player.poured[0]['added'] == {command['condition']: 1}
                   and player.holding is None)
    if not transfer_ok:
        warnings.append('The liquid Player did not record exactly one A-to-C transfer and release.')
    _emit(kind='result', ok=transfer_ok and all(issue.severity != 'block' for issue in issues),
          video_name=video_name, frame_count=recorder.frames, motion_seconds=round(player.t, 2),
          warnings=warnings, contents=player.contents, **_snapshot(renderer, scene, folder))


if __name__ == '__main__':
    try:
        _run(Path(sys.argv[1]), json.loads(sys.argv[2]))
    except Exception as exc:
        _emit(kind='error', reason=f'MuJoCo execution or rendering failed ({type(exc).__name__}).')
        sys.exit(1)
