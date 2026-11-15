"""Solves arm poses for places given in ruler centimetres, for picking a loose object off the table.

    echo '{"places": {"A": [22.3, 7.6], "B": [10, 8]}}' | python -m openarms_sim.reach

For each place it solves a GRASP pose (the grasp point `height` above the table) and an ABOVE pose
(`lift` higher, same gripper tilt), and prints them in the real arm's units (degrees, as LeRobot
reports them):

    {"poses": {"GRASP_A": {"shoulder_pan.pos": ...}, "ABOVE_A": {...}, ...},
     "error_mm": {"GRASP_A": 0.2, ...}, "tilt_deg": 15, "unreachable": ["B"],
     "joint_map_measured": false}

The gripper is kept level where the arm can do that; where a level gripper would need the wrist to
bend past its limit, it tilts nose-down in steps until every place is reached. All places share one
tilt, so a thing picked up at one is set down upright at another.

The ruler frame (where the arm stands among the rulers) comes from a setup's bench.yaml. The poses
are worked out in the model and converted with config/joint_map.yaml; while that file says
measured: false, the real gripper can end up a couple of centimetres from the place asked for.
"""

from __future__ import annotations

import json
import math
import sys

import mujoco
import numpy as np
from scipy.optimize import least_squares

from .config import ARM_JOINTS, _read_yaml, load_joint_map, ruler_to_arm, setup_dir
from .ik import PAN_AXIS_XY, UP
from .joints import JointMap
from .recording import _empty_bench
from .scene import build_scene

REACHED_M = 0.003  # a solve further than this from its target did not reach it
TILTS_DEG = (0, 15, 30, 45, 60)  # nose-down tilts tried, level first
AIM_DEG = 3.0  # a solve whose gripper points further than this from the direction asked for did not reach it


def solve(scene, target, roll: float, tilt: float, seed=None) -> tuple[np.ndarray, float, float]:
    """Joint angles (model radians) putting the grasp point at `target`, the gripper pointing `tilt`
    radians below level and its jaw axis rolled `roll` radians. Returns them, the position error (m)
    and how far the gripper is from the direction asked for (degrees)."""
    m, d = scene.model, scene.data
    lo = np.array([m.jnt_range[m.joint(j).id][0] for j in ARM_JOINTS]) + 0.02
    hi = np.array([m.jnt_range[m.joint(j).id][1] for j in ARM_JOINTS]) - 0.02
    pan = math.atan2(target[1] - PAN_AXIS_XY[1], target[0] - PAN_AXIS_XY[0])

    def frame(q):
        for adr, v in zip(scene.arm_qadr, q):
            d.qpos[adr] = v
        mujoco.mj_kinematics(m, d)
        R = d.site_xmat[scene.grasp_site].reshape(3, 3)
        return d.site_xpos[scene.grasp_site].copy(), R[:, 0].copy(), R[:, 2].copy()

    def aim(q):
        """The three direction errors, each the sine of an angle: nose tilt, and the jaw axis's two parts."""
        _, x, z = frame(q)
        t = np.cross(UP, x)
        t /= max(np.linalg.norm(t), 1e-9)
        return np.array([x[2] + math.sin(tilt), z[2] - math.sin(roll) * math.cos(tilt), z @ t - math.cos(roll)])

    def residual(q):
        return np.concatenate([(frame(q)[0] - target) / 0.001, aim(q) / 0.01])

    seeds = [seed] if seed is not None else []
    for p in (-pan, pan):  # the model's pan joint turns clockwise for positive angles, so try both signs
        for r in (roll, roll - 2 * math.pi, -roll):
            seeds += [[p, 0.2, 0.6, -0.8, r], [p, -0.6, 1.2, -0.6, r], [p, 0.6, 0.2, 0.6, r]]
    best = None
    for s in seeds:
        res = least_squares(residual, np.clip(np.asarray(s, dtype=float), lo, hi), bounds=(lo, hi))
        if best is None or res.cost < best.cost:
            best = res
        if best.cost < 1e-6:
            break
    off = float(np.degrees(np.arcsin(min(1.0, float(np.abs(aim(best.x)[:2]).max())))))
    return best.x, float(np.linalg.norm(frame(best.x)[0] - target)), off


def solve_places(places: dict, setup: str = "demo", height: float = 0.03, lift: float = 0.09, roll_deg: float = 180.0) -> dict:
    frame = _read_yaml(setup_dir(setup) / "bench.yaml").get("ruler_frame")
    if not frame:
        raise ValueError(f"setup {setup} has no ruler_frame, so ruler centimetres mean nothing there")
    scene, jm = build_scene(_empty_bench()), JointMap(load_joint_map())
    roll = math.radians(roll_deg)
    arm_m = {name: list(ruler_to_arm(cm, frame)) for name, cm in places.items()}

    def attempt(tilt_deg):
        """Every place solved with the same nose tilt, so a thing picked up at one is set down upright at another."""
        tilt, found, missed = math.radians(tilt_deg), {}, []
        for name, (x, y) in arm_m.items():
            grasp, e_grasp, a_grasp = solve(scene, np.array([x, y, height]), roll, tilt)
            above, e_above, a_above = solve(scene, np.array([x, y, height + lift]), roll, tilt, seed=grasp)
            found[name] = (grasp, e_grasp, above, e_above)
            # The arm goes straight down from ABOVE to GRASP. A solve that swings the shoulder or flips the
            # wrist between the two is a different arm shape, not a descent, and is not offered.
            swing = abs(math.degrees(grasp[0] - above[0])) > 5 or abs(math.degrees(grasp[4] - above[4])) > 20
            if max(e_grasp, e_above) > REACHED_M or max(a_grasp, a_above) > AIM_DEG or swing:
                missed.append(name)
        return tilt_deg, found, missed

    best = None
    for tilt_deg in TILTS_DEG:
        tried = attempt(tilt_deg)
        if best is None or len(tried[2]) < len(best[2]):
            best = tried
        if not best[2]:
            break
    tilt_deg, found, unreachable = best
    poses, errors = {}, {}
    for name, (grasp, e_grasp, above, e_above) in found.items():
        for pose, q, err in ((f"GRASP_{name}", grasp, e_grasp), (f"ABOVE_{name}", above, e_above)):
            poses[pose] = {f"{j}.pos": v for j, v in jm.pose_from_model([float(v) for v in q]).items()}
            errors[pose] = round(err * 1000, 1)
    return {"poses": poses, "error_mm": errors, "tilt_deg": tilt_deg, "unreachable": unreachable, "arm_m": arm_m,
            "arm_cm": list(frame["arm_cm"]), "joint_map_measured": jm.measured}


def main() -> None:
    req = json.load(sys.stdin)
    out = solve_places(req["places"], req.get("setup", "demo"), float(req.get("height", 0.03)),
                       float(req.get("lift", 0.09)), float(req.get("roll_deg", 180.0)))
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
