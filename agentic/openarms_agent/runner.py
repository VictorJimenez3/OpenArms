"""Runs an approved plan step by step. Never retries: a blind retry around liquid risks a spill."""
from .catalog import expand
from .types import ArmError, ArmPort, ExecutionResult, Plan


def run(plan: Plan, arm: ArmPort, should_stop=lambda: False) -> ExecutionResult:
    done: list[str] = []

    def result(status, failed=None, reason=None) -> ExecutionResult:
        return {"plan_id": plan["plan_id"], "status": status, "steps_done": done, "failed_step": failed, "reason": reason}

    for step in expand(plan):
        if should_stop():
            arm.stop()
            return result("stopped", reason="stopped before " + step["action"])
        try:
            arm.run_step(step["action"], step["args"])
        except ArmError as e:
            return result("failed", e.step, e.reason)
        except Exception as e:  # serial/timeout errors from firmware must still end the run as failed
            return result("failed", step["action"], f"{type(e).__name__}: {e}")
        done.append(step["action"])
    return result("executed")
