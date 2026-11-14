"""Contact-only SO-101 block transfer candidate. Live validation is required."""
import numpy as np
from scipy.spatial.transform import Rotation
from pxr import UsdPhysics
from isaacsim.core.api.objects import DynamicCuboid, FixedCuboid
from isaacsim.core.api.materials import PhysicsMaterial
from isaacsim.core.prims import SingleRigidPrim, RigidPrim
from kinematics import Model
from manipulation_checks import Sample, TransferCheck


class CubeTrial:
    def __init__(self, world, stage, asset_dir):
        self.model = Model.from_usd(stage, '/World/Robot')
        self.source = np.array([.23, 0., .01])
        self.destination = np.array([.20, .10, .014])
        self.phase = 'reset'
        self.success = False
        self.failure = None
        self.lost_since = None
        self.settle_since = None
        self.body_initial = {}
        self.phases = []
        from cube_plan import make_plan
        (self.initial_q, self.phases, self.duration_s, orientation, yaw,
         contact_jaw, closed_jaw) = make_plan(self.model)
        material = PhysicsMaterial('/World/BlockMaterial', static_friction=.9,
                                   dynamic_friction=.8, restitution=0.)
        self.cube = world.scene.add(DynamicCuboid('/World/Block', name='trial_block',
            position=self.source, orientation=orientation, size=.020, mass=.010,
            color=np.array([.8, .15, .05]), physics_material=material))
        self.floor = world.scene.add(DynamicCuboid('/World/Receiver/Floor', name='receiver_floor',
            position=np.array([.20, .10, .002]), scale=np.array([.10, .10, .004]),
            size=1., mass=1., color=np.array([.1, .35, .5]), physics_material=material))
        UsdPhysics.RigidBodyAPI(stage.GetPrimAtPath('/World/Receiver/Floor')).CreateKinematicEnabledAttr(True)
        for name, position, scale in (
                ('Left', [.152, .10, .006], [.004, .10, .004]),
                ('Right', [.248, .10, .006], [.004, .10, .004]),
                ('Back', [.20, .148, .006], [.092, .004, .004]),
                ('Front', [.20, .052, .006], [.092, .004, .004])):
            world.scene.add(FixedCuboid('/World/Receiver/'+name, name='receiver_'+name,
                position=np.array(position), scale=np.array(scale), size=1.,
                color=np.array([.1, .35, .5]), physics_material=material))
        self.contact = world.scene.add(RigidPrim('/World/Block', name='block_contact',
            reset_xform_properties=False, track_contact_forces=True,
            contact_filter_prim_paths_expr=['/World/Robot/gripper', '/World/Robot/jaw',
                                           '/World/Receiver/Floor'], max_contact_count=256))
        self.bodies = {path: SingleRigidPrim(path, name='measure_'+path.rsplit('/', 1)[-1],
                                          reset_xform_properties=False)
                       for path in self.model.authored_body_poses}
        self.check = TransferCheck(self.source, self.destination, xy_tolerance_m=.020,
                                   z_tolerance_m=.002, lift_m=.04)
        self.config = {'kind': 'cube_to_receiver_candidate', 'source_m': self.source.tolist(),
                       'destination_m': self.destination.tolist(), 'cube_edge_m': .02,
                       'cube_mass_kg': .01, 'cube_yaw_rad': yaw,
                       'material': {'static_friction': .9, 'dynamic_friction': .8, 'restitution': 0.},
                       'contact_jaw_rad': contact_jaw, 'closed_jaw_rad': closed_jaw,
                       'phases': self.phases, 'attachments': False,
                       'pose_writes_after_reset': False, 'receiver_kinematic_fixture': True}

    def initialize(self, measured_q):
        poses = {}
        for path, body in self.bodies.items():
            body.initialize()
            position, quaternion = body.get_world_pose()
            transform = np.eye(4)
            transform[:3, 3] = position
            transform[:3, :3] = Rotation.from_quat(np.asarray(quaternion)[[1, 2, 3, 0]]).as_matrix()
            poses[path] = transform
        errors = self.model.compare_body_poses(measured_q, poses)
        self.config['runtime_fk_errors'] = errors
        if any(e['position_error_m'] > .001 or e['rotation_error_rad'] > .01 for e in errors.values()):
            raise RuntimeError(f'Live FK/physics disagreement: {errors}')
        self.body_initial['base'] = self.bodies[self.model.base_path].get_world_pose()[0].copy()
        self.body_initial['receiver'] = self.floor.get_world_pose()[0].copy()
        self.body_initial['base_quat'] = self.bodies[self.model.base_path].get_world_pose()[1].copy()
        self.body_initial['receiver_quat'] = self.floor.get_world_pose()[1].copy()

    def command(self, t):
        phase = next((p for p in self.phases if t < p['end_s']), self.phases[-1])
        self.phase = phase['name']
        if self.phase in ('carry', 'lower', 'release', 'retreat', 'settle') and not self.check.verified_lift:
            raise RuntimeError('No sustained two-finger lift; refusing transfer')
        u = np.clip((t-phase['start_s'])/(phase['end_s']-phase['start_s']), 0, 1)
        u = u*u*(3-2*u)
        return (1-u)*np.array(phase['from_rad'])+u*np.array(phase['to_rad'])

    def observe(self, t):
        pos, quat = self.cube.get_world_pose()
        linear = float(np.linalg.norm(self.cube.get_linear_velocity()))
        angular = float(np.linalg.norm(self.cube.get_angular_velocity()))
        matrix = np.asarray(self.contact.get_contact_force_matrix(dt=1/120))
        if matrix.shape != (1, 3, 3):
            raise RuntimeError(f'Unexpected contact matrix {matrix.shape}')
        forces = np.linalg.norm(matrix[0], axis=1)
        grip_pos, grip_quat = self.bodies[self.model.gripper_path].get_world_pose()
        tip = grip_pos+Rotation.from_quat(np.asarray(grip_quat)[[1, 2, 3, 0]]).apply([.00210000038147, 0, -.1])
        distance = float(np.linalg.norm(tip-pos))
        base_pos, base_quat = self.bodies[self.model.base_path].get_world_pose()
        receiver_pos, receiver_quat = self.floor.get_world_pose()
        self.last_observation = {'sim_time_s': t, 'phase': self.phase,
                                 'object_position_m': pos.tolist(),
                                 'object_quaternion_wxyz': quat.tolist(),
                                 'contact_vectors_N': matrix[0].tolist(),
                                 'linear_speed_m_s': linear, 'angular_speed_rad_s': angular}
        sample = Sample(t, tuple(pos), linear, angular, tuple(forces[:2]), distance,
                        self.phase in ('retreat', 'settle'))
        checks = self.check.update(sample)
        lost = self.check.verified_lift and self.phase in ('lift', 'hold', 'carry', 'lower') and min(forces[:2]) <= .02
        self.lost_since = (t if self.lost_since is None else self.lost_since) if lost else None
        if self.lost_since is not None and t-self.lost_since > .1:
            self.failure = 'Finger contact lost before commanded release'
        if np.linalg.norm(base_pos-self.body_initial['base']) > .001:
            self.failure = 'Fixed robot base moved'
        if np.linalg.norm(receiver_pos-self.body_initial['receiver']) > .001:
            self.failure = 'Fixed receiver moved'
        for name, quat in [('base', base_quat), ('receiver', receiver_quat)]:
            if abs(np.dot(quat, self.body_initial[name+'_quat'])) < np.cos(.01/2):
                self.failure = f'Fixed {name} rotated'
        supported = bool(forces[2] > .05)
        upright = float(Rotation.from_quat(np.asarray(quat)[[1, 2, 3, 0]]).apply([0, 0, 1])[2]) > .98
        strict_valid = (checks['verified_lift'] and checks['in_receiver'] and
                        self.phase in ('retreat', 'settle') and max(forces[:2]) < .02 and
                        distance > .05 and supported and upright and linear < .01 and angular < .1)
        self.settle_since = (t if self.settle_since is None else self.settle_since) if strict_valid else None
        self.success = bool(self.settle_since is not None and t-self.settle_since >= 1.)
        return {'phase': self.phase, 'object_position_m': pos.tolist(),
                'object_quaternion_wxyz': quat.tolist(), 'linear_speed_m_s': linear,
                'angular_speed_rad_s': angular, 'contact_vectors_N': matrix[0].tolist(),
                'finger_forces_N': forces[:2].tolist(), 'receiver_force_N': float(forces[2]),
                'base_position_m': base_pos.tolist(), 'receiver_position_m': receiver_pos.tolist(),
                'base_quaternion_wxyz': base_quat.tolist(), 'receiver_quaternion_wxyz': receiver_quat.tolist(),
                'gripper_distance_m': distance, **checks, 'supported': supported,
                'upright': upright, 'success': self.success, 'failure': self.failure}

    def check_after_sample(self):
        if self.failure:
            raise RuntimeError(self.failure)
