"""Measured fixed-camera plane mapping. A tabletop point is not a cup grasp pose.

Original implementation using OpenCV findHomography/perspectiveTransform.
See https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from numbers import Real
from pathlib import Path

import cv2
import numpy as np


class GeometryError(ValueError):
    pass


def number(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not math.isfinite(value):
        raise GeometryError(f"{name} must be finite")
    return float(value)


def points(value, name, minimum=1):
    try:
        if len(value) < minimum or any(len(p) != 2 for p in value):
            raise GeometryError(f"{name} needs {minimum} two-dimensional points")
        return np.array([[number(x, name), number(y, name)] for x, y in value], dtype=np.float64)
    except (TypeError, KeyError) as exc:
        raise GeometryError(f"invalid {name}") from exc


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def project(matrix, pixels):
    p = points(pixels, "pixels")
    h = np.asarray(matrix, dtype=float)
    if h.shape != (3, 3) or not np.isfinite(h).all():
        raise GeometryError("invalid homography")
    homogeneous = np.column_stack((p, np.ones(len(p)))) @ h.T
    if np.any(np.abs(homogeneous[:, 2]) < 1e-9):
        raise GeometryError("point projects to infinity")
    return homogeneous[:, :2] / homogeneous[:, 2, None]


def _convex_polygon(raw):
    polygon = points(raw, "workspace_mm", 3)
    hull = cv2.convexHull(polygon.astype(np.float32)).reshape(-1, 2)
    if len(hull) != len(polygon) or abs(cv2.contourArea(hull)) < 1e-6:
        raise GeometryError("workspace must be a nondegenerate convex polygon")
    # Require a boundary ordering, not a self-intersecting list of convex vertices.
    if not cv2.isContourConvex(polygon.astype(np.float32)):
        raise GeometryError("workspace vertices must follow the boundary")
    return polygon


def fit_calibration(spec):
    """Fit on measured plane points; require disjoint held-out checks.

    Input evidence provenance is retained, not certified by this computation.
    Synthetic geometry can exercise software but cannot qualify physical mapping.
    """
    required = ("calibration_id", "camera_id", "camera_mount_id", "plane_id", "clock_id", "measurement_ref")
    for key in required:
        if not isinstance(spec.get(key), str) or not spec[key].strip():
            raise GeometryError(f"missing {key}")
    if spec.get("provenance") not in ("physical_measurement", "synthetic"):
        raise GeometryError("provenance must be physical_measurement or synthetic")
    if spec.get("pixel_space") != "undistorted":
        raise GeometryError("use undistorted image points and the same camera intrinsics at inference")
    if not isinstance(spec.get("intrinsics_id"), str) or not spec["intrinsics_id"]:
        raise GeometryError("missing intrinsics_id")
    start = number(spec.get("valid_from_s"), "valid_from_s")
    end = number(spec.get("valid_until_s"), "valid_until_s")
    if end <= start:
        raise GeometryError("invalid calibration validity interval")
    threshold = number(spec.get("max_error_mm"), "max_error_mm")
    if threshold <= 0:
        raise GeometryError("max_error_mm must be positive")
    number(spec.get("plane_height_mm"), "plane_height_mm")
    fit, checks = spec.get("fit_points", []), spec.get("check_points", [])
    try:
        fit_px = points([p["pixel"] for p in fit], "fit pixels", 4)
        fit_xy = points([p["xy_mm"] for p in fit], "fit metric points", 4)
        check_px = points([p["pixel"] for p in checks], "check pixels", 3)
        check_xy = points([p["xy_mm"] for p in checks], "check metric points", 3)
        ids = [p["id"] for p in fit + checks]
    except (KeyError, TypeError) as exc:
        raise GeometryError("each measured point needs id, pixel, xy_mm") from exc
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise GeometryError("fit and check IDs must be unique and disjoint")
    for array in (fit_px, fit_xy, check_px, check_xy):
        if len(np.unique(array, axis=0)) != len(array) or np.linalg.matrix_rank(array-array.mean(axis=0)) < 2:
            raise GeometryError("points must be distinct and span a plane")
    for left, right in ((fit_px, check_px), (fit_xy, check_xy)):
        if any(np.linalg.norm(a-b) < 1e-6 for a in left for b in right):
            raise GeometryError("held-out checks cannot reuse fitted coordinates")
    matrix, _ = cv2.findHomography(fit_px, fit_xy, method=0)
    if matrix is None or not np.isfinite(matrix).all() or abs(np.linalg.det(matrix)) < 1e-12:
        raise GeometryError("degenerate homography")
    residuals = np.linalg.norm(project(matrix, check_px)-check_xy, axis=1)
    fit_errors = np.linalg.norm(project(matrix, fit_px)-fit_xy, axis=1)
    if max(residuals.max(), fit_errors.max()) > threshold:
        raise GeometryError("calibration residual exceeds declared tolerance")
    polygon = _convex_polygon(spec.get("workspace_mm", []))
    # Do not extrapolate outside the measured fit support.
    support = cv2.convexHull(fit_xy.astype(np.float32))
    if any(cv2.pointPolygonTest(support, tuple(map(float, p)), False) < 0 for p in polygon):
        raise GeometryError("workspace exceeds measured fit support")
    artifact = dict(spec)
    artifact.update(schema_version=1, homography=matrix.tolist(), validation={
        "check_count": len(checks), "check_rmse_mm": float(np.sqrt(np.mean(residuals**2))),
        "check_max_mm": float(residuals.max()), "fit_max_mm": float(fit_errors.max()),
        "physical_qualification": "operator_measurements_not_independently_verified" if spec["provenance"] == "physical_measurement" else "not_physical",
    })
    artifact["content_hash"] = digest(artifact)
    return artifact


def localize(calibration, observation, *, now_s, max_age_s=0.25):
    """Return explicit unknown for stale, moved-camera, elevated or unsupported points."""
    result = {"status": "unknown", "object_id": observation.get("object_id"),
              "camera_id": observation.get("camera_id"), "timestamp_s": observation.get("timestamp_s"),
              "calibration_id": calibration.get("calibration_id"), "xy_mm": None,
              "provenance": "synthetic" if calibration.get("provenance") == "synthetic" else observation.get("provenance", "unknown"),
              "calibration_provenance": calibration.get("provenance"), "reason": None}
    try:
        payload = {k: v for k, v in calibration.items() if k != "content_hash"}
        if digest(payload) != calibration.get("content_hash"):
            raise GeometryError("calibration content changed")
        now = number(now_s, "now_s")
        age = now-number(observation.get("timestamp_s"), "timestamp_s")
        if not 0 <= age <= number(max_age_s, "max_age_s"):
            raise GeometryError("stale or future observation")
        if not calibration["valid_from_s"] <= now <= calibration["valid_until_s"]:
            raise GeometryError("expired calibration")
        for key in ("calibration_id", "camera_id", "camera_mount_id", "plane_id", "clock_id", "intrinsics_id", "pixel_space"):
            if observation.get(key) != calibration[key]:
                raise GeometryError(f"{key} mismatch")
        if observation.get("status") != "ok" or observation.get("feature") != "table_contact":
            raise GeometryError("need a visible table-contact feature, not a box center or cup rim")
        height = number(observation.get("feature_height_mm"), "feature_height_mm")
        if abs(height-calibration["plane_height_mm"]) > 1e-6:
            raise GeometryError("feature is not on the calibrated plane")
        # Every localization includes >=3 visible independently measured anchors.
        anchors = observation.get("anchors", [])
        known = {p["id"]: p["xy_mm"] for p in calibration["check_points"]}
        if len(anchors) < 3 or len({a["id"] for a in anchors}) != len(anchors):
            raise GeometryError("need three distinct current check anchors to detect camera movement")
        if any(a["id"] not in known for a in anchors):
            raise GeometryError("unknown check anchor")
        anchor_px = points([a["pixel"] for a in anchors], "current anchor pixels", 3)
        if np.linalg.matrix_rank(anchor_px-anchor_px.mean(axis=0)) < 2:
            raise GeometryError("current anchors are collinear")
        drift = np.linalg.norm(project(calibration["homography"], anchor_px)-np.array([known[a["id"]] for a in anchors]), axis=1)
        if drift.max() > calibration["max_error_mm"]:
            raise GeometryError("camera/anchor movement exceeds validated residual")
        pixel = points([observation.get("pixel")], "feature pixel")[0]
        xy = project(calibration["homography"], [pixel])[0]
        uncertainty_px = number(observation.get("uncertainty_px"), "uncertainty_px")
        if uncertainty_px < 0:
            raise GeometryError("negative pixel uncertainty")
        probes = [pixel+[dx,dy] for dx,dy in ((uncertainty_px,0),(-uncertainty_px,0),(0,uncertainty_px),(0,-uncertainty_px))]
        uncertainty = float(np.linalg.norm(project(calibration["homography"], probes)-xy, axis=1).max()+calibration["validation"]["check_max_mm"]+drift.max())
        polygon = _convex_polygon(calibration["workspace_mm"])
        clearance = cv2.pointPolygonTest(polygon.astype(np.float32), tuple(map(float, xy)), True)
        if clearance < uncertainty:
            raise GeometryError("target or its uncertainty extends outside validated workspace")
        if uncertainty > calibration["max_error_mm"]:
            raise GeometryError("localization uncertainty exceeds tolerance")
        result.update(status="ok", xy_mm=xy.tolist(), uncertainty_mm=uncertainty,
                      camera_mount_id=calibration["camera_mount_id"], feature="table_contact",
                      coordinate_frame=calibration["plane_id"], clock_id=calibration["clock_id"], units="mm",
                      grasp_pose=None, controller_validation_required=True)
    except (GeometryError, KeyError, TypeError, ValueError, IndexError) as exc:
        result["reason"] = str(exc)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fit = sub.add_parser("fit")
    fit.add_argument("spec", type=Path)
    fit.add_argument("--out", required=True, type=Path)
    locate = sub.add_parser("localize")
    locate.add_argument("calibration", type=Path)
    locate.add_argument("observation", type=Path)
    locate.add_argument("--now", required=True, type=float)
    args = parser.parse_args()
    if args.command == "fit":
        value = fit_calibration(json.loads(args.spec.read_text()))
        with args.out.open("x") as output:
            json.dump(value, output, indent=2, allow_nan=False)
    else:
        value = localize(json.loads(args.calibration.read_text()), json.loads(args.observation.read_text()), now_s=args.now)
        print(json.dumps(value, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
