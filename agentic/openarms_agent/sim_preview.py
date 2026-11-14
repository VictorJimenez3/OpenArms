"""Optional MuJoCo preflight for an approved, validator-checked plan.

The simulator is deliberately loaded at call time.  The agentic harness can
run with only its deterministic ``MockArm`` when the optional simulation lane
has not been installed.  A successful preflight is evidence about the
simulator's model, not evidence that a physical arm moved.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Callable

from .types import ArmState, Plan


PreviewFn = Callable[..., dict[str, Any]]


def _placements(state: ArmState | None) -> dict[str, str]:
    """Return loose-object locations from the shared validator state."""
    if not state:
        return {}
    holds = state.get("point_holds") or {}
    return {thing: station for station, thing in holds.items() if thing}


def _setup_for(plan: Plan, before: ArmState) -> str:
    actions = {step.get("action") for step in plan.get("steps", [])}
    if "add_sample" in actions:
        return "liquid"
    if "move_block" in actions:
        return "block"
    if before.get("point_holds"):
        return "block"
    if before.get("portions_left") or before.get("receiver_load"):
        return "liquid"
    return "block"


class MuJoCoPreview:
    """Call Stefanie's headless MuJoCo preview as a preflight.

    ``preview`` is injectable so the harness remains testable without the
    optional simulation package.  Production callers leave it as ``None``
    and the adapter imports ``openarms_sim`` only when invoked.
    """

    def __init__(self, preview: PreviewFn | None = None, setup: str | None = None) -> None:
        self._preview = preview
        self._setup = setup

    @staticmethod
    def _load_preview() -> PreviewFn:
        try:
            from openarms_sim import preview
        except ImportError as exc:
            raise RuntimeError(
                "MuJoCo simulator is unavailable. Install the optional "
                "simulation package before requesting a physics preflight."
            ) from exc
        return preview

    def __call__(self, plan: Plan, before: ArmState, expected: ArmState) -> dict[str, Any]:
        started = perf_counter()
        setup = self._setup or _setup_for(plan, before)
        starting = _placements(before)
        expected_placements = _placements(expected)

        if setup != "block" or any(step["action"] == "add_sample" for step in plan["steps"]):
            return self._failure(
                "unsupported_setup", "This adapter supports the block scene. Use the deterministic bench for liquid plans.",
                setup, starting, expected_placements, started,
            )
        if not starting or set(starting) != {"block"}:
            return self._failure(
                "unsupported_object", "The MuJoCo block scene requires one block.",
                setup, starting, expected_placements, started,
            )
        try:
            preview = self._preview or self._load_preview()
        except RuntimeError as exc:
            return self._failure(
                "simulator_unavailable", str(exc), setup, starting, expected_placements, started
            )

        kwargs: dict[str, Any] = {
            "render": False,
            "use_cache": False,
            "setup": setup,
        }
        if starting:
            # Stefanie's block setup accepts the current loose-object location.
            # Liquid plans intentionally have no loose-object map in ArmState.
            kwargs["objects"] = starting

        try:
            result = preview(plan, **kwargs)
        except Exception as exc:  # simulation errors are preflight failures
            return self._failure(
                "simulator_error",
                f"{type(exc).__name__}: {exc}",
                setup,
                starting,
                expected_placements,
                started,
            )

        reported = {
            item.get("name"): item.get("at")
            for item in result.get("objects", [])
            if item.get("name")
        }
        block_issues = [i for i in result.get("issues", []) if i.get("severity") == "block"]
        mismatch = {
            name: (reported.get(name), location)
            for name, location in expected_placements.items()
            if reported.get(name) != location
        }
        ok = result.get("ok") is True and not mismatch and not block_issues \
            and result.get("plan_id") == plan["plan_id"]
        reason = None
        if block_issues:
            reason = block_issues[0].get("message") or block_issues[0].get("code")
        elif mismatch:
            reason = f"simulated placement disagrees with the validated end state: {mismatch}"
        elif result.get("plan_id") != plan["plan_id"]:
            reason = "Simulation returned an unmatched plan ID."
        elif not result.get("ok"):
            issues = result.get("issues", [])
            reason = (issues[0].get("message") if issues else None) or "the simulator blocked this plan"

        return {
            "ok": ok,
            "mode": "physics_simulation",
            "engine": "mujoco",
            "evidence_type": "kinematics_and_contact_preflight_with_scripted_grasp_release",
            "setup": result.get("setup", setup),
            "reason": reason,
            "reported_placement": reported,
            "expected_placement": expected_placements,
            "simulated_duration_s": result.get("motion_seconds"),
            "issues": result.get("issues", []),
            "warnings": result.get("warnings", []),
            "cached": bool(result.get("cached", False)),
            "wall_time_s": round(perf_counter() - started, 4),
        }

    @staticmethod
    def _failure(
        code: str,
        reason: str,
        setup: str,
        starting: dict[str, str],
        expected: dict[str, str],
        started: float,
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "mode": "physics_simulation",
            "engine": "mujoco",
            "evidence_type": "kinematics_and_contact_preflight_with_scripted_grasp_release",
            "setup": setup,
            "reason": reason,
            "reported_placement": {},
            "expected_placement": expected,
            "simulated_duration_s": None,
            "issues": [{"severity": "block", "code": code, "message": reason, "step": None}],
            "warnings": [reason],
            "cached": False,
            "wall_time_s": round(perf_counter() - started, 4),
            "starting_placement": starting,
        }
