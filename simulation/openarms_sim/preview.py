"""`preview(plan)`: the simulation's one entry point for the rest of OpenArms.

    from openarms_sim import preview
    result = preview({"plan_id": "p-0007", "steps": [
        {"action": "move_block", "args": {"from": "A", "to": "B"}}]})

Returns a dict:

    ok          True if nothing in the simulation says the real arm must not run this.
    video_url   file:// link to the preview MP4 (None if rendering was skipped).
    warnings    Readable sentences: every reason for a block, then the notes.
    issues      The same, structured: {severity, code, message, step}.
    objects     Where each loose object ends up (block setup).
    predicted   What each receiver is predicted to look like afterwards (liquid setup).
    cached      True if the video already existed for this exact plan and config.

From a terminal:

    python -m openarms_sim --from A --to B
    python -m openarms_sim --plan '{"steps": [...]}'
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
from pathlib import Path

from .chemistry import load_model
from .config import (
    CONFIG_DIR,
    OUTPUT_DIR,
    load_bench,
    load_chemistry_config,
    load_joint_map,
    load_pose_file,
    load_poses,
    poses_are_placeholder,
    setup_dir,
    setup_name,
)
from .joints import JointMap
from .motion import PlanError, build_segments, expand_plan
from .player import Issue, Player
from .render import VideoRecorder
from .scene import build_scene

FPS = 30
VIDEO_SPEED = 2.0  # the preview video plays the motion at twice real speed


def _cache_key(plan: dict, setup: str, contents, objects) -> str:
    h = hashlib.sha256()
    state = {"steps": plan.get("steps"), "setup": setup, "contents": contents, "objects": objects}
    h.update(json.dumps(state, sort_keys=True).encode())
    files = [CONFIG_DIR / "joint_map.yaml", CONFIG_DIR / "chemistry.yaml"]
    files += [setup_dir(setup) / "bench.yaml", setup_dir(setup) / "poses.json"]
    files += sorted(Path(__file__).parent.glob("*.py"))
    for f in files:
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def preview(
    plan: dict,
    contents: dict | None = None,
    objects: dict | None = None,
    render: bool = True,
    use_cache: bool = True,
    poses: dict | None = None,
    setup: str | None = None,
) -> dict:
    """Simulates a plan.

    objects   where loose objects start, e.g. {"block": "B"}; default is bench.yaml.
    contents  what each container holds at the start (liquid setup),
              e.g. {"C": {"cabbage_indicator": 1, "vinegar": 1}}.
    setup     "block" or "liquid"; default is the active setup.
    poses     overrides the setup's poses.json (used by the tests); skips the cache.
    """
    setup = setup_name(setup)
    if poses is not None:
        use_cache = False
    bench = load_bench(setup)
    jm = JointMap(load_joint_map())
    chem_cfg = load_chemistry_config()
    notes: list[Issue] = []
    if poses_are_placeholder(setup):
        notes.append(
            Issue(
                "note",
                "placeholder_poses",
                "Poses are placeholders, not recorded on the real arm, so this preview is illustrative.",
            )
        )
    if not jm.measured:
        notes.append(
            Issue("note", "unmeasured_joint_map", "The joint mapping to the real arm has not been measured yet.")
        )

    def result(ok, issues, video=None, objs=None, predicted=None, seconds=None):
        ordered = [i for i in issues if i.severity == "block"] + [i for i in issues if i.severity != "block"]
        return {
            "plan_id": plan.get("plan_id"),
            "setup": setup,
            "ok": ok,
            "video_url": video.resolve().as_uri() if video else None,
            "warnings": [i.message for i in ordered],
            "issues": [vars(i) for i in ordered],
            "objects": objs or [],
            "predicted": predicted or [],
            "motion_seconds": seconds,
            "cached": False,
        }

    try:
        pose_file = load_pose_file(setup)
        taught = pose_file.get("source") == "taught"
        jm.use_taught_gripper(pose_file.get("gripper"))
        all_poses = poses or pose_file["poses"]
        steps = expand_plan(plan)
        segments = build_segments(steps, all_poses, jm, bench.stations)
        scene = build_scene(bench)
        # Poses taken from the real arm are trusted: they may sit past the model's joint
        # range, and what touches in them is not reported as a collision.
        trusted = [np.array(jm.pose_to_model(all_poses[n])) for n in pose_file.get("taught", []) if n in all_poses]
        player = Player(
            scene, jm, chem_cfg, load_model(chem_cfg), contents, objects, strict_limits=not taught, trusted_poses=trusted
        )
    except (PlanError, ValueError) as e:
        return result(False, [Issue("block", "bad_plan", str(e))])

    key = _cache_key(plan, setup, contents, objects)
    video = OUTPUT_DIR / "previews" / f"{key}.mp4"
    meta = video.with_suffix(".json")
    if use_cache and render and video.exists() and meta.exists():
        cached = json.loads(meta.read_text())
        cached.update(plan_id=plan.get("plan_id"), cached=True)
        return cached

    recorder = VideoRecorder(scene, video, FPS, VIDEO_SPEED) if render else None
    player.run(segments, FPS, on_frame=recorder)
    if recorder:
        recorder.close()

    objs = [
        {"name": name, "at": player.location[name], "started_at": player.start_location[name],
         "moved": player.location[name] != player.start_location[name]}
        for name in bench.objects
    ]
    predicted = []
    for r in bench.receivers:
        outcome = player.chem.predict(player.contents[r])
        predicted.append(
            {
                "station": r,
                "contents": player.contents[r],
                "color": outcome.label,
                "observations": outcome.observations,
                "rgb": list(outcome.color),
                "changed": sum(player.contents[r].values()) != player.initial[r],
            }
        )
    issues = player.issues + notes
    ok = not any(i.severity == "block" for i in issues)
    seconds = round(sum(s.duration for s in segments), 1)
    out = result(ok, issues, video if render else None, objs, predicted, seconds)
    if render and poses is None:
        meta.write_text(json.dumps(out, indent=2))
    return out


def example_plan(source: str | None = None, into: str | None = None, portions: int = 1, setup: str | None = None) -> dict:
    """A one-step plan: move the block (block setup) or add a sample (liquid setup)."""
    if load_bench(setup_name(setup)).receivers:  # a bench with receivers pours (liquid, kit)
        source, into = source or "A", into or "C"
        step = {"action": "add_sample", "args": {"source": source, "into": into, "portions": portions}}
        said = f"add some of {source} to {into}"
    else:
        source, into = source or "A", into or "B"
        step = {"action": "move_block", "args": {"from": source, "to": into}}
        said = f"move the block from {source} to {into}"
    return {"plan_id": "example", "student_instruction": said, "steps": [step]}
