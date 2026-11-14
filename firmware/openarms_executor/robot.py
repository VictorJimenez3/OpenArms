"""Connects to the SO-101 follower (same as lerobot-teleoperate --robot.type=so101_follower) or a FakeRobot."""
from .motion import FakeRobot

FOLLOWER_ID = "my_awesome_follower_arm"  # picks calibration/robots/so_follower/<id>.json via env.sh


def connect(fake: bool = True, port: str | None = None, robot_id: str = FOLLOWER_ID):
    if fake:
        return FakeRobot()
    if not port:
        raise SystemExit("--port is required for the real arm (find it with lerobot-find-port)")
    # shortcut: LeRobot API unverified here, check at the bench
    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

    # max_relative_target caps each command at 10 deg; keeping torque on exit stops the arm dropping when a script ends.
    robot = SO101Follower(SO101FollowerConfig(port=port, id=robot_id, max_relative_target=10.0,
                                              disable_torque_on_disconnect=False))
    robot.connect(calibrate=False)  # never start an interactive calibration (see firmware/README.md)
    if not robot.is_calibrated:
        robot.disconnect()
        raise SystemExit(f"{robot_id} not calibrated: `source env.sh`, check the id, or run lerobot-teleoperate once and press ENTER")
    return robot
