import copy
import json
from pathlib import Path

import pytest

from agentic.openarms_agent.skill_routing import is_stop, route


ROOT = Path(__file__).resolve().parents[2]
LIQUID = json.loads((ROOT / "agentic/contracts/stations.example.json").read_text())
BLOCK = json.loads((ROOT / "agentic/contracts/stations.block.example.json").read_text())


def state(stations, **overrides):
    result = {
        "at": "HOME",
        "holding": None,
        "armed": True,
        "portions_left": {name: value.get("portions", 0) for name, value in stations.items() if value.get("kind") == "source"},
        "receiver_load": {name: 0 for name, value in stations.items() if value.get("kind") == "receiver"},
    }
    if any(value.get("kind") == "point" for value in stations.values()):
        result["point_holds"] = {name: value.get("holds") for name, value in stations.items() if value.get("kind") == "point"}
    result.update(overrides)
    return result


def test_warm_router_preserves_the_current_object_identity():
    assert route("move the block from A to B", state(BLOCK), BLOCK) == [
        {"action": "move_block", "args": {"from": "A", "to": "B"}}
    ]
    legacy_state = state(BLOCK)
    legacy_state.pop("point_holds")
    assert route("move the block from A to B", legacy_state, BLOCK)[0]["args"] == {"from": "A", "to": "B"}
    assert route("move the mandarin from A to B", state({"A": {"kind": "point", "holds": "mandarin"}, "B": {"kind": "point"}}),
                  {"A": {"kind": "point", "holds": "mandarin"}, "B": {"kind": "point"}}) == [
        {"action": "move_block", "args": {"from": "A", "to": "B"}}
    ]


def test_mismatched_or_ambiguous_object_is_rejected():
    with pytest.raises(ValueError, match="does not match"):
        route("move the mandarin from A to B", state(BLOCK), BLOCK)
    with pytest.raises(ValueError, match="object"):
        route("move the object from A to B", state({"A": {"kind": "point"}, "B": {"kind": "point"}}),
              {"A": {"kind": "point"}, "B": {"kind": "point"}})


def test_router_handles_portions_and_composition_without_dropping_a_clause():
    result = route("add two portions from A to C then add 1 portion from B into D", state(LIQUID), LIQUID)
    assert result == [
        {"action": "add_sample", "args": {"source": "A", "into": "C", "portions": 2}},
        {"action": "add_sample", "args": {"source": "B", "into": "D", "portions": 1}},
    ]
    with pytest.raises(ValueError, match="compound"):
        route("move the block from A to B and look at B", state(BLOCK), BLOCK)


def test_router_supports_look_wait_go_to_and_gripper():
    s = state(LIQUID, poses=["HOME", "ABOVE_A", "TIP_C"])
    assert route("look at C", s, LIQUID) == [{"action": "look", "args": {"station": "C"}}]
    assert route("wait 2 seconds", s, LIQUID) == [{"action": "wait", "args": {"seconds": 2}}]
    assert route("go to HOME", s, LIQUID) == [{"action": "go_to", "args": {"pose": "HOME"}}]
    assert route("open the gripper", s, LIQUID) == [{"action": "gripper", "args": {"state": "open"}}]
    with pytest.raises(ValueError, match="seconds"):
        route("wait 31 seconds", s, LIQUID)


def test_unknown_or_novel_request_is_left_for_cold_planner():
    assert route("make the experiment more interesting", state(LIQUID), LIQUID) is None
    assert route("move the block from A to B with a gentle grip", state(BLOCK), BLOCK) is None


def test_stop_control_is_conservative_about_negation_and_compounds():
    assert is_stop("stop")
    assert is_stop("Please stop the arm now")
    assert is_stop("cancel this plan")
    assert not is_stop("do not stop")
    assert not is_stop("stop and move the block")
    assert not is_stop("the arm stopped")


def test_route_does_not_mutate_state():
    before = state(LIQUID)
    route("add 1 portion from A to C", before, LIQUID)
    assert before == state(LIQUID)
