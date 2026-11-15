"""Render the six stills and the measured ruler-plane illustration."""
import json
from pathlib import Path

import cv2
import numpy as np


RESEARCH = Path(__file__).resolve().parent.parent
SOURCE = RESEARCH / "outputs" / "supervised-aerial-run-02"
OUTPUT = RESEARCH / "outputs" / "reproduced"
(OUTPUT / "evidence").mkdir(parents=True, exist_ok=True)
RENDER = OUTPUT / "aerial-video-frames"
RENDER.mkdir(exist_ok=True)
WIDTH, HEIGHT = 1920, 1080
WHITE, MUTED, CYAN = (245, 245, 237), (185, 190, 190), (240, 231, 134)


def text(frame, message, xy, size, color=WHITE, weight=2):
    cv2.putText(frame, message, xy, cv2.FONT_HERSHEY_SIMPLEX, size, color, weight, cv2.LINE_AA)


def slide(title, subtitle, image, footer):
    frame = np.full((HEIGHT, WIDTH, 3), (22, 25, 28), dtype=np.uint8)
    text(frame, title, (73, 60), 1.2, weight=3)
    text(frame, subtitle, (75, 104), .72, MUTED)
    ih, iw = image.shape[:2]
    ratio = min(1768 / iw, 841 / ih)
    scaled = cv2.resize(image, (round(iw * ratio), round(ih * ratio)), interpolation=cv2.INTER_AREA)
    h, w = scaled.shape[:2]
    x, y = (WIDTH - w) // 2, 119 + (841 - h) // 2
    frame[y:y + h, x:x + w] = scaled
    text(frame, footer, (75, 1020), .7, WHITE)
    return frame


def labeled_plane(localization):
    mosaic = cv2.imread(str(SOURCE / "fresh-overhead-review.png"))
    visible = cv2.imread(str(SOURCE / "fresh-overhead-review.png"), cv2.IMREAD_UNCHANGED)[:, :, 3]
    pixels_per_cm = 47
    x_lo, x_hi, y_lo, y_hi = -2, 30, -1, 16
    display = np.array([[pixels_per_cm, 0, -x_lo * pixels_per_cm],
                        [0, pixels_per_cm, -y_lo * pixels_per_cm], [0, 0, 1]], dtype=float)
    homography = display @ np.asarray(localization["mosaic_preview_to_ruler_cm"])
    size = ((x_hi - x_lo) * pixels_per_cm, (y_hi - y_lo) * pixels_per_cm)
    plane = cv2.warpPerspective(mosaic, homography, size)
    valid = cv2.warpPerspective(visible, homography, size) > 128
    plane[~valid] = (36, 38, 42)
    grid = plane.copy()
    origin = (int(-x_lo * pixels_per_cm), int(-y_lo * pixels_per_cm))
    for cm in range(0, x_hi, 2):
        x = origin[0] + cm * pixels_per_cm
        cv2.line(grid, (x, origin[1]), (x, size[1] - 1), WHITE, 1, cv2.LINE_AA)
        text(plane, str(cm), (x + 5, origin[1] - 9), .48, (20, 20, 20), 3)
        text(plane, str(cm), (x + 5, origin[1] - 9), .48, WHITE, 1)
    for cm in range(0, y_hi, 2):
        y = origin[1] + cm * pixels_per_cm
        cv2.line(grid, (origin[0], y), (size[0] - 1, y), WHITE, 1, cv2.LINE_AA)
        text(plane, str(cm), (origin[0] - 33, y + 7), .48, (20, 20, 20), 3)
        text(plane, str(cm), (origin[0] - 33, y + 7), .48, WHITE, 1)
    plane = cv2.addWeighted(plane, .70, grid, .30, 0)
    cv2.arrowedLine(plane, origin, (size[0] - 20, origin[1]), CYAN, 2, tipLength=.02)
    cv2.arrowedLine(plane, origin, (origin[0], size[1] - 20), CYAN, 2, tipLength=.04)
    text(plane, "X", (size[0] - 47, origin[1] + 33), .7, CYAN)
    text(plane, "Y", (origin[0] - 33, size[1] - 26), .7, CYAN)
    for label, vessel in localization["vessels"].items():
        x, y = vessel["estimated_center_ruler_cm"]
        dot = (round(origin[0] + x * pixels_per_cm), round(origin[1] + y * pixels_per_cm))
        cv2.drawMarker(plane, dot, (20, 20, 20), cv2.MARKER_CROSS, 25, 6)
        cv2.drawMarker(plane, dot, CYAN, cv2.MARKER_CROSS, 25, 3)
        caption = f"{label}  ({x:.1f}, {y:.1f}) cm"
        tag = (dot[0] + 15, dot[1] + 50)
        text(plane, caption, tag, .72, (20, 20, 20), 5)
        text(plane, caption, tag, .72, CYAN)
    return plane


localization = json.loads((OUTPUT / "evidence/supervised-aerial-vessel-locations.json").read_text())
rows = [json.loads(line) for line in (SOURCE / "review-decisions.jsonl").read_text().splitlines()]
captures = [row for row in rows if row["event"] == "captured"]
assert [row["recorded_view"] for row in captures] == [735, 725, 716, 708, 698, 617]
start = captures[0]["host_monotonic_s"]
cards = []
for index, row in enumerate(captures, 1):
    elapsed = row["host_monotonic_s"] - start
    image = cv2.imread(str(SOURCE / row["image"]))
    subtitle = f"Saved view {index} of {len(captures)}   /   waypoint {row['recorded_view']}   /   capture +{elapsed:.2f} s"
    cards.append((slide("OpenArms wrist scan", subtitle, image,
                        "Sequential still images from the supervised scan. Playback is condensed."), 1.3))
cards.append((slide("Six registered wrist views", "Reciprocal feature alignment to the center view",
                    cv2.imread(str(OUTPUT / "aerial-vessel-locations.png")),
                    "A = donor beaker. C = receiver bowl. Coordinates belong to the tabletop rulers."), 4))
cards.append((slide("Ruler-plane vessel locations", "Approximate vessel-base centers in tabletop centimeters",
                    labeled_plane(localization),
                    "Origin: ruler junction. Robot-base registration and motion qualification remain pending."), 6))

listing = []
for index, (frame, duration) in enumerate(cards, 1):
    filename = f"card-{index:02d}.png"
    assert cv2.imwrite(str(RENDER / filename), frame)
    listing.extend([f"file {filename}", f"duration {duration}"])
listing.append(f"file {filename}")
(RENDER / "list.ffconcat").write_text("\n".join(listing) + "\n")
