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


def _red(image, hue=8, saturation=110):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    return (cv2.inRange(hsv, np.array([0, saturation, 80]), np.array([hue, 255, 255]))
            | cv2.inRange(hsv, np.array([170, saturation, 80]), np.array([180, 255, 255])))


def _redder_than_around(image):
    """Pixels clearly redder than the table around them (Lab a*, minus its local median). Under warm light the whole
    table reads red by hue, but the rulers are still much redder than what surrounds them."""
    a = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)[:, :, 1]
    h, w = a.shape
    step = max(1, max(h, w) // 240)
    small = cv2.resize(a, (w // step, h // step), interpolation=cv2.INTER_AREA)
    around = cv2.resize(cv2.medianBlur(small, (max(small.shape) // 8) | 1), (w, h), interpolation=cv2.INTER_LINEAR)
    redder = cv2.subtract(a, around)
    t, _ = cv2.threshold(redder, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return ((redder > max(t, 10)) * 255).astype(np.uint8)


# Ways of picking out the red rulers: the usual red; a wider red, for rulers overexposed under bright light to
# orange-red; and red compared with its surroundings, for a warm cast that makes the whole table read red.
RED_VIEWS = (lambda im: _red(im, 8, 110), lambda im: _red(im, 10, 90), _redder_than_around)


def find_rulers(image: np.ndarray) -> dict:
    """The outline (four corners, pixels) of the ruler along X and of the ruler along Y, from the first red view
    that shows two ruler shapes."""
    failed = None
    for view in RED_VIEWS:
        try:
            return _find_rulers(image, view(image))
        except ValueError as exc:
            failed = failed or exc
    raise failed


def _find_rulers(image: np.ndarray, red_mask: np.ndarray) -> dict:
    size = max(image.shape[:2])
    k = max(15, int(0.006 * size)) | 1
    red = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
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
        # The biggest red thing may be something else (a red-lit wall, a red object), so the biggest one shaped like
        # the ruler is taken.
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:6]:
            box = cv2.boxPoints(cv2.minAreaRect(contour))
            long_side, short_side = sorted([np.linalg.norm(box[0] - box[1]), np.linalg.norm(box[1] - box[2])], reverse=True)
            if short_side >= 1 and 5 < long_side / short_side < 16 and long_side >= span:
                out[name] = box
                break
        else:
            raise ValueError("found something red that is not shaped like the 30 cm ruler")
    return out


def _find_l_any_angle(image: np.ndarray, red_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The two rulers wherever they lie, each along its own direction (they need not look square to each other
    in a slanted picture). Returns the X and Y ruler corners in the order _mapping_from uses:
    X: corner end outer, far end outer, far end inner, corner end inner; Y: corner end outer, corner end inner,
    far end inner, far end outer ("inner" is the side facing the inside of the L)."""
    size = max(image.shape[:2])
    k = max(15, int(0.006 * size)) | 1
    red = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    span = int(0.12 * size)
    edges = cv2.Canny(red, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 360, 60, minLineLength=span, maxLineGap=k)
    if lines is None:
        raise ValueError("could not find both red rulers")
    lengths = np.hypot(lines[:, 0, 2] - lines[:, 0, 0], lines[:, 0, 3] - lines[:, 0, 1])
    angles = np.degrees(np.arctan2(lines[:, 0, 3] - lines[:, 0, 1], lines[:, 0, 2] - lines[:, 0, 0])) % 180
    hist, _ = np.histogram(angles, bins=180, range=(0, 180), weights=lengths)
    hist = np.convolve(np.r_[hist[-3:], hist, hist[:3]], np.ones(7), "valid")  # wraps around 0/180
    first = int(np.argmax(hist))
    apart = np.array([min(abs(a - first), 180 - abs(a - first)) for a in range(180)])
    second = int(np.argmax(np.where(apart >= 40, hist, -1)))
    boxes = []
    for theta in (first + 0.5, second + 0.5):
        kernel = np.zeros((span | 1, span | 1), np.uint8)
        c, r = span // 2, span // 2
        dx, dy = r * np.cos(np.radians(theta)), r * np.sin(np.radians(theta))
        cv2.line(kernel, (int(round(c - dx)), int(round(c - dy))), (int(round(c + dx)), int(round(c + dy))), 1, 1)
        mask = cv2.morphologyEx(red, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        found = None
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:6]:
            (cx, cy), (w, h), _ = cv2.minAreaRect(contour)
            long_side, short_side = max(w, h), min(w, h)
            if short_side >= 1 and 5 < long_side / short_side < 16 and long_side >= span:
                found = cv2.boxPoints(cv2.minAreaRect(contour))
                break
        if found is None:
            raise ValueError("found something red that is not shaped like the 30 cm ruler")
        boxes.append(found)

    def ends(box):
        """The two short-side midpoints, and the long direction."""
        sides = [(box[i], box[(i + 1) % 4]) for i in range(4)]
        short = sorted(sides, key=lambda e: np.linalg.norm(e[0] - e[1]))[:2]
        return [(a + b) / 2 for a, b in short]
    (a0, a1), (b0, b1) = ends(boxes[0]), ends(boxes[1])
    pairs = [(np.linalg.norm(p - q), i, j) for i, p in enumerate((a0, a1)) for j, q in enumerate((b0, b1))]
    gap, i, j = min(pairs)
    width = min(np.linalg.norm(boxes[0][0] - boxes[0][1]), np.linalg.norm(boxes[0][1] - boxes[0][2]))
    if gap > 3 * width:
        raise ValueError("the two red rulers do not meet in an L")
    near_a, far_a = ((a0, a1) if i == 0 else (a1, a0))
    near_b, far_b = ((b0, b1) if j == 0 else (b1, b0))
    da, db = far_a - near_a, far_b - near_b
    # Picture coordinates have y down, so "Y a quarter turn clockwise from X, seen from above" is a positive cross product.
    if da[0] * db[1] - da[1] * db[0] > 0:
        xbox, ybox, dx_, dy_, nx, ny = boxes[0], boxes[1], da, db, near_a, near_b
    else:
        xbox, ybox, dx_, dy_, nx, ny = boxes[1], boxes[0], db, da, near_b, near_a

    def corners(box, along, across, near):
        """Corners as (near outer, far outer, far inner, near inner)."""
        u = along / np.linalg.norm(along)
        v = across / np.linalg.norm(across)
        t = [(float((c - near) @ u), float((c - near) @ v), c) for c in box]
        near2 = sorted(t, key=lambda e: e[0])[:2]
        far2 = sorted(t, key=lambda e: e[0])[2:]
        no, ni = sorted(near2, key=lambda e: e[1])
        fo, fi = sorted(far2, key=lambda e: e[1])
        return no[2], fo[2], fi[2], ni[2]
    xo, xfo, xfi, xi = corners(xbox, dx_, dy_, nx)   # X ruler's inner side faces along Y
    yo, yfo, yfi, yi = corners(ybox, dy_, dx_, ny)   # Y ruler's inner side faces along X
    return np.array([xo, xfo, xfi, xi], np.float32), np.array([yo, yi, yfi, yfo], np.float32)


def _ordered(box):
    """Corners as top-left, top-right, bottom-right, bottom-left."""
    box = np.asarray(box, np.float32)
    total, difference = box.sum(axis=1), box[:, 0] - box[:, 1]
    return np.array([box[np.argmin(total)], box[np.argmax(difference)], box[np.argmax(total)], box[np.argmin(difference)]])


LOOSEST_CM = 2.0  # a ruler fit looser than this is a wrong reading, not a rough one, and is refused


def ruler_mapping(image: np.ndarray) -> tuple[np.ndarray, float]:
    """(H, fit error in cm). H maps picture pixels to ruler centimetres on the table plane.

    The rulers may lie at any angle in the picture. If they are not the usual way up (one across the top, one
    down the left), the picture is turned until they are, the mapping is found there and turned back."""
    GOOD_CM = 1.0  # a fit this tight is taken at once; otherwise every turn is tried and the tightest kept
    best, first = None, None
    try:
        best = _ruler_mapping(image)
        if best[1] <= GOOD_CM:
            return best
    except ValueError as exc:
        first = exc
    # The rulers along their own directions: for a turned camera, and for a slanted one where they do not look square.
    for view in RED_VIEWS:
        try:
            found = _mapping_from_corners(*_find_l_any_angle(image, view(image)))
        except ValueError as exc:
            first = first or exc
            continue
        if best is None or found[1] < best[1]:
            best = found
    if best is not None and best[1] <= GOOD_CM:
        return best
    h, w = image.shape[:2]
    for angle in _candidate_angles(image):
        R = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        cos, sin = abs(R[0, 0]), abs(R[0, 1])
        size = (int(h * sin + w * cos), int(h * cos + w * sin))  # big enough that nothing is cut off
        R[0, 2] += size[0] / 2 - w / 2
        R[1, 2] += size[1] / 2 - h / 2
        try:
            H, error = _ruler_mapping(cv2.warpAffine(image, R, size))
        except ValueError:
            continue
        if best is None or error < best[1]:
            best = (H @ np.vstack([R, [0, 0, 1]]), error)
        if error <= GOOD_CM:
            break
    if best is None:
        raise first
    if best[1] > LOOSEST_CM:
        raise ValueError(f"the red shapes found do not fit the two rulers (off by {best[1]:.1f} cm); they may be partly out of view")
    return best


def _candidate_angles(image: np.ndarray) -> list[float]:
    """Turns (degrees) that may bring the rulers square to the picture, best guesses first."""
    red = cv2.morphologyEx(_red(image) | _red(image, 10, 90), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    lines = cv2.HoughLinesP(red, 1, np.pi / 360, 80, minLineLength=max(image.shape[:2]) // 8, maxLineGap=10)
    guesses = []
    if lines is not None:
        # The ruler edges are long straight lines; their direction, folded into 0..90 degrees, says how far it is turned.
        lengths = np.hypot(lines[:, 0, 2] - lines[:, 0, 0], lines[:, 0, 3] - lines[:, 0, 1])
        angles = np.degrees(np.arctan2(lines[:, 0, 3] - lines[:, 0, 1], lines[:, 0, 2] - lines[:, 0, 0])) % 90
        hist, edges = np.histogram(angles, bins=90, range=(0, 90), weights=lengths)
        guesses.append(float(edges[int(np.argmax(hist))]) + 0.5)
    out = []
    for base in guesses + [0.0]:
        for quarter in (0, 90, 180, 270):
            for nudge in (0, -4, 4):
                a = (base + quarter + nudge) % 360
                if all(abs(a - b) > 1 for b in out):
                    out.append(a)
    return out


def _ruler_mapping(image: np.ndarray) -> tuple[np.ndarray, float]:
    """The tightest mapping any red view gives, with the picture as it is."""
    best, failed = None, None
    for view in RED_VIEWS:
        try:
            found = _mapping_from(_find_rulers(image, view(image)))
        except ValueError as exc:
            failed = failed or exc
            continue
        if best is None or found[1] < best[1]:
            best = found
        if best[1] <= 1.0:  # the first view that fits well is kept, so a picture that read before reads the same
            break
    if best is None:
        raise failed
    return best


def _mapping_from(rulers: dict) -> tuple[np.ndarray, float]:
    x, y = _ordered(rulers["x"]), _ordered(rulers["y"])
    if x[:, 1].mean() > y[:, 1].mean() or y[:, 0].mean() > x[:, 0].mean():
        raise ValueError("expected the L with one ruler across the top and the other down the left of the picture")
    return _mapping_from_corners(x, y)


def _mapping_from_corners(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    pixels = np.array([*x, *y], np.float32)
    L, W, a, b = RULER_LENGTH, RULER_WIDTH, BUTT_X, BUTT_Y
    cm = np.array([[a, -W], [a + L, -W], [a + L, 0], [a, 0], [-W, b], [0, b], [0, b + L], [-W, b + L]], np.float32)
    H, _ = cv2.findHomography(pixels, cm, 0)
    if H is None:
        raise ValueError("the ruler outlines do not give a usable mapping")
    error = float(np.abs(cv2.perspectiveTransform(pixels[None], H)[0] - cm).max())
    return H, error


def carry_mapping(reference: np.ndarray, reference_H: np.ndarray, image: np.ndarray) -> tuple[np.ndarray, int, float]:
    """The ruler mapping of an earlier picture, carried over to this one: (H, matched points, camera shift in pixels).

    For a picture whose rulers cannot be read (a hand or the arm over them, glare). The two pictures are lined up
    by features on the table and the rulers' printing (ORB, RANSAC); if the camera has not moved this is nearly the
    identity. Raises ValueError when they cannot be lined up."""
    def gray(im):
        g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        scale = 960 / max(g.shape)
        return cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA), scale
    g1, s1 = gray(image)
    g0, s0 = gray(reference)
    orb = cv2.ORB_create(4000)
    k1, d1 = orb.detectAndCompute(g1, None)
    k0, d0 = orb.detectAndCompute(g0, None)
    if d1 is None or d0 is None:
        raise ValueError("no features to line the pictures up by")
    matches = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(d1, d0, k=2)
    good = [m for m, n in (p for p in matches if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 30:
        raise ValueError(f"only {len(good)} features match the last picture whose rulers were read")
    a = np.float32([k1[m.queryIdx].pt for m in good]) / s1
    b = np.float32([k0[m.trainIdx].pt for m in good]) / s0
    T, inliers = cv2.findHomography(a, b, cv2.RANSAC, 4.0)
    count = int(inliers.sum()) if inliers is not None else 0
    if T is None or count < 25:
        raise ValueError(f"only {count} features agree with the last picture whose rulers were read")
    h, w = image.shape[:2]
    corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    shift = float(np.abs(cv2.perspectiveTransform(corners[None], T)[0] - corners).max())
    return reference_H @ T, count, shift


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
    return _find_pieces(flat, lambda pts: np.asarray(pts, float) / PX_PER_CM - MARGIN_CM, PX_PER_CM, arm_cm, keep_clear_cm)


def raw_scale(H: np.ndarray, at_cm=(15.0, 10.0)) -> float:
    """Picture pixels per ruler centimetre around `at_cm` on the table."""
    Hinv = np.linalg.inv(H)
    pts = cv2.perspectiveTransform(np.array([[at_cm, (at_cm[0] + 1, at_cm[1]), (at_cm[0], at_cm[1] + 1)]], np.float32), Hinv)[0]
    return float((np.linalg.norm(pts[1] - pts[0]) + np.linalg.norm(pts[2] - pts[0])) / 2)


def find_pieces_raw(image: np.ndarray, H: np.ndarray, arm_cm=None, keep_clear_cm: float = 14.0) -> dict:
    """find_pieces on the camera's own picture: circles are found in its pixels and only their centres are turned
    into ruler cm with H. Nothing is cropped or resampled, so whatever the camera sees can be used."""
    return _find_pieces(image, lambda pts: to_cm(H, pts), raw_scale(H), arm_cm, keep_clear_cm)


def _find_pieces(flat: np.ndarray, px_to_cm, scale: float, arm_cm, keep_clear_cm: float) -> dict:
    """The shared search. `px_to_cm` turns picture pixels into ruler cm; `scale` is pixels per cm on the table."""
    k = scale / PX_PER_CM  # sizes below were tuned on the 20 px/cm flattened picture

    def odd(n):
        return max(3, int(round(n * k)) | 1)
    hsv, gray = cv2.cvtColor(flat, cv2.COLOR_BGR2HSV), cv2.cvtColor(flat, cv2.COLOR_BGR2GRAY)
    bright = cv2.morphologyEx(cv2.inRange(hsv, np.array([0, 0, 170]), np.array([180, 70, 255])), cv2.MORPH_OPEN, np.ones((odd(9), odd(9)), np.uint8))
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(bright)
    large = np.zeros_like(bright)
    blobs = []  # bright, roundish, container-sized things: under strong light the clear plastic itself shows up this way
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] > (3 * scale) ** 2:
            w, h = stats[i, cv2.CC_STAT_WIDTH] / scale, stats[i, cv2.CC_STAT_HEIGHT] / scale
            cx, cy = px_to_cm([centroids[i]])[0]
            clear = arm_cm is None or np.hypot(cx - arm_cm[0], cy - arm_cm[1]) >= keep_clear_cm
            if 3.5 <= min(w, h) and max(w, h) <= 10.5 and max(w, h) / min(w, h) < 1.4 and stats[i, cv2.CC_STAT_AREA] > 0.5 * w * h * scale ** 2 and 0 < cx < RULER_LENGTH and 0 < cy < RULER_LENGTH and clear:
                blobs.append((float(cx), float(cy), float((w + h) / 4), i))
            else:
                large[labels == i] = 255
    # The outlines are used only when they show one thing of each size; otherwise they are treated like any other glare.
    if sorted(b[2] > 3.25 for b in blobs) != [False, True]:
        for b in blobs:
            large[labels == b[3]] = 255
        blobs = []
    block = cv2.dilate(_red(flat) | large, np.ones((odd(25), odd(25)), np.uint8))
    if not (block == 0).any():
        return {}
    work = gray.copy()
    work[block > 0] = int(np.median(gray[block == 0]))
    work = cv2.GaussianBlur(work, (odd(7), odd(7)), 0)

    def circles(r_min_cm, r_max_cm):
        for votes in (40, 34, 28, 24, 20):
            found = cv2.HoughCircles(work, cv2.HOUGH_GRADIENT, dp=1.5 * max(1.0, k), minDist=25 * k, param1=60, param2=votes,
                                     minRadius=int(r_min_cm * scale), maxRadius=int(r_max_cm * scale))
            if found is None:
                continue
            out = []
            for x, y, r in found[0]:
                cx, cy = px_to_cm([(x, y)])[0]
                inside = 0 <= int(y) < block.shape[0] and 0 <= int(x) < block.shape[1]
                if not inside or block[int(y), int(x)] or cx < 0 or cy < 0:
                    continue
                if arm_cm is not None and np.hypot(cx - arm_cm[0], cy - arm_cm[1]) < keep_clear_cm:
                    continue
                out.append((float(cx), float(cy), float(r / scale)))
            if out:
                return out
        return []

    def describe(name, c):
        spec = PIECES[name]
        which = "base" if abs(c[2] - spec["base"]) <= abs(c[2] - spec["rim"]) else "rim"
        return {"cm": (round(c[0], 1), round(c[1], 1)), "radius_cm": round(c[2], 2), "found": which,
                "note": "" if which == "base" else "this is the raised rim, so the true position is probably 1 to 3 cm closer to the camera's centre"}

    if blobs:
        # The outline of each thing is in plain sight, so size decides which is which (dish rim 8.4 cm, beaker 4.5 cm
        # plus its spout). A circle found inside the outline (the base, on the table) gives the better position.
        result = {}
        for cx, cy, r, _ in sorted(blobs, key=lambda b: -b[2]):
            name = "dish" if r > 3.25 else "beaker"
            if name in result:
                continue
            lo, hi = (2.6, 4.9) if name == "dish" else (1.2, 3.0)
            inside = [c for c in circles(lo, hi) if np.hypot(c[0] - cx, c[1] - cy) < 0.5 * r]
            bases = [c for c in inside if abs(c[2] - PIECES[name]["base"]) < 0.35]
            base = min(bases, key=lambda c: np.hypot(c[0] - cx, c[1] - cy)) if bases else None
            result[name] = describe(name, base or (cx, cy, r))
        return result
    result = {}
    dish = circles(2.6, 4.9)
    if dish:
        # Seen from above, the beaker's raised rim reads up to about 2.9 cm, which is inside the dish's range, so
        # the strongest circle can be the beaker. The dish also shows a circle of 3 cm or more around the same
        # centre (its base or its rim); take the strongest circle that has one.
        def has_dish_sized(c):
            return any(o[2] >= 3.0 and np.hypot(o[0] - c[0], o[1] - c[1]) < 3.0 for o in dish)
        strongest = next((c for c in dish if has_dish_sized(c)), dish[0])
        # The base lies on the table and is the true position; prefer it when it was found near that circle.
        base = next((c for c in dish if abs(c[2] - PIECES["dish"]["base"]) < 0.35 and np.hypot(c[0] - strongest[0], c[1] - strongest[1]) < 3.0), None)
        result["dish"] = describe("dish", base or strongest)
    d = result.get("dish")
    for c in circles(1.2, 3.0):
        if d and np.hypot(c[0] - d["cm"][0], c[1] - d["cm"][1]) < PIECES["dish"]["rim"] + 1.5:
            continue  # the dish's own base and reflections
        result["beaker"] = describe("beaker", c)
        break
    return result


MANDARIN_CM = (3.0, 9.5)  # how wide and tall a mandarin may look from above, cm


def find_mandarin(flat: np.ndarray, arm_cm=None, keep_clear_cm: float = 12.0) -> dict | None:
    """The orange, roundish thing on the table in a flattened picture: {'cm': (x, y), 'size_cm': (w, h)}, or None.

    The colour test is firmware.openarms_camera.stations.find_objects, with the rulers blanked out so
    their red is never taken for the fruit. Things outside the L, within `keep_clear_cm` of the arm's
    base, or not the size of a mandarin are ignored. The position is the middle of what the camera
    sees; the fruit is a few centimetres tall, so away from the point under the camera it reads up to
    about a centimetre further out than where the fruit touches the table."""
    from .stations import find_objects
    work = flat.copy()
    x0, y0 = flat_px((0.3, 0.3))
    work[:y0, :], work[:, :x0] = 0, 0
    work[cv2.dilate(_red(flat), np.ones((15, 15), np.uint8)) > 0] = 0
    for found in find_objects(work):
        x, y, w, h = found["box"]
        size = (w / PX_PER_CM, h / PX_PER_CM)
        cx, cy = (x + w / 2) / PX_PER_CM - MARGIN_CM, (y + h / 2) / PX_PER_CM - MARGIN_CM
        if not all(MANDARIN_CM[0] <= v <= MANDARIN_CM[1] for v in size):
            continue
        if arm_cm is not None and np.hypot(cx - arm_cm[0], cy - arm_cm[1]) < keep_clear_cm:
            continue
        return {"cm": (round(float(cx), 1), round(float(cy), 1)), "size_cm": (round(size[0], 1), round(size[1], 1))}
    return None


def draw(flat: np.ndarray, pieces: dict | None = None, arm_cm=None, mandarin: dict | None = None, places: dict | None = None) -> np.ndarray:
    """The flattened picture with a 5 cm grid, the detections, the named places and the arm's base marked."""
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
    for name, cm in (places or {}).items():
        cv2.drawMarker(out, flat_px(cm), (255, 255, 255), cv2.MARKER_TILTED_CROSS, 22, 2)
        cv2.putText(out, name, (flat_px(cm)[0] + 12, flat_px(cm)[1] + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    if mandarin:
        cx, cy = flat_px(mandarin["cm"])
        cv2.circle(out, (cx, cy), int(max(mandarin["size_cm"]) * PX_PER_CM / 2), (0, 140, 255), 2)
        cv2.putText(out, f"mandarin {mandarin['cm'][0]}, {mandarin['cm'][1]}", (cx + 8, cy - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 140, 255), 2)
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
