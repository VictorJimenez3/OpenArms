"""Read ruler ticks and visible vessel bases from the fresh sweep."""
from hashlib import sha256
import json
from pathlib import Path

import cv2
import numpy as np


RESEARCH = Path(__file__).resolve().parent.parent
SOURCE = RESEARCH / "outputs" / "supervised-aerial-run-02"
OUTPUT = RESEARCH / "outputs" / "reproduced"
(OUTPUT / "evidence").mkdir(parents=True, exist_ok=True)



def marked_crop_to_preview(coords, origin):
    return (np.asarray(coords, dtype=np.float64) / 1.75 + origin).tolist()


def project(points, matrix):
    return cv2.perspectiveTransform(np.asarray([points], dtype=np.float64), matrix)[0]


def asset_hash(path):
    return sha256(path.read_bytes()).hexdigest()


# Manual readings at major tick marks on the inner ruler edges, in enlarged
# crops of the 1400 px mosaic. Along X the metric ruler runs from 30 down.
x_pixels = marked_crop_to_preview(
    [(62, 356), (228, 317), (389, 279), (548, 242), (706, 205), (864, 167)],
    (350, 145),
)
y_pixels = marked_crop_to_preview(
    [(192, 37), (193, 131), (195, 236), (196, 345), (197, 459), (197, 582), (194, 717)],
    (275, 330),
)
x_inches = [(distance, 0) for distance in (0, 4, 8, 12, 16, 20)]
y_inches = [(0, inches * 2.54) for inches in range(7)]
points, values = np.asarray(x_pixels + y_pixels), np.asarray(x_inches + y_inches)
check_indices = [2, 4, 8, 10]
fit_indices = [i for i in range(len(points)) if i not in check_indices]
plane, _ = cv2.findHomography(points[fit_indices], values[fit_indices], 0)
errors = np.linalg.norm(project(points, plane) - values, axis=1)
assert max(errors[check_indices]) < 1.0, errors

raw_mosaic = SOURCE / "fresh-overhead.png"
preview_mosaic = SOURCE / "fresh-overhead-review.png"
mosaic = cv2.imread(str(raw_mosaic))
preview = cv2.imread(str(preview_mosaic))
scale = np.asarray([preview.shape[1] / mosaic.shape[1], preview.shape[0] / mosaic.shape[0]])
registration = json.loads((SOURCE / "fresh-registration.json").read_text())
inputs = {int(name.split("-")[3]): SOURCE / name for name in registration["inputs"]}

# Approximate bottom-center cues, clicked on two separate 1000 px-wide views
# for each cup. The outer raised rim is excluded from the ruler-plane mapping.
vessel_cues = {
    "A": {"name": "donor beaker", "cues": [(716, (710, 181)), (725, (593, 178))]},
    "C": {"name": "receiver bowl", "cues": [(617, (448, 418)), (698, (312, 201))]},
}
vessels = {}
for label, item in vessel_cues.items():
    observations = []
    for view, clicked_px in item["cues"]:
        frame = cv2.imread(str(inputs[view]))
        full_px = np.asarray(clicked_px) * (frame.shape[1] / 1000)
        mosaic_px = project([full_px], np.asarray(registration["image_to_mosaic"][str(view)]))[0] * scale
        estimate_cm = project([mosaic_px], plane)[0]
        observations.append({"view_id": view, "frame_sha256": asset_hash(inputs[view]),
                             "base_center_cue_frame_px": full_px.tolist(),
                             "base_center_cue_mosaic_px": mosaic_px.tolist(),
                             "ruler_cm": estimate_cm.tolist()})
    positions = np.asarray([o["ruler_cm"] for o in observations])
    estimate = positions.mean(axis=0)
    dot = np.rint(project([estimate], np.linalg.inv(plane))[0]).astype(int)
    vessels[label] = {"name": item["name"], "estimated_center_ruler_cm": estimate.tolist(),
                      "cross_view_spread_cm": float(np.linalg.norm(positions[0] - positions[1])),
                      "observations": observations}
    cv2.drawMarker(preview, tuple(dot), (240, 240, 170), cv2.MARKER_CROSS, 25, 3)
    caption = f"{label}  ({estimate[0]:.1f}, {estimate[1]:.1f}) cm"
    text_origin = (int(dot[0] + 16), int(dot[1] + 48))
    cv2.putText(preview, caption, text_origin, cv2.FONT_HERSHEY_SIMPLEX, .75, (22, 22, 22), 4, cv2.LINE_AA)
    cv2.putText(preview, caption, text_origin, cv2.FONT_HERSHEY_SIMPLEX, .75, (240, 240, 170), 2, cv2.LINE_AA)

origin = tuple(np.rint(project([[0, 0]], np.linalg.inv(plane))[0]).astype(int))
cv2.drawMarker(preview, origin, (240, 240, 170), cv2.MARKER_CROSS, 19, 2)
cv2.putText(preview, "Ruler origin", (origin[0] - 151, origin[1] + 34),
            cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 255, 255), 2, cv2.LINE_AA)
assert cv2.imwrite(str(OUTPUT / "aerial-vessel-locations.png"), preview)
result = {
    "run": SOURCE.name,
    "frame": "ruler plane in cm; X along upper ruler to the right, Y along left ruler down",
    "provenance": "fresh supervised aerial scan, reciprocal image registration, manual tick and base-center readings",
    "quality_scope": "Ruler-relative estimates. Check ticks assess the ruler fit only. Cross-view spread is not independent vessel-position accuracy.",
    "limitations": "Visual base cues can have refraction, seam, parallax, and reading bias. Robot-base transform, measured camera/cup geometry, certified localization error and clearance are unavailable.",
    "ruler_check_errors_cm": errors[check_indices].tolist(),
    "mosaic_preview_to_ruler_cm": plane.tolist(),
    "all_ticks": [{"mosaic_px": point.tolist(), "ruler_cm": value.tolist(),
                   "role": "check" if i in check_indices else "fit"}
                  for i, (point, value) in enumerate(zip(points, values))],
    "vessels": vessels,
    "input_frame_sha256": {p.name: asset_hash(p) for p in inputs.values()},
    "robot_base_target": None,
    "motion_status": "blocked",
}
(OUTPUT / "evidence" / "supervised-aerial-vessel-locations.json").write_text(
    json.dumps(result, indent=2) + "\n"
)
for label, vessel in vessels.items():
    print(label, vessel["estimated_center_ruler_cm"], "cross-view spread cm", vessel["cross_view_spread_cm"])
print("Maximum held-out ruler-tick error cm:", float(max(errors[check_indices])))
