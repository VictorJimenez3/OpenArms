"""Checks a plan against the arm state before a teacher ever sees it."""
import copy

from .catalog import PRIMITIVES, expand
from .types import ArmState, Plan, Station, Step, ValidationResult

MAX_PLAN_ACTIONS = 6
MAX_PRIMITIVE_ACTIONS = 12  # a plan built from single moves needs more of them to do the same work
LOW_POSES = ("GRASP_", "TIP_")  # positions down among the things on the bench


def _station(stations: dict[str, Station], name: str, kind: str | None, step: str) -> None:
    if name not in stations:
        raise ValueError(f"{step}: there is no station {name}.")
    if kind and stations[name].get("kind") != kind:
        raise ValueError(f"{step}: station {name} is not a {kind}.")


def _held(state: ArmState, stations: dict[str, Station], article: bool = False) -> str:
    """Names what the gripper holds: a cup (holding is its source station) or a loose object."""
    if state["holding"] in stations:
        return "a cup" if article else f"cup from {state['holding']}"
    return f"the {state['holding']}" if article else state["holding"]


def pose_names(stations: dict[str, Station]) -> list[str]:
    """The saved positions a bench implies: HOME, ABOVE_x for every station, GRASP_x where something
    is picked up or set down, TIP_x over receivers. The real arm reports its own list instead."""
    names = ["HOME"]
    for name, st in stations.items():
        names += [f"ABOVE_{name}", f"TIP_{name}" if st.get("kind") == "receiver" else f"GRASP_{name}"]
    return names


def _low_station(pose: str) -> str | None:
    """'GRASP_A' -> 'A'; None for a position that is clear of the bench."""
    return next((pose[len(p):] for p in LOW_POSES if pose.startswith(p)), None)


def _go_to(state: ArmState, stations: dict[str, Station], pose: str) -> None:
    known = state.get("poses") or pose_names(stations)
    if pose not in known:
        raise ValueError(f"go_to: there is no saved position {pose}; the saved positions are {', '.join(known)}.")
    here, there = _low_station(state["at"]), _low_station(pose)
    # Every move is a straight line between two positions. Only the line between ABOVE_x and the
    # low position under it was recorded as a clear vertical path; any other line into or out of
    # a low position could sweep across the bench.
    if here is not None and pose not in (state["at"], f"ABOVE_{here}"):
        raise ValueError(f"go_to: from {state['at']} the arm must go up to ABOVE_{here} before anywhere else.")
    if there is not None and state["at"] not in (pose, f"ABOVE_{there}"):
        raise ValueError(f"go_to: the arm must be at ABOVE_{there} before going down to {pose}.")
    if there is not None and pose.startswith("GRASP_") and state["at"] != pose:
        standing = (state.get("point_holds") or {}).get(there)
        if standing and state["holding"]:
            raise ValueError(f"go_to: {there} already has the {standing} on it.")
        if standing and state.get("gripper") != "open":
            raise ValueError(f"go_to: open the gripper before going down to {pose}; the {standing} is there.")
    state["at"] = pose


def _gripper(state: ArmState, stations: dict[str, Station], want: str) -> None:
    at = state["at"]
    here = at[len("GRASP_"):] if at.startswith("GRASP_") else None
    points = state.setdefault("point_holds", {}) if here in stations and stations[here].get("kind") == "point" else None
    if want == "close":
        if not state["holding"] and state.get("gripper") != "closed":
            if points is not None and points.get(here):
                state["holding"], points[here] = points[here], None
            elif here in stations and stations[here].get("kind") == "source" and state["portions_left"].get(here, 0) > 0:
                state["portions_left"][here] -= 1
                state["holding"] = here
        state["gripper"] = "closed"
        return
    held = state["holding"]
    if held:
        if held in stations:  # a cup goes back to its own holder
            if here != held:
                raise ValueError(f"gripper: opening at {at} would drop the cup from {held}; go to GRASP_{held} first.")
        elif points is None:
            raise ValueError(f"gripper: opening at {at} would drop the {held}; go down to a GRASP position first.")
        elif points.get(here):
            raise ValueError(f"gripper: {here} already has the {points[here]} on it.")
        else:
            points[here] = held
        state["holding"] = None
    state["gripper"] = "open"


def initial_point_holds(stations: dict[str, Station]) -> dict:
    """What stands on each point at the start; {} for a bench with no points."""
    return {k: s.get("holds") for k, s in stations.items() if s.get("kind") == "point"}


def apply_step(state: ArmState, stations: dict[str, Station], step: Step) -> None:
    """Applies one arm step to state in place; raises ValueError if it can't run. MockArm shares this."""
    a, args = step["action"], step["args"]
    if a == "go_to":
        _go_to(state, stations, args["pose"])
    elif a == "gripper":
        _gripper(state, stations, args["state"])
    elif a == "pick" and stations.get(args.get("station"), {}).get("kind") == "point":
        # A loose object on a marked point: holding becomes the object's name, not a station.
        st = args["station"]
        if state["holding"]:
            raise ValueError(f"pick: the gripper is already holding the {_held(state, stations)}.")
        thing = state.setdefault("point_holds", {}).get(st)
        if not thing:
            raise ValueError(f"pick: there is nothing at {st} to pick up.")
        state["point_holds"][st] = None
        state["holding"], state["at"] = thing, st
        state["gripper"] = "closed"
    elif a == "place":
        st = args["station"]
        _station(stations, st, "point", "place")
        if not state["holding"] or state["holding"] in stations:
            raise ValueError("place: the gripper is not holding an object to put down.")
        if state.setdefault("point_holds", {}).get(st):
            raise ValueError(f"place: {st} already has the {state['point_holds'][st]} on it.")
        state["point_holds"][st] = state["holding"]
        state["holding"], state["at"] = None, st
        state["gripper"] = "open"
    elif a == "pick":
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
        if state["holding"] not in stations:  # empty, or a loose object that cannot be poured
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
            raise ValueError(f"home: the gripper still holds {_held(state, stations, article=True)}.")
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
    items = plan.get("steps") or []
    n = len(items)
    limit = MAX_PRIMITIVE_ACTIONS if any(i.get("action") in PRIMITIVES for i in items) else MAX_PLAN_ACTIONS
    if not 1 <= n <= limit:
        return reject(f"A plan needs 1 to {limit} actions, not {n}.")
    end = copy.deepcopy(state)
    try:
        for step in expanded:
            apply_step(end, stations, step)
    except ValueError as e:
        return reject(str(e))
    if end["at"] != "HOME" or end["holding"]:
        return reject("The plan must end at HOME with an empty gripper.")
    return {"ok": True, "reason": None, "expanded": expanded, "end_state": end}
