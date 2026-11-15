import pytest

from . import dance
from .motion import FakeRobot

START = {"shoulder_pan.pos": 0.0, "shoulder_lift.pos": -83.0, "elbow_flex.pos": 77.0, "wrist_flex.pos": 57.0,
         "wrist_roll.pos": 90.0, "gripper.pos": 40.0}
LIMITS = {j: (-180.0, 180.0) for j in dance.ARM_JOINTS}


def test_every_command_stays_near_the_start_and_returns_and_never_touches_the_gripper():
    robot = FakeRobot(START)
    assert dance.run(robot, limits=LIMITS, seconds=0.02, hz=30)
    assert robot.sent
    for command in robot.sent:
        assert "gripper.pos" not in command
        for joint, value in command.items():
            assert abs(value - START[joint]) <= dance.MAX_OFFSET_DEG + 1e-6
    assert {j: round(robot.pos[j], 3) for j in dance.ARM_JOINTS} == {j: START[j] for j in dance.ARM_JOINTS}
    assert robot.pos["gripper.pos"] == START["gripper.pos"]


def test_stop_halts_between_moves_and_does_not_return_true():
    robot = FakeRobot(START)
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 8

    assert dance.run(robot, should_stop=stop, limits=LIMITS, seconds=0.02, hz=30) is False


def test_a_target_near_the_calibrated_edge_is_refused_before_any_motion():
    robot = FakeRobot(START)
    tight = {**LIMITS, "wrist_roll.pos": (80.0, 100.0)}
    with pytest.raises(ValueError, match="calibrated range"):
        dance.run(robot, limits=tight, seconds=0.02)
    assert robot.sent == []


def test_missing_joint_report_is_refused():
    with pytest.raises(ValueError, match="did not report"):
        dance.script({"shoulder_pan.pos": 0.0})
