"""Private subprocess for the MuJoCo metered-dose apparatus."""
from __future__ import annotations

import json
import re
import sys
import time
import uuid
from pathlib import Path

try:
    import imageio.v2 as imageio
    import mujoco

    from simulation.lab_demos.ph import HEIGHT, SCENE, WIDTH
    from simulation.lab_demos.ph.run import JOINTS, Apparatus, camera
except ImportError:
    if __name__ != '__main__':
        raise
    print(json.dumps({'kind': 'error', 'reason': 'The MuJoCo lab scene or its dependencies are unavailable.'}))
    sys.exit(1)

FPS = 30


def _emit(**receipt):
    print(json.dumps(receipt, allow_nan=False), flush=True)


def _save_frame(folder, pixels):
    name = uuid.uuid4().hex + '.png'
    captured_at = time.time()
    imageio.imwrite(folder / name, pixels)
    return {'frame_name': name, 'captured_at': captured_at}


def _run(folder: Path, command: dict):
    apparatus = Apparatus()
    view = camera(command.get('view', 'primary'))
    with mujoco.Renderer(apparatus.model, height=HEIGHT, width=WIDTH) as renderer:
        def render():
            # Rebuild transforms from qpos/mocap before every frame.
            mujoco.mj_kinematics(apparatus.model, apparatus.data)
            renderer.update_scene(apparatus.data, view)
            return renderer.render()

        if command['kind'] == 'capture':
            if command.get('state') is not None:
                apparatus.restore(command['state'])
            _emit(kind='capture', motion_seconds=apparatus.data.time, **_save_frame(folder, render()))
        elif command['kind'] == 'execute':
            _execute(apparatus, render, folder, command)
        else:
            raise ValueError('Unsupported MuJoCo worker request.')


def _execute(apparatus, render, folder, command):
    video_name = command['video_name']
    if not re.fullmatch(r'\.[0-9a-f]{32}\.mp4', video_name):
        raise ValueError('Invalid MuJoCo staging video name.')
    frames = 0
    next_frame = 0.
    last_phase = None
    with imageio.get_writer(folder / video_name, fps=FPS, codec='libx264',
                            macro_block_size=8, ffmpeg_params=['-preset', 'veryfast']) as writer:
        def frame(phase):
            nonlocal frames, next_frame, last_phase
            now = apparatus.data.time
            changed = phase != last_phase
            if not changed and now < next_frame:
                return
            pixels = render()
            writer.append_data(pixels)
            frames += 1
            if now >= next_frame:
                next_frame += 1 / FPS
            if changed:
                _emit(kind='progress', phase=phase, frame_count=frames, motion_seconds=now,
                      **_save_frame(folder, pixels))
                last_phase = phase

        action_enabled = command.get('action_enabled', True)
        apparatus.execute(command['condition'], frame, action_enabled=action_enabled)
        pixels = render()
        for _ in range(FPS):
            writer.append_data(pixels)
            frames += 1

    _emit(kind='result', ok=apparatus.doses == 1, video_name=video_name, frame_count=frames,
          motion_seconds=apparatus.data.time, warnings=[] if action_enabled else ['Dose action disabled.'],
          state=apparatus.snapshot(), trace=apparatus.trace, dose_count=apparatus.doses,
          joint_names=list(JOINTS), scene=SCENE, **_save_frame(folder, pixels))


if __name__ == '__main__':
    try:
        _run(Path(sys.argv[1]), json.loads(sys.argv[2]))
    except (ValueError, RuntimeError) as exc:
        _emit(kind='error', reason=f'MuJoCo trial failed: {exc}')
        sys.exit(1)
    except Exception as exc:
        _emit(kind='error', reason=f'MuJoCo execution or rendering failed ({type(exc).__name__}).')
        sys.exit(1)
