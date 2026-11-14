"""Which station is the mandarin on? A fixed camera and plain OpenCV, no model.

The camera does not measure positions. It is taught where each station appears in
its picture: put the object on a station, and the region around the detected object
is saved under that station's name. Afterwards a detection that falls in a saved
region means "the object is on that station"; a detection anywhere else means it is
somewhere the app does not know (in the gripper, or moved by hand), and no detection
means it is hidden or gone. The camera must not move after the regions are marked.

    python -m firmware.openarms_camera list                 # which camera index is the bench camera
    python -m firmware.openarms_camera mark --camera 1      # teach the regions for A and B
    python -m firmware.openarms_camera look --camera 1      # report where the object is now

Colour thresholds are for an orange object under indoor light. A detection is a
coloured, roundish blob, not proof of identity. Wood and skin share the fruit's colour:
keep them out of the picture, or at least out of the station regions.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
REGIONS_FILE = HERE / "stations.json"
# HSV ranges, strictest first. A vivid fruit under good light passes the strict one, which
# leaves out skin and most wood; a dim scene needs the looser ones. The first range that
# gives a plausible object is used.
ORANGE_LADDER = [((8, 190, 140), (22, 255, 255)), ((6, 150, 110), (22, 255, 255)), ((6, 120, 90), (22, 255, 255))]
MAX_AREA = 0.12  # of the picture: anything larger is background, not the object
ASPECT = (0.4, 2.5)  # width / height: a fruit is roundish; a desk edge or a cable is not
SLIVER = (0.28, 3.5)  # pieces outside this are never part of a fruit, even one split by a jaw
MIN_AREA = 0.002  # of the picture: smaller blobs are reflections or clutter
MERGE_GAP = 0.12  # of the picture width: pieces this close are one object split by a gripper jaw
GROW = 0.6  # a station's region is the object's box grown by this fraction on every side


def _blobs(hsv, low, high, width, height) -> list[tuple]:
    mask = cv2.inRange(hsv, np.array(low), np.array(high))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = [cv2.boundingRect(c) + (cv2.contourArea(c),) for c in contours if cv2.contourArea(c) >= MIN_AREA * width * height]
    # Long strips (a desk edge, a cable) are dropped before joining, or they would swallow the fruit.
    boxes = [b for b in boxes if SLIVER[0] <= b[2] / b[3] <= SLIVER[1]]
    # A jaw in front of the fruit cuts it into side-by-side pieces; join pieces that sit at the
    # same height and nearly touch. Things merely near the fruit, above or below it, stay separate.
    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                (x1, y1, w1, h1, a1), (x2, y2, w2, h2, a2) = boxes[i], boxes[j]
                gap_x = max(x1, x2) - min(x1 + w1, x2 + w2)
                shared = min(y1 + h1, y2 + h2) - max(y1, y2)
                if gap_x <= MERGE_GAP * width and shared >= 0.5 * min(h1, h2):
                    x, y = min(x1, x2), min(y1, y2)
                    boxes[i] = (x, y, max(x1 + w1, x2 + w2) - x, max(y1 + h1, y2 + h2) - y, a1 + a2)
                    del boxes[j]
                    merged = True
                    break
            if merged:
                break
    # Shape is judged after joining, so a fruit split by a jaw is not thrown out as two slivers.
    return [b for b in boxes if ASPECT[0] <= b[2] / b[3] <= ASPECT[1] and b[2] * b[3] <= MAX_AREA * width * height]


def find_objects(image: np.ndarray) -> list[dict]:
    """Orange, roundish blobs in a BGR picture, largest first:
    {'box': (x, y, w, h), 'center': (cx, cy), 'area': fraction of the picture}."""
    if image is None or image.ndim != 3:
        raise ValueError("expected a colour picture")
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(cv2.GaussianBlur(image, (5, 5), 0), cv2.COLOR_BGR2HSV)
    boxes = []
    for low, high in ORANGE_LADDER:
        boxes = _blobs(hsv, low, high, width, height)
        if boxes:
            break
    out = [{"box": (int(x), int(y), int(w), int(h)), "center": (x + w / 2, y + h / 2), "area": round(a / (width * height), 4)}
           for x, y, w, h, a in boxes]
    return sorted(out, key=lambda b: -b["area"])


def region_around(box, shape) -> list[int]:
    """The saved region for a station: the object's box, grown, clipped to the picture."""
    x, y, w, h = box
    height, width = shape[:2]
    return [max(0, int(x - GROW * w)), max(0, int(y - GROW * h)),
            min(width, int(x + w + GROW * w)), min(height, int(y + h + GROW * h))]


def load_regions(path: Path | str | None = None) -> dict | None:
    path = Path(path or REGIONS_FILE)
    return json.loads(path.read_text()) if path.exists() else None


def where(image: np.ndarray, regions: dict) -> dict:
    """What the camera says about the object.

    {'station': 'A' | None, 'seen': bool, 'status': 'at_station' | 'elsewhere' | 'not_seen' | 'unclear', ...}"""
    size = regions.get("image_size")
    if size and [image.shape[1], image.shape[0]] != size:
        raise ValueError(f"the picture is {image.shape[1]}x{image.shape[0]} but the regions were marked at {size[0]}x{size[1]}")
    found = find_objects(image)
    if not found:
        return {"station": None, "seen": False, "status": "not_seen", "objects": [],
                "text": "The camera does not see the object."}
    inside = []
    for obj in found:
        cx, cy = obj["center"]
        # Regions may overlap when stations are close in the picture: the nearest region centre wins.
        near = [(((x0 + x1) / 2 - cx) ** 2 + ((y0 + y1) / 2 - cy) ** 2, name)
                for name, (x0, y0, x1, y1) in regions["stations"].items() if x0 <= cx <= x1 and y0 <= cy <= y1]
        if near:
            inside.append((min(near)[1], obj))
    stations = sorted({name for name, _ in inside})
    if len(stations) == 1:
        return {"station": stations[0], "seen": True, "status": "at_station", "objects": found,
                "text": f"The camera sees the object at {stations[0]}."}
    if len(stations) > 1:
        return {"station": None, "seen": True, "status": "unclear", "objects": found,
                "text": f"The camera sees orange at {' and '.join(stations)}; it cannot tell which is the object."}
    return {"station": None, "seen": True, "status": "elsewhere", "objects": found,
            "text": "The camera sees the object, but not on a marked station."}


def annotate(image: np.ndarray, regions: dict | None, result: dict | None = None) -> np.ndarray:
    """The picture with the station regions and detections drawn on it."""
    out = image.copy()
    for name, (x0, y0, x1, y1) in (regions or {}).get("stations", {}).items():
        here = result is not None and result.get("station") == name
        cv2.rectangle(out, (x0, y0), (x1, y1), (60, 220, 60) if here else (220, 180, 60), 2)
        cv2.putText(out, name, (x0 + 6, y0 + 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 3)
        cv2.putText(out, name, (x0 + 6, y0 + 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (30, 30, 30), 1)
    for obj in (result or {}).get("objects", []):
        x, y, w, h = obj["box"]
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 140, 255), 2)
    return out


class Camera:
    """One fixed webcam. Opened per picture so nothing holds the device between looks."""

    def __init__(self, index: int = 0, warmup: int = 8):
        self.index, self.warmup = index, warmup

    def read(self) -> np.ndarray:
        cap = cv2.VideoCapture(self.index)
        try:
            if not cap.isOpened():
                raise OSError(f"camera {self.index} could not be opened (check the cable and macOS camera permission)")
            frame = None
            for _ in range(self.warmup):  # the first frames are dark while exposure settles
                ok, got = cap.read()
                if ok:
                    frame = got
                time.sleep(0.03)
            if frame is None:
                raise OSError(f"camera {self.index} returned no picture")
            return frame
        finally:
            cap.release()


def mark_station(regions: dict, name: str, image: np.ndarray) -> dict:
    """Adds the region for one station from a picture with the object standing on it."""
    found = find_objects(image)
    if not found:
        raise ValueError("no orange object found in the picture; check the light and that the object is in view")
    regions.setdefault("stations", {})[name] = region_around(found[0]["box"], image.shape)
    regions["image_size"] = [image.shape[1], image.shape[0]]
    return regions


def check_regions(regions: dict) -> list[str]:
    """Problems that make the regions unusable, e.g. two stations that overlap in the picture."""
    problems, items = [], list(regions.get("stations", {}).items())
    for i, (a, (ax0, ay0, ax1, ay1)) in enumerate(items):
        for b, (bx0, by0, bx1, by1) in items[i + 1:]:
            # Overlapping edges are fine; one station's middle inside the other's core is not,
            # because a slightly misplaced object could then be read as either.
            dx, dy = abs((ax0 + ax1) - (bx0 + bx1)) / 2, abs((ay0 + ay1) - (by0 + by1)) / 2
            if dx < min(ax1 - ax0, bx1 - bx0) / 4 and dy < min(ay1 - ay0, by1 - by0) / 4:
                problems.append(f"{a} and {b} look like the same place in the picture; move the camera so they are further apart")
    return problems
