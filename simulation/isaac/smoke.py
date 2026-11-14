"""Headless Isaac 5.1 SO-101 articulation/camera proof, not a grasp claim."""
import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import uuid

parser = argparse.ArgumentParser()
parser.add_argument('--workshop', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--seconds', type=float, default=8)
parser.add_argument('--task', choices=['articulation','vial','cube'], default='articulation')
parser.add_argument('--request-id', default=None)
parser.add_argument('--startup-stage', choices=['new', 'existing'], default='new')
parser.add_argument('--cleanup', choices=['full', 'immediate', 'sensors'], default='full',
                    help='sensors: experimental Isaac 5.1 sensor/viewport teardown before normal close')
args = parser.parse_args()
if not math.isfinite(args.seconds) or args.seconds <= 0:
    parser.error('--seconds must be positive and finite')
args.output.mkdir(parents=True, exist_ok=False)
receipt = {
    'schema_version': 1, 'provenance': 'SIMULATED',
    'request_id': args.request_id or str(uuid.uuid4()), 'backend': 'simulated', 'kind': {'articulation':'articulation_smoke','vial':'vial_to_rack','cube':'cube_to_receiver'}[args.task],
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

def event(kind, **data):
    with (args.output/'events.jsonl').open('a') as stream:
        stream.write(json.dumps({'request_id':receipt['request_id'],'backend':'simulated',
            'provenance':'SIMULATED','event':kind,**data})+'\n')

def save():
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2))

app = None
writer = None
trial = None
world = None
camera = None
World = None
version = None
observation_error = None
frame_count = 0
try:
    save()
    event('started', task=args.task)
    from execution_context import validate_context
    receipt['execution_context'] = validate_context()
    receipt['git_commit'] = git(Path(__file__).resolve().parents[2], 'rev-parse', 'HEAD')
    receipt['git_dirty'] = bool(git(Path(__file__).resolve().parents[2], 'status', '--porcelain'))
    receipt['workshop_commit'] = git(args.workshop, 'rev-parse', 'HEAD')
    version = importlib.metadata.version('isaacsim')
    receipt['isaac_version'] = version
    if version.split('.')[:3] != ['5', '1', '0']:
        raise RuntimeError(f'Expected Isaac 5.1.0, found {version}')
    asset = args.workshop.resolve() / 'source/sim_to_real_so101/assets/usd/SO-ARM101-USD-NO-CAMERA.usd'
    raw = asset.read_bytes()
    if raw.startswith(b'version https://git-lfs'):
        raise RuntimeError('Robot is an LFS pointer; run git lfs pull.')
    receipt['robot_asset'] = {'path': str(asset), 'sha256': hashlib.sha256(raw).hexdigest()}
    receipt['gpu'] = subprocess.check_output([
        'nvidia-smi', '--query-gpu=uuid,name,driver_version,memory.total', '--format=csv'
    ], text=True)
    save()
    from isaacsim import SimulationApp
    receipt['launcher_config'] = {'headless': True, 'width': 960, 'height': 720,
                                 'renderer': 'RayTracedLighting', 'multi_gpu': False,
                                 'create_new_stage': args.startup_stage == 'new'}
    receipt['cleanup_mode'] = args.cleanup
    save()
    app = SimulationApp(receipt['launcher_config'])
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
    from appearance import apply_white_plastic
    receipt['scene']['appearance'] = apply_white_plastic(stage)
    light = UsdLux.DomeLight.Define(stage, '/World/Light')
    light.CreateIntensityAttr(1200)
    robot = world.scene.add(SingleArticulation('/World/Robot', name='so101'))
    camera = Camera('/World/EvidenceCamera', frequency=30, resolution=(960,720))
    # OpenUSD camera coordinates: -Z view, +Y up.
    eye, target = Gf.Vec3d(.7,-.65,.5), Gf.Vec3d(.14,0,.14)
    camera_transform = Gf.Matrix4d().SetLookAt(eye,target,Gf.Vec3d(0,0,1)).GetInverse()
    rotation = camera_transform.ExtractRotationQuat()
    camera.set_world_pose(np.array(eye), np.array([rotation.GetReal(), *rotation.GetImaginary()]), camera_axes='usd')
    camera.set_horizontal_aperture(.036)
    camera.set_vertical_aperture(.027)
    camera.set_focal_length(.024)
    camera.set_clipping_range(.01, 20)
    trial = None
    if args.task == 'vial':
        from vial_scene import VialTrial
        trial = VialTrial(world, stage, asset.parent)
    elif args.task == 'cube':
        from cube_scene import CubeTrial
        trial = CubeTrial(world, stage, asset.parent)
    world.reset()
    camera.initialize()
    names = ['Rotation','Pitch','Elbow','Wrist_Pitch','Wrist_Roll','Jaw']
    indices = np.array([robot.get_dof_index(n) for n in names])
    q0 = np.array([-.2736,-.6109,-.0745,1.5148,-1.6034,-.1465]) if trial is None else trial.initial_q
    robot.set_joint_positions(q0, joint_indices=indices)  # Reset only.
    robot.set_joint_velocities(np.zeros(6), joint_indices=indices)
    robot.apply_action(ArticulationAction(joint_positions=q0, joint_indices=indices))
    receipt['joint_names'] = names
    receipt['initial_joint_positions_rad'] = q0.tolist()
    stage.Flatten().Export(str(args.output/'scene.usda'))
    for _ in range(120):
        world.step(render=False)
        world.render()
    if trial is not None:
        receipt['trial_configuration'] = trial.config
        (args.output/'trial-configuration.json').write_text(json.dumps(trial.config, indent=2))
        save()
        trial.initialize(robot.get_joint_positions()[indices])
        args.seconds = trial.duration_s
        (args.output/'trial-configuration.json').write_text(json.dumps(trial.config, indent=2))
    start_sim_time = world.current_time
    writer = imageio.get_writer(args.output/'camera.mp4', fps=30, codec='libx264', quality=8,
                               macro_block_size=1, ffmpeg_log_level='error')
    frame_count = 0
    measured = []
    previous_phase = None
    with (args.output/'state.jsonl').open('w') as states:
        for step in range(int(args.seconds*120)):
            t = step/120
            target_q = q0.copy() if trial is None else trial.command(t)
            if trial is None:
                target_q[0] += .18*np.sin(2*np.pi*t/args.seconds)
            robot.apply_action(ArticulationAction(joint_positions=target_q, joint_indices=indices))
            world.step(render=False)
            actual = robot.get_joint_positions()[indices].tolist()
            observed = {} if trial is None else trial.observe(float(world.current_time-start_sim_time))
            phase = 'articulation' if trial is None else trial.phase
            if phase != previous_phase:
                event('phase', phase=phase, sim_time_s=float(world.current_time-start_sim_time))
                previous_phase = phase
            states.write(json.dumps({'sim_time_s':float(world.current_time-start_sim_time),
                'joint_command_rad':target_q.tolist(),'joint_measured_rad':actual,**observed})+'\n')
            states.flush()
            if trial is not None and hasattr(trial, 'check_after_sample'):
                trial.check_after_sample()
            if step%4==0:
                world.render()
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

    writer.close()
    writer = None
    measured = np.asarray(measured)
    motion = float(np.ptp(measured[:,0]))
    if not np.isfinite(measured).all() or not math.isfinite(motion) or (trial is None and motion < .1):
        raise RuntimeError(f'Insufficient measured articulation motion: {motion} rad')
    if trial is not None and not trial.success:
        raise RuntimeError('Transfer failed live contact/lift/release/receiver/settling criteria')
    receipt['manipulation_success'] = bool(trial is not None and trial.success)
    receipt.update(status='passed', frames=frame_count, measured_rotation_span_rad=motion,
                   video='camera.mp4', visual_review='required', result=('Robot rendered and articulation moved; grasp/place not attempted' if trial is None
                   else 'Contact/lift/release/receiver/settling checks passed; video review required'))
    receipt['sha256'] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in args.output.iterdir() if p.is_file() and p.name!='receipt.json'}
except BaseException as exc:
    observation_error = exc
    receipt.update(status='failed', error_type=type(exc).__name__, error=str(exc))
    if trial is not None and hasattr(trial, 'last_observation'):
        (args.output/'failure-state.json').write_text(json.dumps(trial.last_observation, indent=2))
        (args.output/'trial-configuration.json').write_text(json.dumps(trial.config, indent=2))
    traceback.print_exc()
    raise
finally:
    video_close_error = None
    if writer is not None:
        try:
            writer.close()
        except Exception as close_error:
            video_close_error = close_error
            receipt.update(status='failed', video_close_error=str(close_error))
            traceback.print_exc()
    receipt['observation_status'] = receipt['status']
    receipt['frames'] = frame_count
    receipt['shutdown_status'] = 'pending'
    receipt['status'] = 'failed' if receipt['observation_status']=='failed' else 'awaiting_shutdown'
    event('observations_finished',status=receipt['observation_status'],manipulation_success=receipt['manipulation_success'])
    receipt['utc_finished'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    receipt['sha256'] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in args.output.iterdir() if p.is_file() and p.name!='receipt.json'}
    save()
    cleanup_errors = []
    if app is not None:
        if args.cleanup == 'sensors':
            from cleanup import cleanup_sensors

            receipt['cleanup_diagnostic'] = {
                'mode': 'sensors', 'steps': [],
                'initialized': {'world': world is not None, 'camera': camera is not None,
                                'world_type': World is not None},
            }

            def checkpoint(operation, phase, **details):
                marker = {'operation': operation, 'phase': phase, **details}
                receipt['cleanup_diagnostic']['steps'].append(marker)
                if details.get('status') == 'failed':
                    receipt['shutdown_status'] = 'failed'
                    receipt['status'] = 'failed'
                save()
                print('ISAAC_CLEANUP ' + json.dumps(marker), flush=True)

            cleanup_errors = cleanup_sensors(app, world, camera, World, version, checkpoint)
        else:
            app.close(skip_cleanup=args.cleanup == 'immediate')
    receipt['shutdown_status'] = 'failed' if cleanup_errors else 'completed'
    receipt['status'] = 'failed' if cleanup_errors else receipt['observation_status']
    if cleanup_errors:
        receipt['cleanup_errors'] = [
            {'error_type': type(exc).__name__, 'error': str(exc)}
            for exc in cleanup_errors
        ]
    save()
    # Preserve an observation exception already in flight. Otherwise a Python
    # cleanup failure must produce nonzero exit, even when normal close returned.
    if args.cleanup == 'sensors' and observation_error is None:
        if video_close_error is not None:
            raise video_close_error
        if cleanup_errors:
            # Even an unexpected SystemExit(0) during teardown is a failure.
            raise RuntimeError('Sensor cleanup failed; see receipt cleanup_errors') from cleanup_errors[0]
