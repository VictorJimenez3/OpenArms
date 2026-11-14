"""Shared shapes for every lane. Values stay plain JSON dicts; these TypedDicts only name the keys.
Examples of each shape live in agentic/contracts/. Only the master agent edits this file."""
from typing import Any, Literal, NotRequired, Optional, Protocol, TypedDict

PlanAction = Literal["add_sample", "move_block", "go_to", "gripper", "wait", "look"]  # what the brain may put in a plan
ArmStep = Literal["pick", "place", "pour", "return_cup", "home", "go_to", "gripper", "wait", "look"]  # what ArmPort runs
RunStatus = Literal["rejected", "awaiting_teacher", "teacher_rejected", "executing", "executed", "failed", "stopped"]
TurnStatus = Literal["reply", "awaiting_teacher", "stop_requested", "help_requested"]
LabStage = Literal["pre_lab", "experiment", "post_lab"]


class Station(TypedDict, total=False):
    kind: Literal["source", "receiver", "point"]  # point: a mark a loose object stands on
    contents: str
    holds: str  # points: the object standing there at the start, e.g. "block"; absent if empty
    portions: int  # sources: full mini-cups at the start
    capacity: int  # receivers: max portions


class Step(TypedDict):
    action: str
    args: dict[str, Any]


class Plan(TypedDict):
    plan_id: str
    student_instruction: str
    steps: list[Step]


class ArmState(TypedDict):
    at: str
    holding: Optional[str]
    portions_left: dict[str, int]
    receiver_load: dict[str, int]
    armed: bool
    point_holds: NotRequired[dict[str, Optional[str]]]  # benches with points: what stands on each, or None
    poses: NotRequired[list[str]]  # saved positions go_to may name; if absent they follow from the stations
    gripper: NotRequired[Literal["open", "closed"]]  # set once a plan has commanded the gripper


class ValidationResult(TypedDict):
    ok: bool
    reason: Optional[str]  # one readable sentence when ok is False
    expanded: list[Step]  # arm steps, as the teacher will see them
    end_state: Optional[ArmState]


class ExecutionResult(TypedDict):
    plan_id: str
    status: RunStatus
    steps_done: list[str]
    failed_step: Optional[str]
    reason: Optional[str]


class TurnReply(TypedDict):
    turn_id: str
    text: str
    status: TurnStatus
    plan: Optional[Plan]
    lab_stage: LabStage


class ArmError(Exception):
    def __init__(self, step: str, reason: str):
        super().__init__(f"{step}: {reason}")
        self.step, self.reason = step, reason


class ArmPort(Protocol):
    """The real executor (firmware/) and MockArm both match this. Steps are ArmStep names."""

    def run_step(self, action: str, args: dict[str, Any]) -> None: ...  # raises ArmError
    def stop(self) -> None: ...  # finish the current motion, then hold; never cut torque
    def state(self) -> ArmState: ...


# Signatures lanes code against (implemented in the named modules):
#   catalog.expand(plan: Plan) -> list[Step]                        raises ValueError
#   validator.validate(plan: Plan, state: ArmState, stations: dict[str, Station]) -> ValidationResult
#   runner.run(plan: Plan, arm: ArmPort, should_stop=lambda: False) -> ExecutionResult
#   notebook.Notebook(session_id).add(kind, **data) / .entries() / .save() / .as_text()
#   brain.Brain(session_id).handle_turn(turn_id, text) -> TurnReply ; .notify(result) -> TurnReply
