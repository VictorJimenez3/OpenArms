"""Corrects poses recorded on the real arm for a container that stands a little away from where it stood.

    echo '{"poses": {"GRASP_A": {"shoulder_pan.pos": ...}}, "shift_cm": {"GRASP_A": [-2.1, 0.9]}}' \\
        | python -m openarms_sim.shift

For each pose, the model works out where the gripper is, then solves for joint angles that put it
`shift_cm` (ruler centimetres) further along the table with the gripper pointing the same way. Only
the change in each joint is applied to the recorded pose:

    corrected = recorded + (model pose after the shift - model pose before)

so the recording keeps everything the real arm learned (how it actually grips and tips), and the
model only supplies how the joints must change to move that grip a few centimetres. While
config/joint_map.yaml is unmeasured the model's arm is not exactly the real one, so the change is
good to a few millimetres per centimetre of shift; small shifts come out closest.

A shift can also be three numbers, [dx, dy, dz]: dz raises (+) or lowers (-) the grip, in centimetres.

Prints {"poses": {...corrected...}, "error_mm": {...}, "turn_deg": {...}, "joint_change_deg": {...},
"grasp_cm": {name: [x, y, height]}}: grasp_cm is where the model puts the gripper's grasp point for every
pose given (shifted or not), in ruler centimetres, with its height above the arm's base plane.
"""

from __future__ import annotations

import json
import sys

import mujoco
import numpy as np
from scipy.optimize import least_squares

from .config import ARM_JOINTS, _read_yaml, load_joint_map, ruler_to_arm, setup_dir
from .joints import JointMap
from .recording import _empty_bench
from .scene import build_scene


def _frame(scene, q):
    m, d = scene.model, scene.data
    for adr, v in zip(scene.arm_qadr, q):
        d.qpos[adr] = v
    mujoco.mj_kinematics(m, d)
    return d.site_xpos[scene.grasp_site].copy(), d.site_xmat[scene.grasp_site].reshape(3, 3).copy()


def shift_pose(scene, q0, move_m, limits=None) -> tuple[np.ndarray, float, float]:
    """Model joint angles that move the grasp point by `move_m` (arm frame, metres) with the gripper
    tilted and rolled as before. Its heading may turn with the base: five joints cannot slide the
    gripper sideways and keep all three of its directions. Returns the angles, the position error (m)
    and how far the tilt or roll changed (degrees). `limits` is (low, high) model radians per joint: the
    real arm's calibrated range, which can be wider than the model's; without it the model's own is used."""
    m = scene.model
    q0 = np.asarray(q0, dtype=float)
    if limits is None:
        limits = ([m.jnt_range[m.joint(j).id][0] for j in ARM_JOINTS], [m.jnt_range[m.joint(j).id][1] for j in ARM_JOINTS])
    # A recorded pose can sit a hair past a limit; it is where the real arm was, so it stays allowed.
    lo, hi = np.minimum(limits[0], q0 - 0.01), np.maximum(limits[1], q0 + 0.01)
    p0, R0 = _frame(scene, q0)
    target = p0 + np.asarray(move_m, dtype=float)

    def aim(R):
        """Nose tilt, and the jaw axis's height and its part across the arm: what a turn of the base leaves alone."""
        x, z = R[:, 0], R[:, 2]
        t = np.cross([0.0, 0.0, 1.0], x)
        t /= max(np.linalg.norm(t), 1e-9)
        return np.array([x[2], z[2], z @ t])

    a0 = aim(R0)

    def residual(q):
        p, R = _frame(scene, q)
        return np.concatenate([(p - target) / 0.001, (aim(R) - a0) / 0.005, (q - q0) * 0.01])

    res = least_squares(residual, q0, bounds=(lo, hi))
    p, R = _frame(scene, res.x)
    turn = float(np.degrees(np.arcsin(min(1.0, float(np.abs(aim(R) - a0).max())))))
    return res.x, float(np.linalg.norm(p - target)), turn


def arm_to_ruler(xy_m, frame: dict) -> tuple[float, float]:
    """The inverse of config.ruler_to_arm: a point in the arm's frame (metres) as ruler centimetres."""
    ax, ay = (float(v) for v in frame["arm_cm"])
    h = np.radians(float(frame["arm_heading_deg"]))
    fx, fy = np.cos(h), np.sin(h)
    x, y = float(xy_m[0]), float(xy_m[1])
    return round(float(ax + 100 * (x * fx + y * fy)), 1), round(float(ay + 100 * (x * fy - y * fx)), 1)


def shift_poses(poses: dict, shift_cm: dict, setup: str = "demo", limits_deg: dict | None = None) -> dict:
    """`limits_deg`: {"shoulder_pan.pos": [low, high], ...} in the real arm's degrees (its calibrated range)."""
    frame = _read_yaml(setup_dir(setup) / "bench.yaml").get("ruler_frame")
    if not frame:
        raise ValueError(f"setup {setup} has no ruler_frame, so ruler centimetres mean nothing there")
    scene, jm = build_scene(_empty_bench()), JointMap(load_joint_map())
    origin = np.array(ruler_to_arm([0.0, 0.0], frame))
    limits = None
    if limits_deg:
        ends = [sorted((jm.to_model(j, limits_deg[f"{j}.pos"][0]), jm.to_model(j, limits_deg[f"{j}.pos"][1]))) for j in ARM_JOINTS]
        limits = ([e[0] for e in ends], [e[1] for e in ends])
    out, errors, turns, changes, grasp = {}, {}, {}, {}, {}

    def where(q):
        p, _ = _frame(scene, q)
        return [*arm_to_ruler(p[:2], frame), round(float(p[2]) * 100, 1)]

    for name, pose in poses.items():
        d = [float(v) for v in shift_cm.get(name, (0.0, 0.0))]
        dx, dy, dz = (d + [0.0])[:3]
        q0 = jm.pose_to_model({j: float(pose[f"{j}.pos"]) for j in ARM_JOINTS})
        if max(abs(dx), abs(dy), abs(dz)) < 1e-9:
            out[name] = dict(pose)
            grasp[name] = where(q0)
            continue
        move = np.array([*(np.array(ruler_to_arm([dx, dy], frame)) - origin), dz / 100.0])
        q1, err, turn = shift_pose(scene, q0, move, limits)
        grasp[name] = where(q1)
        before, after = jm.pose_from_model(q0), jm.pose_from_model([float(v) for v in q1])
        delta = {j: after[j] - before[j] for j in ARM_JOINTS}
        out[name] = {**pose, **{f"{j}.pos": round(float(pose[f"{j}.pos"]) + delta[j], 2) for j in ARM_JOINTS}}
        errors[name], turns[name] = round(err * 1000, 1), round(turn, 1)
        changes[name] = {j: round(v, 1) for j, v in delta.items()}
    return {"poses": out, "error_mm": errors, "turn_deg": turns, "joint_change_deg": changes,
            "grasp_cm": grasp, "joint_map_measured": jm.measured}


def main() -> None:
    req = json.load(sys.stdin)
    json.dump(shift_poses(req["poses"], req.get("shift_cm", {}), req.get("setup", "demo"), req.get("limits_deg")), sys.stdout)


if __name__ == "__main__":
    main()
