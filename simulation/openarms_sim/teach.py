"""Turns one recording of the real arm into a setup the simulation can plan in.

    python -m openarms_sim.teach recordings/block_A_B

You show the arm two spots by moving an object from one to the other with the
leader arm. This reads that take and writes config/setups/taught/:

- bench.yaml: point A where the gripper closed, point B where it opened. No
  ruler: the arm's own joint angles say where the spots are.
- poses.json: HOME (where the arm came to rest), GRASP_A and GRASP_B (the real
  joint angles at those two moments), and ABOVE_A, ABOVE_B (worked out by the
  simulation: the same grip, lifted straight up).

After that the simulation can plan moves you never recorded, such as B to A:

    python -m openarms_sim --setup taught --from B --to A --objects '{"block": "B"}'
"""

from __future__ import annotations

import argparse
import json

import mujoco
import numpy as np
import yaml
from scipy.optimize import least_squares

from .config import ARM_JOINTS, CONFIG_DIR, load_joint_map
from .joints import JointMap
from .recording import _empty_bench, bench_from_recording, find_hold, load_recording
from .scene import build_scene

LIFTS = (0.07, 0.06, 0.05, 0.04, 0.03)  # tried in order until the arm can reach


def lifted_pose(scene, q_grasp: np.ndarray, lift: float) -> tuple[np.ndarray, float]:
    """Joint angles (model radians) for the same grip as `q_grasp`, `lift` metres higher.
    Returns the angles and how far short of the target the grasp point ends up, in metres."""
    m, d = scene.model, scene.data

    def frame(q):
        for adr, v in zip(scene.arm_qadr, q):
            d.qpos[adr] = v
        mujoco.mj_kinematics(m, d)
        R = d.site_xmat[scene.grasp_site].reshape(3, 3)
        return d.site_xpos[scene.grasp_site].copy(), R[:, 0].copy(), R[:, 2].copy()

    p0, x0, z0 = frame(q_grasp)
    target = p0 + np.array([0.0, 0.0, lift])
    span = np.radians(15)
    lo = np.array([min(m.jnt_range[m.joint(j).id][0], q - span) for j, q in zip(ARM_JOINTS, q_grasp)])
    hi = np.array([max(m.jnt_range[m.joint(j).id][1], q + span) for j, q in zip(ARM_JOINTS, q_grasp)])

    def residual(q):
        p, x, z = frame(q)
        # Position matters most; keeping the gripper at the same angle matters less.
        return np.concatenate([(p - target) / 0.001, (x - x0) / 0.05, (z - z0) / 0.05])

    res = least_squares(residual, q_grasp, bounds=(lo, hi))
    p, _, _ = frame(res.x)
    return res.x, float(np.linalg.norm(p - target))


def teach(path, setup: str = "taught", block_size=None) -> dict:
    rec = load_recording(path)
    jm = JointMap(load_joint_map())
    close, release = find_hold(rec)
    bench, facts = bench_from_recording(rec, jm, close, release, block_size)
    probe = build_scene(_empty_bench())

    def model(row):
        return np.array(jm.pose_to_model(dict(zip(ARM_JOINTS, row[:5]))))

    def real(q):
        return jm.pose_from_model([float(v) for v in q])

    def recorded(row):
        return {j: round(float(v), 2) for j, v in zip(ARM_JOINTS, row[:5])}

    rest = np.median(rec.state[-rec.fps // 2 :], axis=0)  # where the arm settled at the end
    poses = {"HOME": recorded(rest), "GRASP_A": recorded(rec.state[close]), "GRASP_B": recorded(rec.state[release])}
    taught = ["HOME", "GRASP_A", "GRASP_B"]
    grasp_q = {"A": model(rec.state[close]), "B": model(rec.state[release])}

    # The object stood on the table when it was picked up, so the pick sets the grasp height.
    # If it was let go from a little higher, lower GRASP_B to that same height; otherwise a
    # move that picks up at B would hold the object higher and push it into the table at A.
    drop = (facts["place"]["xyz_cm"][2] - facts["pick"]["xyz_cm"][2]) / 100
    levelled = None
    if abs(drop) > 0.005:
        q, err = lifted_pose(probe, grasp_q["B"], -drop)
        if err < 0.004:
            grasp_q["B"], poses["GRASP_B"] = q, real(q)
            taught.remove("GRASP_B")
            levelled = round(drop * 100, 1)

    lifts = {}
    for name in ("A", "B"):
        for lift in LIFTS:
            q, err = lifted_pose(probe, grasp_q[name], lift)
            if err < 0.004:
                break
        else:
            raise ValueError(f"the simulated arm cannot lift straight up from {name}; it is at the edge of its reach")
        poses[f"ABOVE_{name}"] = poses[f"LIFT_{name}"] = real(q)
        lifts[name] = lift

    g = rec.state[:, 5]
    hold = slice(close, release)
    gripper = {
        "open_value": round(float(np.max(g[max(0, close - 2 * rec.fps) : close])), 1),
        "closed_value": round(float(np.median(g[hold])), 1),
        "closed_command": round(float(np.median(rec.action[hold, 5])), 1),
    }

    folder = CONFIG_DIR / "setups" / setup
    folder.mkdir(parents=True, exist_ok=True)
    obj = bench.objects["block"]
    bench_yaml = {
        "table": {"size": [round(float(v), 3) for v in bench.table_size], "center": [round(float(v), 3) for v in bench.table_center]},
        "stations": {n: {"kind": "point", "pos": [round(float(v), 4) for v in s.pos]} for n, s in bench.stations.items()},
        "objects": {"block": {"size": [round(float(v), 4) for v in obj.size], "at": "A", "color": [float(c) for c in obj.color]}},
        "grasp": {
            "height": round(float(bench.grasp_height), 4),
            "lift": float(min(lifts.values())),
            "release_tolerance": 0.03,
            "grasp_tolerance": 0.03,
        },
    }
    header = (
        f"# Taught from {path} by `python -m openarms_sim.teach`. Do not edit by hand; re-run teach.\n"
        "# Positions are where the simulation places the real arm's gripper at the pick (A) and the\n"
        "# place (B). They were not measured with a ruler, and they shift if joint_map.yaml changes.\n"
        + ("" if block_size else "# The block's size is a guess. Pass --block-size WIDTH_CM HEIGHT_CM to teach.\n")
    )
    (folder / "bench.yaml").write_text(header + yaml.safe_dump(bench_yaml, sort_keys=False))
    pose_file = {
        "source": "taught",
        "note": (
            f"The poses listed under 'taught' are real joint readings from {path}. The others were "
            "worked out by the simulation and have not been run on the real arm."
            + (
                f" GRASP_B was lowered {levelled} cm from the recorded release, because the simulation "
                "shows the object being let go that far above the table."
                if levelled
                else ""
            )
        ),
        "units": "degrees per arm joint, as LeRobot reports them (use_degrees=true)",
        "taught": taught,
        "gripper": gripper,
        "poses": poses,
    }
    (folder / "poses.json").write_text(json.dumps(pose_file, indent=2) + "\n")
    return {
        "setup": setup,
        "folder": str(folder),
        **facts,
        "grasp_b_lowered_cm": levelled,
        "lift_cm": {k: round(v * 100, 1) for k, v in lifts.items()},
        "gripper": gripper,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Teach the simulation points A and B from a recording of the real arm.")
    ap.add_argument("path", help="the folder given to lerobot-record as --dataset.root")
    ap.add_argument("--setup", default="taught", help="name of the setup to write (default: taught)")
    ap.add_argument("--block-size", nargs=2, type=float, metavar=("WIDTH_CM", "HEIGHT_CM"), help="if you know it")
    a = ap.parse_args()
    size = (a.block_size[0] / 100, a.block_size[1] / 100) if a.block_size else None
    print(json.dumps(teach(a.path, a.setup, size), indent=2))


if __name__ == "__main__":
    main()
