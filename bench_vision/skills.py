"""Offline demonstration evidence compiler. No registry activation or hardware access.

Run ``python -m bench_vision.skills --help`` from the repository root.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from agentic.openarms_agent.catalog import expand
from agentic.openarms_agent.runner import run
from agentic.openarms_agent.validator import validate
from firmware.openarms_executor.motion import FakeRobot
from firmware.openarms_executor.pose_arm import PoseArm
from firmware.openarms_executor.poses import ARM_JOINTS, GRIPPER
from firmware.openarms_executor.pour_once import PLAN, POSE_NAMES, STATIONS, preflight

SETUP_IDS = ("calibration_id", "fixture_id", "cup_id", "camera_mount_id", "robot_id")
CHECKPOINTS = ("HOME", "open", "ABOVE_A", "GRASP_A", "cup", "ABOVE_C", "TIP_C", "finish")
PROVENANCE = {"synthetic", "recorded", "physical", "fake", "simulated", "predicted", "unknown"}


def _finite(value: Any, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _json(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (ValueError, TypeError) as exc:
        raise ValueError("artifact must contain finite JSON values") from exc


def content_hash(value: Any) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _xy(value: Any, name: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must contain two coordinates")
    return [_finite(item, name) for item in value]


def _validate_context(context: dict) -> None:
    if not isinstance(context, dict):
        raise ValueError("context must be an object")
    for name in SETUP_IDS:
        _text(context.get(name), name)
    if context.get("provenance") not in PROVENANCE:
        raise ValueError("context needs explicit provenance")
    limits = context.get("joint_limits", {})
    if set(limits) != set(ARM_JOINTS):
        raise ValueError("joint_limits must name the five existing arm joints")
    for joint, pair in limits.items():
        low, high = _xy(pair, joint)
        if low >= high:
            raise ValueError("joint limits must be increasing")
    age = _finite(context.get("max_observation_age_s", 1), "max_observation_age_s")
    if age <= 0:
        raise ValueError("max_observation_age_s must be positive")
    _json(context)


def _validate_trace(trace: list[dict], poses: dict) -> list[dict]:
    if not isinstance(trace, list) or not trace:
        raise ValueError("demonstration needs the original nonempty joint trace")
    previous = -math.inf
    checkpoints = []
    samples = 0
    for row in trace:
        t = _finite(row.get("t"), "trace t")
        if t < previous:
            raise ValueError("trace timestamps must be monotonic")
        previous = t
        if row.get("event") not in ("sample", "checkpoint"):
            raise ValueError("unsupported joint trace event")
        state = row.get("state", {})
        for joint in (*ARM_JOINTS, GRIPPER):
            _finite(state.get(joint), f"trace state {joint}")
        if row["event"] == "sample":
            for field in ("command", "leader", "sent"):
                values = row.get(field, {})
                if not isinstance(values, dict):
                    raise ValueError(f"trace sample {field} must contain joint values")
                for joint in (*ARM_JOINTS, GRIPPER):
                    _finite(values.get(joint), f"trace {field} {joint}")
            samples += 1
            continue
        name = row.get("name")
        _text(name, "checkpoint name")
        if name in POSE_NAMES:
            for joint in ARM_JOINTS:
                if abs(state[joint] - poses["poses"][name][joint]) > 1e-6:
                    raise ValueError(f"{name} does not match the saved demonstration pose")
        elif name in ("open", "cup"):
            reading = row.get("command", {}).get(GRIPPER) if name == "cup" else state[GRIPPER]
            if abs(_finite(reading, f"{name} gripper") - poses["gripper"][name]) > 1e-6:
                raise ValueError(f"{name} does not match the saved gripper command")
        checkpoints.append({"name": name, "t": t})
    # Repeated finish prompts are legal; the first complete ordered sequence is sufficient.
    remaining = iter(CHECKPOINTS)
    wanted = next(remaining)
    for row in checkpoints:
        if row["name"] == wanted:
            wanted = next(remaining, None)
    if wanted is not None or samples == 0:
        raise ValueError("trace needs samples and ordered water-teaching checkpoints")
    return checkpoints


def _validate_summary(summary: dict, trace: list[dict]) -> None:
    if not isinstance(summary, dict) or summary.get("schema_version") != 1:
        raise ValueError("episode summary needs schema_version 1")
    _text(summary.get("episode_id"), "episode_id")
    if summary.get("provenance") not in PROVENANCE:
        raise ValueError("episode summary needs explicit provenance")
    if not isinstance(summary.get("phases"), list) or not summary["phases"]:
        raise ValueError("episode summary needs selected phases")
    offset = _finite(summary.get("telemetry_time_offset_s", 0), "telemetry_time_offset_s")
    first, last = trace[0]["t"] + offset, trace[-1]["t"] + offset
    previous = -math.inf
    for phase in summary["phases"]:
        _text(phase.get("name"), "phase name")
        t = _finite(phase.get("t"), "phase t")
        if not first <= t <= last or t < previous:
            raise ValueError("phase timestamps must be ordered inside the trace")
        previous = t
        if not isinstance(phase.get("views"), list):
            raise ValueError("each phase needs views, including explicit missing views")
    _json(summary)


def _fake_validation(poses: dict, limits: dict) -> dict:
    preflight(poses, limits)
    robot = FakeRobot(poses["poses"]["HOME"])
    arm = PoseArm(robot, copy.deepcopy(poses), STATIONS, seconds=0, pour_hold=0,
                  stop_within_move=True)
    verdict = validate(PLAN, arm.state(), STATIONS)
    if not verdict["ok"]:
        raise ValueError(verdict["reason"])
    result = run(PLAN, arm)
    if result.get("status") != "executed":
        raise ValueError("existing pose executor failed on FakeRobot")
    return {"backend": "fake", "static_preflight": "passed", "result": result,
            "commands_sent": len(robot.sent), "physical_outcome": "unknown",
            "scope": "existing catalog, validator and PoseArm; no collision, grip or liquid model"}


def _outcome(summary: dict) -> dict:
    raw = summary.get("outcome", {"status": "unknown", "evidence": []})
    if not isinstance(raw, dict) or raw.get("status") not in ("unknown", "passed", "failed"):
        raise ValueError("outcome status must be unknown, passed or failed")
    evidence = raw.get("evidence", [])
    if not isinstance(evidence, list):
        raise ValueError("outcome evidence must be a list")
    if raw["status"] != "unknown" and not evidence:
        raise ValueError("a reported outcome needs independent evidence")
    for item in evidence:
        if item.get("provenance") not in PROVENANCE:
            raise ValueError("outcome evidence needs explicit provenance")
        _text(item.get("reference"), "outcome evidence reference")
        _text(item.get("observer"), "outcome observer")
    return copy.deepcopy(raw)


def compile_candidate(poses: dict, trace: list[dict], summary: dict, context: dict,
                      baseline: dict | None = None) -> dict:
    """Compile one existing A→C water take. All results remain offline candidates."""
    _validate_context(context)
    _json(poses)
    validation = _fake_validation(poses, context["joint_limits"])
    checkpoints = _validate_trace(trace, poses)
    _validate_summary(summary, trace)
    if baseline is not None:
        verify_candidate(baseline)
    payload = {
        "schema_version": 1,
        "skill_id": "bench.add_sample.A.C",
        "status": "candidate",
        "execution": "offline_only",
        "controller_ref": "firmware.openarms_executor.pose_arm:PoseArm",
        "plan": copy.deepcopy(PLAN),
        "expanded_steps": expand(PLAN),
        "poses": copy.deepcopy(poses),
        "context": copy.deepcopy(context),
        "preconditions": {
            "setup_ids": {key: context[key] for key in SETUP_IDS},
            "operator_authorization": "required separately for each physical run",
            "current_home_check": "required by existing supervised executor",
            "source_quantity": "one independently known pre-portioned cup",
            "fixture": "A source and C receiver unchanged",
            "max_observation_age_s": context.get("max_observation_age_s", 1),
        },
        "geometry_assumptions": copy.deepcopy(context.get("geometry", {
            "status": "unavailable", "mode": "taught_fixture_only",
            "reason": "no metric calibration; relocation is rejected"})),
        "checkpoints": checkpoints,
        "phases": copy.deepcopy(summary["phases"]),
        "episode": {"id": summary["episode_id"], "provenance": summary["provenance"],
                    "summary": copy.deepcopy(summary)},
        "source_hashes": {"poses": content_hash(poses), "trace": content_hash(trace),
                          "summary": content_hash(summary), "context": content_hash(context)},
        "validation": validation,
        "outcome": _outcome(summary),
        "required_outcome_checks": ["grip and clearance", "delivery independently observed",
                                    "spill observation", "cup returned", "HOME and reset"],
        "rollback": {"baseline_version": baseline["version"] if baseline else None,
                     "baseline_candidate": copy.deepcopy(baseline),
                     "retained_poses": copy.deepcopy(baseline["poses"] if baseline else poses),
                     "scope": "offline export; never changes the live executor or its files"},
    }
    return {**payload, "version": content_hash(payload)}


def verify_candidate(candidate: dict) -> None:
    """Detect edits to a candidate and its retained baseline; this is not a signature."""
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be an object")
    payload = {key: value for key, value in candidate.items() if key != "version"}
    if candidate.get("version") != content_hash(payload):
        raise ValueError("candidate content does not match its version")
    if candidate.get("schema_version") != 1 or candidate.get("execution") != "offline_only":
        raise ValueError("unsupported candidate schema or execution scope")
    if candidate.get("status") != "candidate":
        raise ValueError("offline compiler cannot activate a skill")
    for key, field in (("poses", "poses"), ("context", "context")):
        if candidate.get("source_hashes", {}).get(key) != content_hash(candidate.get(field)):
            raise ValueError(f"candidate {key} no longer matches its source")
    summary = candidate.get("episode", {}).get("summary")
    if candidate.get("source_hashes", {}).get("summary") != content_hash(summary):
        raise ValueError("candidate summary no longer matches its source")
    if summary.get("phases") != candidate.get("phases"):
        raise ValueError("candidate phases differ from the bound episode summary")
    baseline = candidate.get("rollback", {}).get("baseline_candidate")
    if baseline is not None:
        verify_candidate(baseline)
        if candidate["rollback"]["baseline_version"] != baseline["version"]:
            raise ValueError("rollback baseline version mismatch")


def write_candidate(candidate: dict, directory: str | Path) -> Path:
    """Exclusive immutable write, safely idempotent for the exact same candidate."""
    verify_candidate(candidate)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{candidate['version']}.json"
    try:
        with path.open("x") as output:
            output.write(json.dumps(candidate, indent=2, allow_nan=False) + "\n")
    except FileExistsError:
        if load_candidate(path) != candidate:
            raise ValueError("existing candidate cannot be overwritten")
    return path


def load_candidate(path: str | Path) -> dict:
    candidate = json.loads(Path(path).read_text())
    verify_candidate(candidate)
    return candidate


def rollback(candidate: dict) -> dict:
    """Export the retained baseline without modifying any live registry or pose file."""
    verify_candidate(candidate)
    retained = candidate["rollback"]
    poses = copy.deepcopy(retained["retained_poses"])
    baseline = retained["baseline_candidate"]
    if baseline is not None and poses != baseline["poses"]:
        raise ValueError("retained rollback poses differ from baseline")
    return {"schema_version": 1, "execution": "offline_only", "from_version": candidate["version"],
            "baseline_version": retained["baseline_version"], "poses": poses,
            "poses_hash": content_hash(poses), "physical_activation": "not_performed"}


def preview_adaptation(candidate: dict, observation: dict, current_context: dict, now_s: float) -> dict:
    """Validate a bounded source XY proposal. Never synthesize or authorize motor targets.

    Geometry requires held-out measured checks and a declared support rectangle. The
    observation must describe a calibrated tabletop contact point, not a cup rim or box
    center. A successful preview still needs a matching, evaluated robot controller.
    """
    verify_candidate(candidate)
    reasons = []
    result = {"candidate_version": candidate["version"], "execution": "offline_only",
              "status": "rejected", "reasons": reasons, "motor_targets": None}
    try:
        if not isinstance(observation, dict):
            raise ValueError("observation must be an object")
        _validate_context(current_context)
        now = _finite(now_s, "now_s")
        for key in SETUP_IDS:
            if current_context[key] != candidate["context"][key]:
                reasons.append(f"changed {key}")
        if content_hash(current_context.get("geometry")) != content_hash(candidate["context"].get("geometry")):
            reasons.append("geometry evidence changed; compile a new candidate")
        if observation.get("status") != "ok":
            reasons.append("source localization is unknown")
        for key in ("calibration_id", "camera_mount_id"):
            if observation.get(key) != current_context[key]:
                reasons.append(f"observation has changed or missing {key}")
        _text(observation.get("camera_id"), "camera_id")
        _text(observation.get("object_id"), "object_id")
        if observation.get("feature") != "table_contact":
            reasons.append("localization must use the calibrated table contact feature")
        t = _finite(observation.get("timestamp_s"), "observation timestamp_s")
        age = now - t
        if age < 0 or age > candidate["preconditions"]["max_observation_age_s"]:
            reasons.append("source observation is stale or from a different clock")
        xy = _xy(observation.get("xy_mm"), "xy_mm")
        uncertainty = _finite(observation.get("uncertainty_mm"), "uncertainty_mm")
        if uncertainty < 0:
            reasons.append("negative localization uncertainty")
        geometry = candidate["context"].get("geometry", {})
        _text(geometry.get("clock_id"), "geometry clock_id")
        _text(geometry.get("coordinate_frame"), "geometry coordinate_frame")
        for key in ("clock_id", "coordinate_frame"):
            if observation.get(key) != geometry[key]:
                reasons.append(f"observation has changed or missing {key}")
        if observation.get("units") != "mm":
            reasons.append("observation units must be mm")
        if geometry.get("status") != "validated" or geometry.get("units") != "mm":
            reasons.append("metric geometry is not validated")
        if geometry.get("feature") != "table_contact":
            reasons.append("geometry does not define a table contact feature")
        if geometry.get("camera_id") != observation.get("camera_id"):
            reasons.append("observation camera is outside validated geometry")
        if observation.get("object_id") != geometry.get("object_id"):
            reasons.append("localized object differs from the taught source")
        check = geometry.get("validation", {})
        if (check.get("provenance") != "physical" or check.get("independent") is not True
                or type(check.get("held_out_count")) is not int or check["held_out_count"] < 3):
            reasons.append("independent held-out physical geometry checks are missing")
        _text(check.get("receipt"), "geometry validation receipt")
        error = _finite(check.get("max_error_mm"), "max_error_mm")
        maximum = _finite(geometry.get("max_total_error_mm"), "max_total_error_mm")
        if error < 0 or maximum <= 0 or uncertainty + error > maximum:
            reasons.append("localization plus held-out residual exceeds the declared tolerance")
        source = _xy(geometry.get("source_xy_mm"), "source_xy_mm")
        region = geometry.get("supported_region_mm", {})
        low, high = _xy(region.get("min"), "region min"), _xy(region.get("max"), "region max")
        margin = max(0, uncertainty + error)
        if any(low[i] >= high[i] or not low[i] + margin <= xy[i] <= high[i] - margin for i in range(2)):
            reasons.append("target and its uncertainty exceed the validated source region")
        maximum_shift = _finite(geometry.get("max_source_shift_mm"), "max_source_shift_mm")
        distance = math.dist(source, xy)
        if maximum_shift <= 0 or distance + margin > maximum_shift:
            reasons.append("source shift exceeds the validated bound")
        height = _finite(geometry.get("grip_height_mm"), "grip_height_mm")
        if height <= 0:
            reasons.append("actual cup grip geometry is not defined")
        if observation.get("provenance") not in ("physical", "recorded"):
            reasons.append("source localization is not recorded physical evidence")
        if candidate["episode"]["provenance"] not in ("physical", "recorded"):
            reasons.append("teaching episode is not recorded physical evidence")
        for phase_name in ("before", "grasp", "after"):
            phases = [phase for phase in candidate["phases"] if phase["name"] == phase_name]
            cameras = {view.get("camera_id") for phase in phases for view in phase["views"]
                       if view.get("status") == "ok" and view.get("image")}
            if len(cameras - {None}) < 2:
                reasons.append(f"{phase_name} lacks two usable teaching-camera views")
        if reasons:
            return result
        result.update(status="geometry_preview_only", target_xy_mm=xy,
                      source_displacement_mm=[xy[i] - source[i] for i in range(2)],
                      total_error_bound_mm=margin, grip_height_mm=height,
                      unchanged_phases=["receiver_approach", "tip", "receiver_recovery", "home"],
                      controller_validation="required: measured robot-base mapping, reachability, clearance, supervised dry trial",
                      physical_authorization="not_granted")
        return result
    except (ValueError, KeyError, TypeError) as exc:
        reasons.append(str(exc))
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    compile_parser = commands.add_parser("compile")
    for option in ("poses", "trace", "summary", "context", "out"):
        compile_parser.add_argument(f"--{option}", required=True, type=Path)
    compile_parser.add_argument("--baseline", type=Path)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("candidate", type=Path)
    rollback_parser = commands.add_parser("rollback")
    rollback_parser.add_argument("candidate", type=Path)
    rollback_parser.add_argument("--out", required=True, type=Path)
    preview_parser = commands.add_parser("preview")
    preview_parser.add_argument("candidate", type=Path)
    for option in ("observation", "context"):
        preview_parser.add_argument(f"--{option}", required=True, type=Path)
    preview_parser.add_argument("--now-s", required=True, type=float)
    args = parser.parse_args(argv)
    read = lambda path: json.loads(path.read_text())
    try:
        if args.command == "compile":
            trace = [json.loads(line) for line in args.trace.read_text().splitlines() if line.strip()]
            candidate = compile_candidate(read(args.poses), trace, read(args.summary), read(args.context),
                                          load_candidate(args.baseline) if args.baseline else None)
            print(write_candidate(candidate, args.out))
        elif args.command == "verify":
            print(json.dumps({"version": load_candidate(args.candidate)["version"], "status": "intact"}))
        elif args.command == "rollback":
            receipt = rollback(load_candidate(args.candidate))
            with args.out.open("x") as output:
                json.dump(receipt, output, indent=2, allow_nan=False)
                output.write("\n")
            print(args.out)
        else:
            result = preview_adaptation(load_candidate(args.candidate), read(args.observation),
                                        read(args.context), args.now_s)
            print(json.dumps(result, indent=2, allow_nan=False))
            return 0 if result["status"] == "geometry_preview_only" else 2
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
