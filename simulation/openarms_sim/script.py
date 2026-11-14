"""Plays the real arm's own waypoint script in the simulation, before the arm runs it.

The firmware's transfer runner sends the arm a list of targets: either the five arm
joints (degrees, as LeRobot reports them) or the gripper alone (0..100). This module
plays that same list, at the same seconds per move, and reports what it shows:

    from openarms_sim.script import preview_script
    out = preview_script(script, home, marks={"A": grasp_a, "B": grasp_b},
                         object_at="A", source="A", destination="B", seconds=1.5)

`marks` are the arm poses in which the gripper is on each station; the simulation
draws a mark where each puts the gripper, so no ruler is needed. The object starts
on the `object_at` mark (or nowhere, if None).

The poses come from the real arm, so the model's joint range is not enforced. Until
config/joint_map.yaml has been measured, what the simulation shows touching the table
or the object is reported as a note, not a block: it is as likely to be the mapping
as the motion. A grasp that closes on nothing, or an object that never reaches the
destination, blocks either way.

From a terminal (reads a JSON request on stdin, prints the result as JSON):

    python -m openarms_sim.script < request.json
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from .chemistry import load_model
from .config import ARM_JOINTS, OUTPUT_DIR, Bench, ObjectSpec, Station, load_chemistry_config, load_joint_map
from .joints import JointMap
from .motion import Segment
from .player import Issue, Player
from .recording import GEOMETRY_CODES, _empty_bench, _fk
from .render import VideoRecorder
from .scene import build_scene

FPS = 30
VIDEO_SPEED = 2.0
GRIPPER = "gripper.pos"
COLORS = {"mandarin": (0.95, 0.55, 0.10), "sample": (0.25, 0.55, 0.90)}


def _arm(pose: dict) -> dict:
    """{"shoulder_pan.pos": v, ...} or {"shoulder_pan": v, ...} -> {"shoulder_pan": v, ...}"""
    out = {k.removesuffix(".pos"): float(v) for k, v in pose.items() if k != GRIPPER}
    missing = [j for j in ARM_JOINTS if j not in out]
    if missing:
        raise ValueError(f"an arm target is missing {missing}")
    return {j: out[j] for j in ARM_JOINTS}


def _row(pose: dict) -> np.ndarray:
    return np.array([pose[j] for j in ARM_JOINTS])


def _bench(jm: JointMap, marks: dict, object_name: str, object_at: str | None) -> tuple[Bench, dict]:
    probe = build_scene(_empty_bench())
    where = {name: _fk(probe, jm, _row(_arm(pose)))[0] for name, pose in marks.items()}
    if not where:
        raise ValueError("no station marks were given")
    # Every mark is on the same table, so the object is drawn for the lowest grasp.
    grasp_height = float(np.clip(min(p[2] for p in where.values()), 0.015, 0.25))
    xs = [p[0] for p in where.values()] + [0.0]
    ys = [p[1] for p in where.values()] + [0.0]
    size = min(0.045, grasp_height + 0.02)
    objects = {}
    if object_at is not None:
        if object_at not in where:
            raise ValueError(f"the {object_name} cannot start at {object_at!r}; marks are {sorted(where)}")
        objects[object_name] = ObjectSpec(
            object_name, (size, size, grasp_height + 0.02), object_at, COLORS.get(object_name, (0.9, 0.3, 0.15))
        )
    bench = Bench(
        table_size=(max(xs) - min(xs) + 0.40, max(ys) - min(ys) + 0.60),
        table_center=((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2),
        stations={n: Station(n, "point", (float(p[0]), float(p[1]))) for n, p in where.items()},
        objects=objects,
        grasp_height=grasp_height,
        lift=0.09,
        release_tolerance=0.04,  # a real release can be a little high; the object drops onto the mark
        grasp_tolerance=0.03,
    )
    return bench, {n: [round(float(v) * 100, 1) for v in p] for n, p in where.items()}


def _segments(script: list[dict], home: dict, jm: JointMap, seconds: float, source: str, destination: str):
    """One segment per target, exactly as the runner's move_to interpolates them."""
    arm = _arm(home)
    grip = float(home.get(GRIPPER, script[0].get(GRIPPER, 50.0)) if script else 50.0)
    q = np.array(jm.pose_to_model(arm))
    out, held, released = [], False, False
    for target in script:
        if set(target) == {GRIPPER}:
            new = float(target[GRIPPER])
            event = None
            if new < grip - 1 and not held and not released:
                event, held = "close", True
            elif new > grip + 1 and held:
                event, held, released = "open", False, True
            label = "close the gripper" if new < grip - 1 else "open the gripper" if new > grip + 1 else "hold the gripper"
            step = f"place({destination})" if event == "open" else f"pick({source})" if not released else "home()"
            index = 0 if not (held or released) or event == "close" else 1 if not released or event == "open" else 2
            out.append(Segment(index, step, label, q, q, grip, new, seconds, event))
            grip = new
        else:
            q1 = np.array(jm.pose_to_model(_arm(target)))
            if released:
                index, step, label = 2, "home()", "move away and return"
            elif held:
                index, step, label = 1, f"place({destination})", "carry"
            else:
                index, step, label = 0, f"pick({source})", "reach"
            out.append(Segment(index, step, label, q, q1, grip, grip, seconds, None))
            q = q1
    return out


def preview_script(
    script: list[dict],
    home: dict,
    marks: dict,
    object_at: str | None,
    source: str = "A",
    destination: str = "B",
    object_name: str = "mandarin",
    seconds: float = 1.5,
    render: bool = True,
    trusted: list[dict] | None = None,
) -> dict:
    """Simulates a waypoint script. `trusted` are poses recorded on the real arm."""
    jm = JointMap(load_joint_map())
    notes = []
    if not jm.measured:
        notes.append(Issue("note", "unmeasured_joint_map", "The joint mapping to the real arm has not been measured yet."))

    def result(ok, issues, video=None, objs=None, marks_cm=None, motion=None):
        ordered = [i for i in issues if i.severity == "block"] + [i for i in issues if i.severity != "block"]
        return {
            "ok": ok,
            "video_url": video.resolve().as_uri() if video else None,
            "video_file": video.name if video else None,
            "warnings": [i.message for i in ordered],
            "issues": [vars(i) for i in ordered],
            "objects": objs or [],
            "marks_cm": marks_cm or {},
            "motion_seconds": motion,
            "joint_map_measured": jm.measured,
            "source": source,
            "destination": destination,
        }

    try:
        bench, marks_cm = _bench(jm, marks, object_name, object_at)
        scene = build_scene(bench)
        segments = _segments(script, home, jm, seconds, source, destination)
        chem_cfg = load_chemistry_config()
        poses = [np.array(jm.pose_to_model(_arm(p))) for p in (trusted or [])]
        player = Player(scene, jm, chem_cfg, load_model(chem_cfg), strict_limits=False, trusted_poses=poses)
    except (ValueError, KeyError) as e:
        return result(False, [Issue("block", "bad_plan", str(e))] + notes)

    video = None
    if render:
        state = {"script": script, "home": home, "marks": marks, "at": object_at, "seconds": seconds,
                 "route": [source, destination, object_name], "jm": jm.cfg}
        h = hashlib.sha256(json.dumps(state, sort_keys=True).encode())
        for f in sorted(Path(__file__).parent.glob("*.py")):
            h.update(f.read_bytes())
        video = OUTPUT_DIR / "previews" / f"script-{h.hexdigest()[:16]}.mp4"
    recorder = VideoRecorder(scene, video, FPS, VIDEO_SPEED, show_blocks=jm.measured) if render else None
    player.run(segments, FPS, on_frame=recorder)
    if recorder:
        recorder.close()

    issues = []
    for i in player.issues:
        if i.code in GEOMETRY_CODES and not jm.measured:
            # Not trusted to stop a run until the mapping to the real arm is measured.
            issues.append(Issue("note", i.code, i.message + " (not blocking: joint map unmeasured)", i.step))
        else:
            issues.append(i)
    objs = [
        {"name": n, "at": player.location[n], "started_at": player.start_location[n],
         "moved": player.location[n] != player.start_location[n]}
        for n in bench.objects
    ]
    closes = any(s.event == "close" for s in segments)
    if closes and object_at is not None and player.location.get(object_name) != destination:
        if not any(i.severity == "block" for i in issues):
            at = player.location.get(object_name)
            issues.append(Issue("block", "not_delivered",
                                f"In the simulation the {object_name} ends "
                                f"{'at ' + at if at else 'off its marks'}, not at {destination}."))
    issues += notes
    ok = not any(i.severity == "block" for i in issues)
    return result(ok, issues, video, objs, marks_cm, round(sum(s.duration for s in segments), 1))


def main() -> None:
    req = json.load(sys.stdin)
    out = preview_script(
        req["script"], req["home"], req["marks"], req.get("object_at"), req.get("source", "A"),
        req.get("destination", "B"), req.get("object", "mandarin"), float(req.get("seconds", 1.5)),
        bool(req.get("render", True)), req.get("trusted"),
    )
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
