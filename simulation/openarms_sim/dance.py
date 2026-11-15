"""A short wave-and-dance for the simulated SO-101, from HOME and back to HOME.

Simulation only. It is built from joint targets (degrees, as LeRobot reports them) played through the same
Player and joint map as every other motion, and it is rejected if the Player reports any blocking issue.
Nothing here is sent to a real arm; a physical routine needs its own supervised, recorded poses.
"""
from __future__ import annotations

import numpy as np

from .motion import Segment, go_to_duration
from .joints import JointMap

HOME_KEY = "HOME"
# Raised, open-handed "hello" held in front of the arm, then small swings of the wrist and base.
RAISED = {"shoulder_pan": 0.0, "shoulder_lift": -35.0, "elbow_flex": 45.0, "wrist_flex": 20.0, "wrist_roll": 0.0}
WAVE = [{"wrist_roll": 35.0}, {"wrist_roll": -35.0}] * 3
DANCE = [{"shoulder_pan": 18.0, "wrist_roll": 25.0}, {"shoulder_pan": -18.0, "wrist_roll": -25.0}] * 2
BOW = {"shoulder_lift": -55.0, "elbow_flex": 60.0, "wrist_flex": 45.0, "wrist_roll": 0.0}


def choreography() -> list[tuple[str, dict]]:
    """(label, joint overrides on RAISED) in order; the routine starts and ends at HOME."""
    steps = [("raise the arm", {})]
    steps += [(f"wave {i + 1}", w) for i, w in enumerate(WAVE)]
    steps += [("centre", {})]
    steps += [(f"dance {i + 1}", d) for i, d in enumerate(DANCE)]
    steps += [("bow", BOW), ("raise the arm", {})]
    return steps


def build_dance(jm: JointMap, home: dict[str, float]) -> list[Segment]:
    mcfg = jm.cfg["motion"]
    q = np.array(jm.pose_to_model(home))
    segments: list[Segment] = []
    grip = jm.gripper_open_value

    def go(label, target):
        nonlocal q
        t = np.array(jm.pose_to_model(target))
        segments.append(Segment(0, "dance()", label, q, t, grip, grip, go_to_duration(q, t, 70.0, 0.45)))
        q = t

    for label, change in choreography():
        go(label, {**RAISED, **change})
    go("back to HOME", home)
    return segments
