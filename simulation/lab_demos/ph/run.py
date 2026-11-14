"""Actuator feedback and qualitative indicator dosing using the imported titration bench."""
from __future__ import annotations

import mujoco
import numpy as np

from simulation.lab_demos.titration.run import DROP_ML, build, pose_rad

from . import CONDITIONS

JOINTS = ('shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper')
NEUTRAL = (.49, .19, .72, 1.)
DOSED_RGBA = {
    'vinegar': (.91, .15, .54, 1.),
    'water': NEUTRAL,
    'baking_soda': (.10, .42, .9, 1.),
}
JOINT_ERROR_RAD = .015
JOINT_SPEED_RAD_S = .08
PRESS_DISTANCE_M = .014
MAX_MOVE_S = 5
STATE_SPEC = mujoco.mjtState.mjSTATE_INTEGRATION


def camera(view):
    eye = mujoco.MjvCamera()
    eye.lookat[:] = [.215, .052, .13]
    eye.distance = .79
    eye.azimuth, eye.elevation = {'primary': (150, -39), 'secondary': (121, -63)}[view]
    return eye


class Apparatus:
    def __init__(self):
        self.model, self.data, poses, _ = build()
        m, d = self.model, self.data
        # Keep one station of the imported two-well apparatus for the student trial.
        for stem in ('dishbase', 'dishwall', 'liquid', 'dropper', 'dropper_tip', 'pump', 'pad', 'drop'):
            geom = m.geom(stem + '_large')
            geom.rgba[3] = 0
            geom.contype[0] = geom.conaffinity[0] = 0
        self.liquid = m.geom('liquid_small')
        wall = m.geom('dishwall_small')
        wall.rgba[3] = .35
        # Expose the liquid surface to both cameras above the translucent dish.
        self.liquid.pos[2] = .035
        self.liquid.size[:2] = [.028, .006]
        m.geom('dishbase_small').rgba[:] = [.94, .58, .04, 1]
        dropper = m.geom('dropper_small')
        dropper.rgba[:] = [.04, .55, .43, 1]
        dropper.size[1], dropper.pos[2] = .044, .128
        m.geom('dropper_tip_small').pos[2] = .075
        self.drop = m.geom('drop_small')
        self.drop_mocap = int(m.body('dropbody_small').mocapid[0])
        self.drop_start_z = .062
        d.mocap_pos[self.drop_mocap, 2] = self.drop_start_z
        self.pad = m.geom('pad_small')
        self.pad.pos[2] += .0035
        self.pad_rest_z = float(self.pad.pos[2])
        self.site = m.site('gripperframe').id
        self.joints = [m.joint(name).id for name in JOINTS]
        self.qaddrs = m.jnt_qposadr[self.joints]
        self.vaddrs = m.jnt_dofadr[self.joints]
        self.actuators = [m.actuator(name).id for name in JOINTS]
        self.goals = {name: np.r_[pose_rad(poses[name]), .15] for name in ('HOME', 'ABOVE_A', 'GRASP_A')}
        self.condition = None
        self.doses = 0
        self.trace = []
        d.qpos[self.qaddrs] = self.goals['HOME']
        d.ctrl[self.actuators] = self.goals['HOME']
        self._appearance()
        mujoco.mj_forward(m, d)
        self._check_state()

    def _appearance(self):
        # Source selection alone leaves the receiver at its starting color.
        self.liquid.rgba[:] = DOSED_RGBA[self.condition] if self.doses else NEUTRAL

    def snapshot(self):
        integration = np.empty(mujoco.mj_stateSize(self.model, STATE_SPEC))
        mujoco.mj_getState(self.model, self.data, integration, STATE_SPEC)
        return {'integration': integration.tolist(), 'source_condition': self.condition, 'dose_count': self.doses}

    def restore(self, state):
        integration = np.asarray(state['integration'], dtype=float)
        if integration.shape != (mujoco.mj_stateSize(self.model, STATE_SPEC),) or not np.isfinite(integration).all():
            raise ValueError('Invalid saved MuJoCo integration state.')
        self.condition, self.doses = state['source_condition'], state['dose_count']
        if self.condition not in CONDITIONS or self.doses not in (0, 1):
            raise ValueError('Invalid saved MuJoCo dose state.')
        self._appearance()
        mujoco.mj_setState(self.model, self.data, integration, STATE_SPEC)
        mujoco.mj_forward(self.model, self.data)
        self._check_state()

    def _check_state(self):
        m, d = self.model, self.data
        if not all(np.isfinite(values).all() for values in (d.qpos, d.qvel, d.qacc, d.ctrl, d.actuator_force)):
            raise RuntimeError('Nonfinite actuator state.')
        low, high = m.jnt_range[self.joints].T
        qpos = d.qpos[self.qaddrs]
        if np.any(qpos < low - 1e-6) or np.any(qpos > high + 1e-6):
            raise RuntimeError('Simulated arm crossed a joint bound.')

    def _step(self):
        previous_time = self.data.time
        mujoco.mj_step(self.model, self.data)
        if not np.isclose(self.data.time, previous_time + self.model.opt.timestep, rtol=0, atol=1e-9):
            raise RuntimeError('MuJoCo integration time did not advance by one timestep.')
        self._check_state()

    def _xyz(self):
        # Evaluate geometry at the integrated state, as mj_step updates qpos last.
        mujoco.mj_kinematics(self.model, self.data)
        return self.data.site_xpos[self.site].copy()

    def _log(self, event, **fields):
        self.trace.append({'event': event, 'simulation_seconds': round(self.data.time, 6), **fields})

    def _move(self, target, phase, frame):
        d, m = self.data, self.model
        goal = self.goals[target]
        low, high = m.actuator_ctrlrange[self.actuators].T
        if not np.isfinite(goal).all() or np.any(goal < low) or np.any(goal > high):
            raise RuntimeError(f'Actuator target {target} is outside control limits.')
        dt = m.opt.timestep
        cmd = d.ctrl[self.actuators].copy()
        started = d.time
        for _ in range(round(MAX_MOVE_S / dt)):
            cmd += np.clip(goal - cmd, -dt, dt)  # Ramp setpoints at at most 1 rad/s.
            d.ctrl[self.actuators] = cmd
            self._step()
            frame(phase)
            error = float(np.max(np.abs(d.qpos[self.qaddrs] - goal)))
            speed = float(np.max(np.abs(d.qvel[self.vaddrs])))
            if np.max(np.abs(cmd - goal)) < 1e-8 and error < JOINT_ERROR_RAD and speed < JOINT_SPEED_RAD_S:
                self._log('motion_converged', phase=phase, target=target, elapsed_seconds=round(d.time-started, 6),
                          max_joint_error_rad=error, max_joint_speed_rad_s=speed, goal_rad=goal.tolist(),
                          joint_position_rad=d.qpos[self.qaddrs].tolist(), actuator_control_rad=cmd.tolist(),
                          actuator_force=d.actuator_force[self.actuators].tolist(), gripper_xyz_m=self._xyz().tolist())
                return
        raise RuntimeError(f'Actuator target {target} failed to converge within {MAX_MOVE_S} simulated seconds '
                           f'(error {error:.4f} rad, speed {speed:.4f} rad/s).')

    def execute(self, condition, frame, *, action_enabled=True):
        if condition not in CONDITIONS or self.condition is not None:
            raise ValueError('A supported source condition requires a fresh apparatus.')
        self.condition = condition
        self._log('source_prepared', source_condition=condition, dose_count=0)
        frame('prepare_source')
        self._move('ABOVE_A', 'approach_paddle', frame)
        # The imported paddle is fixed in the world. Use its actual top surface as the goal.
        press_xyz = self.pad.pos + [0., 0., self.pad.size[1]]
        clearance = float(np.linalg.norm(self._xyz() - press_xyz))
        self._move('GRASP_A', 'press_paddle', frame)
        xyz = self._xyz()
        distance = float(np.linalg.norm(xyz - press_xyz))
        engaged = distance < PRESS_DISTANCE_M and clearance > 2 * PRESS_DISTANCE_M
        self._log('paddle_engagement', geometric_engagement=engaged, action_enabled=action_enabled,
                  approach_distance_m=clearance, engagement_distance_m=distance,
                  threshold_m=PRESS_DISTANCE_M, paddle_target_xyz_m=press_xyz.tolist(),
                  measured_gripper_xyz_m=xyz.tolist())
        if not engaged:
            raise RuntimeError('Gripper did not geometrically engage the metering paddle.')
        frame('paddle_engaged')
        if action_enabled:
            self._dispense(frame)
        self._move('ABOVE_A', 'release_paddle', frame)
        if np.linalg.norm(self._xyz() - press_xyz) <= 2 * PRESS_DISTANCE_M:
            raise RuntimeError('Gripper did not clear the metering paddle.')
        self._move('HOME', 'return_home', frame)
        self._log('trial_complete', dose_count=self.doses)

    def _dispense(self, frame):
        # Illustrative droplet flight after the geometric trigger. Apply the dose when it reaches the surface.
        self.pad.pos[2] = self.pad_rest_z - .0025
        self.drop.rgba[:] = [.38, .76, .95, 1]
        self._log('dose_released', trigger='geometric_gripper_paddle_engagement', dose_ml=DROP_ML)
        steps = round(.20 / self.model.opt.timestep)
        for z in np.linspace(self.drop_start_z, self.liquid.pos[2] + self.liquid.size[1], steps):
            self.data.mocap_pos[self.drop_mocap, 2] = z
            self._step()
            frame('dispense_drop')
        self.drop.rgba[3] = 0
        self.pad.pos[2] = self.pad_rest_z
        self.doses += 1
        self._appearance()
        self._log('dose_delivered', dose_count=self.doses, dose_ml=DROP_ML)
        frame('indicator_response')
