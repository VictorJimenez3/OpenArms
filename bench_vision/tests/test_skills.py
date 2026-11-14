"""Software evidence only: synthetic inputs, existing PoseArm and FakeRobot."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bench_vision.skills import (CHECKPOINTS, compile_candidate, content_hash, load_candidate,
                                 preview_adaptation, rollback, verify_candidate, write_candidate)
from bench_vision.keyframes import select_events
from firmware.openarms_executor.poses import ARM_JOINTS, GRIPPER

ROOT = Path(__file__).resolve().parents[2]


def inputs():
    poses = json.loads((ROOT / "firmware/openarms_executor/poses.example.json").read_text())
    trace = []
    for index, name in enumerate(CHECKPOINTS):
        state = {**poses["poses"].get(name, poses["poses"]["HOME"]),
                 GRIPPER: poses["gripper"][name] if name in ("open", "cup") else 20}
        trace += [{"event": "sample", "t": 100 + index, "state": state,
                   "command": state, "sent": state, "leader": state},
                  {"event": "checkpoint", "name": name, "t": 100 + index,
                   "state": state, "command": state}]
    summary = {"schema_version": 1, "episode_id": "synthetic-test", "provenance": "synthetic",
               "phases": [{**event, "views": [
                   {"camera_id": camera, "status": "ok", "image": f"{camera}-{event['name']}.jpg"}
                   for camera in ("overview", "side")]}
                   for event in select_events(trace) if event["name"] in ("before", "grasp", "after")],
               "outcome": {"status": "unknown", "evidence": []}}
    context = {"calibration_id": "test-cal", "fixture_id": "test-fixture", "cup_id": "test-cup",
               "camera_mount_id": "test-mount", "robot_id": "test-robot", "provenance": "synthetic",
               "joint_limits": {joint: [-180, 180] for joint in ARM_JOINTS},
               "max_observation_age_s": 1}
    return poses, trace, summary, context


def geometry_fixture():
    poses, trace, summary, context = inputs()
    # These are contract-test values; this is not a physical calibration receipt.
    summary["provenance"] = "recorded"
    context["geometry"] = {
        "status": "validated", "units": "mm", "feature": "table_contact", "camera_id": "overview",
        "clock_id": "test-host-boot", "coordinate_frame": "test-table-plane",
        "object_id": "source-cup", "source_xy_mm": [100, 100], "grip_height_mm": 35,
        "supported_region_mm": {"min": [80, 80], "max": [120, 120]},
        "max_source_shift_mm": 15, "max_total_error_mm": 2,
        "validation": {"provenance": "physical", "independent": True,
                       "held_out_count": 5, "max_error_mm": 0.5, "receipt": "unit-test-only"}}
    observation = {"status": "ok", "object_id": "source-cup", "camera_id": "overview",
                   "timestamp_s": 200, "calibration_id": "test-cal", "camera_mount_id": "test-mount",
                   "feature": "table_contact", "xy_mm": [105, 103], "uncertainty_mm": 0.4,
                   "clock_id": "test-host-boot", "coordinate_frame": "test-table-plane", "units": "mm",
                   "provenance": "recorded"}
    return compile_candidate(poses, trace, summary, context), observation, context


class SkillTests(unittest.TestCase):
    def test_compiler_reuses_executor_and_retains_unknown_outcome(self):
        with patch("firmware.openarms_executor.robot.connect", side_effect=AssertionError("hardware")):
            candidate = compile_candidate(*inputs())
        self.assertEqual(candidate["validation"]["result"]["status"], "executed")
        self.assertEqual(candidate["validation"]["physical_outcome"], "unknown")
        self.assertEqual(candidate["outcome"]["status"], "unknown")
        self.assertEqual(candidate["execution"], "offline_only")
        self.assertEqual([s["action"] for s in candidate["expanded_steps"]],
                         ["pick", "pour", "return_cup", "home"])
        verify_candidate(candidate)

    def test_deterministic_content_version_changes_with_evidence(self):
        first = compile_candidate(*inputs())
        self.assertEqual(first["version"], compile_candidate(*inputs())["version"])
        data = inputs()
        data[2]["episode_id"] = "another-episode"
        self.assertNotEqual(first["version"], compile_candidate(*data)["version"])

    def test_input_not_modified(self):
        data = inputs()
        original = copy.deepcopy(data)
        compile_candidate(*data)
        self.assertEqual(data, original)

    def test_tampering_is_rejected_before_preview_or_write(self):
        candidate, obs, context = geometry_fixture()
        candidate["poses"]["poses"]["TIP_C"][ARM_JOINTS[0]] += 1
        for operation in (lambda: verify_candidate(candidate),
                          lambda: preview_adaptation(candidate, obs, context, 200)):
            with self.assertRaisesRegex(ValueError, "version"):
                operation()

    def test_exclusive_storage_and_corrupt_file(self):
        candidate = compile_candidate(*inputs())
        with tempfile.TemporaryDirectory() as directory:
            path = write_candidate(candidate, directory)
            self.assertEqual(write_candidate(candidate, directory), path)
            self.assertEqual(load_candidate(path), candidate)
            corrupted = copy.deepcopy(candidate)
            corrupted["status"] = "active"
            path.write_text(json.dumps(corrupted))
            with self.assertRaises(ValueError):
                write_candidate(candidate, directory)
            self.assertEqual(json.loads(path.read_text())["status"], "active")

    def test_rollback_retains_original_baseline(self):
        baseline = compile_candidate(*inputs())
        data = inputs()
        data[2]["episode_id"] = "candidate-2"
        candidate = compile_candidate(*data, baseline=baseline)
        restored = rollback(candidate)
        self.assertEqual(restored["baseline_version"], baseline["version"])
        self.assertEqual(restored["poses"], baseline["poses"])
        self.assertEqual(restored["physical_activation"], "not_performed")
        self.assertEqual(rollback(baseline)["poses"], baseline["poses"])

    def test_missing_checkpoint_rejected(self):
        data = inputs()
        data[1][:] = [r for r in data[1] if r.get("name") != "TIP_C"]
        with self.assertRaisesRegex(ValueError, "ordered"):
            compile_candidate(*data)

    def test_wrong_checkpoint_and_joint_limits_rejected(self):
        data = inputs()
        data[1][1]["state"][ARM_JOINTS[0]] += 10
        with self.assertRaisesRegex(ValueError, "match"):
            compile_candidate(*data)
        data = inputs()
        data[3]["joint_limits"][ARM_JOINTS[0]] = [-1, 1]
        with self.assertRaisesRegex(ValueError, "range"):
            compile_candidate(*data)

    def test_bad_timestamps_and_nonfinite_numbers_rejected(self):
        for value in (float("nan"), float("inf"), True, "100"):
            data = inputs()
            data[1][0]["t"] = value
            with self.assertRaises(ValueError):
                compile_candidate(*data)
        data = inputs()
        data[1][2]["t"] = 90
        with self.assertRaisesRegex(ValueError, "monotonic"):
            compile_candidate(*data)
        data = inputs()
        data[2]["phases"][1]["t"] = 999
        with self.assertRaisesRegex(ValueError, "trace"):
            compile_candidate(*data)

    def test_nonzero_trace_clock_offset_supported(self):
        data = inputs()
        data[2]["telemetry_time_offset_s"] = 25
        for phase in data[2]["phases"]:
            phase["t"] += 25
        candidate = compile_candidate(*data)
        self.assertEqual(candidate["phases"][0]["t"], 125)

    def test_fabricated_grasp_within_trace_range_is_rejected(self):
        for changes in ({"t": 103, "raw_trace_t": 103}, {"checkpoint": "TIP_C"},
                        {"event_source": "inferred_gripper"}, {"name": "lift"}):
            with self.subTest(changes=changes):
                data = inputs()
                data[2]["phases"][1].update(changes)
                with self.assertRaisesRegex(ValueError, "semantics"):
                    compile_candidate(*data)

    def test_fabricated_release_without_trace_opening_is_rejected(self):
        data = inputs()
        data[2]["phases"].insert(2, {"name": "release", "t": 106, "raw_trace_t": 106,
                                    "event_source": "inferred_gripper", "checkpoint": None, "views": []})
        with self.assertRaisesRegex(ValueError, "semantics"):
            compile_candidate(*data)

    def test_duplicate_claimed_event_is_rejected(self):
        data = inputs()
        data[2]["phases"].insert(2, copy.deepcopy(data[2]["phases"][1]))
        with self.assertRaisesRegex(ValueError, "more than once"):
            compile_candidate(*data)

    def test_raw_and_aligned_phase_timestamps_must_agree(self):
        data = inputs()
        data[2]["phases"][1]["raw_trace_t"] -= 1
        with self.assertRaisesRegex(ValueError, "aligned timestamp"):
            compile_candidate(*data)

    def test_semantics_can_use_offset_when_raw_timestamp_omitted(self):
        data = inputs()
        data[2]["telemetry_time_offset_s"] = 25.125
        for phase in data[2]["phases"]:
            phase.pop("raw_trace_t")
            phase["t"] += 25.125
        candidate = compile_candidate(*data)
        self.assertEqual(candidate["phases"][1]["checkpoint"], "cup")

    def test_optional_trace_aligned_time_cannot_relabel_event(self):
        data = inputs()
        for row in data[1]:
            row["aligned_t"] = row["t"] + 1
        # Untrusted convenience fields in trace rows do not change original semantics.
        compile_candidate(*data)
        data[2]["phases"][1].update(t=105, raw_trace_t=105)
        with self.assertRaisesRegex(ValueError, "semantics"):
            compile_candidate(*data)

    def test_explicit_missing_views_are_allowed_for_candidate_evidence(self):
        data = inputs()
        data[2]["phases"][1]["views"] = [{"camera_id": "side", "status": "missing", "image": None}]
        candidate = compile_candidate(*data)
        self.assertEqual(candidate["phases"][1]["views"][0]["status"], "missing")

    def test_nonfinite_command_and_unknown_event_rejected(self):
        data = inputs()
        data[1][0]["command"] = {**data[1][0]["command"], GRIPPER: float("nan")}
        with self.assertRaises(ValueError):
            compile_candidate(*data)
        data = inputs()
        data[1][0]["event"] = "servo-command"
        with self.assertRaisesRegex(ValueError, "unsupported"):
            compile_candidate(*data)

    def test_rehashed_inconsistent_summary_rejected(self):
        candidate = compile_candidate(*inputs())
        candidate["episode"]["summary"]["episode_id"] = "other"
        candidate["version"] = content_hash({k: v for k, v in candidate.items() if k != "version"})
        with self.assertRaisesRegex(ValueError, "summary"):
            verify_candidate(candidate)

    def test_claimed_outcome_requires_provenance_and_observer(self):
        data = inputs()
        data[2]["outcome"]["status"] = "passed"
        with self.assertRaisesRegex(ValueError, "independent evidence"):
            compile_candidate(*data)
        data[2]["outcome"]["evidence"] = [{"provenance": "fake", "reference": "fake-receipt", "observer": "test"}]
        candidate = compile_candidate(*data)
        self.assertEqual(candidate["outcome"]["evidence"][0]["provenance"], "fake")
        self.assertEqual(candidate["validation"]["physical_outcome"], "unknown")

    def test_valid_geometry_preview_never_outputs_motor_commands(self):
        candidate, observation, context = geometry_fixture()
        poses_before = copy.deepcopy(candidate["poses"])
        preview = preview_adaptation(candidate, observation, context, 200.1)
        self.assertEqual(preview["status"], "geometry_preview_only", preview)
        self.assertEqual(preview["source_displacement_mm"], [5, 3])
        self.assertIsNone(preview["motor_targets"])
        self.assertEqual(candidate["poses"], poses_before)
        self.assertEqual(preview["physical_authorization"], "not_granted")

    def test_changed_setup_rejected(self):
        candidate, obs, context = geometry_fixture()
        for key in ("calibration_id", "cup_id", "fixture_id", "robot_id", "camera_mount_id"):
            changed = copy.deepcopy(context)
            changed[key] = "changed"
            result = preview_adaptation(candidate, obs, changed, 200.1)
            self.assertEqual(result["status"], "rejected")
            self.assertIn(f"changed {key}", result["reasons"])

    def test_unknown_stale_future_wrong_feature_and_object_rejected(self):
        candidate, obs, context = geometry_fixture()
        cases = [{"status": "unknown"}, {"timestamp_s": 198}, {"timestamp_s": 201},
                 {"feature": "rim"}, {"object_id": "receiver"}, {"camera_id": "side"},
                 {"clock_id": "another-host"}, {"coordinate_frame": "robot-base"}, {"units": "m"},
                 {"xy_mm": [121, 100]}, {"xy_mm": [119.5, 100]}, {"uncertainty_mm": 3},
                 {"xy_mm": [111, 111]}, {"timestamp_s": float("nan")}, {"uncertainty_mm": -1}]
        for case in cases:
            with self.subTest(case=case):
                result = preview_adaptation(candidate, {**obs, **case}, context, 200.1)
                self.assertEqual(result["status"], "rejected", result)

    def test_missing_geometry_and_missing_images_rejected(self):
        candidate = compile_candidate(*inputs())
        _, obs, _ = geometry_fixture()
        result = preview_adaptation(candidate, obs, candidate["context"], 200.1)
        self.assertEqual(result["status"], "rejected")
        data = list(inputs())
        _, obs, data[3] = geometry_fixture()
        data[2]["provenance"] = "recorded"
        data[2]["phases"][0]["views"][1]["status"] = "missing"
        candidate = compile_candidate(*data)
        result = preview_adaptation(candidate, obs, candidate["context"], 200.1)
        self.assertIn("before lacks two usable teaching-camera views", result["reasons"])

    def test_fit_residual_is_not_held_out_validation(self):
        data = list(inputs())
        _, obs, data[3] = geometry_fixture()
        data[2]["provenance"] = "recorded"
        data[3]["geometry"]["validation"]["independent"] = False
        candidate = compile_candidate(*data)
        result = preview_adaptation(candidate, obs, candidate["context"], 200.1)
        self.assertEqual(result["status"], "rejected")
        self.assertIn("independent held-out physical geometry checks are missing", result["reasons"])


if __name__ == "__main__":
    unittest.main()
