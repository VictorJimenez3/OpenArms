"""Render and read the provisional A/C bench from its MuJoCo overview camera."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
import uuid
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import label

from .chemistry import load_model
from .config import load_bench, load_chemistry_config, load_joint_map, load_poses
from .joints import JointMap
from .player import Player
from .preview import example_plan, preview
from .render import OVERVIEW_HEIGHT, OVERVIEW_WIDTH, overview_image
from .scene import build_scene

SCENE_ID = "two_vessel_docks"
SCENE_VERSION = 1
CAMERA_ID = "two_vessel_overview"
CONFIGURATION_ID = "two_vessel_overview.v1"
CALIBRATION_ID = "two_vessel_nominal_pixels.v1"
WIDTH, HEIGHT = OVERVIEW_WIDTH, OVERVIEW_HEIGHT
VARIANTS = ("nominal", "camera_shift", "missing", "swapped", "occluded")
LIMITATIONS = [
    "Pixel localization in the rendered overview, with color-coded rim and tabletop fiducials.",
    "Provisional fixture dimensions and camera reference. No measured grasp pose or physical calibration.",
]


def capture(path, *, variant="nominal", contents=None, generation=0, timestamp_s=None):
    """Write fresh raw RGB evidence. The scenario perturbation is kept out of the image record."""
    if variant not in VARIANTS:
        raise ValueError(f"Unknown two-vessel overview variant {variant!r}.")
    bench = load_bench("liquid")
    scene = build_scene(bench, view_variant=variant)
    jm = JointMap(load_joint_map())
    chemistry = load_chemistry_config()
    player = Player(scene, jm, chemistry, load_model(chemistry), contents=contents)
    if variant == "missing":
        player.pos["A"][2] = -1.0
    if variant == "swapped":
        player.pos["A"][:2], player.pos["C"][:2] = player.pos["C"][:2].copy(), player.pos["A"][:2].copy()
    player._apply(np.array(jm.pose_to_model(load_poses("liquid")["HOME"])), jm.gripper_open_value)
    path = Path(path).resolve()
    overview_image(scene, path, shifted=variant == "camera_shift")
    return _frame_record(path, generation, timestamp_s)


def _frame_record(path, generation, timestamp_s):
    evidence_id = uuid.uuid4().hex
    captured_at = time.time() if timestamp_s is None else timestamp_s
    return {
        "evidence_id": evidence_id,
        "frame_id": evidence_id,
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "camera_id": CAMERA_ID,
        "configuration_id": CONFIGURATION_ID,
        "calibration_id": CALIBRATION_ID,
        "captured_at": captured_at,
        "clock": "unix_seconds",
        "coordinate_frame": "overview_image",
        "units": "px",
        "generation": generation,
        "provenance": "SIMULATED",
    }


def _pixels(frame):
    path = frame["path"] if isinstance(frame, dict) else frame
    raw = Path(path).read_bytes()
    if isinstance(frame, dict) and hashlib.sha256(raw).hexdigest() != frame.get("sha256"):
        raise ValueError("Overview content hash changed.")
    with Image.open(io.BytesIO(raw)) as image:
        if image.size != (WIDTH, HEIGHT):
            raise ValueError("Overview dimensions differ from camera registration.")
        return np.asarray(image.convert("RGB"), dtype=int)


def _centroid(mask, *, minimum, largest=False):
    if largest:
        labels, _ = label(mask)
        count = np.bincount(labels.ravel())
        count[0] = 0
        mask = labels == count.argmax() if count.any() else mask
    y, x = np.nonzero(mask)
    if len(x) < minimum:
        return None
    return np.array([x.mean(), y.mean()])


def _fiducials(pixels):
    r, g, b = pixels.transpose(2, 0, 1)
    return {
        "f1": _centroid((r > 100) & (r - g > 65) & (r - b > 65), minimum=50, largest=True),
        "f2": _centroid((g > 100) & (g - r > 65) & (g - b > 65), minimum=50, largest=True),
        "f3": _centroid((b > 100) & (b - r > 65) & (b - g > 65), minimum=50, largest=True),
        "f4": _centroid((r > 100) & (g > 95) & (r - b > 65) & (g - b > 65), minimum=50, largest=True),
    }


def _rims(pixels):
    r, g, b = pixels.transpose(2, 0, 1)
    return {
        "donor": _centroid((r > 120) & (b > 105) & (r - g > 70) & (b - g > 70), minimum=90),
        "receiver": _centroid((g > 120) & (b > 120) & (g - r > 70) & (b - r > 70), minimum=130),
    }


def _receiver_liquid(pixels, rim):
    """Read only the calibrated water fixture's visible interior appearance."""
    x, y = np.rint(rim).astype(int)
    interior = pixels[y - 5:y + 15, x - 10:x + 10]
    r, g, b = interior.transpose(2, 0, 1)
    water = (r > 155) & (g > 195) & (b > 220) & (g - r > 22)
    base = (r < 105) & (g < 120) & (b < 145)
    state = "water_appearance" if water.mean() >= 0.85 else "dark_base_visible" if base.mean() >= 0.85 else "unknown"
    return {"state": state, "provenance": "SIMULATED", "method": "registered-receiver-interior-v1"}


def observe(frame, reference, *, now_s=None, generation=None, max_age_s=5.0):
    """Read the image against a trusted nominal registration. Pixels supply all detections."""
    result = {
        "status": "unknown", "ready": False, "provenance": "SIMULATED", "coordinate_frame": "overview_image",
        "units": "px", "method": "color-fiducials-and-rims-v1", "limitations": LIMITATIONS,
        "camera_registration": "unknown", "stations": {}, "receiver_appearance": {"state": "unknown"},
    }
    try:
        if isinstance(frame, dict):
            result["evidence_id"] = frame["evidence_id"]
            if (frame.get("camera_id"), frame.get("configuration_id"), frame.get("calibration_id"), frame.get("clock")) != (
                CAMERA_ID, CONFIGURATION_ID, CALIBRATION_ID, "unix_seconds"
            ):
                raise ValueError("Overview metadata does not match the camera reference.")
            if generation is not None and frame.get("generation") != generation:
                raise ValueError("Overview belongs to a previous setup generation.")
            if now_s is not None and not 0 <= now_s - frame["captured_at"] <= max_age_s:
                raise ValueError("Overview is stale or future-dated.")
        elif generation is not None or now_s is not None:
            raise ValueError("Overview lacks capture generation or timestamp metadata.")
        nominal = _pixels(reference)
        pixels = _pixels(frame)
        fixed, current = _fiducials(nominal), _fiducials(pixels)
        if any(value is None for value in (*fixed.values(), *current.values())):
            raise ValueError("One or more camera check fiducials are unreadable.")
        drift = {key: round(float(np.linalg.norm(current[key] - centre)), 2) for key, centre in fixed.items()}
        result["fiducial_drift_px"] = drift
        if max(drift.values()) > load_bench("liquid").camera.registration_tolerance_px:
            result["camera_registration"] = "shifted"
            raise ValueError("Camera registration shifted outside the overview tolerance.")
        result["camera_registration"] = "registered"
        expected, observed = _rims(nominal), _rims(pixels)
        if any(value is None for value in expected.values()):
            raise ValueError("The nominal registration does not locate both vessel rims.")
        stations = {"A": "donor", "C": "receiver"}
        for station, name in stations.items():
            # Compare against the other slot too. A vessel in the opposite dock has a
            # different radius and can have a different projected rim height.
            own = observed[name]
            other_name = "receiver" if name == "donor" else "donor"
            other = observed[other_name]
            if own is not None and np.linalg.norm(own - expected[name]) <= 9:
                result["stations"][station] = {"status": "identified", "vessel": name,
                                                "pixel": own.round(2).tolist()}
            elif other is not None and np.linalg.norm(other - expected[name]) <= 34:
                result["stations"][station] = {"status": "unexpected_vessel", "vessel": other_name,
                                                "pixel": other.round(2).tolist()}
            else:
                result["stations"][station] = {"status": "unreadable", "vessel": None, "pixel": None}
        if not all(station["status"] == "identified" for station in result["stations"].values()):
            raise ValueError("Both vessels must be readable and in their registered docks.")
        result["receiver_appearance"] = _receiver_liquid(pixels, observed["receiver"])
        result.update(status="ok", ready=True, reason=None)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        result["reason"] = str(exc)
    return result


def evidence(output_dir: Path):
    """Generate a fresh reproducible fixture suite and a nominal rendered pour."""
    output_dir.mkdir(parents=True, exist_ok=True)
    generation, now_s = 1, 100.0  # frozen replay clock, independent of wall time
    frames = {variant: capture(output_dir / f"{variant}.png", variant=variant, generation=generation,
                               timestamp_s=now_s) for variant in VARIANTS}
    reference = frames["nominal"]
    cases = {variant: observe(frame, reference, now_s=now_s, generation=generation)
             for variant, frame in frames.items()}
    cases["stale"] = observe(reference, reference, now_s=now_s + 6, generation=generation)
    cases["previous_generation"] = observe(reference, reference, now_s=now_s, generation=generation + 1)
    reset = capture(output_dir / "reset.png", generation=generation + 1, timestamp_s=now_s + 7)
    cases["reset"] = observe(reset, reference, now_s=now_s + 7, generation=generation + 1)
    after_path = output_dir / "after.png"
    motion = preview(example_plan("A", "C", setup="liquid"), setup="liquid", video_path=output_dir / "a-to-c.mp4",
                     overview_path=after_path)
    after = _frame_record(after_path, generation, now_s + motion["motion_seconds"])
    cases["after"] = observe(after, reference, now_s=after["captured_at"], generation=generation)
    return {"scene_id": SCENE_ID, "scene_version": SCENE_VERSION,
            "cases": cases, "frames": {**frames, "reset": reset, "after": after}, "motion": motion,
            "evaluation_only": {"expected_ready": ["nominal", "reset", "after"],
                                "expected_unknown": ["camera_shift", "missing", "swapped", "occluded",
                                                     "stale", "previous_generation"]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output-dir", type=Path)
    mode.add_argument("--pour-preview", action="store_true")
    args = parser.parse_args()
    if args.pour_preview:
        print(json.dumps(preview(example_plan(setup="liquid"), setup="liquid")))
        return
    output_dir = args.output_dir
    receipt = evidence(output_dir)
    (output_dir / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    expected = receipt["evaluation_only"]["expected_ready"]
    actual = [name for name, value in receipt["cases"].items() if value["ready"]]
    appearances = [receipt["cases"][case]["receiver_appearance"]["state"] for case in ("nominal", "after", "reset")]
    if (actual != expected or not receipt["motion"]["ok"]
            or appearances != ["dark_base_visible", "water_appearance", "dark_base_visible"]):
        raise SystemExit("Two-vessel evidence did not match the frozen expectations. Check receipt.json.")
    print(output_dir / "receipt.json")


if __name__ == "__main__":
    main()
