"""Core lane tests (C1-C5). Run from repo root: python -m agentic.tests.test_core"""
import copy
import json
import os
import sys
import traceback
from pathlib import Path

from agentic.openarms_agent import catalog, runner, validator
from agentic.openarms_agent.mock_arm import MockArm
from agentic.openarms_agent.notebook import Notebook
from agentic.openarms_agent.types import ArmError

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"


def _load(name):
    return json.loads((CONTRACTS / name).read_text())


STATIONS = _load("stations.example.json")
STATE = _load("arm_state.example.json")


def _plan(*steps, plan_id="p-test"):
    return {"plan_id": plan_id, "student_instruction": "test", "steps": list(steps)}


def _add(source, into, portions=1):
    return {"action": "add_sample", "args": {"source": source, "into": into, "portions": portions}}


def _state(**over):
    s = copy.deepcopy(STATE)
    s.update(over)
    return s


def _raises_value_error(plan):
    try:
        catalog.expand(plan)
    except ValueError as e:
        assert str(e).strip(), "ValueError has no readable reason"
        return
    raise AssertionError(f"expand did not raise ValueError for {plan['steps']}")


# --- C1 catalog ---

def test_expand_add_sample_two_portions_gives_7_steps():
    steps = catalog.expand(_plan(_add("A", "C", 2)))
    want = [("pick", {"station": "A"}), ("pour", {"into": "C"}), ("return_cup", {"station": "A"})] * 2 + [("home", {})]
    got = [(s["action"], s["args"]) for s in steps]
    assert got == want, f"got {got}"


def test_expand_contract_example_matches():
    got = catalog.expand(_load("plan.example.json"))
    assert got == _load("expanded_steps.example.json"), f"got {got}"


def test_expand_unknown_action_raises():
    _raises_value_error(_plan({"action": "dance", "args": {}}))


def test_expand_arm_step_in_plan_raises():
    _raises_value_error(_plan({"action": "pick", "args": {"station": "A"}}))


def test_expand_missing_source_raises():
    _raises_value_error(_plan({"action": "add_sample", "args": {"into": "C"}}))


def test_expand_zero_portions_raises():
    _raises_value_error(_plan(_add("A", "C", 0)))


# --- C2 validator ---

def _reject(plan, state=None, stations=None):
    r = validator.validate(plan, state or _state(), stations or STATIONS)
    assert r["ok"] is False, f"expected rejection, got ok for {plan['steps']}"
    assert isinstance(r["reason"], str) and r["reason"].strip(), "rejection has no reason"
    assert "\n" not in r["reason"].strip(), f"reason is not one sentence: {r['reason']!r}"
    assert isinstance(r["expanded"], list), "expanded missing on rejection"
    return r


def test_validate_accepts_and_predicts_end_state():
    plan = _plan(_add("A", "C", 2))
    r = validator.validate(plan, _state(), STATIONS)
    assert r["ok"] is True, f"rejected: {r['reason']}"
    assert len(r["expanded"]) == 7, f"expanded has {len(r['expanded'])} steps"
    e = r["end_state"]
    assert e["at"] == "HOME" and e["holding"] is None, f"end pose {e}"
    assert e["portions_left"] == {"A": 0, "B": 2}, f"portions_left {e['portions_left']}"
    assert e["receiver_load"] == {"C": 2, "D": 0}, f"receiver_load {e['receiver_load']}"


def test_validate_accepts_contract_example():
    r = validator.validate(_load("plan.example.json"), _state(), STATIONS)
    assert r["ok"] is True, f"rejected: {r['reason']}"
    assert r["expanded"] == _load("expanded_steps.example.json")
    assert r["end_state"]["receiver_load"]["C"] == 1


def test_validate_does_not_mutate_input_state():
    s = _state()
    before = copy.deepcopy(s)
    validator.validate(_plan(_add("A", "C", 2)), s, STATIONS)
    assert s == before, f"input state mutated: {s}"


def test_validate_rejects_empty_source():
    _reject(_plan(_add("A", "C", 1)), state=_state(portions_left={"A": 0, "B": 2}))


def test_validate_rejects_more_portions_than_left():
    _reject(_plan(_add("A", "C", 3)))


def test_validate_rejects_wrong_kind_source():
    _reject(_plan(_add("C", "D", 1)))


def test_validate_rejects_wrong_kind_receiver():
    _reject(_plan(_add("A", "B", 1)))


def test_validate_rejects_unknown_station():
    _reject(_plan(_add("Z", "C", 1)))


def test_validate_rejects_receiver_over_capacity():
    # A has 2 and B has 2, so 4 portions into C (capacity 3) is the only failure.
    _reject(_plan(_add("A", "C", 2), _add("B", "C", 2)))


def test_validate_rejects_receiver_already_full():
    _reject(_plan(_add("A", "C", 1)), state=_state(receiver_load={"C": 3, "D": 0}))


def test_validate_rejects_more_than_6_actions():
    look = {"action": "look", "args": {"station": "C"}}
    assert validator.validate(_plan(*[look] * 6), _state(), STATIONS)["ok"] is True, "6 actions should pass"
    _reject(_plan(*[look] * 7))


def test_validate_rejects_bad_wait_seconds():
    for secs in (0, 31, -1):
        _reject(_plan({"action": "wait", "args": {"seconds": secs}}))
    for secs in (1, 30):
        r = validator.validate(_plan({"action": "wait", "args": {"seconds": secs}}), _state(), STATIONS)
        assert r["ok"] is True, f"wait {secs} rejected: {r['reason']}"


def test_validate_rejects_unknown_action():
    _reject(_plan({"action": "dance", "args": {}}))
    _reject(_plan({"action": "pour", "args": {"into": "C"}}))


def test_validate_rejects_look_unknown_station():
    _reject(_plan({"action": "look", "args": {"station": "Z"}}))


def test_validate_rejects_empty_plan():
    # Harness Part B: the brain submits 1-6 plan actions.
    _reject(_plan())


# --- C3 mock arm ---

def test_mock_default_state_matches_contract():
    assert MockArm(step_seconds=0).state() == STATE, f"got {MockArm(step_seconds=0).state()}"


def test_mock_matches_validator_end_state():
    plan = _plan(_add("A", "C", 2), {"action": "wait", "args": {"seconds": 1}}, _add("B", "D", 1),
                 {"action": "look", "args": {"station": "D"}})
    arm = MockArm(step_seconds=0)
    r = validator.validate(plan, arm.state(), STATIONS)
    assert r["ok"], r["reason"]
    for s in r["expanded"]:
        arm.run_step(s["action"], s["args"])
    assert arm.state() == r["end_state"], f"arm {arm.state()} != predicted {r['end_state']}"


def test_mock_pick_updates_holding():
    arm = MockArm(step_seconds=0)
    arm.run_step("pick", {"station": "A"})
    assert arm.state()["holding"] == "A", f"got {arm.state()}"


def test_mock_fail_at_raises_arm_error():
    arm = MockArm(fail_at="pour", step_seconds=0)
    arm.run_step("pick", {"station": "A"})
    try:
        arm.run_step("pour", {"into": "C"})
    except ArmError as e:
        assert e.step == "pour", f"ArmError.step is {e.step}"
        return
    raise AssertionError("fail_at='pour' did not raise ArmError")


def test_mock_state_returns_copy():
    arm = MockArm(step_seconds=0)
    arm.state()["portions_left"]["A"] = 99
    assert arm.state()["portions_left"]["A"] == 2, "state() leaks internal dict"


# --- C4 runner ---

class RecordingArm:
    """Fake ArmPort that logs every call and fails on a chosen step."""

    def __init__(self, fail_at=None):
        self.calls, self.fail_at, self.stopped = [], fail_at, False

    def run_step(self, action, args):
        self.calls.append(action)
        if action == self.fail_at:
            raise ArmError(action, "injected")

    def stop(self):
        self.stopped = True

    def state(self):
        return copy.deepcopy(STATE)


def test_runner_clean_run_executed():
    plan = _plan(_add("A", "C", 1), plan_id="p-clean")
    r = runner.run(plan, MockArm(step_seconds=0))
    assert r["status"] == "executed", f"got {r}"
    assert r["plan_id"] == "p-clean"
    assert r["steps_done"] == ["pick", "pour", "return_cup", "home"], f"steps_done {r['steps_done']}"
    assert r["failed_step"] is None and r["reason"] is None, f"got {r}"


def test_runner_failure_at_pour():
    r = runner.run(_plan(_add("A", "C", 1)), MockArm(fail_at="pour", step_seconds=0))
    assert r["status"] == "failed", f"got {r}"
    assert r["failed_step"] == "pour", f"failed_step {r['failed_step']}"
    assert r["steps_done"] == ["pick"], f"steps_done {r['steps_done']}"
    assert isinstance(r["reason"], str) and r["reason"], "no failure reason"


def test_runner_never_retries_or_continues_after_failure():
    arm = RecordingArm(fail_at="pour")
    r = runner.run(_plan(_add("A", "C", 2)), arm)
    assert arm.calls == ["pick", "pour"], f"arm saw {arm.calls}"
    assert r["status"] == "failed"


def test_runner_stop_before_start_runs_nothing():
    arm = RecordingArm()
    r = runner.run(_plan(_add("A", "C", 1)), arm, should_stop=lambda: True)
    assert r["status"] == "stopped", f"got {r}"
    assert arm.calls == [], f"arm moved after stop: {arm.calls}"


def test_runner_stop_midway():
    arm = RecordingArm()

    def should_stop():
        return len(arm.calls) >= 2  # stop once two steps have run

    r = runner.run(_plan(_add("A", "C", 2)), arm, should_stop=should_stop)
    assert r["status"] == "stopped", f"got {r}"
    assert arm.calls == ["pick", "pour"], f"arm saw {arm.calls}"
    assert r["steps_done"] == ["pick", "pour"], f"steps_done {r['steps_done']}"


def test_runner_invalid_plan_does_not_move():
    arm = RecordingArm()
    try:
        r = runner.run(_plan({"action": "dance", "args": {}}), arm)
    except ValueError:
        r = None
    assert arm.calls == [], f"arm moved on invalid plan: {arm.calls}"
    assert r is None or r["status"] != "executed", f"invalid plan reported {r}"


# --- C5 notebook ---

def test_notebook_roundtrip():
    sid = "s-test-core-roundtrip"
    n = Notebook(sid)
    n.add("prediction", text="turns pink")
    n.add("plan", plan_id="p-1", steps=["add_sample"])
    n.add("result", plan_id="p-1", status="executed")
    n.add("observation", text="pinkish", source="student")
    n.add("help", reason="spill")
    path = Path("outputs/sessions") / f"{sid}.json"
    try:
        n.save()
        assert path.exists(), f"{path} not written"
        m = Notebook.load(sid)
        assert m.entries() == n.entries(), f"{m.entries()} != {n.entries()}"
        assert len(m.entries()) == 5
        text = m.as_text()
        assert "turns pink" in text and "pinkish" in text, f"as_text missing data: {text!r}"
        assert len(text) < 2000, f"as_text is long: {len(text)} chars"
    finally:
        if path.exists():
            os.remove(path)


def test_notebook_rejects_unknown_kind():
    try:
        Notebook("s-test-core-kind").add("gossip", text="x")
    except (ValueError, KeyError):
        return
    raise AssertionError("unknown kind accepted")


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:
            failed += 1
            msg = f"{type(e).__name__}: {e}" if not isinstance(e, AssertionError) else str(e)
            print(f"FAIL {name}: {msg}")
            if not isinstance(e, AssertionError):
                traceback.print_exc(limit=2)
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
