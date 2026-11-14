"""Simulation-only plan lifecycle for text commands and reviewed reusable skills."""

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from threading import Event, RLock
from time import perf_counter
from typing import Callable
from uuid import uuid4

from . import runner, validator
from .cold_planner import Draft, PlanningRequest
from .mock_arm import MockArm
from .notebook import Notebook
from .skill_library import MAX_TEXT_LENGTH, SkillLibrary
from .skill_routing import is_stop, route
from .types import ArmError, ArmPort, ArmState, Plan, Station, Step

Planner = Callable[[PlanningRequest], Draft | None]
Preview = Callable[[Plan, ArmState, ArmState], dict]
MAX_TEXT = 1000
HISTORY_LIMIT = 12


@dataclass(frozen=True)
class Proposal:
    plan: Plan
    before: ArmState
    expected: ArmState
    route: str
    scope: str


def _ms(start: float) -> float:
    return (perf_counter() - start) * 1000


class SkillHarness:
    """Owns one simulated bench. One process, one writer per session and registry.

    A preview is valid against one starting state. In-flight stop is cooperative:
    the current backend step may finish, and no later step may dispatch.
    """

    def __init__(self, *, session_id: str, stations: dict[str, Station], arm: ArmPort,
                 planner: Planner | None = None, library: SkillLibrary | None = None,
                 preview: Preview | None = None, journal_dir: Path | None = None):
        self.mode = getattr(arm, "mode", "mock" if isinstance(arm, MockArm) else None)
        if self.mode not in {"mock", "simulation"}:
            raise ValueError("The skill harness accepts only mock or simulation backends; physical motion requires a separate runner.")
        self.stations = deepcopy(stations)
        if hasattr(arm, "stations") and arm.stations != self.stations:
            raise ValueError("Harness station configuration must match the backend.")
        self.arm, self.planner, self.library, self.preview = arm, planner, library, preview
        try:
            self._notebook = Notebook.load(session_id, journal_dir)
        except FileNotFoundError:
            self._notebook = Notebook(session_id, journal_dir)
        self._lock = RLock()
        self._stop = Event()
        self._stop_error: str | None = None
        self._revision = 0
        self._planning = False
        self._running = False
        self._pending: Proposal | None = None
        self._consumed: set[str] = set()
        self._reviewable: dict[str, Proposal] = {}

    def _record(self, kind: str, **data) -> None:
        self._notebook.add(kind, **deepcopy(data))
        self._notebook.save()

    def history(self) -> list[dict]:
        with self._lock:
            return self._notebook.entries()

    def record_prediction(self, text: str) -> None:
        self._record_student_entry("prediction", text, "student")

    def record_observation(self, text: str, *, source: str) -> None:
        if source not in {"student", "teacher"}:
            raise ValueError("An observation needs an explicit student or teacher source.")
        self._record_student_entry("observation", text, source)

    def _record_student_entry(self, kind: str, text: str, source: str) -> None:
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
            raise ValueError("Entry must contain 1 to 1000 characters.")
        with self._lock:
            self._record(kind, text=text, source=source)

    def _history_for_planning(self) -> list[dict]:
        entries = self._notebook.entries()
        # Only facts explicitly labeled in the notebook, bounded in size. Planning
        # proposals and prior student requests do not automatically carry forward.
        return [entry for entry in entries
                if entry["kind"] in {"prediction", "observation", "result", "control"}][-HISTORY_LIMIT:]

    def _scope(self, state: ArmState) -> str:
        scope = {"catalog_version": 1, "stations": self.stations, "state": state,
                 "backend_mode": self.mode}
        return sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()

    def propose(self, text: str) -> dict:
        """Resolve or draft an instruction, then return a preview for confirmation."""
        start = perf_counter()
        if isinstance(text, str) and is_stop(text):
            return {**self.stop(), "route": "control"}

        with self._lock:
            if self._running or self._planning:
                return {"status": "busy", "reason": "A command is in progress."}
            self._pending = None
            if self._stop.is_set():
                return {"status": "rejected", "reason": "The bench is stopped. Reset the simulation before continuing."}
            self._revision += 1
            revision = self._revision
            self._planning = True

        try:
            reply, proposal = self._propose(text, start)
            with self._lock:
                if revision != self._revision:
                    return {"status": "stopped", "reason": "The proposed command was cancelled."}
                self._record("plan", instruction=text[:MAX_TEXT] if isinstance(text, str) else None, **reply)
                self._pending = proposal
                return reply
        finally:
            with self._lock:
                self._planning = False

    def _propose(self, text: str, start: float) -> tuple[dict, Proposal | None]:
        timings = dict(route=0.0, planning=0.0, validation=0.0, preview=0.0)
        usage = {"input_tokens": None, "output_tokens": None}
        path = "warm"
        calls = 0

        def reply(status: str, reason: str | None = None, **extra) -> dict:
            return {"status": status, "route": path, "reason": reason, "planner_calls": calls,
                    "usage": usage, "timings_ms": {**timings, "total": _ms(start)}, **extra}

        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
            return reply("rejected", "Instruction must contain 1 to 1000 characters."), None

        try:
            before = self.arm.state()
            if before.get("armed") is not True or before.get("at") != "HOME" or before["holding"] is not None:
                return reply("rejected", "Start from an armed bench at HOME with an empty gripper."), None
            for name, station in self.stations.items():
                field = {"point": "point_holds", "source": "portions_left", "receiver": "receiver_load"}[station["kind"]]
                value = before[field][name]
                is_valid = ((value is None or isinstance(value, str) and bool(value)) if field == "point_holds"
                            else type(value) is int and value >= 0)
                if not is_valid:
                    raise ValueError("Invalid current station value.")
        except Exception as exc:
            return reply("rejected", f"Starting state unavailable ({type(exc).__name__})."), None

        scope = self._scope(before)
        routed = perf_counter()
        try:
            steps = route(text, before, self.stations)
            if steps is None and self.library is not None and len(text) <= MAX_TEXT_LENGTH:
                steps = self.library.resolve(text, scope=scope)
        except (ValueError, OSError) as exc:
            timings["route"] = _ms(routed)
            return reply("rejected", str(exc)), None
        timings["route"] = _ms(routed)

        if steps is None:
            path = "cold"
            if self.planner is None:
                return reply("needs_clarification", "Use explicit actions, quantities and station names."), None
            if self._stop.is_set():
                return reply("stopped", "The proposed command was cancelled."), None
            with self._lock:
                history = self._history_for_planning()
            request = PlanningRequest(text, deepcopy(before), deepcopy(self.stations), history)
            planning = perf_counter()
            try:
                calls = 1
                draft = self.planner(request)
            except Exception as exc:
                timings["planning"] = _ms(planning)
                return reply("needs_clarification", f"Cold planner unavailable ({type(exc).__name__})."), None
            timings["planning"] = _ms(planning)
            if not isinstance(draft, Draft):
                return reply("needs_clarification", "Planner supplied no supported plan. Specify the goal and stations."), None
            steps = draft.steps
            usage = {"input_tokens": draft.input_tokens, "output_tokens": draft.output_tokens}

        validation = perf_counter()
        # Check size before expanding any repeated actions in the legacy validator.
        if not isinstance(steps, list) or not 1 <= len(steps) <= validator.MAX_PRIMITIVE_ACTIONS:
            timings["validation"] = _ms(validation)
            return reply("rejected", "Supply a bounded list of catalog actions."), None
        if any(not isinstance(step, dict) or set(step) != {"action", "args"}
               or not isinstance(step["args"], dict) for step in steps):
            timings["validation"] = _ms(validation)
            return reply("rejected", "Each step must specify only an action and its argument object."), None

        actions = [step["action"] for step in steps]
        if any(action in validator.PRIMITIVES for action in actions if isinstance(action, str)) and any(
            action in ("move_block", "add_sample") for action in actions
        ):
            timings["validation"] = _ms(validation)
            return reply("rejected", "Run taught macros and direct pose or gripper commands in separate plans."), None

        plan: Plan = {"plan_id": uuid4().hex, "student_instruction": text, "steps": deepcopy(steps)}
        check = validator.validate(plan, before, self.stations)
        timings["validation"] = _ms(validation)
        if not check["ok"]:
            return reply("rejected", check["reason"]), None

        expected = check["end_state"]
        preflight = None
        if self.preview is not None and not self._stop.is_set():
            preview_start = perf_counter()
            try:
                preflight = self.preview(deepcopy(plan), deepcopy(before), deepcopy(expected))
                allowed = isinstance(preflight, dict) and preflight.get("ok") is True
            except Exception as exc:
                preflight = {"ok": False, "reason": f"Simulation preflight unavailable ({type(exc).__name__})."}
                allowed = False
            timings["preview"] = _ms(preview_start)
            if not allowed:
                reason = preflight.get("reason") if isinstance(preflight, dict) else None
                return reply("rejected", reason or "Simulation preflight rejected the plan.", preview=preflight), None

        result = reply("awaiting_confirmation", plan_id=plan["plan_id"], plan=deepcopy(plan),
                       expanded=check["expanded"], expected_state=deepcopy(expected), preview=preflight)
        return result, Proposal(plan, before, expected, path, scope)

    def confirm(self, plan_id: str) -> dict:
        """Consume a matching preview once. Recheck the bench before any step."""
        start = perf_counter()
        with self._lock:
            if not isinstance(plan_id, str) or not plan_id:
                return {"status": "rejected", "reason": "Confirmation needs an exact plan ID."}
            if plan_id in self._consumed:
                return {"status": "already_consumed", "plan_id": plan_id}
            if self._running:
                return {"status": "busy", "plan_id": plan_id}
            proposal = self._pending
            if proposal is None or plan_id != proposal.plan["plan_id"] or self._stop.is_set():
                return {"status": "rejected", "plan_id": plan_id, "reason": "No matching pending preview."}

            self._pending = None
            self._consumed.add(plan_id)
            try:
                current = self.arm.state()
            except Exception:
                current = None
            if current != proposal.before:
                result = {"status": "rejected", "plan_id": plan_id, "reason": "Bench state changed or is unavailable. Request a new preview.",
                          "timings_ms": {"dispatch": _ms(start), "execution": 0.0, "total": _ms(start)}}
                self._record("result", **result)
                return result
            self._record("control", status="confirmed", plan_id=plan_id)
            self._running = True

        try:
            return self._execute(proposal, start, current)
        finally:
            with self._lock:
                self._running = False

    def _execute(self, proposal: Proposal, start: float, predicted: ArmState) -> dict:
        def verify_step(step: Step) -> None:
            validator.apply_step(predicted, self.stations, step)
            if self.arm.state() != predicted:
                raise ArmError(step["action"], "Backend state differs from the validated step.")

        execution = perf_counter()
        result = runner.run(proposal.plan, self.arm, self._stop.is_set, verify_step=verify_step, stop_on_request=False)
        with self._lock:
            if self._stop.is_set() and result["status"] == "executed":
                result.update(status="stopped", reason="Stop requested during execution.")

            # Commit outcome before exposing it. A trace records backend state
            # only. An experiment observation requires separate provenance.
            try:
                state = self.arm.state()
            except Exception:
                state = None
            if result["status"] == "executed" and state != proposal.expected:
                result.update(status="failed", reason="Final bench state could not be verified.")
            if result["status"] != "executed":
                self._stop.set()
                self._hold()
                if self._stop_error:
                    result["reason"] = f"{result['reason']} {self._stop_error}"
                try:
                    state = self.arm.state()
                except Exception:
                    state = None
            result.update(state=state, evidence={"source": f"{self.mode}_state", "observation": None},
                          timings_ms={"dispatch": (execution - start) * 1000,
                                      "execution": _ms(execution), "total": _ms(start)})
            self._record("result", **result)
            if result["status"] == "executed" and proposal.route == "cold":
                self._reviewable[proposal.plan["plan_id"]] = proposal
            return result

    def _hold(self) -> None:
        try:
            self.arm.stop()
        except Exception as exc:
            self._stop_error = f"Backend stop failed ({type(exc).__name__})."

    def stop(self) -> dict:
        """Invalidate queued motion immediately and request a hold between steps."""
        with self._lock:
            first = not self._stop.is_set()
            self._stop.set()
            self._revision += 1
            self._pending = None
            if self._running:
                result = {"status": "stop_requested"}
            else:
                if first:
                    self._hold()
                result = {"status": "stopped"} if self._stop_error is None else {
                    "status": "failed", "reason": self._stop_error,
                }
            if first:
                self._record("control", **result)
            return result

    def promote(self, plan_id: str) -> int:
        """Explicitly review a successful cold run and register its exact phrase."""
        with self._lock:
            proposal = self._reviewable.get(plan_id)
            if proposal is None or self.library is None:
                raise ValueError("Promotion requires a successful cold run and a configured skill library.")
            version = self.library.promote(proposal.plan["student_instruction"], proposal.plan["steps"],
                                           scope=proposal.scope)
            del self._reviewable[plan_id]
            self._record("skill", plan_id=plan_id, version=version, scope=proposal.scope)
            return version
