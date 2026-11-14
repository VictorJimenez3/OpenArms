import copy

import pytest

from bench_vision.geometry import GeometryError, fit_calibration, localize


def spec():
    def point(i, x, y):
        return {"id": i, "pixel": [x * 2 + 10, y * 2 + 20], "xy_mm": [x, y]}
    return {"calibration_id": "cal-1", "camera_id": "overview", "camera_mount_id": "fixed-1",
            "plane_id": "table", "clock_id": "episode-1", "measurement_ref": "synthetic-known-transform",
            "provenance": "synthetic", "pixel_space": "undistorted", "intrinsics_id": "synthetic-pinhole",
            "valid_from_s": 0, "valid_until_s": 100, "max_error_mm": 2, "plane_height_mm": 0,
            "fit_points": [point("f1",0,0), point("f2",100,0), point("f3",100,100), point("f4",0,100)],
            "check_points": [point("c1",20,20), point("c2",80,20), point("c3",50,80)],
            "workspace_mm": [[5,5],[95,5],[95,95],[5,95]]}


def observation():
    s = spec()
    return {**{k:s[k] for k in ("calibration_id","camera_id","camera_mount_id","plane_id","clock_id","intrinsics_id","pixel_space")},
            "object_id": "source-cup", "timestamp_s": 50, "status": "ok", "feature": "table_contact",
            "feature_height_mm": 0, "pixel": [110,120], "uncertainty_px": 1,
            "anchors": [{"id":p["id"],"pixel":p["pixel"]} for p in s["check_points"]]}


def test_fit_independent_checks_and_localize():
    cal = fit_calibration(spec())
    assert cal["validation"]["check_max_mm"] < 1e-8
    result = localize(cal, observation(), now_s=50.1)
    assert result["status"] == "ok"
    assert result["xy_mm"] == pytest.approx([50,50])
    assert result["grasp_pose"] is None
    assert result["uncertainty_mm"] == pytest.approx(.5)
    assert result["provenance"] == "synthetic"


@pytest.mark.parametrize("key,value", [
    ("timestamp_s",49), ("timestamp_s",51), ("camera_mount_id","moved"), ("calibration_id","old"),
    ("feature","cup_rim"), ("feature_height_mm",70), ("pixel",[500,500]),
    ("pixel",[float("nan"),120]), ("uncertainty_px",20), ("uncertainty_px",-1),
    ("anchors",[]), ("status","unknown"), ("clock_id","other-host"), ("pixel_space","distorted"),
])
def test_unknown_on_invalid_observation(key,value):
    obs = observation()
    obs[key] = value
    result = localize(fit_calibration(spec()),obs,now_s=50.1)
    assert result["status"] == "unknown" and result["xy_mm"] is None and result["reason"]


def test_camera_movement_even_if_id_unchanged():
    obs = observation()
    for anchor in obs["anchors"]:
        anchor["pixel"][0] += 30
    assert "movement" in localize(fit_calibration(spec()),obs,now_s=50.1)["reason"]


def test_calibration_tampering_and_expiry():
    cal = fit_calibration(spec())
    changed = copy.deepcopy(cal)
    changed["homography"][0][2] += 1
    assert localize(changed,observation(),now_s=50)["status"] == "unknown"
    obs = observation()
    obs["timestamp_s"] = 101
    assert "expired" in localize(cal,obs,now_s=101)["reason"]


@pytest.mark.parametrize("change", ["reuse_id","reuse_point","collinear","bad_check","extrapolate","bowtie","distorted","nan","zero_tolerance"])
def test_reject_invalid_calibration(change):
    s = spec()
    if change == "reuse_id": s["check_points"][0]["id"] = "f1"
    if change == "reuse_point": s["check_points"][0]["pixel"] = s["fit_points"][0]["pixel"]
    if change == "collinear":
        for p in s["fit_points"]: p["pixel"][1] = 0
    if change == "bad_check": s["check_points"][0]["xy_mm"][0] += 10
    if change == "extrapolate": s["workspace_mm"][0] = [-1,-1]
    if change == "bowtie": s["workspace_mm"] = [[5,5],[95,95],[95,5],[5,95]]
    if change == "distorted": s["pixel_space"] = "distorted"
    if change == "nan": s["valid_until_s"] = float("nan")
    if change == "zero_tolerance": s["max_error_mm"] = 0
    with pytest.raises(GeometryError): fit_calibration(s)
