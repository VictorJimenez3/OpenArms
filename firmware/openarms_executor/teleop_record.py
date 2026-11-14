"""Teleoperate the follower from the leader and save named poses while it runs, so torque never drops mid-recording."""
import argparse
import threading
import time

from .poses import ARM_JOINTS, GRIPPER, save_gripper, save_pose
from .robot import connect, connect_leader

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True, help="pose file, e.g. firmware/openarms_executor/poses.json")
ap.add_argument("--follower-port")
ap.add_argument("--leader-port")
ap.add_argument("--fake", action="store_true")
ap.add_argument("--hz", type=float, default=30)
a = ap.parse_args()

follower, leader = connect(a.fake, a.follower_port), connect_leader(a.fake, a.leader_port)
bus, done = threading.Lock(), threading.Event()  # one serial transaction at a time


def mirror() -> None:
    while not done.is_set():
        with bus:
            follower.send_action(leader.get_action())
        time.sleep(1 / a.hz)


worker = threading.Thread(target=mirror, daemon=True)
worker.start()
print("Move the leader; the follower copies it. Type a pose name (HOME, ABOVE_A, ...) to save the follower's joints,")
print("'open' or 'cup' to save the gripper value, or press Enter on an empty line to finish.")
try:
    while name := input("save as> ").strip():
        time.sleep(0.3)  # let the follower settle after the last leader move
        with bus:
            obs = follower.get_observation()
        if name in ("open", "cup"):
            save_gripper(a.out, name, obs[GRIPPER])
            print(f"  gripper {name} = {obs[GRIPPER]:.1f}")
        else:
            save_pose(a.out, name, obs)
            print(f"  {name}:", {k.removesuffix('.pos'): round(float(obs[k]), 1) for k in ARM_JOINTS})
except (EOFError, KeyboardInterrupt):
    pass
finally:
    done.set()
    worker.join(timeout=1)
    follower.disconnect()  # torque stays on (robot.py), so the arm holds its last pose
    leader.disconnect()
