"""Turns a plan into arm motion.

A plan action expands into arm steps: `move_block` into `pick`, `place`,
`home`; `add_sample` into `pick`, `pour`, `return_cup`, `home`. Each arm step is a fixed script of named poses and
gripper commands. `go_to` between two poses is a joint-space move with a speed
limit and smooth start and stop.

The firmware must move the real arm with the same scripts and the same
`go_to` timing, or the preview will not match. Import them from here rather
than writing a second copy.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .joints import JointMap

ARM_STEPS = {"pick", "place", "pour", "return_cup", "home", "wait"}


class PlanError(ValueError):
    """The plan is malformed or names something that does not exist."""


@dataclass
class Segment:
    """One continuous move: the arm joints (model radians) and the gripper
    (LeRobot 0..100) go from the start values to the end values over `duration`."""

    step_index: int
    step: str  # e.g. "pick(A)"
    label: str  # e.g. "move to ABOVE_A"
    q0: np.ndarray
    q1: np.ndarray
    grip0: float
    grip1: float
    duration: float
    event: str | None = None  # "close" or "open", applied when the segment ends


def expand_plan(plan: dict) -> list[dict]:
    """Plan actions -> arm steps. Arm steps already in the plan pass through."""
    steps: list[dict] = []
    for i, item in enumerate(plan.get("steps", [])):
        action, args = item.get("action"), item.get("args") or {}
        if action == "move_block":
            try:
                src, dst = args["from"], args["to"]
            except KeyError as e:
                raise PlanError(f"step {i + 1}: move_block needs {e.args[0]!r}") from None
            if src == dst:
                raise PlanError(f"step {i + 1}: move_block from {src} to {dst} goes nowhere")
            steps.append({"action": "pick", "args": {"station": src}})
            steps.append({"action": "place", "args": {"station": dst}})
            steps.append({"action": "home", "args": {}})
        elif action == "add_sample":
            try:
                source, into = args["source"], args["into"]
            except KeyError as e:
                raise PlanError(f"step {i + 1}: add_sample needs {e.args[0]!r}") from None
            portions = int(args.get("portions", 1))
            if portions < 1:
                raise PlanError(f"step {i + 1}: portions must be at least 1")
            steps.append({"action": "pick", "args": {"station": source}})
            steps += [{"action": "pour", "args": {"into": into}} for _ in range(portions)]
            steps.append({"action": "return_cup", "args": {}})
            steps.append({"action": "home", "args": {}})
        elif action == "look":
            continue  # a camera still; nothing moves
        elif action in ARM_STEPS:
            steps.append({"action": action, "args": args})
        else:
            raise PlanError(f"step {i + 1}: unknown action {action!r}")
    return steps


def go_to_duration(q0: np.ndarray, q1: np.ndarray, max_speed_deg_s: float, min_duration_s: float) -> float:
    """How long a move takes so that no joint exceeds the speed limit.
    The smooth profile peaks at 1.5x its average speed, hence the factor."""
    biggest = float(np.max(np.abs(np.degrees(q1 - q0)))) if len(q0) else 0.0
    return max(min_duration_s, 1.5 * biggest / max_speed_deg_s)


def blend(u: float) -> float:
    """Smooth 0..1 progress for a move: zero speed at both ends."""
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def build_segments(
    steps: list[dict], poses: dict[str, dict[str, float]], jm: JointMap, stations: dict,
    *, start_q: np.ndarray | None = None, start_grip: float | None = None, held_source: str | None = None,
) -> list[Segment]:
    """Arm steps -> moves, from HOME/open unless resuming a simulated action."""
    mcfg = jm.cfg["motion"]
    open_v, closed_v = jm.gripper_open_value, jm.gripper_closed_value

    def pose(name: str) -> np.ndarray:
        if name not in poses:
            raise PlanError(f"no pose named {name} in poses.json")
        return np.array(jm.pose_to_model(poses[name]))

    segments: list[Segment] = []
    q = pose("HOME") if start_q is None else np.asarray(start_q, dtype=float)
    grip = open_v if start_grip is None else start_grip
    holding = held_source  # station the held cup came from, as the plan intends

    def move(i, step, name):
        nonlocal q
        target = pose(name)
        dur = go_to_duration(q, target, mcfg["max_speed_deg_s"], mcfg["min_duration_s"])
        segments.append(Segment(i, step, f"move to {name}", q, target, grip, grip, dur))
        q = target

    def gripper(i, step, value, event):
        nonlocal grip
        segments.append(
            Segment(i, step, f"gripper {event}", q, q, grip, value, mcfg["gripper_duration_s"], event)
        )
        grip = value

    for i, st in enumerate(steps):
        action, args = st["action"], st.get("args") or {}
        if action == "pick":
            s = args.get("station")
            if s not in stations or stations[s].kind not in ("source", "point"):
                raise PlanError(f"pick: there is nothing to pick up at {s!r}")
            step = f"pick({s})"
            if grip != open_v:
                gripper(i, step, open_v, "open")
            move(i, step, f"ABOVE_{s}")
            move(i, step, f"GRASP_{s}")
            gripper(i, step, closed_v, "close")
            move(i, step, f"LIFT_{s}")
            holding = s if stations[s].kind == "source" else None
        elif action == "place":
            s = args.get("station")
            if s not in stations or stations[s].kind != "point":
                raise PlanError(f"place: {s!r} is not a point an object can be placed on")
            step = f"place({s})"
            move(i, step, f"ABOVE_{s}")
            move(i, step, f"GRASP_{s}")
            gripper(i, step, open_v, "open")
            move(i, step, f"ABOVE_{s}")
        elif action == "pour":
            r = args.get("into")
            if r not in stations or stations[r].kind != "receiver":
                raise PlanError(f"pour: {r!r} is not a receiver station")
            step = f"pour({r})"
            move(i, step, f"ABOVE_{r}")
            move(i, step, f"TIP_{r}")
            segments.append(Segment(i, step, "hold while pouring", q, q, grip, grip, 1.2))
            move(i, step, f"ABOVE_{r}")
        elif action == "return_cup":
            step = "return_cup()"
            if holding is None:
                raise PlanError("return_cup: the plan is not holding a cup from a source station")
            move(i, step, f"ABOVE_{holding}")
            move(i, step, f"GRASP_{holding}")
            gripper(i, step, open_v, "open")
            move(i, step, f"ABOVE_{holding}")
            holding = None
        elif action == "home":
            move(i, "home()", "HOME")
        elif action == "wait":
            seconds = float(args.get("seconds", 1))
            if not 1 <= seconds <= 30:
                raise PlanError("wait: seconds must be between 1 and 30")
            segments.append(Segment(i, f"wait({seconds:g})", "hold still", q, q, grip, grip, seconds))
    return segments
