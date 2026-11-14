"""Tests for the safety fixes, written from the behaviour spec before reading the code.
Run: python -m agentic.tests.test_fixes"""
import copy
import json
import os
import sys
import time
import traceback
from pathlib import Path
from types import SimpleNamespace as NS

from agentic.openarms_agent.types import ArmError

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "agentic" / "contracts"
STATIONS = json.loads((CONTRACTS / "stations.example.json").read_text())
STATE = json.loads((CONTRACTS / "arm_state.example.json").read_text())
PLAN = json.loads((CONTRACTS / "plan.example.json").read_text())
POSES_FILE = ROOT / "firmware" / "openarms_executor" / "poses.example.json"
SESSION_IDS = []  # brain sessions to delete afterwards


def _plan(steps):
    return {"plan_id": "p-t", "student_instruction": "x", "steps": steps}


def _add(portions):
    return {"action": "add_sample", "args": {"source": "A", "into": "C", "portions": portions}}


# ---------- core: validator ----------

def _rejects(plan, state=None):
    from agentic.openarms_agent import validator
    r = validator.validate(plan, copy.deepcopy(state or STATE), copy.deepcopy(STATIONS))
    assert r["ok"] is False, r
    assert isinstance(r["reason"], str) and r["reason"].strip(), r
    return r


def test_validator_accepts_example():
    from agentic.openarms_agent import validator
    r = validator.validate(copy.deepcopy(PLAN), copy.deepcopy(STATE), copy.deepcopy(STATIONS))
    assert r["ok"] is True, r


def test_validator_steps_not_list():
    _rejects(_plan("add A to C"))
    _rejects(_plan(None))
    _rejects(_plan({"action": "wait"}))


def test_validator_step_not_dict():
    _rejects(_plan(["wait"]))
    _rejects(_plan([None]))


def test_validator_args_not_dict():
    _rejects(_plan([{"action": "wait", "args": [10]}]))
    _rejects(_plan([{"action": "look", "args": "C"}]))


def test_validator_portions_range():
    _rejects(_plan([_add(0)]))
    _rejects(_plan([_add(11)]))
    _rejects(_plan([_add(-1)]))


def test_validator_disarmed():
    s = copy.deepcopy(STATE)
    s["armed"] = False
    _rejects(copy.deepcopy(PLAN), s)


# ---------- core: runner ----------

class RaisingArm:
    def __init__(self, fail_on, exc):
        self.fail_on, self.exc, self.calls = fail_on, exc, []

    def run_step(self, action, args):
        self.calls.append(action)
        if action == self.fail_on:
            raise self.exc

    def stop(self):
        pass

    def state(self):
        return copy.deepcopy(STATE)


def test_runner_any_exception_fails():
    from agentic.openarms_agent import runner
    for exc in (TimeoutError("bus timeout"), ConnectionError("usb"), KeyError("x")):
        arm = RaisingArm("pour", exc)
        r = runner.run(copy.deepcopy(PLAN), arm)
        assert r["status"] == "failed", r
        assert r["failed_step"] == "pour", r
        assert type(exc).__name__ in (r["reason"] or ""), r
        assert arm.calls == ["pick", "pour"], arm.calls  # no retry, nothing after
        assert r["steps_done"] == ["pick"], r


def test_runner_arm_error_still_fails():
    from agentic.openarms_agent import runner
    arm = RaisingArm("pour", ArmError("pour", "lost cup"))
    r = runner.run(copy.deepcopy(PLAN), arm)
    assert r["status"] == "failed" and r["failed_step"] == "pour", r
    assert arm.calls == ["pick", "pour"], arm.calls


# ---------- core: notebook ----------

def test_notebook_session_id():
    from agentic.openarms_agent.notebook import Notebook
    for bad in ("../x", "a/b", "", "x y", "..", "a.json", "s\\x"):
        try:
            Notebook(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad!r}")
    Notebook("s-ok_1")


# ---------- brain ----------

def _text(t):
    return NS(type="text", text=t)


def _tool(i, name, inp):
    return NS(type="tool_use", id=i, name=name, input=inp)


def _resp(blocks, stop="end_turn"):
    return NS(content=blocks, stop_reason=stop)


class FakeClient:
    """Queue of responses; returns a plain text reply when empty."""

    def __init__(self):
        self.queue, self.calls = [], []
        self.messages = self

    def push(self, *resps):
        self.queue.extend(resps)

    def create(self, **kw):
        self.calls.append(copy.deepcopy(kw.get("messages")))
        return self.queue.pop(0) if self.queue else _resp([_text("ok.")])


def _brain(tag):
    from agentic.openarms_agent.brain import Brain
    sid = f"t-fix-{tag}-{os.getpid()}"
    SESSION_IDS.append(sid)
    c = FakeClient()
    return Brain(sid, client=c), c


def _get(b, k):
    return b.get(k) if isinstance(b, dict) else getattr(b, k, None)


def _blocks(msg):
    c = _get(msg, "content")
    return [{"type": "text", "text": c}] if isinstance(c, str) else list(c)


def _check_history(messages):
    """Roles alternate starting with user; every tool_use is answered in the next message."""
    assert messages, "empty history"
    assert _get(messages[0], "role") == "user", messages[0]
    for a, b in zip(messages, messages[1:]):
        assert _get(a, "role") != _get(b, "role"), f"two {_get(a, 'role')} in a row"
    for i, m in enumerate(messages):
        if _get(m, "role") != "assistant":
            continue
        ids = {_get(b, "id") for b in _blocks(m) if _get(b, "type") == "tool_use"}
        if not ids:
            continue
        assert i + 1 < len(messages), f"tool_use {ids} with no reply"
        got = {_get(b, "tool_use_id") for b in _blocks(messages[i + 1]) if _get(b, "type") == "tool_result"}
        assert ids <= got, f"tool_use {ids - got} has no tool_result"


def _tool_result(messages, tid):
    for m in messages:
        if _get(m, "role") == "user":
            for b in _blocks(m):
                if _get(b, "type") == "tool_result" and _get(b, "tool_use_id") == tid:
                    return b
    raise AssertionError(f"no tool_result for {tid}")


GOOD_SUBMIT = {"student_instruction": "add A to C", "steps": [_add(1)]}  # flat, per tools.TOOLS schema


def test_brain_tool_raises_is_error():
    br, c = _brain("raise")
    c.push(_resp([_tool("tu1", "record_prediction", {})], "tool_use"), _resp([_text("Noted.")]))
    reply = br.handle_turn("t1", "I think it turns pink")
    assert isinstance(reply["text"], str), reply
    assert _get(_tool_result(br.messages, "tu1"), "is_error") is True
    _check_history(br.messages)
    br.handle_turn("t2", "next?")  # history still usable
    _check_history(br.messages)


def test_brain_max_tokens_tool_use_answered():
    br, c = _brain("maxtok")
    c.push(_resp([_text("Let me note"), _tool("tu1", "record_prediction", {"text": "pink"})], "max_tokens"))
    br.handle_turn("t1", "it will turn pink")
    _tool_result(br.messages, "tu1")
    br.handle_turn("t2", "and?")
    _check_history(br.messages)
    for sent in c.calls:  # what reached the API was valid too
        _check_history(sent)


def test_brain_roles_alternate():
    br, c = _brain("alt")
    br.handle_turn("t1", "hello")
    br.handle_turn("t2", "stop")  # stop never reaches the model but may touch history
    br.handle_turn("t3", "what now?")
    c.push(_resp([_tool("tu9", "get_notebook", {})], "tool_use"), _resp([_text("Here.")]))
    br.handle_turn("t4", "show notebook")
    _check_history(br.messages)
    for sent in c.calls:
        _check_history(sent)


def test_brain_stop_latch():
    br, c = _brain("stop")
    c.push(_resp([_tool("s1", "submit_plan", GOOD_SUBMIT)], "tool_use"), _resp([_text("Sent to teacher.")]))
    r = br.handle_turn("t1", "add one portion of A to C")
    assert br.session.pending_plan is not None, (r, _tool_result(br.messages, "s1"))
    n_calls = len(c.calls)
    r = br.handle_turn("t2", "stop")
    assert r["status"] == "stop_requested", r
    assert len(c.calls) == n_calls, "stop reached the model"
    assert br.session.stop_requested is True
    assert br.session.pending_plan is None
    br.handle_turn("t3", "ok what happened")
    assert br.session.stop_requested is True, "non-stop turn cleared the stop"
    br.handle_turn("t3b", "cancel")
    assert br.session.stop_requested is True
    c.push(_resp([_tool("s2", "submit_plan", GOOD_SUBMIT)], "tool_use"), _resp([_text("Sent.")]))
    br.handle_turn("t4", "try again: one portion of A to C")
    assert br.session.pending_plan is not None, _tool_result(br.messages, "s2")
    assert br.session.stop_requested is False, "awaiting_teacher should clear the stop"
    _check_history(br.messages)


def test_brain_rejected_submit_keeps_stop():
    br, c = _brain("stoprej")
    br.handle_turn("t1", "stop")
    bad = {"student_instruction": "x", "steps": [_add(50)]}
    c.push(_resp([_tool("s1", "submit_plan", bad)], "tool_use"), _resp([_text("Can't.")]))
    br.handle_turn("t2", "add 50 of A to C")
    assert br.session.stop_requested is True, "a rejected plan must not clear the stop"


def test_brain_pending_survives_chat():
    br, c = _brain("pend")
    c.push(_resp([_tool("s1", "submit_plan", GOOD_SUBMIT)], "tool_use"), _resp([_text("Sent.")]))
    br.handle_turn("t1", "add one portion of A to C")
    p = br.session.pending_plan
    assert p is not None, _tool_result(br.messages, "s1")
    br.handle_turn("t2", "ok thanks")
    assert br.session.pending_plan == p, br.session.pending_plan


# ---------- arm ----------

def _poses():
    from firmware.openarms_executor.poses import load_poses
    return copy.deepcopy(load_poses(str(POSES_FILE)))


def _robot_cls():
    # FakeRobot records every command in .sent, so subclasses count sends for free
    from firmware.openarms_executor.motion import FakeRobot
    return FakeRobot, FakeRobot


def _arm(robot, poses=None, **kw):
    from firmware.openarms_executor.pose_arm import PoseArm
    kw.setdefault("seconds", 0.01)
    kw.setdefault("hz", 30)
    kw.setdefault("pour_hold", 0.0)
    return PoseArm(robot, poses or _poses(), copy.deepcopy(STATIONS), **kw)


def _assert_latched(arm, robot):
    st = arm.state()
    assert st["at"] == "unknown", st
    assert st["armed"] is False, st
    n = len(robot.sent)
    for action, args in (("home", {}), ("pick", {"station": "A"}), ("look", {"station": "C"})):
        try:
            arm.run_step(action, args)
        except ArmError:
            pass
        else:
            raise AssertionError(f"{action} ran after a fault")
    assert len(robot.sent) == n, "commands sent after a fault"


def test_move_to_fake_arrives():
    from firmware.openarms_executor.motion import move_to
    FakeRobot, _ = _robot_cls()
    r = FakeRobot()
    tgt = {"shoulder_pan.pos": 20.0, "elbow_flex.pos": -15.0}
    assert move_to(r, tgt, 0.01, 30, lambda: False, tol=3.0, settle=0.2) is True
    obs = r.get_observation()
    assert all(obs[k] == v for k, v in tgt.items()), obs


def test_move_to_lagging_robot_converges():
    from firmware.openarms_executor.motion import move_to
    FakeRobot, _ = _robot_cls()

    class Lagging(FakeRobot):
        # each command only gets the joint halfway there
        def __init__(self):
            super().__init__()
            self.pos, self.sends = dict(super().get_observation()), 0

        def get_observation(self):
            return dict(self.pos)

        def send_action(self, a):
            self.sends += 1
            for k, v in a.items():
                self.pos[k] = self.pos.get(k, 0.0) + (v - self.pos.get(k, 0.0)) / 2

    r = Lagging()
    assert move_to(r, {"shoulder_pan.pos": 40.0}, 0.01, 30, lambda: False, tol=3.0, settle=1.0) is True
    assert abs(r.pos["shoulder_pan.pos"] - 40.0) <= 3.0, r.pos


def test_move_to_never_arrives_raises():
    from firmware.openarms_executor.motion import move_to
    FakeRobot, _ = _robot_cls()

    class Stuck(FakeRobot):
        def get_observation(self):
            o = dict(super().get_observation())
            o["shoulder_pan.pos"] = 0.0  # pan joint blocked at 0
            return o

    t0 = time.monotonic()
    try:
        move_to(Stuck(), {"shoulder_pan.pos": 30.0}, 0.01, 30, lambda: False, tol=3.0, settle=0.3)
    except RuntimeError:
        assert time.monotonic() - t0 < 2.0, "settle not honoured"
        return
    raise AssertionError("no error for a joint that never arrived")


def test_pose_arm_send_error_latches():
    _, Counting = _robot_cls()

    class Flaky(Counting):
        def send_action(self, a):
            if len(self.sent) >= 3:
                raise ConnectionError("usb dropped")
            return super().send_action(a)

    r = Flaky()
    arm = _arm(r)
    try:
        arm.run_step("pick", {"station": "A"})
    except ArmError as e:
        assert e.step == "pick", e.step
    else:
        raise AssertionError("ConnectionError not raised as ArmError")
    _assert_latched(arm, r)


def test_pose_arm_not_arriving_latches():
    _, Counting = _robot_cls()

    class Stuck(Counting):
        def get_observation(self):
            o = dict(super().get_observation())
            o["shoulder_lift.pos"] = 0.0
            return o

    r = Stuck()
    arm = _arm(r)
    try:
        arm.run_step("home", {})
    except ArmError as e:
        assert e.step == "home", e.step
    else:
        raise AssertionError("no ArmError for a joint that never arrived")
    _assert_latched(arm, r)


def test_pose_arm_stop_latches():
    _, Counting = _robot_cls()
    holder = {}

    class Stopper(Counting):
        def send_action(self, a):
            if len(self.sent) == 2:
                holder["arm"].stop()
            return super().send_action(a)

    r = Stopper()
    arm = _arm(r, seconds=0.2)
    holder["arm"] = arm
    try:
        arm.run_step("pick", {"station": "A"})
    except ArmError:
        pass
    else:
        raise AssertionError("stop part-way did not raise ArmError")
    _assert_latched(arm, r)


def test_pose_arm_missing_args():
    _, Counting = _robot_cls()
    for action in ("pick", "pour", "return_cup", "look"):
        r = Counting()
        try:
            _arm(r).run_step(action, {})
        except ArmError:
            assert not r.sent, f"{action} moved before failing"
            continue
        except Exception as e:  # noqa: BLE001
            raise AssertionError(f"{action} raised {type(e).__name__}, not ArmError")
        raise AssertionError(f"{action} with no args did not fail")


SLOT = {"shoulder_pan.pos": -33.0, "shoulder_lift.pos": -37.0, "elbow_flex.pos": 51.0,
        "wrist_flex.pos": 41.0, "wrist_roll.pos": 0.0}


def _with_slots(above, grasp):
    p = _poses()
    for n in (1, 2):
        if above:
            p["poses"][f"ABOVE_A{n}"] = dict(SLOT)
        if grasp:
            p["poses"][f"GRASP_A{n}"] = dict(SLOT, **{"shoulder_lift.pos": -22.0})
    return p


def _near(obs, pose):
    return all(abs(obs[k] - v) < 1e-6 for k, v in pose.items())


def test_slot_both_used():
    _, Counting = _robot_cls()
    r = Counting()
    _arm(r, _with_slots(True, True)).run_step("pick", {"station": "A"})
    assert _near(r.get_observation(), SLOT), r.get_observation()


def test_slot_half_defined_raises():
    _, Counting = _robot_cls()
    for above, grasp in ((True, False), (False, True)):
        r = Counting()
        try:
            _arm(r, _with_slots(above, grasp)).run_step("pick", {"station": "A"})
        except ArmError:
            assert not r.sent, "moved before rejecting a half-defined slot"
            continue
        raise AssertionError(f"half slot above={above} grasp={grasp} accepted")


def test_slot_neither_uses_base():
    _, Counting = _robot_cls()
    r = Counting()
    p = _poses()
    _arm(r, p).run_step("pick", {"station": "A"})
    assert _near(r.get_observation(), p["poses"]["ABOVE_A"]), r.get_observation()


def _cleanup():
    for sid in SESSION_IDS:
        f = ROOT / "outputs" / "sessions" / f"{sid}.json"
        if f.exists():
            f.unlink()


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    try:
        for name, fn in tests:
            try:
                fn()
                print(f"PASS {name}")
            except Exception:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name}\n{traceback.format_exc(limit=3)}")
    finally:
        _cleanup()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
