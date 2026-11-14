"""Claude tool schemas and their dispatcher. No tool here moves the arm."""
import time
from dataclasses import dataclass
from typing import Any, Optional

from . import validator
from .notebook import Notebook
from .types import ArmPort, Plan, Station

OBSERVATION_SOURCES = ["student", "teacher", "unknown"]


@dataclass
class Session:
    session_id: str
    stations: dict[str, Station]
    arm: ArmPort
    notebook: Notebook
    pending_plan: Optional[Plan] = None
    help_requested: bool = False
    stop_requested: bool = False
    plan_count: int = 0
    predicted: bool = False


def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


_STATION = {"type": "string", "description": "Station name from the lab table"}
_STEP = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["add_sample", "wait", "look"]},
        "args": {"type": "object", "description": 'add_sample: {"source","into","portions"}; wait: {"seconds"}; look: {"station"}'},
    },
    "required": ["action", "args"],
}

TOOLS = [
    {"name": "submit_plan",
     "description": "Send a plan for ONE student instruction to the validator. Only after the student said yes. "
                    "Returns a rejection reason to fix, or awaiting_teacher. Never moves the arm.",
     "input_schema": _obj({"student_instruction": {"type": "string"},
                           "steps": {"type": "array", "items": _STEP, "minItems": 1, "maxItems": 6}},
                          ["student_instruction", "steps"])},
    {"name": "record_prediction", "description": "Save the student's prediction, in their words, before any run.",
     "input_schema": _obj({"text": {"type": "string"}}, ["text"])},
    {"name": "record_observation", "description": "Save what was seen and who saw it. Never invent an observation.",
     "input_schema": _obj({"text": {"type": "string"}, "source": {"type": "string", "enum": OBSERVATION_SOURCES}},
                          ["text", "source"])},
    {"name": "look", "description": "Take a camera picture of a station. No motion. Returns an image reference.",
     "input_schema": _obj({"station": _STATION}, ["station"])},
    {"name": "request_help", "description": "Alert the teacher (spill, dropped cup, worried student). Stops further plans.",
     "input_schema": _obj({"reason": {"type": "string"}}, ["reason"])},
    {"name": "get_notebook", "description": "The session so far, as short text.", "input_schema": _obj({}, [])},
]


def _submit_plan(inp: dict, s: Session) -> dict:
    if s.help_requested:
        return {"status": "rejected", "reason": "Help was requested; wait for the teacher before any new plan."}
    s.plan_count += 1
    plan: Plan = {"plan_id": f"{s.session_id}-p{s.plan_count:04d}",
                  "student_instruction": inp.get("student_instruction", ""), "steps": inp.get("steps", [])}
    try:
        v = validator.validate(plan, s.arm.state(), s.stations)
    except (ValueError, KeyError, TypeError) as e:  # a malformed plan is a rejection, not a crash
        v = {"ok": False, "reason": str(e), "expanded": [], "end_state": None}
    s.notebook.add("plan", plan=plan, ok=v["ok"], reason=v["reason"])
    if not v["ok"]:
        return {"status": "rejected", "plan_id": plan["plan_id"], "reason": v["reason"]}
    s.pending_plan, s.stop_requested = plan, False  # a new plan is the only thing that clears a stop
    return {"status": "awaiting_teacher", "plan_id": plan["plan_id"], "expanded": v["expanded"]}


def dispatch(name: str, inp: dict[str, Any], session: Session) -> dict:
    s = session
    if name == "submit_plan":
        return _submit_plan(inp, s)
    if name == "record_prediction":
        s.notebook.add("prediction", text=inp["text"])
        s.predicted = True
        return {"saved": True}
    if name == "record_observation":
        src = inp.get("source") if inp.get("source") in OBSERVATION_SOURCES else "unknown"
        s.notebook.add("observation", text=inp["text"], source=src)
        return {"saved": True, "source": src}
    if name == "look":
        station = inp.get("station")
        if station not in s.stations:
            return {"error": f"No station named {station!r}."}
        # shortcut: no camera yet, returns a placeholder reference; wire the real still when the camera lands
        image = f"{station}_{int(time.time())}.jpg"
        s.notebook.add("observation", station=station, image=image, source="camera")
        return {"image": image}
    if name == "request_help":
        s.help_requested = True
        s.notebook.add("help", reason=inp.get("reason", ""))
        return {"teacher_alerted": True}
    if name == "get_notebook":
        return {"notebook": s.notebook.as_text()}
    return {"error": f"Unknown tool {name!r}."}
