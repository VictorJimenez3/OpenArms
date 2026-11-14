"""Runs the A -> B transfer once from the terminal, without the voice relay.

    python -m firmware.openarms_executor.transfer_once --port /dev/tty.usbmodemXXXX --seconds 3

Uses the same PoseTransferRunner the relay uses: it asks y/n first, needs the arm at HOME, and
replays ABOVE_A, GRASP_A, ABOVE_B, GRASP_B and HOME from the pose file. --fake needs no arm.
"""
import argparse
import asyncio
from pathlib import Path

from . import transfer_runner
from .motion import FakeRobot
from .poses import load_poses
from .robot import connect

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--port")
ap.add_argument("--fake", action="store_true")
ap.add_argument("--poses", default=str(HERE / "poses.json"))
ap.add_argument("--seconds", type=float, default=3.0, help="time per move (the relay uses 1.5)")
ap.add_argument("--home-tol", type=float, default=transfer_runner.HOME_TOL,
                help="how many degrees from HOME each joint may start")
a = ap.parse_args()

poses = load_poses(a.poses)
transfer_runner.HOME_TOL = a.home_tol
robot = FakeRobot(poses["poses"].get("HOME")) if a.fake else connect(False, a.port)
runner = transfer_runner.PoseTransferRunner(robot, poses, seconds=a.seconds)
plan = {"plan_id": "manual", "object": "mandarin", "source": "A", "destination": "B"}


async def main() -> str:
    if not await runner.authorize(plan):
        return "not authorized"
    return (await runner.execute(plan)).status


try:
    print("result:", asyncio.run(main()))
finally:
    robot.disconnect()  # torque stays on (robot.py), so the arm holds its last pose
