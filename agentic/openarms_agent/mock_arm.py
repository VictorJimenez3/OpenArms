"""An ArmPort with no hardware: tracks state the way the validator predicts."""
import copy
import json
import time
from pathlib import Path
from typing import Any

from .types import ArmError, ArmState, Station
from .validator import apply_step, initial_point_holds

_STATIONS = Path(__file__).resolve().parents[1] / "contracts" / "stations.example.json"


class MockArm:
    def __init__(self, stations: dict[str, Station] | None = None, fail_at: str | None = None,
                 step_seconds: float = 0.5) -> None:
        self.stations = stations or json.loads(_STATIONS.read_text())
        self.fail_at, self.step_seconds, self._stopped = fail_at, step_seconds, False
        self._state: ArmState = {
            "at": "HOME", "holding": None, "armed": True,
            "portions_left": {k: s.get("portions", 0) for k, s in self.stations.items() if s.get("kind") == "source"},
            "receiver_load": {k: 0 for k, s in self.stations.items() if s.get("kind") == "receiver"},
        }
        if points := initial_point_holds(self.stations):
            self._state["point_holds"] = points

    def run_step(self, action: str, args: dict[str, Any]) -> None:
        if self._stopped:
            raise ArmError(action, "the arm is stopped")
        if action == self.fail_at:
            raise ArmError(action, "injected failure")
        time.sleep(self.step_seconds)
        try:
            apply_step(self._state, self.stations, {"action": action, "args": args})
        except ValueError as e:
            raise ArmError(action, str(e)) from None

    def stop(self) -> None:
        self._stopped = True
        self._state["armed"] = False  # matches PoseArm: new plans are refused, not failed

    def state(self) -> ArmState:
        return copy.deepcopy(self._state)
