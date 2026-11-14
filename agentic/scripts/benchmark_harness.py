"""Repeatable local benchmark. Run from the repository root."""

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from statistics import median, quantiles
from tempfile import TemporaryDirectory
from time import perf_counter

from agentic.openarms_agent import runner, validator
from agentic.openarms_agent.mock_arm import MockArm

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
LIQUID = json.loads((CONTRACTS / "stations.example.json").read_text())
BLOCK = json.loads((CONTRACTS / "stations.block.example.json").read_text())
MANDARIN = {"A": {"kind": "point", "holds": "mandarin"}, "B": {"kind": "point"}}
REVERSED = {"A": {"kind": "point"}, "B": {"kind": "point", "holds": "block"}}
OCCUPIED = {"A": BLOCK["A"], "B": MANDARIN["A"]}
TRANSFER = {"action": "move_block", "args": {"from": "A", "to": "B"}}
NOVEL = "Put the block on the empty work mark across the bench"


def add(source, target, count=1):
    return {"action": "add_sample", "args": {"source": source, "into": target, "portions": count}}


@dataclass
class Case:
    name: str
    text: str
    stations: dict
    route: str
    status: str
    steps: list | None = None
    expected: dict | None = None
    control: str = ""


BLOCK_END = {"point_holds": {"A": None, "B": "block"}}
CASES = [
    Case("block-transfer", "Move the block from A to B", BLOCK, "warm", "executed", [TRANSFER], BLOCK_END),
    Case("block-paraphrase", "Please carry the block from a into b.", BLOCK, "warm", "executed", [TRANSFER], BLOCK_END),
    Case("mandarin", "Transfer the mandarin from A to B", MANDARIN, "warm", "executed", [TRANSFER],
         {"point_holds": {"A": None, "B": "mandarin"}}),
    Case("reverse", "Move the block from B to A", REVERSED, "warm", "executed",
         [{"action": "move_block", "args": {"from": "B", "to": "A"}}], {"point_holds": {"A": "block", "B": None}}),
    Case("sample-a", "Add one portion of A to C", LIQUID, "warm", "executed", [add("A", "C")],
         {"receiver_load": {"C": 1, "D": 0}, "portions_left": {"A": 1, "B": 2}}),
    Case("sample-b", "Pour 2 portions from B into D", LIQUID, "warm", "executed", [add("B", "D", 2)],
         {"receiver_load": {"C": 0, "D": 2}, "portions_left": {"A": 2, "B": 0}}),
    Case("compose", "Add from A to C then add from B to D then wait 2 seconds then look at D",
         LIQUID, "warm", "executed",
         [add("A", "C"), add("B", "D"), {"action": "wait", "args": {"seconds": 2}},
          {"action": "look", "args": {"station": "D"}}], {"receiver_load": {"C": 1, "D": 1}}),
    Case("primitive", "Go to ABOVE_A then go to HOME", BLOCK, "warm", "executed",
         [{"action": "go_to", "args": {"pose": "ABOVE_A"}}, {"action": "go_to", "args": {"pose": "HOME"}}], {}),
    Case("quantity", "Add 3 portions from A to C", LIQUID, "warm", "rejected"),
    Case("full-receiver", "Add 2 portions from A to C then add 2 portions from B to C", LIQUID, "warm", "rejected"),
    Case("occupied", "Move the block from A to B", OCCUPIED, "warm", "rejected"),
    Case("identity", "Move the mandarin from A to B", BLOCK, "warm", "rejected"),
    Case("ambiguous", "Move the block from A to B or C", BLOCK, "warm", "rejected"),
    Case("unsupported", "Move it over there", BLOCK, "cold", "needs_clarification"),
    Case("invented-step", "Measure and tell me the pH", LIQUID, "cold", "rejected"),
    Case("cold-and-reuse", NOVEL, BLOCK, "cold", "executed", [TRANSFER], BLOCK_END, "reuse"),
    Case("injected-failure", "Move the block from A to B", BLOCK, "warm", "failed", [TRANSFER],
         {"holding": "block", "armed": False}, "failure"),
    Case("cancel", "Move the block from A to B", BLOCK, "warm", "rejected", control="stop"),
    Case("supersede", "Move the block from A to B", BLOCK, "warm", "rejected", control="revise"),
    Case("duplicate", "Move the block from A to B", BLOCK, "warm", "executed", [TRANSFER], BLOCK_END, "duplicate"),
]


def fixture(request):
    from agentic.openarms_agent.cold_planner import Draft

    if request.text == NOVEL:
        return Draft([TRANSFER])
    if request.text == "Measure and tell me the pH":
        return Draft([{"action": "measure_ph", "args": {}}])
    return None


def ms(since):
    return (perf_counter() - since) * 1000


def matches(state, fields):
    return state is not None and all(state.get(key) == value for key, value in fields.items())


def run_case(case, directory, times):
    from agentic.openarms_agent.skill_harness import SkillHarness
    from agentic.openarms_agent.skill_library import SkillLibrary

    arm = MockArm(case.stations, fail_at="place" if case.control == "failure" else None, step_seconds=0)
    initial = arm.state()
    library = SkillLibrary(directory / "skills.json")
    harness = SkillHarness(session_id="trial", stations=case.stations, arm=arm, planner=fixture,
                           library=library, journal_dir=directory)
    started = perf_counter()
    proposal = harness.propose(case.text)
    proposal_ms = ms(started)
    result = proposal
    extra_ok = True
    if proposal["status"] == "awaiting_confirmation":
        if case.control == "stop":
            harness.stop()
        elif case.control == "revise":
            harness.propose("Move the block from A to A")
        result = harness.confirm(proposal["plan_id"])

    if case.status == "executed":
        path = "cold_fixture" if case.route == "cold" else "warm"
        for name, value in (
            ("proposal", proposal_ms),
            ("planner", proposal["timings_ms"]["planning"]),
            ("dispatch", result.get("timings_ms", {}).get("dispatch")),
            ("execution", result.get("timings_ms", {}).get("execution")),
            ("command_to_receipt", ms(started)),
        ):
            if value is not None:
                times[path + "." + name].append(value)
    expected = case.expected if case.expected is not None else {key: val for key, val in initial.items() if key != "armed"}
    state_ok = matches(arm.state(), expected)
    if case.status == "executed":
        state_ok &= matches(arm.state(), {"at": "HOME", "holding": None})
        extra_ok &= result.get("evidence", {}).get("source") == "mock_state"
        extra_ok &= "observation" in result.get("evidence", {}) and result["evidence"]["observation"] is None
        extra_ok &= proposal.get("plan", {}).get("steps") == case.steps
    if case.control == "duplicate" and proposal.get("plan_id"):
        extra_ok &= harness.confirm(proposal["plan_id"])["status"] == "already_consumed"
    if case.control == "reuse" and result["status"] == "executed":
        extra_ok &= harness.promote(proposal["plan_id"]) == 1
        fresh = SkillHarness(session_id="trial", stations=case.stations,
                             arm=MockArm(case.stations, step_seconds=0),
                             library=SkillLibrary(directory / "skills.json"), journal_dir=directory)
        reused_at = perf_counter()
        warm = fresh.propose(case.text)
        times["promoted_warm.proposal"].append(ms(reused_at))
        extra_ok &= warm["route"] == "warm" and warm["planner_calls"] == 0
        if warm.get("plan_id"):
            done = fresh.confirm(warm["plan_id"])
            extra_ok &= done["status"] == "executed" and matches(done.get("state"), BLOCK_END)
        else:
            extra_ok = False
    return {
        "route_ok": proposal.get("route") == case.route and proposal.get("planner_calls") == (case.route == "cold"),
        "outcome_ok": result["status"] == case.status and state_ok and extra_ok,
        "status": result["status"],
    }


def summarize(samples):
    return {
        name: {"n": len(values), "p50": round(median(values), 4),
               "p95": round(quantiles(values, n=20, method="inclusive")[-1] if len(values) > 1 else values[0], 4),
               "max": round(max(values), 4)}
        for name, values in sorted(samples.items())
    }


def baseline_case(case, times):
    arm = MockArm(case.stations, step_seconds=0)
    plan = {"plan_id": case.name, "student_instruction": case.text, "steps": case.steps}
    start = perf_counter()
    valid = validator.validate(plan, arm.state(), case.stations)
    times["baseline.validator"].append(ms(start))
    run_started = perf_counter()
    result = runner.run(plan, arm) if valid["ok"] else valid
    times["baseline.runner"].append(ms(run_started))
    times["baseline.command_to_receipt"].append(ms(start))
    return result.get("status") == "executed" and matches(arm.state(), case.expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--physics", action="store_true", help="Measure one block preflight per repeat.")
    parser.add_argument("--baseline", action="store_true", help="Measure prewritten plans through the original validator/runner.")
    args = parser.parse_args()
    if args.repeats < 1 or (args.baseline and args.physics):
        parser.error("Use at least one repeat and select at most one mode.")

    times, totals, failures = defaultdict(list), Counter(), Counter()
    if args.baseline:
        selected = [case for case in CASES if case.status == "executed" and case.route == "warm"]
        for _ in range(args.repeats):
            for case in selected:
                totals["prewritten_trials"] += 1
                if not baseline_case(case, times):
                    failures[case.name] += 1
    elif args.physics:
        from agentic.openarms_agent.sim_preview import MuJoCoPreview

        for _ in range(args.repeats):
            arm = MockArm(BLOCK, step_seconds=0)
            before = arm.state()
            plan = {"plan_id": "physics", "student_instruction": "move block", "steps": [TRANSFER]}
            expected = validator.validate(plan, before, BLOCK)["end_state"]
            evidence = MuJoCoPreview()(plan, before, expected)
            totals["preflight_trials"] += 1
            totals["preflight_passed"] += evidence["ok"]
            times["mujoco.wall"].append(evidence["wall_time_s"] * 1000)
            if not evidence["ok"]:
                failures[evidence["reason"]] += 1
        print(json.dumps({"counts": totals, "latency_ms": summarize(times), "last_evidence": evidence,
                          "failures": failures}, indent=2))
        return bool(failures)
    else:
        for _ in range(args.repeats):
            for case in CASES:
                with TemporaryDirectory() as tmp:
                    result = run_case(case, Path(tmp), times)
                totals["scenarios"] += 1
                totals["correct_routes"] += result["route_ok"]
                totals["expected_outcomes"] += result["outcome_ok"]
                totals["expected_completions"] += case.status == "executed"
                totals["verified_completions"] += case.status == "executed" and result["outcome_ok"]
                if not result["route_ok"] or not result["outcome_ok"]:
                    failures[f"{case.name} ({result['status']})"] += 1
    print(json.dumps({
        "mode": "prewritten-plan baseline" if args.baseline else "offline FixturePlanner + MockArm(step_seconds=0)",
        "counts": totals, "latency_ms": summarize(times), "failures": failures,
        "modeled_wait_s_per_compose": 2,
        "live_provider_requests": 0, "live_provider_tokens": None, "live_provider_cost_usd": 0,
    }, indent=2))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
