"""Run with `pytest` from the simulation/ folder. No arm or display needed."""

import copy

import numpy as np
import pytest

from openarms_sim import example_plan, preview
from openarms_sim.chemistry import load_model, safety_issues
from openarms_sim.config import load_bench, load_chemistry_config, load_joint_map, load_poses
from openarms_sim.joints import JointMap
from openarms_sim.motion import PlanError, blend, expand_plan, go_to_duration


def block(plan, **kw):
    return preview(plan, render=False, setup="block", **kw)


def liquid(plan, **kw):
    return preview(plan, render=False, setup="liquid_legacy", **kw)


def move(a, b):
    return example_plan(a, b, setup="block")


def add(source, into, portions=1):
    return example_plan(source, into, portions, setup="liquid_legacy")


def codes(result):
    return {i["code"] for i in result["issues"] if i["severity"] == "block"}


def receiver(result, name):
    return next(p for p in result["predicted"] if p["station"] == name)


def where(result, name="block"):
    return next(o for o in result["objects"] if o["name"] == name)["at"]


POINTS = load_bench("block").points

# ---- block setup: move an object from one point to another -----------------


@pytest.mark.parametrize("a", POINTS)
@pytest.mark.parametrize("b", POINTS)
def test_block_moves_between_every_pair_of_points(a, b):
    if a == b:
        return
    result = block(move(a, b), objects={"block": a})
    assert result["ok"], result["warnings"]
    assert where(result) == b


def test_default_setup_is_block_and_default_plan_moves_a_to_b():
    result = preview(example_plan(), render=False)
    assert result["setup"] == "block" and result["ok"] and where(result) == "B"


def test_two_moves_in_one_plan():
    plan = {"steps": [
        {"action": "move_block", "args": {"from": "A", "to": "C"}},
        {"action": "move_block", "args": {"from": "C", "to": "B"}},
    ]}
    result = block(plan)
    assert result["ok"], result["warnings"]
    assert where(result) == "B"


def test_picking_from_an_empty_point_is_blocked():
    result = block(move("B", "C"))  # the block starts at A
    assert {"missed_grasp", "nothing_held"} <= codes(result)
    assert where(result) == "A"


def test_block_gripper_that_misses_is_blocked():
    poses = copy.deepcopy(load_poses("block"))
    poses["GRASP_A"]["shoulder_pan"] += 12
    result = block(move("A", "B"), poses=poses)
    assert "missed_grasp" in codes(result) and where(result) == "A"


def test_block_released_off_its_mark_is_blocked():
    poses = copy.deepcopy(load_poses("block"))
    poses["GRASP_B"]["shoulder_pan"] += 8
    result = block(move("A", "B"), poses=poses)
    assert "bad_release" in codes(result) and where(result) is None


def test_block_pushed_into_the_table_is_blocked():
    poses = copy.deepcopy(load_poses("block"))
    poses["GRASP_B"]["shoulder_lift"] += 10
    assert codes(block(move("A", "B"), poses=poses)) & {"held_hits_table", "hits_table"}


def test_plan_that_ends_holding_the_block_is_blocked():
    result = block({"steps": [{"action": "pick", "args": {"station": "A"}}, {"action": "home", "args": {}}]})
    assert "still_holding" in codes(result)


def test_bad_block_plans_are_rejected_with_a_reason():
    for steps in (
        [{"action": "dance", "args": {}}],
        [{"action": "move_block", "args": {"from": "A", "to": "Z"}}],
        [{"action": "move_block", "args": {"from": "A", "to": "A"}}],
        [{"action": "move_block", "args": {"from": "A"}}],
        [{"action": "wait", "args": {"seconds": 99}}],
    ):
        result = block({"steps": steps})
        assert not result["ok"] and codes(result) == {"bad_plan"}, steps
    assert codes(block(move("A", "B"), objects={"block": "Z"})) == {"bad_plan"}


def test_unknown_setup_is_a_programming_error():
    with pytest.raises(ValueError, match="unknown setup"):
        preview(move("A", "B"), render=False, setup="nope")


# ---- liquid setup: the normal case -----------------------------------------


@pytest.mark.parametrize("source", load_bench("liquid_legacy").sources)
@pytest.mark.parametrize("into", load_bench("liquid_legacy").receivers)
def test_every_pour_runs_clean(source, into):
    result = liquid(add(source, into))
    assert result["ok"], result["warnings"]
    assert receiver(result, into)["changed"]


def test_acid_turns_indicator_pink_and_base_turns_it_blue():
    assert receiver(liquid(add("A", "C")), "C")["color"] == "pink"
    assert receiver(liquid(add("B", "C")), "C")["color"] == "blue"


def test_acid_then_base_fizzes_back_to_purple():
    start = {"C": {"ph_indicator": 1, "vinegar": 1}}
    c = receiver(liquid(add("B", "C"), contents=start), "C")
    assert c["color"] == "purple" and c["observations"] == ["fizzing"]


def test_other_receiver_is_untouched():
    assert not receiver(liquid(add("A", "C")), "D")["changed"]


# ---- liquid setup: things the preview must block ---------------------------


def test_hazardous_mix_is_blocked_but_still_simulated():
    result = liquid(add("A", "C"), contents={"A": {"bleach": 1}, "C": {"ammonia": 1}})
    assert not result["ok"]
    assert "unsafe_mix" in codes(result)
    assert any("chloramine" in w for w in result["warnings"])
    assert receiver(result, "C")["changed"]  # the student still sees what would happen


def test_simulation_only_substance_is_blocked_even_alone():
    result = liquid(add("A", "C"), contents={"A": {"bleach": 1}, "C": {"water": 1}})
    assert codes(result) == {"unsafe_mix"}


def test_overflow_is_blocked():
    full = {"C": {"ph_indicator": 1, "water": load_bench("liquid_legacy").receiver_capacity - 1}}
    assert "overflow" in codes(liquid(add("A", "C"), contents=full))


def test_gripper_that_misses_the_cup_is_blocked():
    poses = copy.deepcopy(load_poses("liquid_legacy"))
    poses["GRASP_A"]["shoulder_pan"] += 12
    result = liquid(add("A", "C"), poses=poses)
    assert "missed_grasp" in codes(result)
    assert not receiver(result, "C")["changed"]


def test_pouring_beside_the_receiver_is_blocked():
    poses = copy.deepcopy(load_poses("liquid_legacy"))
    for name in ("ABOVE_C", "TIP_C"):
        poses[name]["shoulder_pan"] -= 12  # swings the pour to the empty gap between B and C
    result = liquid(add("A", "C"), poses=poses)
    assert "spill" in codes(result)
    assert not receiver(result, "C")["changed"]


def test_reaching_into_the_table_is_blocked():
    poses = copy.deepcopy(load_poses("liquid_legacy"))
    poses["GRASP_A"]["shoulder_lift"] += 14
    assert codes(liquid(add("A", "C"), poses=poses)) & {"hits_table", "held_hits_table"}


def test_not_tipping_far_enough_is_blocked():
    poses = copy.deepcopy(load_poses("liquid_legacy"))
    poses["TIP_C"] = dict(poses["ABOVE_C"])
    assert "no_pour" in codes(liquid(add("A", "C"), poses=poses))


def test_second_portion_from_the_same_cup_adds_nothing():
    result = liquid(add("B", "D", portions=2))
    assert any(i["code"] == "empty_cup" for i in result["issues"])
    assert receiver(result, "D")["contents"]["baking_soda"] == 1


# ---- building blocks -------------------------------------------------------


def test_plan_actions_expand_to_the_agreed_arm_steps():
    assert [s["action"] for s in expand_plan(move("A", "B"))] == ["pick", "place", "home"]
    steps = expand_plan(add("A", "C", portions=2))
    assert [s["action"] for s in steps] == ["pick", "pour", "pour", "return_cup", "home"]
    with pytest.raises(PlanError):
        expand_plan({"steps": [{"action": "add_sample", "args": {"source": "A", "into": "C", "portions": 0}}]})


def test_joint_map_round_trips():
    jm = JointMap(load_joint_map())
    pose = load_poses("block")["GRASP_A"]
    back = jm.pose_from_model(jm.pose_to_model(pose))
    assert all(abs(back[j] - pose[j]) < 0.02 for j in pose)


def test_go_to_never_exceeds_the_speed_limit():
    q0, q1 = np.radians([0, 0, 0, 0, 0]), np.radians([90, 10, 0, -30, 5])
    duration = go_to_duration(q0, q1, max_speed_deg_s=60, min_duration_s=0.5)
    u = np.linspace(0, 1, 2001)
    progress = np.array([blend(x) for x in u])
    peak = np.max(np.abs(np.diff(progress))) / (u[1] * duration) * 90
    assert peak <= 60 * 1.001
    assert go_to_duration(q0, q0, 60, 0.5) == 0.5


def test_safety_list_is_independent_of_the_colour_model():
    cfg = load_chemistry_config()
    assert safety_issues(cfg, {"ph_indicator": 1, "vinegar": 2, "baking_soda": 1}) == []
    assert safety_issues(cfg, {"mystery": 1}) == ["mystery is not a known substance"]
    assert load_model(cfg).predict({}).label == "empty"


# ---- recordings of the real arm --------------------------------------------


def test_recorded_move_plays_and_places_the_block_where_the_gripper_opened():
    from pathlib import Path

    from openarms_sim.recording import find_hold, load_recording, preview_recording

    path = Path(__file__).resolve().parents[2] / "recordings" / "block_A_B"
    if not path.exists():
        pytest.skip("no recording at recordings/block_A_B")
    rec = load_recording(path)
    close, release = find_hold(rec)
    assert 0 < close < release < len(rec.state)
    result = preview_recording(path, render=False)
    assert result["objects"][0]["at"] == "B"
    assert result["pick"]["time_s"] < result["place"]["time_s"]


# ---- sending a simulated plan to the real arm (no arm needed for these) ----


def test_taught_gripper_command_squeezes_past_where_the_jaw_stops():
    jm = JointMap(load_joint_map())
    jm.use_taught_gripper({"open_value": 40, "closed_value": 22, "closed_command": 4})
    assert jm.gripper_command(40) == pytest.approx(40)  # open stays open
    assert jm.gripper_command(22) == pytest.approx(4)  # shown closed on the object -> commanded tighter
    assert 4 < jm.gripper_command(31) < 40


def test_real_arm_commands_start_and_end_at_home_and_respect_the_speed_limit():
    from openarms_sim.config import CONFIG_DIR
    from openarms_sim.real import FPS, plan_targets

    if not (CONFIG_DIR / "setups" / "taught").exists():
        pytest.skip("no taught setup; run python -m openarms_sim.teach on a recording")
    plan = example_plan("B", "A", setup="taught")
    assert preview(plan, objects={"block": "B"}, render=False, setup="taught")["ok"]
    for speed in (1.0, 0.5):
        targets, home, _ = plan_targets(plan, "taught", speed)
        for cmd in (targets[0], targets[-1]):
            assert all(abs(cmd[f"{j}.pos"] - home[j]) < 2.5 for j in home)
        arr = np.array([[c[f"{j}.pos"] for j in home] for c in targets])
        limit = load_joint_map()["motion"]["max_speed_deg_s"] * speed
        assert np.max(np.abs(np.diff(arr, axis=0))) * FPS <= limit * 1.02
        assert all(0 <= c["gripper.pos"] <= 100 for c in targets)


# ---- playing the real runner's waypoint script ------------------------------------------


def _transfer_script(poses, gripper):
    o, c = {"gripper.pos": gripper["open"]}, {"gripper.pos": gripper["cup"]}
    p = poses
    return [o, p["ABOVE_A"], p["GRASP_A"], c, p["ABOVE_A"], p["ABOVE_B"], p["GRASP_B"], o, p["ABOVE_B"], p["HOME"]]


@pytest.fixture
def firmware_poses():
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "firmware/openarms_executor/poses.json"
    if not path.exists():
        pytest.skip("no firmware pose file in this checkout")
    return json.loads(path.read_text())


def _run_script(fp, **kw):
    from openarms_sim.script import preview_script

    p = fp["poses"]
    args = dict(
        script=_transfer_script(p, fp["gripper"]),
        home={**p["HOME"], "gripper.pos": fp["gripper"]["open"]},
        marks={"A": p["GRASP_A"], "B": p["GRASP_B"]},
        object_at="A",
        render=False,
        trusted=list(p.values()),
    )
    args.update(kw)
    return preview_script(**args)


def test_script_preview_delivers_the_object(firmware_poses):
    out = _run_script(firmware_poses)
    assert out["ok"], out["warnings"]
    assert out["objects"] == [{"name": "mandarin", "at": "B", "started_at": "A", "moved": True}]
    assert out["motion_seconds"] == 15.0  # ten targets at the runner's 1.5 s per move
    assert out["video_url"] is None


def test_script_preview_blocks_a_grasp_on_nothing(firmware_poses):
    out = _run_script(firmware_poses, object_at=None)
    assert not out["ok"]
    assert "missed_grasp" in [i["code"] for i in out["issues"] if i["severity"] == "block"]


def test_script_preview_blocks_when_the_object_is_somewhere_else(firmware_poses):
    out = _run_script(firmware_poses, object_at="B")
    assert not out["ok"]
    assert out["objects"][0]["at"] == "B" and not out["objects"][0]["moved"]


def test_script_preview_geometry_is_a_note_until_the_joint_map_is_measured(firmware_poses):
    out = _run_script(firmware_poses)
    assert not out["joint_map_measured"]
    geometry = [i for i in out["issues"] if i["code"] in ("hits_table", "held_hits_table", "hits_object")]
    assert all(i["severity"] == "note" for i in geometry)
    assert "unmeasured_joint_map" in [i["code"] for i in out["issues"]]


def test_script_preview_rejects_an_incomplete_arm_target(firmware_poses):
    out = _run_script(firmware_poses, marks={"A": {"shoulder_pan.pos": 0.0}, "B": firmware_poses["poses"]["GRASP_B"]})
    assert not out["ok"] and out["issues"][0]["code"] == "bad_plan"
