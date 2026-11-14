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


GRIPPER = "gripper.pos"
STILL_DEG = 0.5  # the arm counts as stopped when no joint has moved more than this...
STILL_SECONDS = 0.3  # ...over this long


def move_to(robot, target: dict, seconds: float = 1.5, hz: float = 30, should_stop=lambda: False,
            tol: float = 3.0, settle: float = 2.0, snag: float = 12.0, nudges: int = 2,
            max_nudge: float = 8.0) -> bool:
    """Steps linearly from the present joints to target, then makes sure the arm really got there.

    Returns True once every arm joint is within `tol` of target, False if stopped part-way.

    A loaded arm at long reach settles a few degrees short, because the servos push less the
    closer they are. So if the arm has stopped moving but is still short, the command is nudged
    past the target by the shortfall (at most `max_nudge`, at most `nudges` times) and checked
    again. A joint that has stopped more than `snag` away is treated as blocked: it is not
    pushed harder, and the move raises. It also raises if the nudges do not close the gap.
    """
    obs = robot.get_observation()
    start = {k: float(obs[k]) for k in target}
    # ceil keeps every step at or below distance / (seconds * hz).
    n = max(1, math.ceil(seconds * hz))
    for i in range(1, n + 1):
        if should_stop():
            return False  # no new command, so the servos hold the last goal
        robot.send_action({k: target[k] if i == n else start[k] + (target[k] - start[k]) * i / n for k in target})
        time.sleep(seconds / n)

    # the gripper stops at the cup's width short of its goal, so only arm joints must arrive
    arm = [k for k in target if k != GRIPPER]
    command = dict(target)
    still_ticks = max(3, round(STILL_SECONDS * hz))
    for attempt in range(nudges + 1):
        # Wait until the arm arrives, stops short, or runs out of time.
        end, seen = time.monotonic() + settle, []
        while True:
            obs = robot.get_observation()
            short = {k: target[k] - float(obs[k]) for k in arm}
            if all(abs(e) <= tol for e in short.values()):
                return True
            if should_stop():
                return False
            seen.append([float(obs[k]) for k in arm])
            recent = seen[-still_ticks:]
            still = len(recent) == still_ticks and all(
                max(col) - min(col) <= STILL_DEG for col in zip(*recent)
            )
            if still or time.monotonic() > end:
                break
            robot.send_action(dict(command))  # a clipped (max_relative_target) command needs repeating
            time.sleep(1 / hz)

        off = {k: round(-e, 1) for k, e in short.items() if abs(e) > tol}
        if max(abs(e) for e in short.values()) > snag:
            raise RuntimeError(f"did not reach target, off by {off}: too far to be sag, something is blocking the arm")
        if attempt == nudges:
            raise RuntimeError(f"did not reach target, off by {off} after {nudges} nudges")

        # Aim past the target by the shortfall, never more than max_nudge away from it.
        goal = {
            k: min(target[k] + max_nudge, max(target[k] - max_nudge, command[k] + short[k])) if k in arm else command[k]
            for k in command
        }
        print("  nudging", {k.removesuffix(".pos"): round(goal[k] - target[k], 1) for k in arm if goal[k] != target[k]})
        ramp = max(1, round(STILL_SECONDS * hz))
        for i in range(1, ramp + 1):
            if should_stop():
                return False
            robot.send_action({k: command[k] + (goal[k] - command[k]) * i / ramp for k in command})
            time.sleep(1 / hz)
        command = goal
    return False  # not reached: the loop always returns or raises
