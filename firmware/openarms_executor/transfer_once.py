"""Runs the mandarin transfer once from the terminal, without the voice relay.

    python -m firmware.openarms_executor.transfer_once --port /dev/tty.usbmodemXXXX --seconds 3

Uses the same PoseTransferRunner the relay uses: it asks y/n first, needs the arm at HOME, and
replays ABOVE_A, GRASP_A, ABOVE_B, GRASP_B and HOME from the pose file. --fake needs no arm.
"""
import argparse
import asyncio
import json
import math
import os
import select
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from . import transfer_runner
from .motion import FakeRobot
from .poses import load_poses
from .robot import FOLLOWER_ID, connect

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--port")
ap.add_argument("--fake", action="store_true")
ap.add_argument("--poses", default=str(HERE / "poses.json"))
ap.add_argument("--source", choices=("A", "C"), default="A")
pickup = ap.add_mutually_exclusive_group()
pickup.add_argument("--pan-offset-deg", type=float, help="signed shoulder-pan offset from A for C")
pickup.add_argument("--pickup", help="recorded file containing ABOVE_C and GRASP_C")
ap.add_argument("--dry-approach", action="store_true", help="run the empty C approach and high transit, then return HOME")
ap.add_argument("--high-carry", action="store_true", help="replay the staged C lift and carry with a lift check")
ap.add_argument("--empty", action="store_true", help="check A to B with the gripper open and no object")
ap.add_argument("--preview", action="store_true", help="print joint targets without connecting to the robot")
ap.add_argument("--receipt-dir", type=Path, help="save command and waypoint events as JSON Lines")
ap.add_argument("--seconds", type=float, default=3.0, help="time per move (the relay uses 1.5)")
ap.add_argument("--home-tol", type=float, default=transfer_runner.HOME_TOL,
                help="how many degrees from HOME each joint may start")
a = ap.parse_args()

poses = load_poses(a.poses)
if (a.source == "C") != (a.pan_offset_deg is not None or a.pickup is not None) or (a.dry_approach and a.source != "C"):
    ap.error("select C with --source C and either --pan-offset-deg DEGREES or --pickup FILE")
if a.empty and a.source != "A":
    ap.error("--empty is for A. Use --dry-approach for C")
if a.high_carry and a.pan_offset_deg is None:
    ap.error("--high-carry requires a C pan offset")
if (a.source == "C" or a.empty) and (not math.isfinite(a.seconds) or a.seconds < 3 or a.home_tol != transfer_runner.HOME_TOL):
    ap.error("C and empty runs require at least 3 seconds per move and the default HOME tolerance")

pan_limits = None
joint_limits = None
if a.pan_offset_deg is not None:
    calibration_dir = Path(os.environ.get("HF_LEROBOT_CALIBRATION", HERE.parents[1] / "calibration"))
    calibration = json.loads((calibration_dir / "robots" / "so_follower" / f"{FOLLOWER_ID}.json").read_text())
    # LeRobot degrees are encoder ticks relative to the calibrated midpoint (4096 counts per turn).
    joint_limits = {f"{name}.pos": (-(cal["range_max"] - cal["range_min"]) * 180 / 4095,
                                  (cal["range_max"] - cal["range_min"]) * 180 / 4095)
                    for name, cal in calibration.items()}
    joint_limits["gripper.pos"] = (0, 100)
    pan_limits = joint_limits[transfer_runner.PAN]

transfer_runner.HOME_TOL = a.home_tol
plan = {"plan_id": "manual", "object": "mandarin", "source": a.source, "destination": "B"}
receipt = None


def confirm_lift(should_stop) -> bool:
    print("Confirm the mandarin is off the table and held securely. Carry to B? y/n> ", end="", flush=True)
    while not should_stop():
        if select.select([sys.stdin], [], [], 0.1)[0]:
            # Read from the unbuffered stream used for both confirmations.
            return read_line().strip().lower() in ("y", "yes")
    return False


def read_line(prompt: str = "") -> str:
    print(prompt, end="", flush=True)
    reply = bytearray()
    while (char := os.read(sys.stdin.fileno(), 1)) not in (b"", b"\n"):
        reply.extend(char)
    return reply.decode(errors="replace")


def trace(event: str, **details) -> None:
    row = {"time": datetime.now(timezone.utc).isoformat(), "event": event, **details}
    receipt.write(json.dumps(row) + "\n")
    receipt.flush()
    if event == "motion_error":
        print(details["error"], flush=True)


try:
    runner = transfer_runner.PoseTransferRunner(
        FakeRobot(poses["poses"].get("HOME")), poses, seconds=a.seconds,
        pan_offset_deg=a.pan_offset_deg, pan_limits=pan_limits, dry_approach=a.dry_approach,
        taught_pickup=load_poses(a.pickup)["poses"] if a.pickup else None,
        empty=a.empty, high_carry=a.high_carry, joint_limits=joint_limits, confirm_lift=confirm_lift,
        ask=read_line if a.high_carry else input,
    )
except ValueError as exc:
    ap.error(str(exc))
if a.preview:
    print(json.dumps(runner.scripts[a.source], indent=2))
    raise SystemExit(0)


async def main() -> str:
    if not await runner.authorize(plan):
        return "not authorized"
    if not a.fake:
        runner.robot = connect(False, a.port)
    status = (await runner.execute(plan)).status
    if receipt:
        try:
            obs = runner.robot.get_observation()
            trace("end_pose", joints={k: float(v) for k, v in obs.items() if k.endswith(".pos")})
        except Exception as exc:
            trace("end_pose_unavailable", error=str(exc))
    return status


try:
    if a.receipt_dir:
        a.receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt = NamedTemporaryFile(mode="w", prefix=f"transfer-{a.source}-", suffix=".jsonl",
                                     dir=a.receipt_dir, delete=False)
        print("Receipt:", Path(receipt.name).relative_to(Path.cwd()) if Path(receipt.name).is_relative_to(Path.cwd())
              else receipt.name, flush=True)
        runner.trace = trace
        trace("request", source=a.source, destination="B", empty=a.empty, dry_approach=a.dry_approach,
              offset_deg=a.pan_offset_deg, high_carry=a.high_carry, poses=a.poses, pickup=a.pickup,
              backend="fake" if a.fake else "physical")
    status = asyncio.run(main())
    print("result:", status)
    if receipt:
        trace("result", status=status)
except BaseException as exc:
    if receipt:
        trace("interrupted" if isinstance(exc, KeyboardInterrupt) else "error", error=str(exc))
    raise
finally:
    try:
        runner.robot.disconnect()  # torque stays on (robot.py), so the arm holds its last pose
    finally:
        if receipt:
            receipt.close()
