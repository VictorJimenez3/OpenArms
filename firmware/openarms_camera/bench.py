"""Reads the bench from one picture: two red rulers taped in an L are the axes.

    python -m firmware.openarms_camera locate --photo outputs/camera/live_demo_2.jpg
    python -m firmware.openarms_camera locate --camera 0 --apply

What it does:
  1. Finds the two red 30 cm rulers and, from their outlines, the mapping from picture
     pixels to bench centimetres. Origin: the inner corner of the L. X along the ruler that
     runs across the picture, Y along the one that runs down it.
  2. Saves a flattened, true top-down picture with a centimetre grid
     (outputs/camera/bench_flat.jpg). Positions can be read straight off it.
  3. Looks for the round container and the beaker as circles of their known sizes, and
     reports the centre of each in ruler centimetres.
  4. With --apply, writes those positions into the simulation's demo bench, re-solves the
     arm poses and runs the pour preview.

Limits, measured on the two bench photos of 2026-11-14:
  - Ruler mapping: within 0.5 cm of hand measurement near the rulers on those photos. On drawn
    test scenes it is within 0.4 cm near the rulers and about 1.2 cm at 25 cm from both under a
    strong tilt. A photo from straight above is best.
  - Only things lying ON the table are placed correctly. Anything raised (a container's
    rim, the arm) appears pushed outward, by up to several centimetres.
  - The containers are clear plastic. The round container was found within 1 cm in both
    photos. The beaker was 1 cm out in one and 3.5 cm out in the other, where only its raised
    rim was visible.
    Always look at bench_flat.jpg, and give --beaker X,Y or --dish X,Y to correct a miss.
  - The rulers must be roughly square to the picture (within about 10 degrees) and fully
    in view.
"""
from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RULER_LENGTH, RULER_WIDTH = 30.9, 3.1  # cm: the red "caliber bendable ruler" body
BUTT_X, BUTT_Y = 0.1, -0.2  # cm: how the rulers' ends sit relative to the corner in the taped L
PX_PER_CM = 20.0  # scale of the flattened picture
MARGIN_CM = 5.0  # table shown beyond the origin on the ruler side
EXTENT_CM = (40.0, 50.0)  # flattened picture covers X -5..35, Y -5..45
# Known pieces, from the bench photos: radius of the base and of the rim, cm.
PIECES = {"dish": {"base": 3.0, "rim": 4.2}, "beaker": {"base": 1.6, "rim": 2.25}}


def _red(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    return (cv2.inRange(hsv, np.array([0, 110, 80]), np.array([8, 255, 255]))
            | cv2.inRange(hsv, np.array([170, 110, 80]), np.array([180, 255, 255])))


def find_rulers(image: np.ndarray) -> dict:
    """The outline (four corners, pixels) of the ruler along X and of the ruler along Y."""
    size = max(image.shape[:2])
    k = max(15, int(0.006 * size)) | 1
    red = cv2.morphologyEx(_red(image), cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    span = int(0.12 * size)
    out = {}
    for name, kernel in (("x", np.ones((1, span), np.uint8)), ("y", np.ones((span, 1), np.uint8))):
        mask = cv2.morphologyEx(red, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            raise ValueError("could not find both red rulers; they must be fully in view and roughly square to the picture")
        # Where the two rulers touch, a few rows of one run on into the other and would stretch its
        # outline by the other's width. Opening with a small block (15 percent of the ruler width) removes that sliver without
        # cutting the ruler where something lies across it.
        width = min(cv2.minAreaRect(max(contours, key=cv2.contourArea))[1])
        block = max(3, int(width * 0.15))
        contours, _ = cv2.findContours(cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((block, block), np.uint8)),
                                       cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            raise ValueError("could not find both red rulers; they must be fully in view and roughly square to the picture")
        box = cv2.boxPoints(cv2.minAreaRect(max(contours, key=cv2.contourArea)))
        long_side, short_side = sorted([np.linalg.norm(box[0] - box[1]), np.linalg.norm(box[1] - box[2])], reverse=True)
        if short_side < 1 or not 5 < long_side / short_side < 16:
            raise ValueError("found something red that is not shaped like the 30 cm ruler")
        out[name] = box
    return out


def _ordered(box):
    """Corners as top-left, top-right, bottom-right, bottom-left."""
    box = np.asarray(box, np.float32)
    total, difference = box.sum(axis=1), box[:, 0] - box[:, 1]
    return np.array([box[np.argmin(total)], box[np.argmax(difference)], box[np.argmax(total)], box[np.argmin(difference)]])


def ruler_mapping(image: np.ndarray) -> tuple[np.ndarray, float]:
    """(H, fit error in cm). H maps picture pixels to ruler centimetres on the table plane."""
    rulers = find_rulers(image)
    x, y = _ordered(rulers["x"]), _ordered(rulers["y"])
    if x[:, 1].mean() > y[:, 1].mean() or y[:, 0].mean() > x[:, 0].mean():
        raise ValueError("expected the L with one ruler across the top and the other down the left of the picture")
    pixels = np.array([*x, *y], np.float32)
    L, W, a, b = RULER_LENGTH, RULER_WIDTH, BUTT_X, BUTT_Y
    cm = np.array([[a, -W], [a + L, -W], [a + L, 0], [a, 0], [-W, b], [0, b], [0, b + L], [-W, b + L]], np.float32)
    H, _ = cv2.findHomography(pixels, cm, 0)
    if H is None:
        raise ValueError("the ruler outlines do not give a usable mapping")
    error = float(np.abs(cv2.perspectiveTransform(pixels[None], H)[0] - cm).max())
    return H, error


def to_cm(H: np.ndarray, pixel_points) -> np.ndarray:
    return cv2.perspectiveTransform(np.array(pixel_points, np.float32)[None], H)[0]


def flatten(image: np.ndarray, H: np.ndarray) -> np.ndarray:
    """A true top-down picture of the table: PX_PER_CM pixels per centimetre, origin MARGIN_CM in."""
    s, m = PX_PER_CM, MARGIN_CM * PX_PER_CM
    T = np.array([[s, 0, m], [0, s, m], [0, 0, 1]])
    return cv2.warpPerspective(image, T @ H, (int(EXTENT_CM[0] * s), int(EXTENT_CM[1] * s)))


def flat_px(cm_point) -> tuple[int, int]:
    return int(round((cm_point[0] + MARGIN_CM) * PX_PER_CM)), int(round((cm_point[1] + MARGIN_CM) * PX_PER_CM))


def find_pieces(flat: np.ndarray, arm_cm=None, keep_clear_cm: float = 14.0) -> dict:
    """{'dish': {...}, 'beaker': {...}}: centre in ruler cm, the circle found, and how it was found.

    Looks in the flattened picture with the rulers and large bright things (the arm, paper)
    blanked out, and ignores anything within `keep_clear_cm` of the arm's base."""
    hsv, gray = cv2.cvtColor(flat, cv2.COLOR_BGR2HSV), cv2.cvtColor(flat, cv2.COLOR_BGR2GRAY)
    bright = cv2.morphologyEx(cv2.inRange(hsv, np.array([0, 0, 170]), np.array([180, 70, 255])), cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(bright)
    large = np.zeros_like(bright)
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] > (3 * PX_PER_CM) ** 2:
            large[labels == i] = 255
    block = cv2.dilate(_red(flat) | large, np.ones((25, 25), np.uint8))
    if not (block == 0).any():
        return {}
    work = gray.copy()
    work[block > 0] = int(np.median(gray[block == 0]))
    work = cv2.GaussianBlur(work, (7, 7), 0)

    def circles(r_min_cm, r_max_cm):
        for votes in (40, 34, 28, 24, 20):
            found = cv2.HoughCircles(work, cv2.HOUGH_GRADIENT, dp=1.5, minDist=25, param1=60, param2=votes,
                                     minRadius=int(r_min_cm * PX_PER_CM), maxRadius=int(r_max_cm * PX_PER_CM))
            if found is None:
                continue
            out = []
            for x, y, r in found[0]:
                cx, cy = x / PX_PER_CM - MARGIN_CM, y / PX_PER_CM - MARGIN_CM
                inside = 0 <= int(y) < block.shape[0] and 0 <= int(x) < block.shape[1]
                if not inside or block[int(y), int(x)] or cx < 0 or cy < 0:
                    continue
                if arm_cm is not None and np.hypot(cx - arm_cm[0], cy - arm_cm[1]) < keep_clear_cm:
                    continue
                out.append((float(cx), float(cy), float(r / PX_PER_CM)))
            if out:
                return out
        return []

    def describe(name, c):
        spec = PIECES[name]
        which = "base" if abs(c[2] - spec["base"]) <= abs(c[2] - spec["rim"]) else "rim"
        return {"cm": (round(c[0], 1), round(c[1], 1)), "radius_cm": round(c[2], 2), "found": which,
                "note": "" if which == "base" else "this is the raised rim, so the true position is probably 1 to 3 cm closer to the camera's centre"}

    result = {}
    dish = circles(2.6, 4.9)
    if dish:
        # The base lies on the table and is the true position; prefer it when it was found near the strongest circle.
        strongest = dish[0]
        base = next((c for c in dish if abs(c[2] - PIECES["dish"]["base"]) < 0.35 and np.hypot(c[0] - strongest[0], c[1] - strongest[1]) < 3.0), None)
        result["dish"] = describe("dish", base or strongest)
    d = result.get("dish")
    for c in circles(1.2, 2.7):
        if d and np.hypot(c[0] - d["cm"][0], c[1] - d["cm"][1]) < PIECES["dish"]["rim"] + 1.5:
            continue  # the dish's own base and reflections
        result["beaker"] = describe("beaker", c)
        break
    return result


def draw(flat: np.ndarray, pieces: dict | None = None, arm_cm=None) -> np.ndarray:
    """The flattened picture with a 5 cm grid, the detections and the arm's base marked."""
    out = flat.copy()
    for c in range(0, int(EXTENT_CM[0] - MARGIN_CM) + 1, 5):
        x = flat_px((c, 0))[0]
        cv2.line(out, (x, 60), (x, out.shape[0] - 1), (255, 255, 0), 1)
        cv2.putText(out, str(c), (x + 3, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
    for c in range(0, int(EXTENT_CM[1] - MARGIN_CM) + 1, 5):
        y = flat_px((0, c))[1]
        cv2.line(out, (60, y), (out.shape[1] - 1, y), (255, 255, 0), 1)
        cv2.putText(out, str(c), (62, y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
    for name, colour in (("dish", (0, 255, 0)), ("beaker", (0, 200, 255))):
        p = (pieces or {}).get(name)
        if p:
            cv2.circle(out, flat_px(p["cm"]), int(p["radius_cm"] * PX_PER_CM), colour, 2)
            cv2.putText(out, f"{name} {p['cm'][0]}, {p['cm'][1]}", (flat_px(p["cm"])[0] + 8, flat_px(p["cm"])[1]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, colour, 2)
    if arm_cm is not None:
        cv2.drawMarker(out, flat_px(arm_cm), (255, 0, 255), cv2.MARKER_CROSS, 30, 2)
        cv2.putText(out, "arm base", (flat_px(arm_cm)[0] + 10, flat_px(arm_cm)[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 0, 255), 2)
    return out


BENCH_FILE = ROOT / "simulation/config/setups/demo/bench.yaml"
STATION = {"beaker": "A", "dish": "C"}


def read_bench(path: Path = BENCH_FILE) -> dict:
    text = path.read_text()
    arm = re.search(r"^\s*arm_cm:\s*\[([^\]]+)\]", text, re.M)
    out = {"arm_cm": tuple(float(v) for v in arm[1].split(",")) if arm else None}
    for piece, station in STATION.items():
        m = re.search(rf"^\s*{station}:\s*\{{[^}}]*ruler:\s*\[([^\]]+)\]", text, re.M)
        out[piece] = tuple(float(v) for v in m[1].split(",")) if m else None
    return out


def write_bench(positions: dict, path: Path = BENCH_FILE) -> None:
    """Updates the `ruler: [x, y]` of the beaker (A) and the dish (C), leaving everything else as it is."""
    text = path.read_text()
    for piece, station in STATION.items():
        if piece not in positions:
            continue
        x, y = positions[piece]
        text, n = re.subn(rf"(^\s*{station}:\s*\{{[^}}]*ruler:\s*\[)[^\]]+(\])", rf"\g<1>{x:.1f}, {y:.1f}\g<2>", text, count=1, flags=re.M)
        if n != 1:
            raise ValueError(f"could not find station {station}'s ruler position in {path}")
    path.write_text(text)
