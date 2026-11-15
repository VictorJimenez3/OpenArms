"""A small wave-and-sway for the real SO-101, built only from offsets around where the arm already is.

No pose is assumed: the routine reads the arm's present joints (it must be at HOME), swings the wrist and the
base a few degrees each way, and returns to the starting joints. The gripper is never commanded. Every target is
checked against the calibrated range and a hard cap before the first command, and a STOP lets the current slow
move finish and then holds. It needs a person at the bench with a hand near Stop.
"""
import time

from .motion import JOINTS, move_to

ARM_JOINTS = tuple(j for j in JOINTS if j != "gripper.pos")
MAX_OFFSET_DEG = 20.0  # no joint ever leaves its starting angle by more than this
MARGIN_DEG = 5.0  # and stays this far inside the calibrated range
SECONDS_PER_MOVE = 1.6
# (label, offsets in degrees from the starting pose)
WAVE = [(f"wave {i + 1}", {"wrist_roll.pos": 18.0 * sign}) for i, sign in enumerate([1, -1, 1, -1, 1, -1])]
SWAY = [(f"sway {i + 1}", {"shoulder_pan.pos": 12.0 * sign, "wrist_roll.pos": 12.0 * sign})
        for i, sign in enumerate([1, -1, 1, -1])]
STEPS = WAVE + [("centre", {})] + SWAY + [("centre", {})]


def script(start: dict, limits: dict | None = None) -> list[tuple[str, dict]]:
    """(label, absolute arm targets) for the whole routine, validated; raises ValueError before any motion."""
    missing = [j for j in ARM_JOINTS if j not in start]
    if missing:
        raise ValueError(f"the arm did not report {', '.join(missing)}")
    base = {j: float(start[j]) for j in ARM_JOINTS}
    out = []
    for label, offsets in STEPS:
        if any(abs(v) > MAX_OFFSET_DEG for v in offsets.values()):
            raise ValueError(f"{label}: offset above {MAX_OFFSET_DEG} degrees")
        target = {j: base[j] + offsets.get(j, 0.0) for j in ARM_JOINTS}
        for joint, value in target.items():
            if limits and not limits[joint][0] + MARGIN_DEG <= value <= limits[joint][1] - MARGIN_DEG:
                raise ValueError(f"{label}: {joint} would leave the calibrated range")
        out.append((label, target))
    return out


def run(robot, *, should_stop=lambda: False, limits: dict | None = None, seconds: float = SECONDS_PER_MOVE,
        hz: float = 30, on_step=lambda label: None) -> bool:
    """Dance from the present pose and come back to it. True when finished, False when stopped part-way."""
    start = {j: float(v) for j, v in robot.get_observation().items()}
    moves = script(start, limits)  # whole routine checked first
    home = {j: start[j] for j in ARM_JOINTS}
    for label, target in [*moves, ("back to start", home)]:
        if should_stop():
            return False
        on_step(label)
        if not move_to(robot, target, seconds, hz, should_stop=should_stop, nudges=0, give=3.0):
            return False
        time.sleep(0.05)
    return True
