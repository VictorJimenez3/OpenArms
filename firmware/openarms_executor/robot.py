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


LEADER_ID = "my_awesome_leader_arm"  # picks calibration/teleoperators/so_leader/<id>.json via env.sh


class FakeLeader(FakeRobot):
    def get_action(self) -> dict:
        return self.get_observation()


def connect_leader(fake: bool = True, port: str | None = None, leader_id: str = LEADER_ID):
    if fake:
        return FakeLeader({"shoulder_pan.pos": 10.0, "gripper.pos": 50.0})
    if not port:
        raise SystemExit("--leader-port is required (find it with lerobot-find-port)")
    # shortcut: checked against LeRobot e0d50211 source, not run here; check at the bench
    from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig

    leader = SO101Leader(SO101LeaderConfig(port=port, id=leader_id))
    leader.connect(calibrate=False)  # the leader never enables torque, so it stays free to move by hand
    if not leader.is_calibrated:
        leader.disconnect()
        raise SystemExit(f"{leader_id} not calibrated: `source env.sh` and check the id")
    return leader
