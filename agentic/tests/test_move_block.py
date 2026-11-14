"""move_block: moving a loose object between point stations. No network, no arm.
Run: python -m agentic.tests.test_move_block"""
import copy
import json
import sys
import tempfile
import traceback
from pathlib import Path

from agentic.openarms_agent import prompting, runner
from agentic.openarms_agent.catalog import expand
from agentic.openarms_agent.mock_arm import MockArm
from agentic.openarms_agent.validator import validate
from agentic.tests.test_brain import FakeClient, resp, text, tool_use

ROOT = Path(__file__).resolve().parents[2]
BLOCK = json.loads((ROOT / "agentic/contracts/stations.block.example.json").read_text())
LIQUID = json.loads((ROOT / "agentic/contracts/stations.example.json").read_text())


def plan(src="A", dst="B", pid="p1"):
    return {"plan_id": pid, "student_instruction": f"move from {src} to {dst}",
            "steps": [{"action": "move_block", "args": {"from": src, "to": dst}}]}


def arm():
    return MockArm(copy.deepcopy(BLOCK), step_seconds=0)


def test_move_block_expands_to_pick_place_home():
    assert expand(plan()) == [{"action": "pick", "args": {"station": "A"}},
                              {"action": "place", "args": {"station": "B"}},
                              {"action": "home", "args": {}}]


def test_fresh_bench_has_the_block_at_a():
    assert arm().state()["point_holds"] == {"A": "block", "B": None}


def test_a_to_b_validates_and_predicts_the_end_state():
    v = validate(plan(), arm().state(), BLOCK)
    assert v["ok"], v["reason"]
    assert v["end_state"]["point_holds"] == {"A": None, "B": "block"}
    assert v["end_state"]["at"] == "HOME" and v["end_state"]["holding"] is None


def test_moves_that_cannot_work_are_rejected_with_a_reason():
    state = arm().state()
    for p, needle in ((plan("B", "A"), "nothing at B"),
                      ({**plan(), "steps": [{"action": "move_block", "args": {"from": "A", "to": "A"}}]}, "goes nowhere"),
                      ({**plan(), "steps": [{"action": "move_block", "args": {"from": "A", "to": "Z"}}]}, "no station Z"),
                      ({**plan(), "steps": [{"action": "move_block", "args": {"from": "A"}}]}, "station name for to")):
        v = validate(p, state, BLOCK)
        assert not v["ok"] and needle in v["reason"], (p["steps"], v["reason"])


def test_runner_moves_the_block_and_back_again():
    a = arm()
    r = runner.run(plan(), a)
    assert r["status"] == "executed" and r["steps_done"] == ["pick", "place", "home"], r
    assert a.state()["point_holds"] == {"A": None, "B": "block"}
    assert not validate(plan(), a.state(), BLOCK)["ok"], "A is empty now"
    assert runner.run(plan("B", "A", "p2"), a)["status"] == "executed"
    assert a.state()["point_holds"] == {"A": "block", "B": None}


def test_a_block_cannot_be_poured_and_a_cup_cannot_be_placed():
    # a plan cannot name arm steps, so this guards the executor's own step check
    from agentic.openarms_agent.validator import apply_step
    mixed = {**copy.deepcopy(LIQUID), "P": {"kind": "point", "holds": "block"}, "Q": {"kind": "point"}}
    for first, second, needle in (
        ({"station": "P"}, ("pour", {"into": "C"}), "not holding a cup"),
        ({"station": "A"}, ("place", {"station": "Q"}), "not holding an object"),
    ):
        state = MockArm(copy.deepcopy(mixed), step_seconds=0).state()
        apply_step(state, mixed, {"action": "pick", "args": first})
        try:
            apply_step(state, mixed, {"action": second[0], "args": second[1]})
        except ValueError as e:
            assert needle in str(e), e
        else:
            raise AssertionError(f"{second[0]} was allowed")


def test_liquid_bench_state_is_unchanged_by_this_feature():
    assert "point_holds" not in MockArm(copy.deepcopy(LIQUID), step_seconds=0).state()


def test_prompt_shows_where_the_block_is_now():
    a = arm()
    before = prompting.render_system_prompt(BLOCK, a.state(), "obj")
    assert "- A: point, the block is here" in before and "- B: point, empty" in before
    assert "move_block(from, to)" in before
    runner.run(plan(), a)
    after = prompting.render_system_prompt(BLOCK, a.state(), "obj")
    assert "- A: point, empty" in after and "- B: point, the block is here" in after


def test_fresh_session_move_from_a_to_b_reaches_the_teacher_and_runs():
    from agentic.scripts.brain_repl import make_brain, MOVING_OBJECTIVE
    a = arm()
    b = make_brain(a, copy.deepcopy(BLOCK))
    steps = [{"action": "move_block", "args": {"from": "A", "to": "B"}}]
    b._client = FakeClient([
        resp([text("I'll move the block from A to B. Send it to your teacher?")], "end_turn"),
        resp([tool_use("submit_plan", {"student_instruction": "move from A to B", "steps": steps})], "tool_use"),
        resp([text("Waiting for your teacher to approve.")], "end_turn"),
    ])
    assert b.objective == MOVING_OBJECTIVE
    first = b.handle_turn("t1", "move from A to B")
    assert first["status"] == "reply" and first["plan"] is None, "no plan before the student says yes"
    system = b._client.calls[0]["system"]
    assert "the block is here" in system and "Moving tasks" in system
    second = b.handle_turn("t2", "yes")
    assert second["status"] == "awaiting_teacher" and second["plan"]["steps"] == steps
    assert a.state()["point_holds"] == {"A": "block", "B": None}, "nothing moves before the teacher approves"
    result = runner.run(second["plan"], a)
    assert result["status"] == "executed"
    assert a.state()["point_holds"] == {"A": None, "B": "block"}
    assert "finished" in b.notify(result)["text"]


def test_pose_arm_replays_saved_poses_for_pick_and_place():
    from firmware.openarms_executor.motion import FakeRobot
    from firmware.openarms_executor.pose_arm import PoseArm
    from firmware.openarms_executor.poses import load_poses
    names = ["HOME", "ABOVE_A", "GRASP_A", "ABOVE_B", "GRASP_B"]
    joints = ["shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos", "wrist_flex.pos", "wrist_roll.pos"]
    poses = {"poses": {n: {j: float(10 * i + k) for k, j in enumerate(joints)} for i, n in enumerate(names)},
             "gripper": {"open": 90.0, "cup": 20.0}}
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "poses.json"
        path.write_text(json.dumps(poses))
        robot = FakeRobot(poses["poses"]["HOME"])
        pa = PoseArm(robot, load_poses(path), copy.deepcopy(BLOCK), seconds=0.01, hz=30)
        assert runner.run(plan(), pa)["status"] == "executed"
    order = []
    for cmd in robot.sent:  # the saved targets in the order the arm reached them
        for n in names:
            if cmd == poses["poses"][n] and (not order or order[-1] != n):
                order.append(n)
        for g, v in poses["gripper"].items():
            if cmd == {"gripper.pos": v} and (not order or order[-1] != g):
                order.append(g)
    assert order == ["open", "ABOVE_A", "GRASP_A", "cup", "ABOVE_A", "ABOVE_B", "GRASP_B", "open", "ABOVE_B", "HOME"], order
    assert pa.state()["point_holds"] == {"A": None, "B": "block"}


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
