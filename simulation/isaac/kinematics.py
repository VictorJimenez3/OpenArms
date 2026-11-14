"""Offline SO-101 USD kinematics, in meters and radians; no simulator required.

Column-vector transforms: T_world_child = T_world_parent @ J0 @ R(q) @ inv(J1).
fk returns a nominal grasp frame (gripper axes, collider-derived translation).
body_poses returns rigid-body frames for the mandatory runtime cross-check.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pxr import Gf, Usd, UsdGeom, UsdPhysics
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation


JOINT_NAMES = ("Rotation", "Pitch", "Elbow", "Wrist_Pitch", "Wrist_Roll", "Jaw")
WORKSHOP_COMMIT = "ce807d99724cb65671abec01f908a2fcb4a6eab7"


def _vector(value, size, name):
    result = np.asarray(value, dtype=float)
    if result.shape != (size,) or not np.isfinite(result).all():
        raise ValueError(f"{name} must contain {size} finite values")
    return result


def _rigid(value):
    """USD uses row vectors; all public matrices here use column vectors."""
    result = np.asarray(value, dtype=float).T.copy()
    r = result[:3, :3]
    if not (np.isfinite(result).all() and
            np.allclose(r.T @ r, np.eye(3), atol=1e-6) and
            np.isclose(np.linalg.det(r), 1, atol=1e-6)):
        raise ValueError("Scaled/reflected/nonrigid body or joint frame is unsupported")
    return result


def _joint_frame(joint, side):
    quaternion = Gf.Quatd(getattr(joint, f"GetLocalRot{side}Attr")().Get())
    matrix = Gf.Matrix4d().SetRotate(quaternion.GetNormalized())
    matrix.SetTranslateOnly(Gf.Vec3d(getattr(joint, f"GetLocalPos{side}Attr")().Get()))
    return _rigid(matrix)


def _rotation_error(a, b):
    return float(Rotation.from_matrix(a[:3, :3].T @ b[:3, :3]).magnitude())


@dataclass(frozen=True)
class Joint:
    name: str
    parent: str
    child: str
    local0: np.ndarray
    inverse_local1: np.ndarray
    axis: np.ndarray


@dataclass(frozen=True)
class IKReport:
    success: bool
    position_error_m: float
    direction_error_rad: float
    position_residual_m: tuple
    direction_residual: tuple
    evaluations: int
    optimizer_success: bool
    message: str


class Model:
    """A fixed-base, serial, six-joint SO-101 model extracted from authored USD.

    Inputs/outputs follow JOINT_NAMES, including Jaw. IK varies only the first
    five joints and preserves seed[5]. It constrains position and local -Z tool
    direction, leaving rotation about that direction free. No collision checks.
    """

    joint_names = JOINT_NAMES
    tool_axis_local = np.array([0., 0., -1.])

    @classmethod
    def from_usd(cls, path, prim_path=None):
        """Read an asset path or Usd.Stage in its *authored zero configuration*.

        prim_path optionally selects a referenced robot inside a composed stage.
        Base pose includes all authored ancestor transforms. Units must be m/Z-up.
        Refuse zero-frame discrepancies >10 um or >10 urad rather than silently
        fitting offsets/signs. This is not validation of nonzero runtime signs.
        """
        stage = path if isinstance(path, Usd.Stage) else Usd.Stage.Open(str(Path(path)))
        if stage is None:
            raise ValueError("Could not open USD")
        if (UsdGeom.GetStageMetersPerUnit(stage) != 1 or
                UsdGeom.GetStageUpAxis(stage) != UsdGeom.Tokens.z):
            raise ValueError("Expected meters and Z-up")
        root = stage.GetPrimAtPath(prim_path) if prim_path else stage.GetDefaultPrim()
        if not root:
            raise ValueError("Missing robot root/default prim")
        prims = list(Usd.PrimRange(root, Usd.TraverseInstanceProxies()))
        revolute = [p for p in prims if p.IsA(UsdPhysics.RevoluteJoint)]
        if sorted(p.GetName() for p in revolute) != sorted(JOINT_NAMES):
            raise ValueError("Expected exactly the six SO-101 joints")
        by_name = {p.GetName(): p for p in revolute}
        model = cls()
        model.joints = []
        lower, upper = [], []
        for name in JOINT_NAMES:
            joint = UsdPhysics.RevoluteJoint(by_name[name])
            if not joint.GetJointEnabledAttr().Get():
                raise ValueError(f"Disabled joint: {name}")
            parents, children = joint.GetBody0Rel().GetTargets(), joint.GetBody1Rel().GetTargets()
            if len(parents) != 1 or len(children) != 1:
                raise ValueError(f"Expected two body targets: {name}")
            parent, child = str(parents[0]), str(children[0])
            for body in (parent, child):
                if not stage.GetPrimAtPath(body).HasAPI(UsdPhysics.RigidBodyAPI):
                    raise ValueError(f"Not a rigid body: {body}")
            if model.joints and parent != model.joints[-1].child:
                raise ValueError("Expected a serial chain in JOINT_NAMES order")
            axis_name = joint.GetAxisAttr().Get()
            if axis_name not in ("X", "Y", "Z"):
                raise ValueError(f"Invalid joint axis: {axis_name}")
            model.joints.append(Joint(name, parent, child, _joint_frame(joint, 0),
                                      np.linalg.inv(_joint_frame(joint, 1)),
                                      np.eye(3)[("X", "Y", "Z").index(axis_name)]))
            lower.append(joint.GetLowerLimitAttr().Get())
            upper.append(joint.GetUpperLimitAttr().Get())
        model.lower = np.deg2rad(lower)
        model.upper = np.deg2rad(upper)
        if not (np.isfinite([model.lower, model.upper]).all() and
                np.all(model.lower < model.upper) and
                np.all(model.lower <= 0) and np.all(model.upper >= 0)):
            raise ValueError("Expected finite SO-101 limits containing zero")
        model.base_path = model.joints[0].parent
        anchors = [UsdPhysics.FixedJoint(p) for p in prims if p.IsA(UsdPhysics.FixedJoint)
                   and list(UsdPhysics.FixedJoint(p).GetBody1Rel().GetTargets()) ==
                   [stage.GetPrimAtPath(model.base_path).GetPath()]]
        if (len(anchors) != 1 or anchors[0].GetBody0Rel().GetTargets() or
                not anchors[0].GetJointEnabledAttr().Get()):
            raise ValueError("Expected base fixed to world")
        cache = UsdGeom.XformCache()
        paths = [model.base_path] + [j.child for j in model.joints]
        model.authored_body_poses = {
            p: _rigid(cache.GetLocalToWorldTransform(stage.GetPrimAtPath(p))) for p in paths}
        model.base_transform = model.authored_body_poses[model.base_path].copy()
        model.zero_errors = model.compare_body_poses(np.zeros(6), model.authored_body_poses)
        if any(e["position_error_m"] > 1e-5 or e["rotation_error_rad"] > 1e-5
               for e in model.zero_errors.values()):
            raise ValueError(f"USD joint frames disagree with authored zero poses: {model.zero_errors}")
        model.gripper_path = model.joints[4].child
        model.jaw_path = model.joints[5].child
        model.tool_transform, model.geometry_evidence = model._grasp_offset(stage, cache)
        return model

    def _grasp_offset(self, stage, cache):
        """SO-101 heuristic: midpoint between opposing distal collider slabs.

        Geometry at nominal Jaw=0, last 10 mm along gripper -Z, offset rounded
        to 1 mm. This is an uncertain planning point, not a calibrated contact TCP.
        """
        inverse_gripper = np.linalg.inv(self.authored_body_poses[self.gripper_path])
        bounds, meshes = [], []
        for body in (self.gripper_path, self.jaw_path):
            points = []
            for prim in Usd.PrimRange(stage.GetPrimAtPath(body), Usd.TraverseInstanceProxies()):
                if not prim.IsA(UsdGeom.Mesh):
                    continue
                ancestor = prim
                collision = False
                while ancestor and str(ancestor.GetPath()) != body:
                    collision |= ancestor.HasAPI(UsdPhysics.CollisionAPI)
                    ancestor = ancestor.GetParent()
                if not collision:
                    continue
                values = np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(), dtype=float)
                if values.ndim != 2 or values.shape[1] != 3 or not np.isfinite(values).all():
                    raise ValueError(f"Invalid collider vertices: {prim.GetPath()}")
                # Geometry may be scaled even though rigid-body frames cannot be.
                transform = inverse_gripper @ np.asarray(cache.GetLocalToWorldTransform(prim)).T
                points.append(values @ transform[:3, :3].T + transform[:3, 3])
                meshes.append(str(prim.GetPath()))
            if not points:
                raise ValueError(f"Missing collider meshes on {body}")
            points = np.concatenate(points)
            slab = points[points[:, 2] <= points[:, 2].min() + .010]
            bounds.append(np.array([slab.min(axis=0), slab.max(axis=0)]))
        fixed, moving = bounds
        overlap_low = np.maximum(fixed[0, 1:], moving[0, 1:])
        overlap_high = np.minimum(fixed[1, 1:], moving[1, 1:])
        if fixed[1, 0] >= moving[0, 0] or np.any(overlap_low >= overlap_high):
            raise ValueError("Distal colliders do not form the expected opposing SO-101 fingers")
        offset = np.r_[(fixed[1, 0] + moving[0, 0]) / 2, (overlap_low + overlap_high) / 2]
        transform = np.eye(4)
        transform[:3, 3] = np.round(offset, 3)
        return transform, {"collider_meshes": meshes,
                           "distal_bounds_gripper_m": np.array(bounds).tolist(),
                           "nominal_jaw_zero_inner_gap_m": float(moving[0, 0] - fixed[1, 0]),
                           "offset_gripper_m": transform[:3, 3].tolist(),
                           "method": "10 mm distal slabs, midpoint, rounded to 1 mm; uncertain; Jaw=0"}

    def _q(self, q):
        q = _vector(q, 6, "q")
        if np.any(q < self.lower) or np.any(q > self.upper):
            raise ValueError("q outside authored joint limits (radians)")
        return q

    def body_poses(self, q):
        q = self._q(q)
        poses = {self.base_path: self.base_transform.copy()}
        for joint, angle in zip(self.joints, q):
            turn = np.eye(4)
            turn[:3, :3] = Rotation.from_rotvec(joint.axis * angle).as_matrix()
            poses[joint.child] = poses[joint.parent] @ joint.local0 @ turn @ joint.inverse_local1
        return poses

    def fk(self, q):
        """4x4 world nominal grasp frame; axes equal the gripper body's axes."""
        return self.body_poses(q)[self.gripper_path] @ self.tool_transform

    def compare_body_poses(self, q, measured):
        """Per-body errors against column-vector world poses, keyed by USD path.

        Requires *all* body poses. Call on runtime measurements at zero AND
        nonzero configurations, with runtime joint positions in JOINT_NAMES order.
        """
        result = {}
        for path, predicted in self.body_poses(q).items():
            actual = np.asarray(measured[path], dtype=float)
            if (actual.shape != (4, 4) or not np.isfinite(actual).all() or
                    not np.allclose(actual[3], [0, 0, 0, 1], atol=1e-8) or
                    not np.allclose(actual[:3, :3].T @ actual[:3, :3], np.eye(3), atol=1e-6) or
                    not np.isclose(np.linalg.det(actual[:3, :3]), 1, atol=1e-6)):
                raise ValueError(f"Invalid measured rigid transform: {path}")
            result[path] = {"position_error_m": float(np.linalg.norm(predicted[:3, 3] - actual[:3, 3])),
                            "rotation_error_rad": _rotation_error(predicted, actual)}
        return result

    def solve(self, target_xyz, tool_axis_world, seed, *, position_tolerance_m=.001,
              direction_tolerance_rad=.02, max_nfev=300):
        """Return (q, report); q is None when the local bounded solve is rejected.

        Targets refer to fk's nominal grasp center and gripper local -Z. Direction
        uses three unit-vector residuals (two independent constraints); its weight
        is 0.1 m. A weak 10 um/rad seed prior resolves redundant directions.
        A prior seed selects the local solution, without global search
        or path guarantees. An unreachable report may also be a local-solver miss.
        """
        target = _vector(target_xyz, 3, "target_xyz")
        direction = _vector(tool_axis_world, 3, "tool_axis_world")
        norm = np.linalg.norm(direction)
        if not np.isfinite(norm) or norm < 1e-12:
            raise ValueError("tool_axis_world must be nonzero")
        direction = direction / norm
        seed = self._q(seed).copy()
        if (not np.isfinite([position_tolerance_m, direction_tolerance_rad]).all() or
                position_tolerance_m <= 0 or not 0 < direction_tolerance_rad < np.pi or
                not isinstance(max_nfev, int) or max_nfev < 1):
            raise ValueError("Expected positive finite tolerances and positive integer max_nfev")

        def errors(arm):
            pose = self.fk(np.r_[arm, seed[5]])
            return pose[:3, 3] - target, pose[:3, :3] @ self.tool_axis_local - direction

        def residual(arm):
            position, axis = errors(arm)
            return np.r_[position, .1 * axis, 1e-5 * (arm - seed[:5])]

        solution = least_squares(residual, seed[:5], bounds=(self.lower[:5], self.upper[:5]),
                                 max_nfev=max_nfev, ftol=1e-11, xtol=1e-11, gtol=1e-11)
        q = np.r_[solution.x, seed[5]]
        position, axis = errors(solution.x)
        position_error = float(np.linalg.norm(position))
        # Norm of unit-vector difference is stable near zero and pi.
        angle_error = float(2 * np.arcsin(np.clip(np.linalg.norm(axis) / 2, 0, 1)))
        success = bool(solution.success and np.isfinite(q).all() and
                       np.all(q >= self.lower) and np.all(q <= self.upper) and
                       position_error <= position_tolerance_m and angle_error <= direction_tolerance_rad)
        report = IKReport(success, position_error, angle_error, tuple(position), tuple(axis),
                          solution.nfev, bool(solution.success),
                          "accepted (kinematics only)" if success else
                          "rejected: local solver failed or target residual exceeds tolerance")
        return (q if success else None), report
