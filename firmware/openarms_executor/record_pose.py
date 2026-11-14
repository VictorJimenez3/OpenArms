"""Saves the follower's current joints as a named pose. Move it there first (teleoperate or by hand)."""
import argparse

from .poses import ARM_JOINTS, GRIPPER, save_gripper, save_pose
from .robot import connect

ap = argparse.ArgumentParser()
ap.add_argument("--name", required=True, help="pose name, e.g. ABOVE_A; with --gripper: open or cup")
ap.add_argument("--out", required=True)
ap.add_argument("--fake", action="store_true")
ap.add_argument("--port")
ap.add_argument("--gripper", action="store_true", help="save only the gripper reading into the gripper table")
a = ap.parse_args()

robot = connect(a.fake, a.port)
try:
    obs = robot.get_observation()
finally:
    robot.disconnect()
if a.gripper:
    save_gripper(a.out, a.name, obs[GRIPPER])
    print(f"saved gripper {a.name} = {obs[GRIPPER]:.2f} to {a.out}")
else:
    save_pose(a.out, a.name, obs)
    print(f"saved {a.name} to {a.out}:", {k: round(float(obs[k]), 2) for k in ARM_JOINTS})
