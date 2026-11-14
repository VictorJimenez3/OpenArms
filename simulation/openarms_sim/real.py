"""Runs a plan from the simulation on the real follower arm.

    source env.sh        # from the repo root, so the arm's calibration loads
    python -m openarms_sim.real --port /dev/tty.usbmodemXXXX \\
        --setup taught --from B --to A --objects '{"block": "B"}'

The same motion the preview shows is converted to the real arm's units and
sent to the motors 30 times a second. What it does, in order:

1. Simulates the plan. If the preview blocks it, nothing is sent.
2. Connects, and checks the arm is resting near HOME.
3. Waits for you to press ENTER, then streams the motion.
4. Ends at HOME, the arm's rest pose, and switches the motors off.

Ctrl+C stops the motion. The arm holds where it is until you press ENTER,
then the motors switch off, so support the arm first.

Start slow: --speed 0.5 is the default. Use --dry-run to see what would be
sent without connecting to anything.

NOT YET RUN ON THE REAL ARM as of writing.
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from .__main__ import add_plan_arguments, plan_from_arguments
from .config import ARM_JOINTS, load_bench, load_joint_map, load_pose_file, setup_name
from .joints import JointMap
from .motion import Segment, blend, build_segments, expand_plan, go_to_duration
from .preview import preview

FPS = 30
NEAR_HOME_DEG = 15.0  # the arm must start this close to HOME, per joint
MAX_STEP_DEG = 20.0  # LeRobot refuses to command a joint further than this from where it is


def targets_from_segments(segments: list[Segment], jm: JointMap, speed: float) -> list[dict[str, float]]:
    """One command per tick, in the units LeRobot's send_action expects."""
    out = []
    for seg in segments:
        n = max(1, round(seg.duration / speed * FPS))
        for k in range(1, n + 1):
            u = blend(k / n)
            q = seg.q0 + (seg.q1 - seg.q0) * u
            grip = seg.grip0 + (seg.grip1 - seg.grip0) * u
            cmd = {f"{j}.pos": jm.from_model(j, float(v)) for j, v in zip(ARM_JOINTS, q)}
            cmd["gripper.pos"] = float(np.clip(jm.gripper_command(grip), 0, 100))
            out.append(cmd)
    return out


def plan_targets(plan: dict, setup: str, speed: float) -> tuple[list[dict[str, float]], dict[str, float], JointMap]:
    """The commands for a plan, the HOME pose in real units, and the joint map used."""
    pose_file = load_pose_file(setup)
    jm = JointMap(load_joint_map())
    jm.use_taught_gripper(pose_file.get("gripper"))
    segments = build_segments(expand_plan(plan), pose_file["poses"], jm, load_bench(setup).stations)
    return targets_from_segments(segments, jm, speed), pose_file["poses"]["HOME"], jm


def _fmt(cmd: dict[str, float]) -> str:
    return " ".join(f"{cmd[f'{j}.pos']:7.1f}" for j in ARM_JOINTS) + f"  grip {cmd['gripper.pos']:5.1f}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Run a simulated plan on the real follower arm.")
    add_plan_arguments(ap)
    ap.add_argument("--port", help="the follower arm's port (not needed with --dry-run)")
    ap.add_argument("--id", default="my_awesome_follower_arm")
    ap.add_argument("--speed", type=float, default=0.5, help="1.0 is the speed shown in the preview (default 0.5)")
    ap.add_argument("--dry-run", action="store_true", help="print what would be sent; do not connect")
    ap.add_argument("--force", action="store_true", help="run even if the preview blocks the plan")
    ap.add_argument("--yes", action="store_true", help="do not wait for ENTER before moving")
    a = ap.parse_args()
    if not 0.05 <= a.speed <= 1.5:
        ap.error("--speed must be between 0.05 and 1.5")
    setup = setup_name(a.setup)
    plan, objects, contents = plan_from_arguments(a)

    # 1. The simulation has the first say.
    result = preview(plan, contents, objects, render=False, setup=setup)
    for w in result["warnings"]:
        print(f"  preview: {w}")
    if not result["ok"] and not a.force:
        raise SystemExit("The preview blocks this plan, so nothing was sent to the arm. (--force overrides.)")
    if load_pose_file(setup).get("source", "placeholder") == "placeholder" and not a.force:
        raise SystemExit(
            f"The '{setup}' setup has placeholder poses that were never on the real arm. "
            "Teach a setup from a recording first (python -m openarms_sim.teach), or pass --force."
        )

    targets, home, jm = plan_targets(plan, setup, a.speed)
    seconds = len(targets) / FPS
    arr = np.array([[c[f"{j}.pos"] for j in ARM_JOINTS] for c in targets])
    fastest = float(np.max(np.abs(np.diff(arr, axis=0)))) * FPS if len(arr) > 1 else 0.0
    print(f"\nPlan: {plan.get('student_instruction') or plan['steps']}")
    print(f"Setup '{setup}', {len(targets)} commands over {seconds:.1f} s at speed {a.speed}, fastest joint {fastest:.0f} deg/s")
    print("            pan    lift   elbow   wrist    roll")
    print(f"  first  {_fmt(targets[0])}")
    print(f"  last   {_fmt(targets[-1])}")
    if a.dry_run:
        step = max(1, len(targets) // 12)
        for i in range(0, len(targets), step):
            print(f"  {i / FPS:5.1f}s {_fmt(targets[i])}")
        print("\nDry run: nothing was sent.")
        return
    if not a.port:
        ap.error("--port is required unless --dry-run")

    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

    robot = SO101Follower(SO101FollowerConfig(port=a.port, id=a.id, max_relative_target=MAX_STEP_DEG))
    robot.connect(calibrate=False)  # from here the motors hold the arm where it is
    try:
        obs = robot.get_observation()
        now = {j: float(obs[f"{j}.pos"]) for j in ARM_JOINTS}
        off = {j: now[j] - home[j] for j in ARM_JOINTS}
        worst = max(off, key=lambda j: abs(off[j]))
        print(f"\nArm is at  {' '.join(f'{now[j]:7.1f}' for j in ARM_JOINTS)}")
        print(f"HOME is    {' '.join(f'{home[j]:7.1f}' for j in ARM_JOINTS)}")
        if abs(off[worst]) > NEAR_HOME_DEG:
            raise SystemExit(
                f"The arm is {abs(off[worst]):.0f} degrees from HOME at {worst}. Put it in its rest pose and try again."
            )
        if not a.yes:
            input("\nClear the bench around the arm and keep a hand near the power switch. ENTER to start, Ctrl+C to cancel... ")

        # Ease from wherever the arm actually is to the plan's first pose.
        q_now = np.array([now[j] for j in ARM_JOINTS])
        q_home = np.array([home[j] for j in ARM_JOINTS])
        ease = max(1, round(go_to_duration(np.radians(q_now), np.radians(q_home), 30, 0.5) * FPS))
        grip_now = float(obs["gripper.pos"])
        lead_in = []
        for k in range(1, ease + 1):
            u = blend(k / ease)
            cmd = {f"{j}.pos": float(v) for j, v in zip(ARM_JOINTS, q_now + (q_home - q_now) * u)}
            cmd["gripper.pos"] = grip_now + (targets[0]["gripper.pos"] - grip_now) * u
            lead_in.append(cmd)

        tick = time.perf_counter()
        late = 0
        for i, cmd in enumerate(lead_in + targets):
            robot.send_action(cmd)
            tick += 1.0 / FPS
            wait = tick - time.perf_counter()
            if wait > 0:
                time.sleep(wait)
            else:
                late += 1
                tick = time.perf_counter()
            if i % FPS == 0:
                print(f"  {i / FPS:5.1f}s {_fmt(cmd)}", end="\r", flush=True)
        time.sleep(0.5)
        end = robot.get_observation()
        err = max(abs(float(end[f"{j}.pos"]) - targets[-1][f"{j}.pos"]) for j in ARM_JOINTS)
        print(f"\nDone. Furthest joint from its final target: {err:.1f} degrees. Late ticks: {late}.")
    except KeyboardInterrupt:
        print("\nStopped. The arm is holding its position.")
        input("Support the arm, then press ENTER to switch the motors off... ")
    finally:
        robot.disconnect()  # motors off


if __name__ == "__main__":
    main()
