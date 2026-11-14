"""Measures config/joint_map.yaml on the real arm, without a ruler.

The idea: the table is flat. Every time the tip of the gripper touches the table, the
model must put the lowest point of the gripper at table height. Touch the table in a
few different places and postures, and the shoulder-lift, elbow and wrist offsets
(and the height of the arm's base above the table) are the values that make all of
those touches land on one plane.

    source env.sh
    python -m openarms_sim.calibrate collect --port /dev/tty.usbmodemXXXX   # at the bench
    python -m openarms_sim.calibrate fit                                    # anywhere
    python -m openarms_sim.calibrate fit --write                            # save joint_map.yaml

`collect` switches the follower's motors off so the arm can be moved by hand. It never
sends a motion command. Shoulder pan and wrist roll are not measured: turning the whole
arm about its base does not change any height, and roll barely does.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from pathlib import Path

import mujoco
import numpy as np
import yaml

from .config import ARM_JOINTS, CONFIG_DIR, SIM_ROOT, load_joint_map

SAMPLES = CONFIG_DIR / "joint_map_samples.json"
FITTED = ("shoulder_lift", "elbow_flex", "wrist_flex")
TIP_BODIES = ("gripper", "moving_jaw_so101_v1")
GOOD_MM, USABLE_MM = 5.0, 10.0  # how flat the fitted touches must be


class Arm:
    """The bare arm model, for kinematics only."""

    def __init__(self):
        self.m = mujoco.MjModel.from_xml_path(str(SIM_ROOT / "models" / "so101" / "so101_new_calib.xml"))
        self.d = mujoco.MjData(self.m)
        self.qadr = [self.m.joint(j).qposadr[0] for j in ARM_JOINTS]
        self.gadr = self.m.joint("gripper").qposadr[0]
        self.tip = []  # (geom id, mesh vertices) for everything that can touch the table
        for g in range(self.m.ngeom):
            if self.m.body(self.m.geom_bodyid[g]).name in TIP_BODIES and self.m.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH:
                mid = self.m.geom_dataid[g]
                a, n = self.m.mesh_vertadr[mid], self.m.mesh_vertnum[mid]
                self.tip.append((g, self.m.mesh_vert[a : a + n].copy()))

    def lowest(self, q_deg: np.ndarray, jaw_rad: float) -> float:
        """Height (m) of the lowest point of the gripper for model joint angles in degrees."""
        for adr, v in zip(self.qadr, q_deg):
            self.d.qpos[adr] = math.radians(v)
        self.d.qpos[self.gadr] = jaw_rad
        mujoco.mj_kinematics(self.m, self.d)
        low = math.inf
        for g, verts in self.tip:
            z = self.d.geom_xpos[g][2] + verts @ self.d.geom_xmat[g].reshape(3, 3)[2]
            low = min(low, float(z.min()))
        return low


def _model_angles(rows: np.ndarray, signs: dict, offsets: dict) -> np.ndarray:
    out = rows[:, :5].copy()
    for i, j in enumerate(ARM_JOINTS):
        out[:, i] = signs.get(j, 1) * rows[:, i] + offsets.get(j, 0.0)
    return out


def _jaw(cfg: dict, value: float) -> float:
    g = cfg["gripper"]
    return math.radians(g["closed_deg"] + (g["open_deg"] - g["closed_deg"]) * value / 100.0)


def fit(rows: np.ndarray, cfg: dict | None = None, arm: Arm | None = None, like: dict | None = None) -> dict:
    """Signs and offsets that put every touch on one plane.

    rows: N x 6, the follower's readings (degrees, gripper 0..100) at each touch."""
    from scipy.optimize import least_squares

    cfg = cfg or load_joint_map()
    arm = arm or Arm()
    rows = np.asarray(rows, dtype=float)
    if len(rows) < 6:
        raise ValueError(f"need at least 6 touches to fit 4 numbers; got {len(rows)}")
    base_signs = {j: cfg["joints"][j]["sign"] for j in ARM_JOINTS}
    base_off = {j: cfg["joints"][j]["offset_deg"] for j in ARM_JOINTS}
    jaws = [_jaw(cfg, r[5]) for r in rows]

    def residuals(x, signs):
        off = {**base_off, **dict(zip(FITTED, x[:3]))}
        q = _model_angles(rows, signs, off)
        return np.array([arm.lowest(q[i], jaws[i]) - x[3] for i in range(len(rows))])

    best = None
    # `like` is an earlier result: keep its directions and start from its numbers (quick refit).
    combos = [tuple(like["signs"][j] for j in FITTED)] if like else list(itertools.product((1, -1), repeat=len(FITTED)))
    starts = ([(*[like["offset_deg"][j] for j in FITTED], like["table_height_cm"] / 100)] if like
              else [(0, 0, 0, 0), (10, -10, 10, 0), (-10, 10, -10, 0)])
    for combo in combos:
        signs = {**base_signs, **dict(zip(FITTED, combo))}
        for start in starts:
            sol = least_squares(residuals, np.array(start, float), args=(signs,),
                                bounds=([-45, -45, -45, -0.05], [45, 45, 45, 0.15]), x_scale=[10, 10, 10, 0.01])
            rms = float(np.sqrt(np.mean(sol.fun**2)))
            if best is None or rms < best["rms_m"] - 1e-6:
                best = {"signs": signs, "x": sol.x, "rms_m": rms, "res": sol.fun, "jac": sol.jac}
    x = best["x"]
    # How well the touches pin each number down: a flat direction means the postures were too alike.
    try:
        cov = np.linalg.inv(best["jac"].T @ best["jac"]) * max(best["rms_m"], 1.5e-3) ** 2
        spread = np.sqrt(np.diag(cov))
    except np.linalg.LinAlgError:
        spread = np.full(4, np.inf)
    before = residuals(np.array([base_off[j] for j in FITTED] + [x[3]]), base_signs)
    return {
        "signs": {j: int(best["signs"][j]) for j in FITTED},
        "offset_deg": {j: round(float(v), 2) for j, v in zip(FITTED, x[:3])},
        "table_height_cm": round(float(x[3]) * 100, 2),
        "rms_mm": round(best["rms_m"] * 1000, 2),
        "worst_mm": round(float(np.max(np.abs(best["res"]))) * 1000, 2),
        "residuals_mm": [round(float(r) * 1000, 1) for r in best["res"]],
        "uncertainty_deg": {j: round(float(s), 2) for j, s in zip(FITTED, spread[:3])},
        "before_rms_mm": round(float(np.sqrt(np.mean((before - before.mean()) ** 2))) * 1000, 2),
        "touches": len(rows),
    }


def verdict(result: dict) -> tuple[str, str]:
    worst_unc = max(result["uncertainty_deg"].values())
    if not math.isfinite(worst_unc) or worst_unc > 3.5:
        return "poor", ("The touches do not pin the offsets down (the postures were too alike). "
                        "Collect again with more variety: near and far, wrist bent and straight.")
    if result["rms_mm"] <= GOOD_MM:
        return "good", f"All touches lie within {result['rms_mm']} mm (RMS) of one flat table."
    if result["rms_mm"] <= USABLE_MM:
        return "usable", (f"Touches lie within {result['rms_mm']} mm (RMS) of one flat table. Usable; "
                          "a careful second collection may tighten it.")
    return "poor", (f"Touches are {result['rms_mm']} mm (RMS) off one flat table. One or more touches were "
                    "probably not on the table, or the table is not level with the arm's base.")


def write_joint_map(result: dict) -> Path:
    """Updates joint_map.yaml in place, keeping its other settings."""
    path = CONFIG_DIR / "joint_map.yaml"
    cfg = yaml.safe_load(path.read_text())
    for j in FITTED:
        cfg["joints"][j] = {"sign": result["signs"][j], "offset_deg": result["offset_deg"][j]}
    cfg["measured"] = True
    cfg["measurement"] = {
        "method": "table touches (python -m openarms_sim.calibrate)",
        "touches": result["touches"], "rms_mm": result["rms_mm"], "worst_mm": result["worst_mm"],
        "table_height_cm": result["table_height_cm"],
        "not_measured": ["shoulder_pan", "wrist_roll"],
    }
    header = (
        "# How the real arm's joint readings map onto the MuJoCo model's joints.\n#\n"
        "#   model_angle_deg = sign * lerobot_deg + offset_deg\n#\n"
        "# STATUS: MEASURED for shoulder_lift, elbow_flex and wrist_flex, by touching the table\n"
        "# (python -m openarms_sim.calibrate). shoulder_pan and wrist_roll are the starting guess:\n"
        "# they do not change any height, so the table cannot measure them.\n"
        "# Re-run after recalibrating the arm in LeRobot, which moves every joint's zero.\n\n"
    )
    path.write_text(header + yaml.safe_dump(cfg, sort_keys=False))
    return path


HINTS = [
    "near the base, gripper upright",
    "far out, gripper leaning away from the base",
    "halfway out, gripper upright",
    "near the base, gripper leaning away from the base",
    "far out, gripper as upright as it goes",
    "halfway out, gripper leaning a lot",
]
MIN_TOUCHES, MAX_TOUCHES = 8, 16
ENOUGH_DEG = 2.5  # stop once every offset is pinned down this tightly
TOO_SIMILAR_DEG = 8.0


def collect(port: str, robot_id: str, count: int, out: Path) -> None:
    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

    robot = SO101Follower(SO101FollowerConfig(port=port, id=robot_id, disable_torque_on_disconnect=True))
    robot.connect(calibrate=False)
    if not robot.is_calibrated:
        robot.disconnect()
        raise SystemExit(f"{robot_id} is not calibrated: run `source env.sh` first.")
    names = [f"{j}.pos" for j in ARM_JOINTS] + ["gripper.pos"]
    cfg, arm = load_joint_map(), Arm()
    print("\nThe arm is about to go limp so you can move it by hand.")
    print("Make sure it is resting on the table or hold it, then press Enter.")
    input("> ")
    robot.bus.disable_torque()
    print("\nMotors are off. Each time: move the arm by hand until the tip of the gripper just")
    print("touches the table, hold still, press Enter. Make every touch look different from the")
    print("last: change how far out it is and how much the gripper leans. The hints are only ideas.")
    print("I will tell you when there are enough. Type q to finish early.\n")
    rows, result = [], None
    try:
        while len(rows) < min(count, MAX_TOUCHES):
            hint = HINTS[len(rows) % len(HINTS)]
            said = input(f"Touch {len(rows) + 1}: touch the table somewhere new (idea: {hint}). Enter> ").strip().lower()
            if said == "q":
                break
            reads = []
            for _ in range(5):  # a short average, and a check that the arm was held still
                obs = robot.get_observation()
                reads.append([float(obs[n]) for n in names])
                time.sleep(0.05)
            reads = np.array(reads)
            if np.ptp(reads[:, :5], axis=0).max() > 1.0:
                print("    The arm moved while reading. Hold it still and try again.")
                continue
            row = reads.mean(axis=0)
            # Only the joints that change the height count toward "different".
            twin = next((i for i, r in enumerate(rows) if np.abs(np.array(r)[1:4] - row[1:4]).max() < TOO_SIMILAR_DEG), None)
            if twin is not None:
                print(f"    That is almost the same posture as touch {twin + 1}. Change the reach or the lean and try again.")
                continue
            rows.append([round(float(v), 3) for v in row])
            if len(rows) < 6:
                print(f"    Saved. {6 - len(rows)} more before I can start checking.")
                continue
            try:
                result = fit(np.array(rows), cfg, arm, like=result if result and result["rms_mm"] < USABLE_MM else None)
            except Exception as e:  # a failed check must not lose the touches
                print(f"    Saved. (Could not check yet: {e})")
                continue
            loose = max(result["uncertainty_deg"].values())
            if result["rms_mm"] > USABLE_MM:
                print(f"    Saved, but the touches are {result['rms_mm']:.0f} mm off one flat table. "
                      "Was the last one really on the table? Keep going; a bad one can be outvoted.")
            elif len(rows) >= MIN_TOUCHES and loose <= ENOUGH_DEG:
                print(f"    Saved. That is enough: offsets pinned to about {loose:.1f} degrees, "
                      f"touches within {result['rms_mm']:.1f} mm of flat.")
                break
            else:
                print(f"    Saved. Offsets pinned to about {loose:.1f} degrees so far (aiming for {ENOUGH_DEG}). Keep going.")
    finally:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"robot_id": robot_id, "taken": time.strftime("%Y-%m-%d %H:%M"),
                                   "columns": names, "rows": rows}, indent=1))
        print(f"\n{len(rows)} touches saved to {out}")
        print("Rest the arm on the table now; its motors stay off.")
        input("Press Enter when it is resting> ")
        robot.disconnect()
    print("\nNext: python -m openarms_sim.calibrate fit")


def main() -> None:
    ap = argparse.ArgumentParser(description="Measure the joint map by touching the table.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="record table touches on the real arm (motors off, moved by hand)")
    c.add_argument("--port", required=True)
    c.add_argument("--id", default="my_awesome_follower_arm")
    c.add_argument("--count", type=int, default=MAX_TOUCHES, help="stop after this many even if more would help")
    c.add_argument("--out", type=Path, default=SAMPLES)
    f = sub.add_parser("fit", help="fit signs and offsets to the recorded touches")
    f.add_argument("--samples", type=Path, default=SAMPLES)
    f.add_argument("--write", action="store_true", help="save the result to config/joint_map.yaml")
    a = ap.parse_args()
    if a.cmd == "collect":
        collect(a.port, a.id, a.count, a.out)
        return
    rows = np.array(json.loads(a.samples.read_text())["rows"], dtype=float)
    result = fit(rows)
    grade, why = verdict(result)
    print(json.dumps(result, indent=1))
    print(f"\n{grade.upper()}: {why}")
    print(f"Before fitting, the same touches were {result['before_rms_mm']} mm (RMS) off flat.")
    if a.write:
        if grade == "poor":
            raise SystemExit("Not saved: the fit is not good enough to trust. Collect again.")
        print("Saved to", write_joint_map(result))
    else:
        print("Nothing saved. Add --write to save it to config/joint_map.yaml.")


if __name__ == "__main__":
    main()
