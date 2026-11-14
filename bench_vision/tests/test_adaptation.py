import copy
import unittest
from unittest.mock import patch

from bench_vision.adaptation import fit_source_map, propose_source_poses, synthetic_fixture
from firmware.openarms_executor.poses import ARM_JOINTS


class AdaptationTests(unittest.TestCase):
    def setUp(self):
        self.spec, self.observation = synthetic_fixture()
        self.model = fit_source_map(self.spec)

    def test_heldout_comparison_reports_actual_joint_errors(self):
        self.assertEqual(self.model["status"], "fit_passed")
        result = self.model["evaluation"]
        self.assertEqual(result["fit_count"], 4)
        self.assertEqual(result["held_out_count"], 2)
        self.assertLess(result["held_out_max_abs_deg"], 1e-10)
        self.assertGreater(result["constant_baseline_max_abs_deg"], .9)
        self.assertEqual(self.model["physical_qualification"], "not_physical")

    def test_only_source_poses_change_and_fake_executor_works(self):
        baseline = copy.deepcopy(self.spec["baseline_poses"])
        with patch("firmware.openarms_executor.robot.connect", side_effect=AssertionError("hardware")):
            result = propose_source_poses(self.model, self.observation, self.spec["setup"], now_s=50.1)
        self.assertEqual(result["status"], "proposed", result)
        proposed = result["proposed_poses"]
        changed = [name for name in baseline["poses"] if proposed["poses"][name] != baseline["poses"][name]]
        self.assertEqual(changed, ["ABOVE_A", "GRASP_A"])
        self.assertEqual(proposed["gripper"], baseline["gripper"])
        self.assertEqual(result["baseline_poses"], baseline)
        self.assertEqual(result["fake_validation"]["result"]["status"], "executed")
        self.assertEqual(result["physical_recommendation"], "blocked_synthetic_evidence")
        self.assertEqual(self.spec["baseline_poses"], baseline)

    def test_cannot_relabel_synthetic_observation_into_physical_authorization(self):
        self.observation["provenance"] = "physical"
        result = propose_source_poses(self.model, self.observation, self.spec["setup"], now_s=50.1)
        self.assertEqual(result["physical_recommendation"], "blocked_synthetic_evidence")
        self.assertEqual(result["physical_authorization"], "not_granted")

    def test_shift_and_uncertainty_must_stay_inside_support(self):
        for xy, uncertainty in (([130,100],0), ([119.8,100],.5), ([120,120],2), ([104,96],20)):
            obs = {**self.observation, "xy_mm": xy, "uncertainty_mm": uncertainty}
            result = propose_source_poses(self.model, obs, self.spec["setup"], now_s=50.1)
            self.assertEqual(result["status"], "rejected", result)

    def test_setup_clock_geometry_convention_and_feature_drift_rejected(self):
        for key in self.spec["setup"]:
            setup = {**self.spec["setup"], key: "changed"}
            self.assertEqual(propose_source_poses(self.model, self.observation, setup, now_s=50.1)["status"], "rejected")
        for key, value in (("clock_id","other"), ("geometry_hash","other"), ("coordinate_frame","other"),
                           ("calibration_id","other"), ("camera_mount_id","other"), ("feature","rim"),
                           ("units","m"), ("object_id","receiver"), ("status","unknown"),
                           ("timestamp_s",40), ("timestamp_s",51), ("provenance","unknown")):
            obs = {**self.observation, key: value}
            self.assertEqual(propose_source_poses(self.model, obs, self.spec["setup"], now_s=50.1)["status"], "rejected")

    def test_expired_tampered_and_malformed_rejected(self):
        self.assertEqual(propose_source_poses(self.model, self.observation, self.spec["setup"], now_s=101)["status"], "rejected")
        self.model["coefficients"][0][0] += 1
        self.assertEqual(propose_source_poses(self.model, self.observation, self.spec["setup"], now_s=50.1)["status"], "rejected")
        self.assertEqual(propose_source_poses(None, [], {}, now_s=50)["status"], "rejected")

    def test_reject_nonfinite_and_negative_uncertainty(self):
        for uncertainty in (float("nan"), float("inf"), -1, True):
            obs = {**self.observation, "uncertainty_mm": uncertainty}
            self.assertEqual(propose_source_poses(self.model, obs, self.spec["setup"], now_s=50.1)["status"], "rejected")
        self.spec["training"][0]["source_poses"]["ABOVE_A"][ARM_JOINTS[0]] = float("nan")
        with self.assertRaises(ValueError):
            fit_source_map(self.spec)

    def test_disjoint_heldout_positions_and_episodes_required(self):
        for key in ("xy_mm", "id", "episode_id"):
            spec = copy.deepcopy(self.spec)
            spec["held_out"][0][key] = spec["training"][0][key]
            with self.assertRaises(ValueError):
                fit_source_map(spec)

    def test_insufficient_collinear_and_extrapolated_data_rejected(self):
        bad = copy.deepcopy(self.spec)
        bad["training"] = bad["training"][:2]
        with self.assertRaises(ValueError): fit_source_map(bad)
        bad = copy.deepcopy(self.spec)
        bad["held_out"] = bad["held_out"][:1]
        with self.assertRaises(ValueError): fit_source_map(bad)
        bad = copy.deepcopy(self.spec)
        for row in bad["training"]: row["xy_mm"][1] = 100
        with self.assertRaises(ValueError): fit_source_map(bad)
        bad = copy.deepcopy(self.spec)
        bad["held_out"][0]["xy_mm"] = [140,100]
        with self.assertRaises(ValueError): fit_source_map(bad)

    def test_heldout_failure_keeps_model_out_of_proposal(self):
        self.spec["held_out"][0]["source_poses"]["GRASP_A"][ARM_JOINTS[0]] += 3
        model = fit_source_map(self.spec)
        self.assertEqual(model["status"], "rejected_residual")
        self.assertGreater(model["evaluation"]["held_out_max_abs_deg"], 2.9)
        self.assertEqual(propose_source_poses(model, self.observation, self.spec["setup"], now_s=50.1)["status"], "rejected")

    def test_joint_limits_and_units_required(self):
        bad = copy.deepcopy(self.spec)
        bad["units"]["arm_joints"] = "radians"
        with self.assertRaises(ValueError): fit_source_map(bad)
        bad = copy.deepcopy(self.spec)
        bad["joint_limits"][ARM_JOINTS[0]] = [-1,1]
        with self.assertRaises(ValueError): fit_source_map(bad)

    def test_error_propagates_through_both_xy_axes(self):
        proposal = propose_source_poses(self.model, self.observation, self.spec["setup"], now_s=50.1)
        expected = .5 * (.1**2 + .01**2)**.5
        self.assertAlmostEqual(proposal["target_error_bound_deg"][4], expected)


if __name__ == "__main__":
    unittest.main()
