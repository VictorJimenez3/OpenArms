"""Records the current joints, lets you move the arm away, moves back and prints the error per joint."""
import argparse

from .motion import move_to
from .poses import ARM_JOINTS
from .robot import connect

ap = argparse.ArgumentParser()
ap.add_argument("--fake", action="store_true")
ap.add_argument("--port")
ap.add_argument("--seconds", type=float, default=1.5)
a = ap.parse_args()

robot = connect(a.fake, a.port)
try:
    target = {k: float(v) for k, v in robot.get_observation().items() if k in ARM_JOINTS}
    print("recorded:", {k: round(v, 2) for k, v in target.items()})
    try:
        input("Move the arm away, then press Enter to move back... ")
    except EOFError:
        print()  # no stdin (e.g. < /dev/null): replay straight away
    move_to(robot, target, a.seconds)
    now = robot.get_observation()
    for k in ARM_JOINTS:
        print(f"{k:20s} error {float(now[k]) - target[k]:+.2f}")
finally:
    robot.disconnect()
