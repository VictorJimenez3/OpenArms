"""Shows the real follower arm's pose on the simulated arm, live.

This is the bench check for config/joint_map.yaml: put the real arm in a pose,
and see whether the simulated arm is in the same one. It also prints where the
simulation thinks the gripper is, to compare against a ruler on the table.

    source env.sh                       # from the repo root, so calibration loads
    mjpython -m openarms_sim.mirror --port /dev/tty.usbmodemXXXX

The arm holds its position while connected. Add --free to switch the motors
off so you can move it by hand. SUPPORT THE ARM FIRST: with the motors off it
falls under its own weight.

NOT YET TESTED ON THE REAL ARM. It needs LeRobot installed (firmware/README.md).
"""

from __future__ import annotations

import argparse
import time

import mujoco
import mujoco.viewer

from .config import ARM_JOINTS, load_bench, load_joint_map
from .joints import JointMap
from .scene import build_scene


def main() -> None:
    ap = argparse.ArgumentParser(description="Mirror the real follower arm in the simulation.")
    ap.add_argument("--port", required=True)
    ap.add_argument("--id", default="my_awesome_follower_arm")
    ap.add_argument("--setup", help="which bench to draw: block or liquid (default: the active setup)")
    ap.add_argument("--free", action="store_true", help="motors off, so the arm can be moved by hand")
    ap.add_argument("--no-viewer", action="store_true", help="only print the numbers")
    a = ap.parse_args()

    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

    jm = JointMap(load_joint_map())
    scene = build_scene(load_bench(a.setup))
    m, d = scene.model, scene.data
    robot = SO101Follower(SO101FollowerConfig(port=a.port, id=a.id))
    robot.connect(calibrate=False)
    if a.free:
        input("The motors are about to switch off. Hold the arm, then press ENTER...")
        robot.bus.disable_torque()

    def update() -> str:
        obs = robot.get_observation()
        for name, adr in zip(ARM_JOINTS, scene.arm_qadr):
            d.qpos[adr] = jm.to_model(name, obs[f"{name}.pos"])
        d.qpos[scene.gripper_qadr] = jm.gripper_to_model(obs["gripper.pos"])
        mujoco.mj_forward(m, d)
        x, y, z = d.site_xpos[scene.grasp_site] * 100
        degs = " ".join(f"{obs[f'{n}.pos']:7.1f}" for n in ARM_JOINTS)
        return f"real deg [{degs}] grip {obs['gripper.pos']:5.1f} | sim grasp point x {x:6.1f} y {y:6.1f} z {z:6.1f} cm"

    try:
        if a.no_viewer:
            while True:
                print(update(), end="\r", flush=True)
                time.sleep(0.1)
        with mujoco.viewer.launch_passive(m, d, show_left_ui=False, show_right_ui=False) as viewer:
            while viewer.is_running():
                print(update(), end="\r", flush=True)
                viewer.sync()
                time.sleep(1 / 20)
    except KeyboardInterrupt:
        pass
    finally:
        print()
        if a.free:
            input("The motors will stay off on exit. Rest the arm on the table, then press ENTER...")
        robot.disconnect()


if __name__ == "__main__":
    main()
