"""Experimental contact-only one-vial transfer. Requires live Isaac validation.

Imports occur only after SimulationApp startup. No object pose is changed after
reset. The rack is a fixed fixture; the vial remains a dynamic rigid body.
"""
from dataclasses import asdict
import math
import numpy as np
from scipy.spatial.transform import Rotation
from pxr import UsdPhysics, PhysxSchema, UsdGeom
from isaacsim.core.prims import SingleRigidPrim, RigidPrim
from isaacsim.core.utils.stage import add_reference_to_stage
from kinematics import Model


class VialTrial:
    def __init__(self, world, stage, asset_dir):
        self.world=world
        self.model=Model.from_usd(stage, '/World/Robot')
        self.source=np.array([.23,0.,.018])
        self.slot=np.array([.18+.029831712932493655,.08+.029857535202155998])
        add_reference_to_stage(str(asset_dir/'Vial_opaque.usda'), '/World/Vial')
        self.vial=world.scene.add(SingleRigidPrim('/World/Vial',name='trial_vial',
            position=self.source,orientation=np.array([1.,0,0,0]),mass=.02))
        PhysxSchema.PhysxRigidBodyAPI.Apply(stage.GetPrimAtPath('/World/Vial')).CreateAngularDampingAttr(100.)
        add_reference_to_stage(str(asset_dir/'Vial_rack_simple.usda'), '/World/Rack')
        self.rack=world.scene.add(SingleRigidPrim('/World/Rack/Body1',name='trial_rack',
            position=np.array([.18,.08,.006]),orientation=np.array([1.,0,0,0]),mass=.2))
        UsdPhysics.RigidBodyAPI(stage.GetPrimAtPath('/World/Rack/Body1')).CreateKinematicEnabledAttr(True)
        self.contact=world.scene.add(RigidPrim('/World/Vial',name='vial_contact',
            reset_xform_properties=False,track_contact_forces=True,
            contact_filter_prim_paths_expr=['/World/Robot/gripper','/World/Robot/jaw','/World/Rack/Body1'],
            max_contact_count=256))
        self.bodies={p:SingleRigidPrim(p,name='measure_'+p.rsplit('/',1)[-1],
                                     reset_xform_properties=False)
                     for p in self.model.authored_body_poses}
        seed=np.array([-.2736,-.6109,-.0745,1.5148,-1.6034,.7])
        q,report=self.model.solve([.19,-.08,.11],[0,0,-1],seed)
        if q is None:raise RuntimeError(f'Initial hover IK rejected: {report}')
        self.initial_q=q.copy()
        self.phases=[]
        # A low grasp is necessary because the wrist limit caps vertical-tool height.
        # Nominal root-to-grasp offset is 9 mm; release puts the vial bottom
        # about 5 mm above the 79 mm rack top. Live clearance is unverified.
        specs=[('approach',3,[.23,0.,.11],.7),
               ('descend',3,[.23,0.,.027],.7),
               ('close',2,[.23,0.,.027],-.15),
               ('lift',3,[.23,0.,.11],-.15),
               ('carry',3,[*self.slot,.113],-.15),
               ('lower',2,[*self.slot,.11],-.15),
               ('release',2,[*self.slot,.11],.7),
               ('retreat',3,[.19,-.08,.11],.7),
               ('settle',3,[.19,-.08,.11],.7)]
        start=0.
        previous=q.copy()
        for name,duration,xyz,jaw in specs:
            q,report=self.model.solve(xyz,[0,0,-1],previous)
            if q is None:raise RuntimeError(f'{name} IK rejected: {report}')
            q[5]=jaw
            self.phases.append({'name':name,'start_s':start,'end_s':start+duration,
                'from_rad':previous.tolist(),'to_rad':q.tolist(),'target_xyz_m':xyz,
                'ik':asdict(report)})
            previous=q.copy();start+=duration
        self.duration_s=start
        self.lift_since=None
        self.lifted=False
        self.settle_since=None
        self.success=False
        self.last_time=None
        self.lost_since=None
        self.phase='reset'
        self.config={'kind':'vial_to_rack_candidate','source_root_m':self.source.tolist(),
            'rack_root_m':[.18,.08,.006],'slot_xy_m':self.slot.tolist(),
            'vial_mass_kg':.02,'vial_angular_damping':100.,'rack_kinematic_fixture':True,
            'tcp_geometry':self.model.geometry_evidence,'phases':self.phases,
            'pose_writes_after_reset':False,'attachments':False}

    def initialize(self, measured_q):
        for body in self.bodies.values():body.initialize()
        self.resting_z=float(self.vial.get_world_pose()[0][2])
        poses={}
        for path,body in self.bodies.items():
            position,quaternion=body.get_world_pose()
            pose=np.eye(4);pose[:3,3]=position
            pose[:3,:3]=Rotation.from_quat(np.asarray(quaternion)[[1,2,3,0]]).as_matrix()
            poses[path]=pose
        errors=self.model.compare_body_poses(measured_q,poses)
        if any(e['position_error_m']>.003 or e['rotation_error_rad']>.03 for e in errors.values()):
            raise RuntimeError(f'Live physics/FK agreement failed: {errors}')
        self.config['runtime_fk_errors']=errors
        self.config['settled_initial_vial_z_m']=self.resting_z

    def command(self,t):
        phase=next((p for p in self.phases if t<p['end_s']),self.phases[-1])
        if phase['name'] in ('carry','lower','release','retreat','settle') and not self.lifted:
            raise RuntimeError('No sustained two-finger lift; refusing to continue transfer')
        self.phase=phase['name']
        u=np.clip((t-phase['start_s'])/(phase['end_s']-phase['start_s']),0,1)
        u=u*u*(3-2*u)
        return (1-u)*np.array(phase['from_rad'])+u*np.array(phase['to_rad'])

    def observe(self,t):
        pos,quat=self.vial.get_world_pose()
        linear=float(np.linalg.norm(self.vial.get_linear_velocity()))
        angular=float(np.linalg.norm(self.vial.get_angular_velocity()))
        matrix=np.asarray(self.contact.get_contact_force_matrix(dt=1/120))
        if matrix.shape!=(1,3,3):raise RuntimeError(f'Unexpected contact tensor shape {matrix.shape}')
        forces=np.linalg.norm(matrix[0],axis=1)
        grip_pos=self.bodies[self.model.gripper_path].get_world_pose()[0]
        distance=float(np.linalg.norm(grip_pos-pos))
        values=[t,*pos,*quat,linear,angular,*forces,distance]
        if not all(math.isfinite(float(v)) for v in values):raise RuntimeError('Nonfinite physics state')
        if self.last_time is not None and not 0<t-self.last_time<=.05:raise RuntimeError('Physics sampling gap')
        self.last_time=t
        held=min(forces[:2])>.02 and pos[2]>self.resting_z+.04
        self.lift_since=(t if self.lift_since is None else self.lift_since) if held else None
        if self.lift_since is not None and t-self.lift_since>=.2:self.lifted=True
        lost=self.lifted and self.phase in ('lift','carry','lower') and min(forces[:2])<=.02
        self.lost_since=(t if self.lost_since is None else self.lost_since) if lost else None
        if self.lost_since is not None and t-self.lost_since>.1:
            raise RuntimeError('Object contact lost before commanded release')
        up=Rotation.from_quat(np.asarray(quat)[[1,2,3,0]]).apply([0,0,1])
        in_slot=np.linalg.norm(pos[:2]-self.slot)<.012 and .012<pos[2]<.065 and up[2]>.95
        released=self.phase in ('retreat','settle') and max(forces[:2])<.02 and distance>.12
        stable=linear<.03 and angular<.3
        supported=forces[2]>.03
        valid=self.lifted and in_slot and released and stable and supported
        self.settle_since=(t if self.settle_since is None else self.settle_since) if valid else None
        self.success=bool(self.settle_since is not None and t-self.settle_since>=1.)
        return {'phase':self.phase,'vial_position_m':pos.tolist(),'vial_quaternion_wxyz':quat.tolist(),
            'linear_speed_m_s':linear,'angular_speed_rad_s':angular,
            'contact_forces_N':{'gripper':float(forces[0]),'jaw':float(forces[1]),'rack':float(forces[2])},
            'gripper_distance_m':distance,'verified_lift':self.lifted,'in_slot':bool(in_slot),
            'released':bool(released),'stable':bool(stable),'supported':bool(supported),'success':self.success}
