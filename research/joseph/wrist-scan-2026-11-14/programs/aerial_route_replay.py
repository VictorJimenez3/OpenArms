"""Compare saved aerial routes using the existing overlap implementation."""
from functools import lru_cache
import json
from pathlib import Path

import cv2

import compare_coverage as method


ROOT = Path(__file__).resolve().parent.parent / "outputs"
INPUT = ROOT / "replay-inputs"
OUTPUT = ROOT / "reproduced" / "evidence" / "aerial-route-ablation.json"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
BASELINE = (735, 725, 716, 708, 698, 617)


def analyze(scene):
    by_view = {frame["view_id"]: frame for frame in scene["frames"]}
    detector = cv2.SIFT_create(nfeatures=4000, contrastThreshold=.013)
    contrast = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(10, 10))
    matcher = cv2.BFMatcher(cv2.NORM_L2)

    @lru_cache(maxsize=None)
    def features(view):
        return method.image_features(INPUT / by_view[view]["image"]["path"], detector, contrast)

    @lru_cache(maxsize=None)
    def score(left, right):
        return {"from_view": left, "to_view": right,
                **method.score_link(features(left), features(right), matcher)}

    def route(drop):
        retained = tuple(view for view in BASELINE if view not in drop)
        missing = sorted(set(retained) - by_view.keys())
        if missing:
            return {"views": retained, "dropped": drop, "status": "unavailable",
                    "missing": missing, "links": []}
        links = [score(left, right) for left, right in zip(retained, retained[1:])]
        return {
            "views": retained,
            "dropped": drop,
            "status": "pass" if all(row["passed"] for row in links) else "fail",
            "weakest_inlier_link": min(links, key=lambda row: row["inliers"]),
            "smallest_support_link": min(links, key=lambda row: row["matched_area_fraction"]),
            "links": links,
        }

    return {"scene_id": scene["scene_id"],
            "routes": [route(())] + [route((view,)) for view in BASELINE[1:-1]]}


cv2.setNumThreads(4)
manifest = json.loads((INPUT / "manifest.json").read_text())
result = {
    "scope": "Saved-image overlap gate only; no measured speed or motion/geometry qualification",
    "gate": {"minimum_inliers": method.MIN_INLIERS,
             "minimum_inlier_ratio": method.MIN_INLIER_RATIO,
             "minimum_area_fraction": method.MIN_SPREAD},
    "scenes": [analyze(scene) for scene in manifest["scenes"]],
}
OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
for scene in result["scenes"]:
    for route in scene["routes"]:
        weak = route.get("weakest_inlier_link", {})
        support = route.get("smallest_support_link", {})
        print(scene["scene_id"], route["dropped"], route["status"],
              weak.get("inliers"), round(100 * support.get("matched_area_fraction", 0), 1))
