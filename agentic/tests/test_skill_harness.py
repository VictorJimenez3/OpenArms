from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from agentic.openarms_agent.cold_planner import Draft
from agentic.openarms_agent.mock_arm import MockArm
from agentic.openarms_agent.skill_harness import SkillHarness
from agentic.openarms_agent.skill_library import SkillLibrary

STATIONS = {"A": {"kind": "point", "holds": "block"}, "B": {"kind": "point"}}
TRANSFER = [{"action": "move_block", "args": {"from": "A", "to": "B"}}]
REQUEST = "Move the block from A to B"


def make(tmp_path, arm=None, **kwargs):
    return SkillHarness(session_id="test", stations=STATIONS,
                        arm=arm or MockArm(STATIONS, step_seconds=0),
                        journal_dir=tmp_path, **kwargs)


def test_confirmation_binds_immutable_single_use_preview(tmp_path):
    harness = make(tmp_path)
    proposal = harness.propose(REQUEST)
    assert proposal["route"] == "warm"
    assert proposal["status"] == "awaiting_confirmation"
    proposal["plan"]["steps"].clear()
    result = harness.confirm(proposal["plan_id"])
    assert result["status"] == "executed"
    assert result["state"]["point_holds"] == {"A": None, "B": "block"}
    assert result["evidence"] == {"source": "mock_state", "observation": None}
    assert harness.confirm(proposal["plan_id"])["status"] == "already_consumed"


def test_recognized_invalid_revision_revokes_prior_preview(tmp_path):
    harness = make(tmp_path)
    proposal = harness.propose(REQUEST)
    assert harness.propose("Move the block from A to A")["status"] == "rejected"
    assert harness.confirm(proposal["plan_id"])["status"] == "rejected"


def test_state_change_makes_preview_stale(tmp_path):
    arm = MockArm(STATIONS, step_seconds=0)
    harness = make(tmp_path, arm)
    proposal = harness.propose(REQUEST)
    arm.run_step("go_to", {"pose": "ABOVE_A"})
    result = harness.confirm(proposal["plan_id"])
    assert result["status"] == "rejected"
    assert arm.state()["point_holds"] == {"A": "block", "B": None}


def test_cold_review_persists_and_history_reaches_future_planner(tmp_path):
    library = SkillLibrary(tmp_path / "skills.json")
    contexts = []

    def planner(request):
        contexts.append(request)
        return Draft(TRANSFER, input_tokens=35, output_tokens=12)

    text = "Put the block in the other work area"
    harness = make(tmp_path, planner=planner, library=library)
    harness.record_prediction("The block will be at B.")
    proposal = harness.propose(text)
    assert proposal["route"] == "cold"
    assert contexts[0].history[-1]["text"] == "The block will be at B."
    assert proposal["usage"] == {"input_tokens": 35, "output_tokens": 12}
    with pytest.raises(ValueError):
        harness.promote(proposal["plan_id"])
    assert harness.confirm(proposal["plan_id"])["status"] == "executed"
    assert harness.promote(proposal["plan_id"]) == 1
    with pytest.raises(ValueError):
        harness.promote(proposal["plan_id"])
    fresh = make(tmp_path, library=SkillLibrary(tmp_path / "skills.json"), planner=planner)
    assert fresh.propose(text)["route"] == "warm"
    assert len(contexts) == 1
    assert fresh.propose("Unknown command")["route"] == "cold"
    assert any(entry["kind"] == "result" for entry in contexts[-1].history)


def test_cold_cannot_invent_actions_or_write_evidence(tmp_path):
    harness = make(tmp_path, planner=lambda _: Draft([{"action": "measure_ph", "args": {}}]))
    proposal = harness.propose("Read the chemistry")
    assert proposal["status"] == "rejected"
    assert not proposal.get("plan_id")
    assert harness.propose("Move the block from A to B or C")["status"] != "awaiting_confirmation"


def test_failure_stops_and_records_partial_state(tmp_path):
    arm = MockArm(STATIONS, fail_at="place", step_seconds=0)
    harness = make(tmp_path, arm)
    result = harness.confirm(harness.propose(REQUEST)["plan_id"])
    assert result["status"] == "failed"
    assert result["steps_done"] == ["pick"]
    assert result["state"]["holding"] == "block"
    assert result["state"]["armed"] is False
    assert harness.propose(REQUEST)["status"] == "rejected"


def test_mismatched_execution_state_is_failure(tmp_path):
    class NoMotionArm(MockArm):
        def run_step(self, action, args):
            pass

    harness = make(tmp_path, NoMotionArm(STATIONS, step_seconds=0))
    result = harness.confirm(harness.propose(REQUEST)["plan_id"])
    assert result["status"] == "failed"
    assert result["steps_done"] == []


def test_stop_during_step_blocks_new_dispatch_and_final_steps(tmp_path):
    started, release = Event(), Event()

    class BlockingArm(MockArm):
        def run_step(self, action, args):
            started.set()
            assert release.wait(3)
            return super().run_step(action, args)

    harness = make(tmp_path, BlockingArm(STATIONS, step_seconds=0))
    plan_id = harness.propose(REQUEST)["plan_id"]
    with ThreadPoolExecutor() as pool:
        result = pool.submit(harness.confirm, plan_id)
        try:
            assert started.wait(3)
            assert harness.confirm(plan_id)["status"] == "already_consumed"
            assert harness.propose(REQUEST)["status"] == "busy"
            assert harness.stop()["status"] == "stop_requested"
            assert harness.stop()["status"] == "stop_requested"
        finally:
            release.set()
        receipt = result.result(3)
    assert receipt["status"] == "stopped"
    assert receipt["steps_done"] == ["pick"]
    assert receipt["state"]["armed"] is False


def test_stop_invalidates_in_flight_authoring(tmp_path):
    started, release = Event(), Event()

    def planner(request):
        started.set()
        assert release.wait(3)
        return Draft(TRANSFER)

    harness = make(tmp_path, planner=planner)
    with ThreadPoolExecutor() as pool:
        result = pool.submit(harness.propose, "Take it to the other side")
        try:
            assert started.wait(3)
            assert harness.stop()["status"] == "stopped"
        finally:
            release.set()
        assert result.result(3)["status"] == "stopped"


def test_preview_failure_blocks_dispatch_and_preserves_evidence(tmp_path):
    preview = lambda *_: {"ok": False, "reason": "Collision", "source": "physics_preflight"}
    harness = make(tmp_path, preview=preview)
    result = harness.propose(REQUEST)
    assert result["status"] == "rejected"
    assert result["reason"] == "Collision"
    assert result["preview"]["source"] == "physics_preflight"


def test_blocks_explicit_physical_backend(tmp_path):
    class PhysicalArm(MockArm):
        mode = "physical"

    with pytest.raises(ValueError, match="physical"):
        make(tmp_path, PhysicalArm(STATIONS))


@pytest.mark.parametrize("text", [
    "Move the block from A to B then stop",
    "Move the block from A to B or move the block from A to C",
    "Do not move the block from A to B",
])
def test_explicit_conflicts_never_delegate_to_a_model(tmp_path, text):
    calls = []
    harness = make(tmp_path, planner=lambda request: calls.append(request) or Draft(TRANSFER))
    assert harness.propose(text)["status"] != "awaiting_confirmation"
    assert not calls


def test_cold_plan_cannot_mix_taught_macros_with_primitive_moves(tmp_path):
    steps = [{"action": "go_to", "args": {"pose": "ABOVE_A"}}] + TRANSFER
    harness = make(tmp_path, planner=lambda request: Draft(steps))
    assert harness.propose("Take it across the room")["status"] == "rejected"


def test_look_has_no_observation_and_go_to_resolves_mock_pose(tmp_path):
    harness = make(tmp_path)
    plan = harness.propose("Look at A then go to HOME")
    assert plan["status"] == "awaiting_confirmation"
    result = harness.confirm(plan["plan_id"])
    assert result["steps_done"] == ["look", "go_to"]
    assert result["evidence"]["observation"] is None


def test_missing_live_point_state_is_rejected_without_authoring(tmp_path):
    class UnobservedArm(MockArm):
        def state(self):
            state = super().state()
            state.pop("point_holds")
            return state

    calls = []
    harness = make(tmp_path, UnobservedArm(STATIONS),
                   planner=lambda request: calls.append(request) or Draft(TRANSFER))
    reply = harness.propose("Take it to the other side")
    assert reply["status"] == "rejected"
    assert not calls


def test_repeated_stop_does_not_claim_success_after_backend_error(tmp_path):
    class StopErrorArm(MockArm):
        def stop(self):
            raise TimeoutError

    harness = make(tmp_path, StopErrorArm(STATIONS))
    assert harness.stop()["status"] == "failed"
    assert harness.stop()["status"] == "failed"
    assert harness.propose(REQUEST)["status"] == "rejected"
