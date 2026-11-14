"""C3+C4 check: clean run matches the validator's prediction; injected failure and stop."""
import json
from pathlib import Path

from agentic.openarms_agent.mock_arm import MockArm
from agentic.openarms_agent.runner import run
from agentic.openarms_agent.validator import validate

plan = json.loads((Path(__file__).resolve().parents[1] / "contracts" / "plan.example.json").read_text())

arm = MockArm(step_seconds=0)
predicted = validate(plan, arm.state(), arm.stations)["end_state"]
r = run(plan, arm)
assert r["status"] == "executed" and arm.state() == predicted, (r, arm.state(), predicted)
print("clean:  ", r)

r = run(plan, MockArm(fail_at="pour", step_seconds=0))
assert r["status"] == "failed" and r["failed_step"] == "pour" and r["steps_done"] == ["pick"]
print("failed: ", r)

arm, calls = MockArm(step_seconds=0), iter([False, False, True])
r = run(plan, arm, should_stop=lambda: next(calls, True))
assert r["status"] == "stopped" and r["steps_done"] == ["pick", "pour"]
print("stopped:", r)
