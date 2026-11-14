"""Brain lane tests (B1-B5). No network: a scripted fake client stands in for Anthropic.
Run: python -m agentic.tests.test_brain"""
import copy
import dataclasses
import json
import re
import sys
import traceback
import uuid
from pathlib import Path
from types import SimpleNamespace

from agentic.openarms_agent import brain, notebook, prompting, tools, validator

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "agentic" / "contracts"
SESSIONS = ROOT / "outputs" / "sessions"
PREFIX = "test-brain-"
STATIONS = json.loads((CONTRACTS / "stations.example.json").read_text())
ARM_STATE = json.loads((CONTRACTS / "arm_state.example.json").read_text())
GOOD_STEPS = [{"action": "add_sample", "args": {"source": "A", "into": "C", "portions": 1}}]
# C is a receiver, not a source: any validator must refuse this.
BAD_STEPS = [{"action": "add_sample", "args": {"source": "C", "into": "D", "portions": 1}}]


class SpyArm:
    """ArmPort that fails the test if anything tries to move it."""

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
    """Returns scripted responses in order and records every create() call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(copy.deepcopy(kw))
        assert self.responses, "fake client ran out of scripted responses"
        return self.responses.pop(0)


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(name, inp, id_=None):
    return SimpleNamespace(type="tool_use", id=id_ or "toolu_" + uuid.uuid4().hex[:8], name=name, input=inp)


def resp(blocks, stop):
    return SimpleNamespace(content=blocks, stop_reason=stop)


def sid():
    return PREFIX + uuid.uuid4().hex[:8]


def make_brain(client, arm=None):
    return brain.Brain(sid(), stations=copy.deepcopy(STATIONS), arm=arm or SpyArm(), client=client)


def make_session(arm=None):
    # Session's fields are not in the contract; fill the ones we can guess by name.
    i = sid()
    known = {"session_id": i, "stations": copy.deepcopy(STATIONS), "arm": arm or SpyArm(),
             "notebook": notebook.Notebook(i)}
    fields = {f.name for f in dataclasses.fields(tools.Session)}
    return tools.Session(**{k: v for k, v in known.items() if k in fields})


# ---- B1 system prompt
def test_prompt_renders_clean():
    s = prompting.render_system_prompt(STATIONS, ARM_STATE, "See what vinegar does to cabbage indicator")
    assert isinstance(s, str) and len(s) > 500, "prompt too short"
    assert "{{" not in s and "}}" not in s, "unfilled placeholder left"
    assert "See what vinegar does to cabbage indicator" in s, "objective missing"


def test_prompt_portions_not_ml():
    s = prompting.render_system_prompt(STATIONS, ARM_STATE, "x")
    assert "portion" in s.lower(), "prompt never says portions"
    for bad in re.findall(r"\b(ml|mL|millilit\w*)\b", s, flags=re.I):
        # Only allowed inside the "never milliliters" rule.
        assert re.search(r"never[^.\n]*" + re.escape(bad), s, flags=re.I), f"prompt uses unit {bad!r}"


def test_prompt_has_station_contents_and_actions():
    s = prompting.render_system_prompt(STATIONS, ARM_STATE, "x")
    for c in ("vinegar", "baking soda water", "purple cabbage indicator"):
        assert c in s, f"station contents {c!r} missing"
    for a in ("add_sample", "wait", "look"):
        assert a in s, f"plan action {a} missing"


def test_prompt_keeps_hard_rules():
    s = prompting.render_system_prompt(STATIONS, ARM_STATE, "x").lower()
    for phrase in ("never invent", "request_help", "teacher"):
        assert phrase in s, f"hard rule phrase {phrase!r} missing"


# ---- B2 tools
TOOL_NAMES = {"submit_plan", "record_prediction", "record_observation", "look", "request_help", "get_notebook"}


def test_tools_names_and_schemas():
    names = [t["name"] for t in tools.TOOLS]
    assert set(names) == TOOL_NAMES, f"tool names {names}"
    assert len(names) == len(set(names)), "duplicate tool names"
    for t in tools.TOOLS:
        assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", t["name"]), t["name"]
        assert isinstance(t.get("description"), str) and t["description"], f"{t['name']} has no description"
        sch = t["input_schema"]
        assert sch.get("type") == "object", f"{t['name']} schema not an object"
        assert isinstance(sch.get("properties", {}), dict)
        for r in sch.get("required", []):
            assert r in sch["properties"], f"{t['name']} requires undeclared {r}"
    json.dumps(tools.TOOLS)


def test_submit_plan_schema_shape():
    sch = next(t for t in tools.TOOLS if t["name"] == "submit_plan")["input_schema"]
    assert {"student_instruction", "steps"} <= set(sch["properties"]), sch["properties"].keys()


def test_dispatch_good_plan_awaits_teacher():
    arm = SpyArm()
    s = make_session(arm)
    r = tools.dispatch("submit_plan", {"student_instruction": "add one of A to C", "steps": GOOD_STEPS}, s)
    json.dumps(r)
    assert r["status"] == "awaiting_teacher", r
    assert r.get("plan_id"), "no plan_id"
    assert isinstance(r.get("expanded"), list) and r["expanded"], "no expanded steps"
    assert arm.moves == [], f"submit_plan moved the arm: {arm.moves}"


def test_dispatch_bad_plan_returns_validator_reason():
    arm = SpyArm()
    s = make_session(arm)
    r = tools.dispatch("submit_plan", {"student_instruction": "add C to D", "steps": BAD_STEPS}, s)
    json.dumps(r)
    assert r["status"] == "rejected", r
    want = validator.validate({"plan_id": "x", "student_instruction": "add C to D", "steps": BAD_STEPS},
                              arm.state(), STATIONS)
    assert not want["ok"], "validator accepted the bad plan; test premise broken"
    assert r["reason"] == want["reason"], f"{r['reason']!r} != {want['reason']!r}"
    assert arm.moves == []


def test_dispatch_every_tool_json_serializable():
    s = make_session()
    inputs = {
        "record_prediction": {"text": "it turns pink"},
        "record_observation": {"text": "pink", "source": "student"},
        "look": {"station": "C"},
        "get_notebook": {},
    }
    for name, inp in inputs.items():
        json.dumps(tools.dispatch(name, inp, s))


def test_request_help_blocks_submit_plan():
    arm = SpyArm()
    s = make_session(arm)
    json.dumps(tools.dispatch("request_help", {"reason": "cup spilled"}, s))
    r = tools.dispatch("submit_plan", {"student_instruction": "add one of A to C", "steps": GOOD_STEPS}, s)
    json.dumps(r)
    assert r.get("status") != "awaiting_teacher", f"submit_plan accepted after request_help: {r}"
    assert arm.moves == []


# ---- B3/B4 brain
def test_stop_words_never_call_model():
    for t in ("stop!", "STOP", "please cancel that", "Cancel."):
        c = FakeClient([])
        r = make_brain(c).handle_turn("t1", t)
        assert c.calls == [], f"{t!r} reached the model"
        assert r["status"] == "stop_requested", f"{t!r} -> {r['status']}"
        assert r["turn_id"] == "t1" and isinstance(r["text"], str) and r["text"]


def test_stop_word_is_word_match():
    # "stopwatch" / "cancellation" contain a stop word but are not one.
    for t in ("use the stopwatch", "what is a cancellation"):
        c = FakeClient([resp([text("ok")], "end_turn")])
        r = make_brain(c).handle_turn("t1", t)
        assert len(c.calls) == 1, f"{t!r} did not reach the model"
        assert r["status"] != "stop_requested"


def test_wait_reaches_model():
    c = FakeClient([resp([text("Which portion count?")], "end_turn")])
    r = make_brain(c).handle_turn("t1", "add A to C then wait 10 seconds")
    assert len(c.calls) == 1, "wait did not reach the model"
    assert r["status"] == "reply", r
    assert r["text"] == "Which portion count?"
    call = c.calls[0]
    assert call["model"] == "claude-sonnet-5-5", call["model"]
    assert isinstance(call["system"], str) or isinstance(call["system"], list)
    assert {t["name"] for t in call["tools"]} == TOOL_NAMES
    assert call["messages"][-1]["role"] == "user"


def test_tool_turn_ends_awaiting_teacher():
    arm = SpyArm()
    tu = tool_use("submit_plan", {"student_instruction": "add one of A to C", "steps": GOOD_STEPS}, "toolu_1")
    c = FakeClient([
        resp([text("Sending it."), tu], "tool_use"),
        resp([text("Waiting for your teacher to approve.")], "end_turn"),
    ])
    r = make_brain(c, arm).handle_turn("t2", "yes")
    assert len(c.calls) == 2, f"expected 2 model calls, got {len(c.calls)}"
    assert r["status"] == "awaiting_teacher", r
    assert r["plan"] and r["plan"]["steps"] == GOOD_STEPS, r["plan"]
    assert r["plan"].get("plan_id"), "plan has no plan_id"
    assert arm.moves == [], "brain moved the arm without teacher approval"
    # Second call must carry assistant tool_use then a user tool_result for toolu_1.
    msgs = c.calls[1]["messages"]
    assert msgs[-2]["role"] == "assistant" and msgs[-1]["role"] == "user", [m["role"] for m in msgs]
    results = [b for b in msgs[-1]["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]
    assert results and results[0]["tool_use_id"] == "toolu_1", msgs[-1]
    json.dumps(c.calls[1]["messages"], default=str)


def test_history_persists_across_turns():
    c = FakeClient([resp([text("Into C or D?")], "end_turn"), resp([text("One portion?")], "end_turn")])
    b = make_brain(c)
    b.handle_turn("t1", "do the vinegar one")
    b.handle_turn("t2", "C")
    msgs = c.calls[1]["messages"]
    assert len(msgs) >= 3, f"history lost: {msgs}"
    flat = json.dumps(msgs, default=str)
    assert "do the vinegar one" in flat and "Into C or D?" in flat
    roles = [m["role"] for m in msgs]
    assert all(a != b_ for a, b_ in zip(roles, roles[1:])), f"roles must alternate: {roles}"


def test_stop_turn_not_in_model_history():
    c = FakeClient([resp([text("ok")], "end_turn")])
    b = make_brain(c)
    b.handle_turn("t1", "stop")
    b.handle_turn("t2", "hello")
    roles = [m["role"] for m in c.calls[0]["messages"]]
    assert roles[0] == "user" and all(a != b_ for a, b_ in zip(roles, roles[1:])), roles


def test_notify_failed_names_step():
    c = FakeClient([resp([text("The arm stopped at pour. What do you see?")], "end_turn")] * 3)
    b = make_brain(c)
    res = json.loads((CONTRACTS / "execution_result.example.json").read_text())
    r = b.notify(res)
    assert r["status"] in ("reply", "help_requested"), r
    assert "pour" in r["text"], f"failed step not named: {r['text']!r}"


def test_notify_executed():
    c = FakeClient([resp([text("The arm finished the steps. What do you see?")], "end_turn")] * 3)
    b = make_brain(c)
    r = b.notify({"plan_id": "p-1", "status": "executed", "steps_done": ["pick", "pour", "return_cup", "home"],
                  "failed_step": None, "reason": None})
    assert r["status"] == "reply", r
    assert r["text"], "empty notify text"
    assert "fail" not in r["text"].lower() and "stopped" not in r["text"].lower(), r["text"]


def cleanup():
    if SESSIONS.exists():
        for p in SESSIONS.rglob(PREFIX + "*"):
            if p.is_file():
                p.unlink()


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    try:
        for n, f in tests:
            try:
                f()
                print(f"PASS {n}")
            except Exception as e:
                failed += 1
                print(f"FAIL {n}: {type(e).__name__}: {e}")
                if not isinstance(e, AssertionError):
                    traceback.print_exc(limit=3)
    finally:
        cleanup()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
