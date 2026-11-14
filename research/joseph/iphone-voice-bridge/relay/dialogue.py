"""Session-local mock. This module never imports an agent or a robot interface."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Context:
    session_id: str
    turn_id: str


@dataclass(frozen=True)
class Reply:
    text: str
    lab_stage: str


class DialogueAdapter(Protocol):
    """An instance belongs to exactly one session; cancellation must propagate."""

    async def respond(self, context: Context, student_text: str | None) -> Reply: ...
    async def close(self) -> None: ...


class MockDialogue:
    def __init__(self):
        self.stage = "prediction"

    async def respond(self, context: Context, student_text: str | None) -> Reply:
        if student_text is None:
            return Reply("This is a simulation. Predict what happens when a mock arm moves a block to the marked target.", "prediction")
        if self.stage == "prediction":
            self.stage = "confirmation"
            return Reply("Preview: the simulated arm will move one block to the marked target. No hardware will move. Say confirm to run the simulation, or cancel.", "preview")
        if self.stage == "confirmation":
            # Exact normalized phrases only: negation, uncertainty and mixed intent
            # cannot accidentally authorize even this simulated action.
            answer = student_text.strip().lower().rstrip(".!?").strip()
            if answer in {"confirm", "i confirm"}:
                self.stage = "reflection"
                return Reply("Simulated result: the block reached the target. No hardware moved. How does this compare with your prediction?", "result")
            if answer in {"cancel", "cancel simulation"}:
                self.stage = "reflection"
                return Reply("Simulation cancelled. No hardware moved. What would you change about your prediction or plan?", "reflection")
            return Reply("Please say confirm to run this simulation, or cancel to stop it.", "confirmation")
        self.stage = "prediction"
        return Reply("Thank you for reflecting. For another simulated trial, predict what happens if the target is farther away.", "reflection")

    async def close(self) -> None:
        pass
