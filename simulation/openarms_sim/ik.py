"""Works out placeholder joint poses for each station from the bench layout.

The real poses are recorded on the real arm with the leader arm. Until that is
done, this module solves for poses that put the simulated gripper where the
bench layout says the cups are, so the rest of the pipeline has something to
run on. Run it with:

    python -m openarms_sim.ik --setup block

It rewrites that setup's poses.json and marks it as a placeholder.
"""

from __future__ import annotations

import json
import math

import mujoco
import numpy as np
from scipy.optimize import least_squares

import argparse

from .config import ARM_JOINTS, load_bench, load_joint_map, poses_path, setup_name
from .joints import JointMap
from .scene import Scene, build_scene

UP = np.array([0.0, 0.0, 1.0])
PAN_AXIS_XY = np.array([0.0388, 0.0])

# Rest pose, in model radians: folded back, clear of the stations and the camera view.
HOME_MODEL = [0.0, -1.45, 1.35, 1.0, math.pi / 2]


def solve(scene: Scene, target: np.ndarray, roll: float, seed=None) -> tuple[np.ndarray, float]:
    """Joint angles (model radians) that put the grasp point at `target` with the
    gripper horizontal and its jaw axis rolled `roll` radians out of the table plane.
    Returns the angles and the remaining position error in metres."""
    m, d = scene.model, scene.data
    lo = np.array([m.jnt_range[m.joint(j).id][0] for j in ARM_JOINTS]) + 0.02
    hi = np.array([m.jnt_range[m.joint(j).id][1] for j in ARM_JOINTS]) - 0.02
    pan_guess = math.atan2(target[1] - PAN_AXIS_XY[1], target[0] - PAN_AXIS_XY[0])

    def frame(q):
        for adr, v in zip(scene.arm_qadr, q):
            d.qpos[adr] = v
        mujoco.mj_kinematics(m, d)
        R = d.site_xmat[scene.grasp_site].reshape(3, 3)
        return d.site_xpos[scene.grasp_site].copy(), R[:, 0].copy(), R[:, 2].copy()

    def residual(q):
        p, x, z = frame(q)
        t = np.cross(UP, x)
        return np.concatenate(
            [(p - target) / 0.001, [x[2] / 0.01, (z[2] - math.sin(roll)) / 0.01, (z @ t - math.cos(roll)) / 0.01]]
        )

    best = None
    seeds = [seed] if seed is not None else []
    # The model's pan joint turns clockwise for positive angles, so try both signs.
    for pan in (-pan_guess, pan_guess):
        for r in (roll, roll - 2 * math.pi, roll + 2 * math.pi, -roll):
            seeds.append([pan, 0.2, 0.6, -0.8, r])
            seeds.append([pan, -0.6, 1.2, -0.6, r])
    for s in seeds:
        s = np.clip(np.asarray(s, dtype=float), lo, hi)
        res = least_squares(residual, s, bounds=(lo, hi))
        if best is None or res.cost < best.cost:
            best = res
        if best.cost < 1e-6:
            break
    p, _, _ = frame(best.x)
    return best.x, float(np.linalg.norm(p - target))


def make_poses(scene: Scene) -> tuple[dict[str, list[float]], dict[str, float]]:
    """Returns {pose_name: model radians} and {pose_name: position error in metres}."""
    b = scene.bench
    poses: dict[str, list[float]] = {"HOME": list(HOME_MODEL)}
    errors: dict[str, float] = {}
    theta = math.radians(b.tip_angle_deg)
    level = math.radians(b.wrist_roll_deg)  # the wrist roll that holds the cup upright

    def add(name, target, roll, seed=None):
        q, err = solve(scene, np.asarray(target, dtype=float), roll, seed)
        poses[name], errors[name] = [float(v) for v in q], err
        return q

    for s in b.sources + b.points:
        x, y = b.stations[s].pos
        grip_height = b.grasp_height + b.dock_height
        grasp = add(f"GRASP_{s}", [x, y, grip_height], level)
        above = add(f"ABOVE_{s}", [x, y, grip_height + b.lift], level, seed=grasp)
        poses[f"LIFT_{s}"], errors[f"LIFT_{s}"] = list(poses[f"ABOVE_{s}"]), errors[f"ABOVE_{s}"]
        del above

    # The held cup's mouth is this far from the grasp point, along the cup's axis.
    mouth = b.cup_height - b.grasp_height
    for r in b.receivers:
        rx, ry = b.stations[r].pos
        approach = np.array([rx - PAN_AXIS_XY[0], ry - PAN_AXIS_XY[1], 0.0])
        approach /= np.linalg.norm(approach)
        tangent = np.cross(UP, approach)
        best = None
        for direction in ((float(b.tip_direction),) if b.tip_direction else (-1.0, 1.0)):  # which way the wrist rolls to tip the cup
            roll = level + direction * theta
            # Cup axis after rolling about the approach axis.
            axis = math.cos(theta) * UP + direction * math.sin(theta) * np.cross(approach, UP)
            side = np.array([axis[0], axis[1], 0.0])
            if b.pour_offset and np.linalg.norm(side) > 1e-6:
                side_unit = side / np.linalg.norm(side)
            else:
                side_unit = np.zeros(3)
            # The mouth ends up `pour_offset` short of the centre, on the side the cup comes from.
            g = np.array([rx, ry, 0.0]) - b.pour_offset * side_unit - mouth * side
            g[2] = b.dock_height + b.receiver_height + b.pour_clearance - mouth * axis[2]
            q_tip, e_tip = solve(scene, g, roll)
            q_above, e_above = solve(scene, g, level, seed=[*q_tip[:4], q_tip[4] - direction * theta])
            score = e_tip + e_above
            if best is None or score < best[0]:
                best = (score, q_tip, e_tip, q_above, e_above)
        _, q_tip, e_tip, q_above, e_above = best
        poses[f"ABOVE_{r}"], errors[f"ABOVE_{r}"] = [float(v) for v in q_above], e_above
        poses[f"TIP_{r}"], errors[f"TIP_{r}"] = [float(v) for v in q_tip], e_tip
        del tangent
    return poses, errors


def main() -> None:
    ap = argparse.ArgumentParser(description="Solve placeholder poses for a setup.")
    ap.add_argument("--setup", help="block or liquid (default: the active setup)")
    setup = setup_name(ap.parse_args().setup)
    scene = build_scene(load_bench(setup))
    jm = JointMap(load_joint_map())
    poses, errors = make_poses(scene)
    out = {
        "source": "placeholder",
        "note": (
            f"Solved from bench.yaml by `python -m openarms_sim.ik --setup {setup}`; not recorded on the real arm. "
            "Replace with recorded poses and set source to 'recorded'."
        ),
        "units": "degrees per arm joint, as LeRobot reports them (use_degrees=true)",
        "poses": {name: jm.pose_from_model(q) for name, q in poses.items()},
    }
    path = poses_path(setup)
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {path}")
    for name in poses:
        err = errors.get(name)
        flag = "" if err is None or err < 0.003 else "   <-- cannot reach"
        print(f"  {name:10s} {'' if err is None else f'{err * 1000:6.1f} mm'}{flag}")


if __name__ == "__main__":
    main()
