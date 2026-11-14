"""Checks a plan against the arm state before a teacher ever sees it."""
import copy

from .catalog import expand
from .types import ArmState, Plan, Station, Step, ValidationResult

MAX_PLAN_ACTIONS = 6


def _station(stations: dict[str, Station], name: str, kind: str | None, step: str) -> None:
    if name not in stations:
        raise ValueError(f"{step}: there is no station {name}.")
    if kind and stations[name].get("kind") != kind:
        raise ValueError(f"{step}: station {name} is not a {kind}.")


def apply_step(state: ArmState, stations: dict[str, Station], step: Step) -> None:
    """Applies one arm step to state in place; raises ValueError if it can't run. MockArm shares this."""
    a, args = step["action"], step["args"]
    if a == "pick":
        st = args["station"]
        _station(stations, st, "source", "pick")
        if state["holding"]:
            raise ValueError(f"pick: the gripper is already holding a cup from {state['holding']}.")
        if state["portions_left"].get(st, 0) < 1:
            raise ValueError(f"pick: source {st} has no full cups left.")
        state["portions_left"][st] -= 1
        state["holding"], state["at"] = st, st
    elif a == "pour":
        into = args["into"]
        _station(stations, into, "receiver", "pour")
        if not state["holding"]:
            raise ValueError("pour: the gripper is not holding a cup.")
        load, cap = state["receiver_load"].get(into, 0), stations[into].get("capacity", 0)
        if load >= cap:
            raise ValueError(f"pour: receiver {into} is full ({cap} portions).")
        state["receiver_load"][into] = load + 1
        state["at"] = into
    elif a == "return_cup":
        st = args["station"]
        if state["holding"] != st:
            raise ValueError(f"return_cup: the gripper is not holding a cup from {st}.")
        state["holding"], state["at"] = None, st
    elif a == "home":
        if state["holding"]:
            raise ValueError("home: the gripper still holds a cup.")
        state["at"] = "HOME"
    elif a == "look":
        _station(stations, args["station"], None, "look")
    elif a != "wait":
        raise ValueError(f"'{a}' is not an arm step.")


def validate(plan: Plan, state: ArmState, stations: dict[str, Station]) -> ValidationResult:
    try:
        expanded = expand(plan)
    except ValueError as e:
        return {"ok": False, "reason": str(e), "expanded": [], "end_state": None}

    def reject(reason: str) -> ValidationResult:
        return {"ok": False, "reason": reason, "expanded": expanded, "end_state": None}

    if not state.get("armed", True):
        return reject("The arm is disarmed after a fault or stop; the teacher has to reset it first.")
    n = len(plan.get("steps") or [])
    if not 1 <= n <= MAX_PLAN_ACTIONS:
        return reject(f"A plan needs 1 to {MAX_PLAN_ACTIONS} actions, not {n}.")
    end = copy.deepcopy(state)
    try:
        for step in expanded:
            apply_step(end, stations, step)
    except ValueError as e:
        return reject(str(e))
    if end["at"] != "HOME" or end["holding"]:
        return reject("The plan must end at HOME with an empty gripper.")
    return {"ok": True, "reason": None, "expanded": expanded, "end_state": end}
