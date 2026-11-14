"""go_to and gripper: plans built from single moves between saved positions. No network, no arm.
Run: python -m agentic.tests.test_go_to"""
import copy
import json
import sys
import tempfile
import traceback
from pathlib import Path

from agentic.openarms_agent import prompting, runner
from agentic.openarms_agent.mock_arm import MockArm
from agentic.openarms_agent.validator import pose_names, validate
from agentic.tests.test_brain import FakeClient, resp, text, tool_use

ROOT = Path(__file__).resolve().parents[2]
BLOCK = json.loads((ROOT / "agentic/contracts/stations.block.example.json").read_text())
LIQUID = json.loads((ROOT / "agentic/contracts/stations.example.json").read_text())


def go(pose):
    return {"action": "go_to", "args": {"pose": pose}}


def grip(state):
    return {"action": "gripper", "args": {"state": state}}


def plan(*steps):
    return {"plan_id": "p1", "student_instruction": "test", "steps": list(steps)}


def arm():
    return MockArm(copy.deepcopy(BLOCK), step_seconds=0)


def check(*steps, state=None):
    return validate(plan(*steps), state or arm().state(), BLOCK)


def rejected(needle, *steps):
    v = check(*steps)
    assert not v["ok"], f"allowed: {[s['args'] for s in steps]}"
    assert needle in v["reason"], v["reason"]


VISIT_B = (go("ABOVE_B"), go("HOME"))
BY_HAND = (grip("open"), go("ABOVE_A"), go("GRASP_A"), grip("close"), go("ABOVE_A"),
           go("ABOVE_B"), go("GRASP_B"), grip("open"), go("ABOVE_B"), go("HOME"))


def test_saved_positions_follow_from_the_bench():
    assert pose_names(BLOCK) == ["HOME", "ABOVE_A", "GRASP_A", "ABOVE_B", "GRASP_B"]
    assert "TIP_C" in pose_names(LIQUID) and "GRASP_C" not in pose_names(LIQUID)


def test_visit_above_b_and_come_home_without_touching_anything():
    a = arm()
    v = validate(plan(*VISIT_B), a.state(), BLOCK)
    assert v["ok"], v["reason"]
    assert v["expanded"] == list(VISIT_B)
    r = runner.run(plan(*VISIT_B), a)
    assert r["status"] == "executed" and r["steps_done"] == ["go_to", "go_to"]
    assert a.state()["point_holds"] == {"A": "block", "B": None} and a.state()["at"] == "HOME"


def test_a_whole_transfer_can_be_built_from_single_moves():
    a = arm()
    v = validate(plan(*BY_HAND), a.state(), BLOCK)
    assert v["ok"], v["reason"]
    assert runner.run(plan(*BY_HAND), a)["status"] == "executed"
    assert a.state()["point_holds"] == {"A": None, "B": "block"} and a.state()["holding"] is None


def test_positions_must_be_saved_ones():
    rejected("no saved position ABOVE_Z", go("ABOVE_Z"), go("HOME"))
    rejected("no saved position 10cm_left", go("10cm_left"), go("HOME"))


def test_low_positions_are_entered_and_left_only_through_the_one_above():
    rejected("must be at ABOVE_B before going down", grip("open"), go("GRASP_B"), go("ABOVE_B"), go("HOME"))
    rejected("must go up to ABOVE_A", grip("open"), go("ABOVE_A"), go("GRASP_A"), go("ABOVE_B"), go("HOME"))
    rejected("must go up to ABOVE_A", grip("open"), go("ABOVE_A"), go("GRASP_A"), go("HOME"))


def test_going_down_onto_the_block_needs_an_open_gripper():
    rejected("open the gripper before going down", go("ABOVE_A"), go("GRASP_A"), go("ABOVE_A"), go("HOME"))
    rejected("open the gripper before going down", grip("close"), go("ABOVE_A"), go("GRASP_A"), go("ABOVE_A"), go("HOME"))
    assert check(grip("open"), go("ABOVE_A"), go("GRASP_A"), go("ABOVE_A"), go("HOME"))["ok"]
    assert check(go("ABOVE_B"), go("GRASP_B"), go("ABOVE_B"), go("HOME"))["ok"], "B is empty, so nothing to knock"


def test_the_block_is_never_let_go_in_the_air_or_left_in_the_gripper():
    lift = (grip("open"), go("ABOVE_A"), go("GRASP_A"), grip("close"), go("ABOVE_A"))
    rejected("would drop the block", *lift, grip("open"), go("HOME"))
    rejected("end at HOME with an empty gripper", *lift, go("HOME"))
    rejected("end at HOME with an empty gripper", go("ABOVE_B"))


def test_plan_length_limit_is_twelve_for_single_moves_and_still_six_otherwise():
    there_and_back = [go("ABOVE_B"), go("HOME")] * 6
    assert check(*there_and_back)["ok"]
    rejected("1 to 12 actions, not 14", *([go("ABOVE_B"), go("HOME")] * 7))
    seven = [{"action": "wait", "args": {"seconds": 1}}] * 7
    rejected("1 to 6 actions, not 7", *seven)


def test_single_moves_and_whole_moves_can_be_mixed():
    a = arm()
    mixed = plan({"action": "move_block", "args": {"from": "A", "to": "B"}}, go("ABOVE_A"), go("HOME"))
    assert validate(mixed, a.state(), BLOCK)["ok"]
    assert runner.run(mixed, a)["steps_done"] == ["pick", "place", "home", "go_to", "go_to"]


def test_liquid_bench_can_visit_a_station_too():
    a = MockArm(copy.deepcopy(LIQUID), step_seconds=0)
    v = validate(plan(go("ABOVE_C"), go("HOME")), a.state(), LIQUID)
    assert v["ok"], v["reason"]
    assert runner.run(plan(go("ABOVE_C"), go("HOME")), a)["status"] == "executed"


def test_prompt_lists_the_saved_positions_and_the_new_actions():
    p = prompting.render_system_prompt(BLOCK, arm().state(), "obj")
    assert "Saved positions the arm can go to: HOME, ABOVE_A, GRASP_A, ABOVE_B, GRASP_B" in p
    assert "go_to(pose)" in p and "gripper(state)" in p and "{{" not in p


def pose_arm_on_fake_robot(d, names):
    from firmware.openarms_executor.motion import FakeRobot
    from firmware.openarms_executor.pose_arm import PoseArm
    from firmware.openarms_executor.poses import load_poses
    joints = ["shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos", "wrist_flex.pos", "wrist_roll.pos"]
    poses = {"poses": {n: {j: float(10 * i + k) for k, j in enumerate(joints)} for i, n in enumerate(names)},
             "gripper": {"open": 90.0, "cup": 20.0}}
    path = Path(d) / "poses.json"
    path.write_text(json.dumps(poses))
    robot = FakeRobot(poses["poses"]["HOME"])
    return robot, PoseArm(robot, load_poses(path), copy.deepcopy(BLOCK), seconds=0.01, hz=30), poses


def test_real_arm_goes_to_exactly_the_named_positions_and_leaves_the_gripper_alone():
    with tempfile.TemporaryDirectory() as d:
        robot, pa, poses = pose_arm_on_fake_robot(d, ["HOME", "ABOVE_A", "GRASP_A", "ABOVE_B", "GRASP_B"])
        assert validate(plan(*VISIT_B), pa.state(), BLOCK)["ok"]
        assert runner.run(plan(*VISIT_B), pa)["status"] == "executed"
    assert not any("gripper.pos" in cmd for cmd in robot.sent), "the gripper was commanded"
    reached = [n for cmd in robot.sent for n, p in poses["poses"].items() if cmd == p]
    assert [n for i, n in enumerate(reached) if i == 0 or reached[i - 1] != n] == ["ABOVE_B", "HOME"]
    assert pa.state()["at"] == "HOME" and pa.state()["point_holds"] == {"A": "block", "B": None}


def test_real_arm_only_offers_positions_that_were_actually_recorded():
    with tempfile.TemporaryDirectory() as d:
        _, pa, _ = pose_arm_on_fake_robot(d, ["HOME", "ABOVE_A", "GRASP_A"])  # nothing recorded for B
        assert pa.state()["poses"] == ["ABOVE_A", "GRASP_A", "HOME"]
        v = validate(plan(*VISIT_B), pa.state(), BLOCK)
        assert not v["ok"] and "no saved position ABOVE_B" in v["reason"], v["reason"]


def test_fresh_session_go_above_b_and_home_reaches_the_teacher_and_runs():
    from agentic.scripts.brain_repl import make_brain
    a = arm()
    b = make_brain(a, copy.deepcopy(BLOCK))
    b._client = FakeClient([
        resp([text("I'll move the arm above B, then back home. Send it to your teacher?")], "end_turn"),
        resp([tool_use("submit_plan", {"student_instruction": "go to ABOVE_B and home", "steps": list(VISIT_B)})], "tool_use"),
        resp([text("Waiting for your teacher to approve.")], "end_turn"),
    ])
    b.handle_turn("t1", "just go to ABOVE_B, don't grasp it and return to HOME")
    assert "ABOVE_B" in b._client.calls[0]["system"]
    reply = b.handle_turn("t2", "yes")
    assert reply["status"] == "awaiting_teacher" and reply["plan"]["steps"] == list(VISIT_B)
    assert runner.run(reply["plan"], a)["status"] == "executed"


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL {name}: {type(e).__name__}: {e or traceback.format_exc(limit=1)}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
