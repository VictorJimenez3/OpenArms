"""C2 check: one accepted and three rejected plans against the contract state."""
import json
from pathlib import Path

from agentic.openarms_agent.validator import validate

C = Path(__file__).resolve().parents[1] / "contracts"
state = json.loads((C / "arm_state.example.json").read_text())
stations = json.loads((C / "stations.example.json").read_text())
plan = json.loads((C / "plan.example.json").read_text())


def p(*steps):
    return {"plan_id": "p-x", "student_instruction": "x", "steps": list(steps)}


ok = validate(plan, state, stations)
assert ok["ok"] and ok["expanded"] == json.loads((C / "expanded_steps.example.json").read_text())
assert ok["end_state"]["portions_left"]["A"] == 1 and ok["end_state"]["receiver_load"]["C"] == 1
print("accepted:", ok["end_state"])
for bad in (p({"action": "add_sample", "args": {"source": "A", "into": "C", "portions": 3}}),  # A has 2
            p({"action": "add_sample", "args": {"source": "C", "into": "A"}}),  # wrong kinds
            p(*[{"action": "look", "args": {"station": "C"}}] * 7)):  # too many actions
    r = validate(bad, state, stations)
    assert not r["ok"] and r["reason"]
    print("rejected:", r["reason"])
