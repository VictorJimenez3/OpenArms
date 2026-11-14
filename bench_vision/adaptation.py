"""Offline empirical source-pose interpolation; never activates or contacts a robot.

Fit separate absolute joint targets at ABOVE_A and GRASP_A against measured table XY.
The same source targets are reused by the existing executor for returning the cup.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from agentic.openarms_agent.runner import run
from firmware.openarms_executor.motion import FakeRobot
from firmware.openarms_executor.pose_arm import PoseArm
from firmware.openarms_executor.poses import ARM_JOINTS
from firmware.openarms_executor.pour_once import PLAN, STATIONS, preflight

SOURCE_POSES = ("ABOVE_A", "GRASP_A")
SETUP_KEYS = ("calibration_id", "fixture_id", "cup_id", "camera_mount_id", "robot_id",
              "robot_base_frame_id", "joint_convention_id")


def _number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _pair(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} needs two values")
    return [_number(v, name) for v in value]


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty")
    return value


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _hull(points):
    """Counterclockwise convex hull of unique 2D points."""
    pts = sorted(set(map(tuple, points)))
    cross = lambda o, a, b: (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lower, upper = [], []
    for sequence, chain in ((pts, lower), (reversed(pts), upper)):
        for point in sequence:
            while len(chain) >= 2 and cross(chain[-2], chain[-1], point) <= 1e-12:
                chain.pop()
            chain.append(point)
    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        raise ValueError("training placements must span a plane")
    return [list(p) for p in hull]


def _contains(hull, point, margin=0):
    for a, b in zip(hull, hull[1:] + hull[:1]):
        dx, dy = b[0]-a[0], b[1]-a[1]
        distance = (dx*(point[1]-a[1])-dy*(point[0]-a[0])) / math.hypot(dx, dy)
        if distance < margin - 1e-9:
            return False
    return True


def _samples(rows, minimum, name):
    if not isinstance(rows, list) or len(rows) < minimum:
        raise ValueError(f"{name} needs at least {minimum} independent placements")
    xy, targets, ids, episodes = [], [], [], []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each placement must be an object")
        ids.append(_text(row.get("id"), "placement id"))
        episodes.append(_text(row.get("episode_id"), "placement episode_id"))
        _text(row.get("receipt"), "placement receipt")
        xy.append(_pair(row.get("xy_mm"), "placement xy_mm"))
        poses = row.get("source_poses", {})
        if not isinstance(poses, dict) or set(poses) != set(SOURCE_POSES):
            raise ValueError("each placement needs exactly ABOVE_A and GRASP_A")
        values = []
        for pose in SOURCE_POSES:
            if not isinstance(poses[pose], dict) or set(poses[pose]) != set(ARM_JOINTS):
                raise ValueError("source pose needs all five named arm joints")
            values += [_number(poses[pose][joint], joint) for joint in ARM_JOINTS]
        targets.append(values)
    if len(set(ids)) != len(ids) or len(set(episodes)) != len(episodes):
        raise ValueError("each placement needs a distinct id and episode")
    if len(set(map(tuple, xy))) != len(xy):
        raise ValueError("placement coordinates must be distinct")
    return np.array(xy), np.array(targets), ids, episodes


def fit_source_map(spec):
    """Fit measured local affine maps and evaluate held-out placements.

    Receipt references/provenance are supplied evidence, not authenticated here.
    Synthetic inputs exercise software only. No model grants physical authorization.
    """
    if not isinstance(spec, dict):
        raise ValueError("source-map specification must be an object")
    _hash(spec)  # Reject nonfinite JSON anywhere, including unused metadata.
    for key in ("mapping_id", "coordinate_frame", "clock_id", "geometry_hash"):
        _text(spec.get(key), key)
    _text(spec.get("object_id"), "object_id")
    setup = spec.get("setup", {})
    if not isinstance(setup, dict):
        raise ValueError("setup must be an object")
    for key in SETUP_KEYS:
        _text(setup.get(key), key)
    if spec.get("units") != {"position": "mm", "arm_joints": "deg", "gripper": "percent_0_100"}:
        raise ValueError("explicit mm, degrees and percent_0_100 conventions are required")
    if spec.get("provenance") not in ("synthetic", "physical_measured"):
        raise ValueError("provenance must be synthetic or physical_measured")
    limits = spec.get("joint_limits", {})
    if not isinstance(limits, dict) or set(limits) != set(ARM_JOINTS):
        raise ValueError("joint limits must cover exactly the five arm joints")
    for pair in limits.values():
        lo, hi = _pair(pair, "joint limits")
        if lo >= hi:
            raise ValueError("joint limits must increase")
    baseline = spec.get("baseline_poses", {})
    if not isinstance(baseline, dict) or not isinstance(baseline.get("poses"), dict) or not isinstance(baseline.get("gripper"), dict):
        raise ValueError("baseline needs poses and gripper objects")
    preflight(baseline, limits)
    source = _pair(spec.get("baseline_source_xy_mm"), "baseline_source_xy_mm")
    for key in ("max_source_shift_mm", "max_heldout_error_deg", "max_target_error_deg", "max_observation_age_s"):
        if _number(spec.get(key), key) <= 0:
            raise ValueError(f"{key} must be positive")
    start = _number(spec.get("valid_from_s"), "valid_from_s")
    end = _number(spec.get("valid_until_s"), "valid_until_s")
    if end <= start:
        raise ValueError("invalid source-map validity interval")
    train_xy, train_q, train_ids, train_episodes = _samples(spec.get("training"), 3, "training")
    test_xy, test_q, test_ids, test_episodes = _samples(spec.get("held_out"), 2, "held_out")
    if set(train_ids) & set(test_ids) or set(train_episodes) & set(test_episodes):
        raise ValueError("held-out placement ids and episodes must be disjoint")
    if any(np.linalg.norm(a-b) < 1e-6 for a in train_xy for b in test_xy):
        raise ValueError("held-out coordinates cannot reuse training positions")
    hull = _hull(train_xy.tolist())
    if not _contains(hull, source) or not all(_contains(hull, p) for p in test_xy):
        raise ValueError("baseline and held-out placements must lie inside training support")
    if any(np.linalg.norm(p-source) > spec["max_source_shift_mm"] for p in np.vstack((train_xy, test_xy))):
        raise ValueError("measured placements exceed the declared local shift bound")
    for samples in (train_q, test_q):
        for index, joint in enumerate(ARM_JOINTS * 2):
            lo, hi = limits[joint]
            if not np.all((lo <= samples[:, index]) & (samples[:, index] <= hi)):
                raise ValueError("measured source target exceeds calibrated joint limits")
    center = train_xy.mean(axis=0)
    scale = np.ptp(train_xy, axis=0)
    if np.any(scale <= 1e-9):
        raise ValueError("training placements must span both dimensions")
    design = np.column_stack((np.ones(len(train_xy)), (train_xy-center)/scale))
    if np.linalg.matrix_rank(design) != 3 or np.linalg.cond(design) > 1e6:
        raise ValueError("source-map fit is degenerate or ill-conditioned")
    coefficients, _, _, _ = np.linalg.lstsq(design, train_q, rcond=None)
    prediction = np.column_stack((np.ones(len(test_xy)), (test_xy-center)/scale)) @ coefficients
    errors = np.abs(prediction-test_q)
    fit_errors = np.abs(design @ coefficients-train_q)
    baseline_q = np.array([baseline["poses"][pose][joint] for pose in SOURCE_POSES for joint in ARM_JOINTS])
    baseline_errors = np.abs(test_q-baseline_q)
    baseline_prediction = np.r_[1, (np.array(source)-center)/scale] @ coefficients
    baseline_consistency = np.abs(baseline_prediction-baseline_q)
    residuals_passed = max(float(errors.max()), float(fit_errors.max())) <= spec["max_heldout_error_deg"]
    baseline_passed = float(baseline_consistency.max()) <= spec["max_heldout_error_deg"]
    status = ("rejected_residual" if not residuals_passed else
              "rejected_baseline_mismatch" if not baseline_passed else "fit_passed")
    artifact = {"schema_version": 1, "kind": "empirical_affine_source_map", "execution": "offline_only",
                "status": status, "spec": copy.deepcopy(spec),
                "baseline_hash": _hash(baseline), "support_hull_mm": hull,
                "center_mm": center.tolist(), "scale_mm": scale.tolist(),
                "coefficients": coefficients.tolist(),
                "evaluation": {"provenance": spec["provenance"], "fit_count": len(train_xy),
                    "held_out_count": len(test_xy), "held_out_ids": test_ids,
                    "fit_max_abs_deg": float(fit_errors.max()), "held_out_max_abs_deg": float(errors.max()),
                    "held_out_rmse_deg": float(np.sqrt(np.mean(errors**2))),
                    "constant_baseline_max_abs_deg": float(baseline_errors.max()),
                    "constant_baseline_rmse_deg": float(np.sqrt(np.mean(baseline_errors**2))),
                    "baseline_consistency_max_abs_deg": float(baseline_consistency.max()),
                    "baseline_consistency_rmse_deg": float(np.sqrt(np.mean(baseline_consistency**2))),
                    "held_out_per_placement_max_abs_deg": errors.max(axis=1).tolist(),
                    "metric_scope": "joint target prediction, not grasp success, clearance or physical path accuracy"},
                "physical_qualification": "not_physical" if spec["provenance"] == "synthetic" else "supplied_measurements_require_independent_review"}
    artifact["content_hash"] = _hash(artifact)
    return artifact


def propose_source_poses(model, observation, current_setup, *, now_s):
    """Return an inspectable proposed pose copy or rejection; no automatic activation."""
    result = {"status": "rejected", "execution": "offline_only", "physical_authorization": "not_granted",
              "proposed_poses": None, "reasons": []}
    try:
        if not all(isinstance(v, dict) for v in (model, observation, current_setup)):
            raise ValueError("model, observation and current_setup must be objects")
        if _hash({k: v for k, v in model.items() if k != "content_hash"}) != model.get("content_hash"):
            raise ValueError("source-map content changed")
        if model.get("status") != "fit_passed" or model.get("execution") != "offline_only":
            raise ValueError("source map has not passed held-out and baseline consistency checks")
        spec = model["spec"]
        if any(current_setup.get(key) != spec["setup"][key] for key in SETUP_KEYS):
            raise ValueError("setup, robot-base registration or joint convention changed")
        if _hash(spec["baseline_poses"]) != model["baseline_hash"]:
            raise ValueError("baseline changed")
        now = _number(now_s, "now_s")
        if not spec["valid_from_s"] <= now <= spec["valid_until_s"]:
            raise ValueError("source map expired")
        for key in ("clock_id", "coordinate_frame", "geometry_hash"):
            if observation.get(key) != spec[key]:
                raise ValueError(f"observation {key} mismatch")
        for key in ("calibration_id", "camera_mount_id"):
            if observation.get(key) != spec["setup"][key]:
                raise ValueError(f"observation {key} mismatch")
        if (observation.get("status") != "ok" or observation.get("feature") != "table_contact"
                or observation.get("units") != "mm" or observation.get("object_id") != spec.get("object_id")):
            raise ValueError("need the identified source cup's calibrated table-contact observation")
        provenance = observation.get("provenance")
        if provenance not in ("synthetic", "physical", "recorded"):
            raise ValueError("observation provenance is unknown")
        age = now-_number(observation.get("timestamp_s"), "timestamp_s")
        if not 0 <= age <= spec["max_observation_age_s"]:
            raise ValueError("observation is stale or future")
        xy = np.array(_pair(observation.get("xy_mm"), "xy_mm"))
        uncertainty = _number(observation.get("uncertainty_mm"), "uncertainty_mm")
        if uncertainty < 0:
            raise ValueError("uncertainty cannot be negative")
        if not _contains(model["support_hull_mm"], xy, uncertainty):
            raise ValueError("target uncertainty exceeds measured interpolation support")
        if np.linalg.norm(xy-np.array(spec["baseline_source_xy_mm"]))+uncertainty > spec["max_source_shift_mm"]:
            raise ValueError("source shift exceeds the declared local bound")
        coefficients = np.array(model["coefficients"])
        scale = np.array(model["scale_mm"])
        query = np.r_[1, (xy-np.array(model["center_mm"]))/scale]
        predicted = query @ coefficients
        # For a Euclidean position-error disk, each affine output has this exact bound.
        sensitivity = np.linalg.norm(coefficients[1:] / scale[:, None], axis=0)
        empirical_residual = max(model["evaluation"]["held_out_max_abs_deg"],
                                 model["evaluation"]["fit_max_abs_deg"],
                                 model["evaluation"]["baseline_consistency_max_abs_deg"])
        error_bound = uncertainty*sensitivity + empirical_residual
        if float(error_bound.max()) > spec["max_target_error_deg"]:
            raise ValueError("propagated position error plus held-out residual exceeds target tolerance")
        proposed = copy.deepcopy(spec["baseline_poses"])
        for i, pose in enumerate(SOURCE_POSES):
            proposed["poses"][pose] = {joint: float(predicted[i*len(ARM_JOINTS)+j])
                                       for j, joint in enumerate(ARM_JOINTS)}
        preflight(proposed, spec["joint_limits"])
        for i, joint in enumerate(ARM_JOINTS * 2):
            lo, hi = spec["joint_limits"][joint]
            if not lo <= predicted[i]-error_bound[i] <= predicted[i]+error_bound[i] <= hi:
                raise ValueError("target error interval exceeds calibrated joint limits")
        robot = FakeRobot(proposed["poses"]["HOME"])
        arm = PoseArm(robot, proposed, STATIONS, seconds=0, pour_hold=0, stop_within_move=True)
        fake = run(PLAN, arm)
        if fake.get("status") != "executed":
            raise ValueError("proposed poses failed existing FakeRobot execution")
        synthetic = spec["provenance"] == "synthetic" or provenance == "synthetic"
        result.update(status="proposed", proposed_poses=proposed, baseline_poses=copy.deepcopy(spec["baseline_poses"]),
                      baseline_hash=model["baseline_hash"], model_hash=model["content_hash"],
                      source_xy_mm=xy.tolist(), target_error_bound_deg=error_bound.tolist(),
                      provenance="synthetic_prediction" if synthetic else "predicted_from_supplied_physical_measurements",
                      changed_poses=list(SOURCE_POSES), fake_validation={"backend": "fake", "result": fake},
                      physical_recommendation="blocked_synthetic_evidence" if synthetic else "requires_independent_review_and_supervised_dry_trial",
                      limitations=["affine interpolation of measured absolute source targets, not inverse kinematics",
                                   "source approach and return change together; receiver, tip, HOME and grip remain unchanged",
                                   "held-out residual is an empirical bound, not a physical guarantee",
                                   "no path clearance, grip or water outcome has been established"])
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        result["reasons"].append(str(exc))
    return result


def synthetic_fixture():
    """Construct an explicitly synthetic affine test problem, not bench measurements."""
    root = Path(__file__).resolve().parents[1]
    baseline = json.loads((root / "firmware/openarms_executor/poses.example.json").read_text())
    setup = {key: f"synthetic-{key}" for key in SETUP_KEYS}
    spec = {"mapping_id": "synthetic-affine-demo", "coordinate_frame": "synthetic-table",
            "clock_id": "synthetic-clock", "geometry_hash": "synthetic-geometry-not-calibration",
            "object_id": "synthetic-source-cup", "setup": setup, "provenance": "synthetic",
            "units": {"position": "mm", "arm_joints": "deg", "gripper": "percent_0_100"},
            "joint_limits": {joint: [-180, 180] for joint in ARM_JOINTS},
            "baseline_poses": baseline, "baseline_source_xy_mm": [100, 100],
            "max_source_shift_mm": 30, "max_heldout_error_deg": .5, "max_target_error_deg": 1,
            "max_observation_age_s": .5, "valid_from_s": 0, "valid_until_s": 100}
    def placement(index, xy):
        dx, dy = xy[0]-100, xy[1]-100
        poses = {pose: {joint: baseline["poses"][pose][joint] +
                       ((j+1)*.02*dx + (5-j)*.01*dy) for j, joint in enumerate(ARM_JOINTS)}
                 for pose in SOURCE_POSES}
        return {"id": f"synthetic-{index}", "episode_id": f"synthetic-episode-{index}",
                "receipt": "constructed-affine-fixture-not-physical", "xy_mm": xy, "source_poses": poses}
    spec["training"] = [placement(i, xy) for i, xy in enumerate(([80,80],[120,80],[120,120],[80,120]))]
    spec["held_out"] = [placement(i+4, xy) for i, xy in enumerate(([90,105],[108,95]))]
    observation = {"status": "ok", "object_id": spec["object_id"], "feature": "table_contact",
                   "units": "mm", "provenance": "synthetic", "timestamp_s": 50,
                   "xy_mm": [104,96], "uncertainty_mm": .5,
                   **{key: spec[key] for key in ("coordinate_frame", "clock_id", "geometry_hash")},
                   **{key: setup[key] for key in ("calibration_id", "camera_mount_id")}}
    return spec, observation


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fit = sub.add_parser("fit")
    fit.add_argument("spec", type=Path)
    fit.add_argument("--out", required=True, type=Path)
    synthetic = sub.add_parser("synthetic")
    synthetic.add_argument("--out", required=True, type=Path)
    propose = sub.add_parser("propose")
    propose.add_argument("model", type=Path)
    propose.add_argument("observation", type=Path)
    propose.add_argument("setup", type=Path)
    propose.add_argument("--now", required=True, type=float)
    propose.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    read = lambda path: json.loads(path.read_text())
    try:
        if args.command == "synthetic":
            spec, observation = synthetic_fixture()
            model = fit_source_map(spec)
            artifact = {"schema_version": 1, "provenance": "synthetic", "spec": spec,
                        "observation": observation, "model": model,
                        "proposal": propose_source_poses(model, observation, spec["setup"], now_s=50.1),
                        "status": model["status"], "claim": "constructed affine fixture; no physical benefit measured"}
        else:
            artifact = fit_source_map(read(args.spec)) if args.command == "fit" else propose_source_poses(
                read(args.model), read(args.observation), read(args.setup), now_s=args.now)
        with args.out.open("x") as output:
            json.dump(artifact, output, indent=2, allow_nan=False)
            output.write("\n")
        print(args.out)
        return 0 if artifact["status"] in ("fit_passed", "proposed") else 2
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
