"""Deterministic warm-path routing for the small, validated OpenArms skill set.

This module intentionally recognizes only explicit, short commands. A request it
does not understand returns ``None`` so the cold planner can author a proposal.
Commands that clearly name a supported operation but contain impossible or
ambiguous parameters raise ``ValueError`` with a reason suitable for the UI.
"""

from __future__ import annotations

import copy
import re
from .types import ArmState, Station, Step
from .validator import pose_names


_NUMBER_WORDS = {
    "one": 1,
    "a": 1,
    "an": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_STATION_TOKEN = r"[A-Za-z0-9_-]+"


def _clean(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("The instruction must be text.")
    # Terminal punctuation is natural in speech transcripts. Internal punctuation
    # remains and therefore prevents a false warm-path match.
    return re.sub(r"\s+", " ", re.sub(r"[.!?]+$", "", text.strip().lower())).strip()


def is_stop(text: str) -> bool:
    """Return true only for a standalone stop/cancel control.

    A compound or negated phrase stays false and can be handled by the normal
    conversation path. This keeps a word embedded in a novel request from
    silently discarding the rest of the request.
    """

    try:
        value = _clean(text)
    except ValueError:
        return False
    return bool(
        re.fullmatch(
            r"(?:please\s+)?(?:stop(?:\s+(?:the\s+)?(?:arm|motion|run))?|cancel(?:\s+(?:this|the)\s+plan)?)(?:\s+(?:now|immediately|right now))?",
            value,
        )
    )


def _station(name: str, stations: dict[str, Station], role: str) -> Station:
    canonical = next((key for key in stations if key.lower() == name.lower()), None)
    if canonical is None:
        raise ValueError(f"{role} station {name} does not exist.")
    return stations[canonical]


def _station_name(name: str, stations: dict[str, Station], role: str) -> str:
    canonical = next((key for key in stations if key.lower() == name.lower()), None)
    if canonical is None:
        raise ValueError(f"{role} station {name} does not exist.")
    return canonical


def _number(value: str | None) -> int:
    if value is None:
        return 1
    value = value.lower()
    if value.isdigit():
        return int(value)
    if value in _NUMBER_WORDS:
        return _NUMBER_WORDS[value]
    raise ValueError("The portion count must be a whole number from 1 to 10.")


def _move(clause: str, state: ArmState, stations: dict[str, Station]) -> Step | None:
    match = re.fullmatch(
        rf"(?:move|transfer|carry)\s+(?:(?:the|a)\s+)?(?P<object>.+?)\s+from\s+(?P<src>{_STATION_TOKEN})\s+(?:to|into)\s+(?P<dst>{_STATION_TOKEN})",
        clause,
    )
    if not match:
        match = re.fullmatch(
            rf"(?:move|transfer|carry)\s+from\s+(?P<src>{_STATION_TOKEN})\s+(?:to|into)\s+(?P<dst>{_STATION_TOKEN})",
            clause,
        )
    if not match:
        return None

    source_name = _station_name(match.group("src"), stations, "Source")
    destination_name = _station_name(match.group("dst"), stations, "Destination")
    source = _station(source_name, stations, "Source")
    destination = _station(destination_name, stations, "Destination")
    if source.get("kind") != "point" or destination.get("kind") != "point":
        raise ValueError("Moving an object requires point stations for both source and destination.")
    if source_name == destination_name:
        raise ValueError("A move from a station to itself goes nowhere.")

    point_holds = state.get("point_holds")
    if point_holds is None:
        # Older arm-state contracts omitted point_holds. The station table's
        # initial ``holds`` field is the best available live identity there.
        point_holds = {name: value.get("holds") for name, value in stations.items() if value.get("kind") == "point"}
    held = point_holds.get(source_name)
    if not held:
        raise ValueError(f"There is no object at {source_name} to move.")
    destination_held = point_holds.get(destination_name)
    if destination_held:
        raise ValueError(f"Destination {destination_name} already holds {destination_held}.")

    explicit = match.groupdict().get("object")
    if explicit:
        explicit = re.sub(r"^(?:the|a)\s+", "", explicit).strip()
        if explicit not in {held, "object", "item", "thing"}:
            raise ValueError(f"The requested object {explicit!r} does not match {held!r} at {source_name}.")

    return {"action": "move_block", "args": {"from": source_name, "to": destination_name}}


def _add(clause: str, state: ArmState, stations: dict[str, Station]) -> Step | None:
    match = re.fullmatch(
        rf"(?:add|pour)\s+(?:(?P<count>\d+|one|a|an|two|three|four|five|six|seven|eight|nine|ten)\s+)?(?:portions?|samples?|amounts?)?(?:\s+of)?\s+(?:the\s+)?(?:sample\s+)?(?:from\s+)?(?P<src>{_STATION_TOKEN})\s+(?:to|into)\s+(?P<dst>{_STATION_TOKEN})",
        clause,
    )
    if not match:
        # Natural short form: "add 2 from A to C".
        match = re.fullmatch(
            rf"(?:add|pour)\s+(?:(?P<count>\d+|one|a|an|two|three|four|five|six|seven|eight|nine|ten)\s+)?from\s+(?P<src>{_STATION_TOKEN})\s+(?:to|into)\s+(?P<dst>{_STATION_TOKEN})",
            clause,
        )
    if not match:
        return None

    source_name = _station_name(match.group("src"), stations, "Source")
    destination_name = _station_name(match.group("dst"), stations, "Destination")
    source = _station(source_name, stations, "Source")
    destination = _station(destination_name, stations, "Destination")
    if source.get("kind") != "source":
        raise ValueError(f"Source {source_name} is not a sample source.")
    if destination.get("kind") != "receiver":
        raise ValueError(f"Destination {destination_name} is not a receiver.")
    portions = _number(match.group("count"))
    if not 1 <= portions <= 10:
        raise ValueError("The portion count must be a whole number from 1 to 10.")
    left = state.get("portions_left", {}).get(source_name, source.get("portions", 0))
    if portions > left:
        raise ValueError(f"Source {source_name} has only {left} portion(s) left.")
    current = state.get("receiver_load", {}).get(destination_name, 0)
    capacity = destination.get("capacity", 0)
    if current + portions > capacity:
        raise ValueError(f"Destination {destination_name} would exceed its capacity of {capacity}.")
    return {"action": "add_sample", "args": {"source": source_name, "into": destination_name, "portions": portions}}


def _simple(clause: str, state: ArmState, stations: dict[str, Station]) -> Step | None:
    match = re.fullmatch(rf"(?:look|inspect|see)\s+(?:at\s+)?(?P<station>{_STATION_TOKEN})", clause)
    if match:
        name = _station_name(match.group("station"), stations, "Look")
        _station(name, stations, "Look")
        return {"action": "look", "args": {"station": name}}
    match = re.fullmatch(rf"(?:take\s+a\s+look)\s+at\s+(?P<station>{_STATION_TOKEN})", clause)
    if match:
        name = _station_name(match.group("station"), stations, "Look")
        _station(name, stations, "Look")
        return {"action": "look", "args": {"station": name}}

    match = re.fullmatch(r"(?:wait|pause)(?:\s+for)?\s+(?P<seconds>\d+(?:\.\d+)?)\s+(?:s|sec|secs|second|seconds)", clause)
    if match:
        seconds = float(match.group("seconds"))
        if not 1 <= seconds <= 30:
            raise ValueError("Wait seconds must be from 1 to 30.")
        value: int | float = int(seconds) if seconds.is_integer() else seconds
        return {"action": "wait", "args": {"seconds": value}}
    if re.fullmatch(r"(?:wait|pause)", clause):
        raise ValueError("A wait command needs a duration from 1 to 30 seconds.")

    match = re.fullmatch(r"go\s+to\s+(?P<pose>[A-Za-z0-9_-]+)", clause)
    if match:
        pose = match.group("pose").upper()
        if pose not in (state.get("poses") or pose_names(stations)):
            raise ValueError(f"There is no saved position {pose}.")
        return {"action": "go_to", "args": {"pose": pose}}

    match = re.fullmatch(r"(?P<state>open|close)\s+(?:the\s+)?gripper", clause)
    if match:
        return {"action": "gripper", "args": {"state": match.group("state")}}
    return None


def _apply_for_routing(state: ArmState, step: Step) -> None:
    """Update only the small pieces needed to validate subsequent clauses."""
    args = step["args"]
    if step["action"] == "add_sample":
        source, destination, portions = args["source"], args["into"], args["portions"]
        state.setdefault("portions_left", {})[source] -= portions
        state.setdefault("receiver_load", {})[destination] += portions
    elif step["action"] == "move_block":
        holds = state.setdefault("point_holds", {})
        holds[args["to"]] = holds.get(args["from"])
        holds[args["from"]] = None


def route(text: str, state: ArmState, stations: dict[str, Station]) -> list[Step] | None:
    """Route a familiar instruction to catalog actions, or return ``None`` for cold planning."""

    clause_text = _clean(text)
    if not clause_text:
        return None
    if is_stop(clause_text):
        return None
    if re.search(r"\b(?:stop|cancel|or|don't|do not|never)\b", clause_text):
        raise ValueError("Specify one positive command. Use STOP or cancel by itself.")
    # ``and then`` is explicit composition. Plain ``and`` is rejected when it
    # appears in a recognizable command so no trailing clause is silently lost.
    clauses = re.split(r"\s+(?:and\s+then|then)\s+|\s*;\s*", clause_text)
    if len(clauses) > 1 and any(not clause for clause in clauses):
        raise ValueError("Each part of a compound command must be complete.")
    if len(clauses) == 1 and re.search(r"\s+and\s+", clause_text):
        if re.match(r"^(?:move|transfer|carry|add|pour|look|inspect|wait|pause|go|open|close)\b", clause_text):
            raise ValueError("Use 'then' to separate complete compound commands.")
        return None

    working = copy.deepcopy(state)
    working.setdefault("point_holds", {key: item.get("holds") for key, item in stations.items()
                                       if item.get("kind") == "point"})
    steps: list[Step] = []
    for clause in clauses:
        clause = clause.removeprefix("please ").strip()
        step = _move(clause, working, stations)
        if step is None:
            step = _add(clause, working, stations)
        if step is None:
            step = _simple(clause, working, stations)
        if step is None:
            return None
        steps.append(step)
        _apply_for_routing(working, step)
    return steps
