"""Headless Isaac 5.1 SO-101 articulation/camera proof, not a grasp claim."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

parser = argparse.ArgumentParser()
parser.add_argument('--workshop', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--seconds', type=float, default=8)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
receipt = {
    'schema_version': 1, 'provenance': 'SIMULATED', 'kind': 'articulation_smoke',
    'status': 'started', 'manipulation_success': False,
    'command': sys.argv, 'utc_started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    'slurm_job_id': os.environ.get('SLURM_JOB_ID'),
    'slurm_step_id': os.environ.get('SLURM_STEP_ID'),
    'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),
    'hostname': os.uname().nodename,
    'scene': {'units': 'meters', 'up_axis': 'Z', 'physics_dt': 1/120, 'video_fps': 30},
}

def git(repo, *arguments):
    return subprocess.check_output(['git', '-C', str(repo), *arguments], text=True).strip()

def save():
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2))

app = None
writer = None
try:
    save()
    if not receipt['slurm_job_id']:
        raise RuntimeError('This Rutgers runner requires a Slurm allocation.')
    receipt['git_commit'] = git(Path(__file__).resolve().parents[2], 'rev-parse', 'HEAD')
    receipt['git_dirty'] = bool(git(Path(__file__).resolve().parents[2], 'status', '--porcelain'))
    receipt['workshop_commit'] = git(args.workshop, 'rev-parse', 'HEAD')
    version = importlib.metadata.version('isaacsim')
    receipt['isaac_version'] = version
    if version.split('.')[:3] != ['5', '1', '0']:
        raise RuntimeError(f'Expected Isaac 5.1.0, found {version}')
    asset = args.workshop.resolve() / 'source/sim_to_real_so101/assets/usd/SO-ARM101-USD.usd'
    raw = asset.read_bytes()
    if raw.startswith(b'version https://git-lfs'):
        raise RuntimeError('Robot is an LFS pointer; run git lfs pull.')
    receipt['robot_asset'] = {'path': str(asset), 'sha256': hashlib.sha256(raw).hexdigest()}
    receipt['gpu'] = subprocess.check_output([
        'nvidia-smi', '--query-gpu=uuid,name,driver_version,memory.total', '--format=csv'
    ], text=True)
    save()
    from isaacsim import SimulationApp
    app = SimulationApp({'headless': True, 'width': 960, 'height': 720,
                         'renderer': 'RayTracedLighting', 'multi_gpu': False})
    receipt['isaac_app_created'] = True
    save()
    # Simulation modules must be imported after the application starts.
    import numpy as np
    import imageio.v2 as imageio
    from pxr import UsdGeom, UsdLux, UsdPhysics, Gf
    from isaacsim.core.api import World
    from isaacsim.core.prims import SingleArticulation
    from isaacsim.core.utils.stage import add_reference_to_stage
    from isaacsim.core.utils.types import ArticulationAction
    from isaacsim.sensors.camera import Camera
    import omni.usd

    world = World(stage_units_in_meters=1, physics_dt=1/120, rendering_dt=1/30)
    world.scene.add_default_ground_plane()
    add_reference_to_stage(str(asset), '/World/Robot')
    stage = omni.usd.get_context().get_stage()
    light = UsdLux.DomeLight.Define(stage, '/World/Light')
    light.CreateIntensityAttr(1200)
    robot = world.scene.add(SingleArticulation('/World/Robot', name='so101'))
    camera = Camera('/World/EvidenceCamera', frequency=30, resolution=(960,720))
    # OpenUSD camera coordinates: -Z view, +Y up.
    eye, target = Gf.Vec3d(.7,-.65,.5), Gf.Vec3d(.14,0,.14)
    camera_transform = Gf.Matrix4d().SetLookAt(eye,target,Gf.Vec3d(0,0,1)).GetInverse()
    rotation = camera_transform.ExtractRotationQuat()
    camera.set_world_pose(np.array(eye), np.array([rotation.GetReal(), *rotation.GetImaginary()]), camera_axes='usd')
    camera.set_focal_length(24)
    camera.set_clipping_range(.01, 20)
    world.reset()
    camera.initialize()
    names = ['Rotation','Pitch','Elbow','Wrist_Pitch','Wrist_Roll','Jaw']
    indices = np.array([robot.get_dof_index(n) for n in names])
    q0 = np.array([-.2736,-.6109,-.0745,1.5148,-1.6034,-.1465])
    robot.set_joint_positions(q0, joint_indices=indices)  # Reset only.
    robot.set_joint_velocities(np.zeros(6), joint_indices=indices)
    robot.apply_action(ArticulationAction(joint_positions=q0, joint_indices=indices))
    receipt['joint_names'] = names
    receipt['initial_joint_positions_rad'] = q0.tolist()
    stage.GetRootLayer().Export(str(args.output/'scene.usda'))
    for _ in range(120):
        world.step(render=True)
    measured_start = robot.get_joint_positions()[indices].copy()
    writer = imageio.get_writer(args.output/'camera.mp4', fps=30, codec='libx264', quality=8,
                               macro_block_size=1, ffmpeg_log_level='error')
    frame_count = 0
    measured = []
    with (args.output/'state.jsonl').open('w') as states:
        for step in range(int(args.seconds*120)):
            t = step/120
            target_q = q0.copy()
            target_q[0] += .18*np.sin(2*np.pi*t/args.seconds)
            robot.apply_action(ArticulationAction(joint_positions=target_q, joint_indices=indices))
            world.step(render=step%4==0)
            if step%4==0:
                frame = camera.get_rgba()
                if frame is None or frame.shape != (720,960,4):
                    raise RuntimeError('Camera did not return a valid RTX frame')
                rgb = np.asarray(frame[:,:,:3], dtype=np.uint8)
                if frame_count == 0:
                    imageio.imwrite(args.output/'first-frame.png', rgb)
                writer.append_data(rgb)
                frame_count += 1
                actual = robot.get_joint_positions()[indices].tolist()
                measured.append(actual)
                states.write(json.dumps({'sim_time_s':t,'joint_command_rad':target_q.tolist(),
                                         'joint_measured_rad':actual})+'\n')
    writer.close()
    writer = None
    measured = np.asarray(measured)
    motion = float(np.ptp(measured[:,0]))
    if motion < .1:
        raise RuntimeError(f'Insufficient measured articulation motion: {motion} rad')
    receipt.update(status='passed', frames=frame_count, measured_rotation_span_rad=motion,
                   video='camera.mp4', result='Robot rendered and articulation moved; grasp/place not attempted')
    receipt['sha256'] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in args.output.iterdir() if p.is_file() and p.name!='receipt.json'}
except BaseException as exc:
    receipt.update(status='failed', error_type=type(exc).__name__, error=str(exc))
    traceback.print_exc()
    raise
finally:
    if writer is not None:
        writer.close()
    receipt['utc_finished'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    save()
    if app is not None:
        app.close()
