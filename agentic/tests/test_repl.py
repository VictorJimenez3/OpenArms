"""Terminal demo tests (brain_repl). No network, no hardware: fake client, MockArm/SpyArm, FakeRobot.
Run: python -m agentic.tests.test_repl"""
import builtins
import contextlib
import copy
import io
import json
import sys
import traceback
import uuid
from pathlib import Path
from types import SimpleNamespace

from agentic.openarms_agent import brain

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "agentic" / "contracts"
SESSIONS = ROOT / "outputs" / "sessions"
POSES = ROOT / "firmware" / "openarms_executor" / "poses.example.json"
PREFIX = "test-repl-"
STATIONS = json.loads((CONTRACTS / "stations.example.json").read_text())
ARM_STATE = json.loads((CONTRACTS / "arm_state.example.json").read_text())
GOOD_STEPS = [{"action": "add_sample", "args": {"source": "A", "into": "C", "portions": 1}}]


class SpyArm:
    def __init__(self):
        self.moves = []
        self._state = copy.deepcopy(ARM_STATE)

    def run_step(self, action, args):
        self.moves.append((action, args))

    def stop(self):
        pass

    def state(self):
        return copy.deepcopy(self._state)


class FakeClient:
    """Scripted responses in order; once exhausted, every call is a plain end_turn reply."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        if self.responses:
            return self.responses.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")], stop_reason="end_turn")


def plan_client():
    tu = SimpleNamespace(type="tool_use", id="toolu_1", name="submit_plan",
                         input={"student_instruction": "add one of A to C", "steps": GOOD_STEPS})
    return FakeClient([
        SimpleNamespace(content=[SimpleNamespace(type="text", text="Sending it."), tu], stop_reason="tool_use"),
        SimpleNamespace(content=[SimpleNamespace(type="text", text="Waiting for your teacher.")], stop_reason="end_turn"),
    ])


@contextlib.contextmanager
def scripted_input(answers):
    """Each answer is a str or callable(prompt) -> str; EOFError once they run out."""
    prompts, queue, real = [], list(answers), builtins.input

    def fake(prompt=""):
        prompts.append(prompt)
        if not queue:
            raise EOFError
        a = queue.pop(0)
        return a(prompt) if callable(a) else a

    builtins.input = fake
    try:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            yield prompts, out
    finally:
        builtins.input = real


def make_brain(arm=None, stations=None):
    b = brain.Brain(PREFIX + uuid.uuid4().hex[:8], stations=copy.deepcopy(stations or STATIONS), arm=arm,
                    client=plan_client())
    results = []
    real_notify = b.notify

    def notify(result):
        results.append(copy.deepcopy(result))
        return real_notify(result)

    b.notify = notify
    return b, results


def repl():
    from agentic.scripts import brain_repl
    return brain_repl


def teacher(answer, side_effect=None):
    def a(prompt):
        assert "approve" in prompt, f"expected the teacher prompt, got {prompt!r}"
        if side_effect:
            side_effect()
        return answer
    return a


def test_import_does_not_load_firmware():
    before = "firmware.openarms_executor" in sys.modules
    repl()
    if not before:
        assert "firmware.openarms_executor" not in sys.modules, "importing brain_repl pulled in firmware"


def test_mockarm_happy_path_executes():
    b, results = make_brain()
    with scripted_input(["add one portion of A to C", teacher("y")]) as (prompts, out):
        repl().main(b)
    assert len(results) == 1, f"notify calls: {results}"
    assert results[0]["status"] == "executed", results[0]
    s = b.session.arm.state()
    assert s["portions_left"]["A"] == 1 and s["receiver_load"]["C"] == 1, s
    assert s["at"] == "HOME", s
    assert "pick" in out.getvalue(), "expanded steps were not printed before approval"


def test_stale_approval_rejected_no_motion():
    arm = SpyArm()
    b, results = make_brain(arm)

    def drain():
        arm._state["portions_left"]["A"] = 0  # cup used up between submit and approval

    with scripted_input(["add one portion of A to C", teacher("y", drain)]):
        repl().main(b)
    assert arm.moves == [], f"arm moved on a stale plan: {arm.moves}"
    assert len(results) == 1, results
    r = results[0]
    assert r["status"] == "rejected" and r["steps_done"] == [], r
    assert isinstance(r.get("reason"), str) and r["reason"], r


def test_teacher_no_is_teacher_rejected():
    arm = SpyArm()
    b, results = make_brain(arm)
    with scripted_input(["add one portion of A to C", teacher("n"), "too much vinegar"]) as (prompts, _):
        repl().main(b)
    assert arm.moves == [], arm.moves
    assert len(results) == 1 and results[0]["status"] == "teacher_rejected", results
    assert len(prompts) >= 3, f"no teacher comment asked: {prompts}"


def test_stop_before_approval_comes_back_stopped():
    arm = SpyArm()
    b, results = make_brain(arm)
    stop = lambda: b.handle_turn("t-stop", "stop")  # someone says stop while the teacher reads the plan
    with scripted_input(["add one portion of A to C", teacher("y", stop)]):
        repl().main(b)
    assert len(results) == 1 and results[0]["status"] == "stopped", results
    assert arm.moves == [], f"arm moved after stop: {arm.moves}"


def test_eof_ends_loop_and_saves_notebook():
    b, results = make_brain(SpyArm())
    with scripted_input([]):
        repl().main(b)
    sid = b.session.session_id if hasattr(b.session, "session_id") else None
    files = [p for p in SESSIONS.rglob(PREFIX + "*") if p.is_file()] if SESSIONS.exists() else []
    assert files and (sid is None or any(sid in str(p) for p in files)), f"no saved notebook under {SESSIONS}"


def test_pose_arm_no_exits_without_connecting():
    from firmware.openarms_executor import robot
    calls, real = [], robot.connect
    robot.connect = lambda *a, **k: calls.append((a, k))  # spec only forbids connecting, not importing
    try:
        with scripted_input(["n"]) as (prompts, _):
            try:
                repl().pose_arm("/dev/does-not-exist", str(POSES), False)
            except SystemExit:
                pass
            else:
                raise AssertionError("pose_arm did not exit on 'n'")
    finally:
        robot.connect = real
    assert len(prompts) == 1 and "HOME" in prompts[0], prompts
    assert calls == [], f"connected before the bench check: {calls}"


def test_fake_robot_pose_arm_executes_and_ends_home():
    with scripted_input(["y"]):
        arm, stations = repl().pose_arm(None, str(POSES), True)
    assert stations == STATIONS, stations
    arm.seconds, arm.pour_hold = 0.01, 0.0
    b, results = make_brain(arm, stations)
    with scripted_input(["add one portion of A to C", teacher("y")]):
        repl().main(b)
    assert len(results) == 1 and results[0]["status"] == "executed", results
    s = arm.state()
    assert s["at"] == "HOME" and s["holding"] is None, s
    assert s["portions_left"]["A"] == 1 and s["receiver_load"]["C"] == 1, s


def cleanup():
    if SESSIONS.exists():
        for p in SESSIONS.rglob(PREFIX + "*"):
            if p.is_file():
                p.unlink()


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failed = 0
    try:
        for n, f in tests:
            try:
                f()
                print(f"PASS {n}")
            except BaseException as e:  # SystemExit from the code under test is a failure, not an exit
                failed += 1
                print(f"FAIL {n}: {type(e).__name__}: {e}")
                if not isinstance(e, AssertionError):
                    traceback.print_exc(limit=4)
    finally:
        cleanup()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
