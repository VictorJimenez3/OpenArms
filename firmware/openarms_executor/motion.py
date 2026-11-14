"""Smooth joint moves, plus a FakeRobot with the same get_observation/send_action shape as LeRobot's follower."""
import math
import time

JOINTS = ("shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos", "wrist_flex.pos", "wrist_roll.pos", "gripper.pos")


class FakeRobot:
    def __init__(self, start: dict | None = None) -> None:
        self.pos = {k: 0.0 for k in JOINTS}
        self.pos.update(start or {})
        self.sent: list[dict] = []

    def get_observation(self) -> dict:
        return dict(self.pos)

    def send_action(self, action: dict) -> dict:
        self.pos.update(action)
        self.sent.append(dict(action))
        return action

    def disconnect(self) -> None:
        pass


def move_to(robot, target: dict, seconds: float = 1.5, hz: float = 30, should_stop=lambda: False,
            tol: float = 3.0, settle: float = 2.0) -> bool:
    """Steps linearly from the present joints to target; returns False if stopped part-way, raises if it never arrives."""
    obs = robot.get_observation()
    start = {k: float(obs[k]) for k in target}
    # ceil keeps every step at or below distance / (seconds * hz).
    n = max(1, math.ceil(seconds * hz))
    for i in range(1, n + 1):
        if should_stop():
            return False  # no new command, so the servos hold the last goal
        robot.send_action({k: target[k] if i == n else start[k] + (target[k] - start[k]) * i / n for k in target})
        time.sleep(seconds / n)
    # a clipped (max_relative_target) or snagged joint must not count as arrived
    end = time.monotonic() + settle
    while True:
        obs = robot.get_observation()
        # the gripper stops at the cup's width short of its goal, so only arm joints must arrive
        off = {k: round(float(obs[k]) - target[k], 1) for k in target
               if k != "gripper.pos" and abs(float(obs[k]) - target[k]) > tol}
        if not off:
            return True
        if should_stop():
            return False
        if time.monotonic() > end:
            raise RuntimeError(f"did not reach target, off by {off}")
        robot.send_action(dict(target))
        time.sleep(1 / hz)
