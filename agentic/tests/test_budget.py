"""The API spending cap. No network. Run: python -m agentic.tests.test_budget"""
import copy
import json
import sys
import tempfile
import traceback
from pathlib import Path
from types import SimpleNamespace

from agentic.openarms_agent import brain
from agentic.openarms_agent.budget import RESERVE_USD, Budget, BudgetExceeded, cost_usd
from agentic.tests.test_brain import STATIONS, FakeClient, SpyArm, resp, sid, text


def usage(inp=0, out=0, read=0, write=0):
    return SimpleNamespace(input_tokens=inp, output_tokens=out, cache_read_input_tokens=read,
                           cache_creation_input_tokens=write)


def with_usage(r, u):
    r.usage = u
    return r


def ledger(d):
    return Path(d) / "api_spend.json"


def test_cost_uses_the_models_price_per_million_tokens():
    assert abs(cost_usd("claude-sonnet-5-5", usage(inp=1_000_000)) - 2.00) < 1e-9
    assert abs(cost_usd("claude-sonnet-5-5", usage(out=1_000_000)) - 10.00) < 1e-9
    assert abs(cost_usd("claude-sonnet-5-5", usage(read=1_000_000, write=1_000_000)) - 2.60) < 1e-9
    assert abs(cost_usd("claude-sonnet-5-5", usage(inp=3000, out=500)) - 0.011) < 1e-9


def test_unknown_model_is_priced_at_the_worst_case_and_missing_usage_is_free():
    assert cost_usd("some-new-model", usage(out=1_000_000)) == 50.0
    assert cost_usd("claude-sonnet-5-5", None) == 0.0


def test_spend_adds_up_and_survives_a_restart():
    with tempfile.TemporaryDirectory() as d:
        b = Budget(cap_usd=10, ledger=ledger(d))
        b.record("claude-sonnet-5-5", usage(out=100_000))
        b.record("claude-sonnet-5-5", usage(out=50_000))
        again = Budget(cap_usd=10, ledger=ledger(d))
        assert abs(again.spent_usd - 1.5) < 1e-9 and abs(again.remaining_usd - 8.5) < 1e-9
        assert json.loads(ledger(d).read_text())["calls"] == 2


def test_check_refuses_once_the_cap_less_the_reserve_is_reached():
    with tempfile.TemporaryDirectory() as d:
        b = Budget(cap_usd=2.0, ledger=ledger(d))
        b.check()
        b.record("claude-sonnet-5-5", usage(out=int((2.0 - RESERVE_USD) * 100_000)))
        try:
            b.check()
        except BudgetExceeded as e:
            assert "$2.00" in str(e), e
        else:
            raise AssertionError("no refusal at the cap")


def test_damaged_ledger_stops_spending_instead_of_resetting_to_zero():
    with tempfile.TemporaryDirectory() as d:
        ledger(d).write_text("{not json")
        try:
            Budget(cap_usd=100, ledger=ledger(d)).check()
        except BudgetExceeded:
            return
        raise AssertionError("a damaged ledger was treated as zero spend")


def test_brain_counts_each_call_and_stops_calling_at_the_cap():
    with tempfile.TemporaryDirectory() as d:
        budget = Budget(cap_usd=1.0, ledger=ledger(d))
        client = FakeClient([with_usage(resp([text("Hello.")], "end_turn"), usage(inp=10_000, out=60_000)),
                             resp([text("should never be requested")], "end_turn")])
        b = brain.Brain(sid(), stations=copy.deepcopy(STATIONS), arm=SpyArm(), client=client, budget=budget)
        assert b.handle_turn("t1", "hi")["text"] == "Hello."
        assert abs(budget.spent_usd - 0.62) < 1e-9
        reply = b.handle_turn("t2", "again")  # 0.62 + reserve >= 1.00
        assert len(client.calls) == 1, "a call was made past the cap"
        assert "budget" in reply["text"] and reply["status"] == "reply"


def test_an_injected_client_gets_no_budget_unless_one_is_passed():
    b = brain.Brain(sid(), stations=copy.deepcopy(STATIONS), arm=SpyArm(),
                    client=FakeClient([resp([text("ok")], "end_turn")]))
    assert b.handle_turn("t1", "hi")["text"] == "ok" and b.budget is None


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
