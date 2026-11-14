"""Actual-asset offline tests: python test_kinematics.py --asset /path/robot.usd.

No mock geometry substitutes for the required asset. --evidence prints candidate
solutions and provenance as JSON; it never launches Isaac or claims contact.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import unittest

import numpy as np
from pxr import Gf, Sdf, Usd, UsdGeom

from kinematics import JOINT_NAMES, Model, WORKSHOP_COMMIT


INITIAL_Q = np.array([-.2736, -.6109, -.0745, 1.5148, -1.6034, -.1465])
# World coordinates, meters. Geometrically reachable points, not approved paths.
CANDIDATES = (
    ("initial_hover", [.23, 0., .08]),
    ("source", [.23, 0., .025]),
    ("source_lift", [.23, 0., .08]),
    ("receiver_hover", [.20, .08, .08]),
    ("receiver", [.20, .08, .025]),
    ("receiver_retreat", [.20, .08, .08]),
)
ASSET = None


def offline_evidence(model, asset):
    seed = INITIAL_Q.copy()
    stations = []
    for name, xyz in CANDIDATES:
        q, report = model.solve(xyz, [0, 0, -1], seed)
        stations.append({"name": name, "target_xyz_m": xyz,
                         "tool_axis_world": [0, 0, -1],
                         "q_rad": None if q is None else q.tolist(),
                         "report": asdict(report)})
        if q is not None:
            seed = q
    return {"kind": "offline_kinematics_only", "physics_contact_tested": False,
            "expected_workshop_commit": WORKSHOP_COMMIT,
            "asset": str(asset), "asset_sha256": hashlib.sha256(Path(asset).read_bytes()).hexdigest(),
            "joint_names": JOINT_NAMES, "seed_rad": INITIAL_Q.tolist(),
            "zero_body_errors": model.zero_errors,
            "geometry": model.geometry_evidence, "candidates": stations}


class ActualAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if ASSET is None:
            raise RuntimeError("Run test_kinematics.py with --asset; actual USD is required")
        cls.model = Model.from_usd(ASSET)

    def test_zero_matches_all_authored_bodies(self):
        self.assertEqual(len(self.model.zero_errors), 7)
        for error in self.model.zero_errors.values():
            self.assertLess(error["position_error_m"], 1e-7)
            self.assertLess(error["rotation_error_rad"], 2e-7)
        np.testing.assert_allclose(self.model.fk(np.zeros(6))[:3, 3],
                                   [.3774733, .0206163, .2668527], atol=2e-6)

    def test_positive_axis_rotation_for_each_joint(self):
        # Independent world-axis Gf rotation around each authored joint pivot.
        # Establishes the implemented USD convention, not a runtime sign proof.
        model = self.model
        zero = model.body_poses(np.zeros(6))
        for index, joint in enumerate(model.joints):
            for angle in (-.15, .15):
                with self.subTest(joint=joint.name, angle=angle):
                    frame = zero[joint.parent] @ joint.local0
                    axis = frame[:3, :3] @ joint.axis
                    gf = Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(*axis), np.rad2deg(angle)))
                    rotation = np.asarray(gf).T[:3, :3]
                    expected = np.eye(4)
                    expected[:3, :3] = rotation @ zero[joint.child][:3, :3]
                    expected[:3, 3] = frame[:3, 3] + rotation @ (zero[joint.child][:3, 3] - frame[:3, 3])
                    q = np.zeros(6)
                    q[index] = angle
                    np.testing.assert_allclose(model.body_poses(q)[joint.child], expected, atol=1e-12)

    def test_collider_proxy_geometry_and_uncertain_offset(self):
        model = self.model
        stage = Usd.Stage.Open(str(ASSET))
        meshes = model.geometry_evidence["collider_meshes"]
        expected = 3 if ASSET.name == 'SO-ARM101-USD-NO-CAMERA.usd' else 4
        self.assertEqual(len(meshes), expected)
        self.assertTrue(all(stage.GetPrimAtPath(path).IsInstanceProxy() for path in meshes))
        np.testing.assert_array_equal(model.tool_transform[:3, 3], [0, 0, -.1])
        self.assertAlmostEqual(model.geometry_evidence["nominal_jaw_zero_inner_gap_m"], .0158, places=6)

    def test_seeded_roundtrips(self):
        model = self.model
        rng = np.random.default_rng(101)
        for trial in range(40):
            with self.subTest(trial=trial):
                q = rng.uniform(model.lower + .15, model.upper - .15)
                pose = model.fk(q)
                seed = np.clip(q + rng.normal(0, .06, 6), model.lower, model.upper)
                solved, report = model.solve(pose[:3, 3], pose[:3, :3] @ model.tool_axis_local,
                                             seed, position_tolerance_m=2e-5,
                                             direction_tolerance_rad=2e-4)
                self.assertTrue(report.success, report)
                self.assertIsNotNone(solved)
                self.assertEqual(solved[5], seed[5])
                self.assertTrue(np.all(solved >= model.lower))
                self.assertTrue(np.all(solved <= model.upper))
                np.testing.assert_allclose(model.fk(solved)[:3, 3], pose[:3, 3], atol=2e-5)

    def test_reachable_station_candidates(self):
        evidence = offline_evidence(self.model, ASSET)
        for station in evidence["candidates"]:
            with self.subTest(station=station["name"]):
                self.assertTrue(station["report"]["success"], station)
                self.assertLess(station["report"]["position_error_m"], 1e-6)
                self.assertLess(station["report"]["direction_error_rad"], 1e-4)

    def test_unreachable_and_orientation_mismatch_rejected(self):
        q, report = self.model.solve([2, 0, .1], [0, 0, -1], INITIAL_Q)
        self.assertIsNone(q)
        self.assertFalse(report.success)
        self.assertGreater(report.position_error_m, 1)
        # At the same near-extended point, flipping the approach direction cannot
        # be achieved within position/direction tolerances and authored limits.
        pose = self.model.fk(np.zeros(6))
        q, report = self.model.solve(pose[:3, 3], -pose[:3, :3] @ self.model.tool_axis_local,
                                     np.zeros(6))
        self.assertIsNone(q)
        self.assertFalse(report.success)

    def test_exhausted_solver_rejected(self):
        q, report = self.model.solve(CANDIDATES[1][1], [0, 0, -1], INITIAL_Q, max_nfev=1)
        self.assertIsNone(q)
        self.assertFalse(report.optimizer_success)

    def test_bad_inputs_and_out_of_limit_commands_rejected(self):
        model = self.model
        for bad in ([0] * 5, [0] * 7, [np.nan] * 6, [np.inf] * 6, model.upper + .01):
            with self.subTest(q=bad), self.assertRaises(ValueError):
                model.fk(bad)
        for direction in ([0, 0, 0], [1, np.nan, 0], [1, 0]):
            with self.subTest(direction=direction), self.assertRaises(ValueError):
                model.solve([.23, 0, .025], direction, INITIAL_Q)
        with self.assertRaises(ValueError):
            model.solve([np.inf, 0, 0], [0, 0, -1], INITIAL_Q)
        with self.assertRaises(ValueError):
            model.solve([.23, 0, .025], [0, 0, -1], model.upper + .01)
        for kwargs in ({"position_tolerance_m": 0}, {"direction_tolerance_rad": np.inf},
                       {"max_nfev": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                model.solve([.23, 0, .025], [0, 0, -1], INITIAL_Q, **kwargs)

    def test_jaw_does_not_move_nominal_grasp_frame(self):
        model = self.model
        open_q = INITIAL_Q.copy()
        open_q[5] = 1
        np.testing.assert_array_equal(model.fk(open_q), model.fk(INITIAL_Q))
        self.assertGreater(np.max(np.abs(model.body_poses(open_q)[model.jaw_path] -
                                        model.body_poses(INITIAL_Q)[model.jaw_path])), .1)

    def test_composed_root_transform_and_runtime_comparison(self):
        stage = Usd.Stage.CreateInMemory()
        UsdGeom.SetStageMetersPerUnit(stage, 1)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        root = UsdGeom.Xform.Define(stage, "/Robot")
        root.GetPrim().GetReferences().AddReference(str(ASSET))
        root.AddTranslateOp(opSuffix="testTranslation").Set(Gf.Vec3d(.4, -.2, .05))
        root.AddRotateZOp(opSuffix="testRotation").Set(37)
        moved = Model.from_usd(stage, "/Robot")
        original = Usd.Stage.Open(str(ASSET))
        authored_root = np.asarray(UsdGeom.XformCache().GetLocalToWorldTransform(
            original.GetDefaultPrim())).T
        wrapper = (np.asarray(UsdGeom.XformCache().GetLocalToWorldTransform(root.GetPrim())).T @
                   np.linalg.inv(authored_root))
        np.testing.assert_allclose(moved.fk(INITIAL_Q), wrapper @ self.model.fk(INITIAL_Q), atol=1e-12)
        measured = moved.body_poses(INITIAL_Q)
        measured[moved.gripper_path][:3, 3] += [.003, 0, 0]
        self.assertAlmostEqual(moved.compare_body_poses(INITIAL_Q, measured)[moved.gripper_path]
                               ["position_error_m"], .003)
        with self.assertRaises(KeyError):
            moved.compare_body_poses(INITIAL_Q, {})
        measured[moved.gripper_path][:3, :3] *= 2
        with self.assertRaises(ValueError):
            moved.compare_body_poses(INITIAL_Q, measured)

    def test_rejects_nonzero_authored_pose_and_wrong_units(self):
        stage = Usd.Stage.Open(Sdf.Layer.FindOrOpen(str(ASSET)), Sdf.Layer.CreateAnonymous())
        stage.SetEditTarget(stage.GetSessionLayer())
        root = stage.GetDefaultPrim().GetPath()
        joint = stage.GetPrimAtPath(root.AppendPath("joints/Elbow"))
        joint.GetAttribute("physics:localPos0").Set(Gf.Vec3f(0, 0, 0))
        with self.assertRaisesRegex(ValueError, "authored zero"):
            Model.from_usd(stage)
        UsdGeom.SetStageMetersPerUnit(stage, .01)
        with self.assertRaisesRegex(ValueError, "meters"):
            Model.from_usd(stage)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--evidence", action="store_true")
    args, unittest_args = parser.parse_known_args()
    ASSET = args.asset.resolve(strict=True)
    if args.evidence:
        print(json.dumps(offline_evidence(Model.from_usd(ASSET), ASSET), indent=2))
    unittest.main(argv=[__file__, *unittest_args])
