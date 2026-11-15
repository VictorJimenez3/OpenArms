"""Compare fresh physical sweeps by adjacent image overlap and measured timing."""
import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np

MIN_INLIERS = 25
MIN_SPREAD = .07
MIN_INLIER_RATIO = .45

def read_outward_frames(run):
    events = [json.loads(line) for line in (run / "review-decisions.jsonl").read_text().splitlines()]
    frames = [row for row in events if row["event"] == "captured" and row.get("phase", "outward") == "outward"]
    receipt = json.loads((run / "capture-finished.json").read_text())
    if receipt["status"] != "complete" or len(frames) < 2:
        raise ValueError(f"An entire outward sweep and a verified return are required: {run}")
    return frames, receipt

def image_features(path, detector, contrast):
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"Missing image {path}.")
    points, descriptors = detector.detectAndCompute(contrast.apply(image), None)
    if descriptors is None or len(descriptors) < 2:
        raise ValueError(f"Too few usable features in {path}.")
    return points, descriptors, image.size

def reciprocal_pairs(left, right, matcher):
    def nearest(a, b):
        return {m.queryIdx: m.trainIdx for pair in matcher.knnMatch(a, b, k=2)
                if len(pair) == 2 for m, n in [pair] if m.distance < .75 * n.distance}
    forward, backward = nearest(left, right), nearest(right, left)
    return [(i, j) for i, j in forward.items() if backward.get(j) == i]

def score_link(left, right, matcher):
    points_a, descriptors_a, _ = left
    points_b, descriptors_b, pixels_b = right
    pairs = reciprocal_pairs(descriptors_a, descriptors_b, matcher)
    score = {"matches": len(pairs), "inliers": 0, "matched_area_fraction": 0.0,
             "median_error_px": None, "passed": False}
    if len(pairs) < 5:
        return score
    source = np.float32([points_a[i].pt for i, _ in pairs])
    target = np.float32([points_b[j].pt for _, j in pairs])
    transform, mask = cv2.findHomography(source, target, cv2.USAC_MAGSAC, 2.5,
                                         maxIters=6000, confidence=.999)
    if transform is None or mask is None:
        return score
    inliers = mask.ravel().astype(bool)
    count = int(inliers.sum())
    if count < 4:
        return score
    spread = cv2.contourArea(cv2.convexHull(target[inliers])) / pixels_b
    error = cv2.perspectiveTransform(source[None], transform)[0] - target
    score.update(inliers=count, matched_area_fraction=spread,
                 median_error_px=float(np.median(np.linalg.norm(error[inliers], axis=1))),
                 passed=count >= MIN_INLIERS and spread >= MIN_SPREAD
                 and count / len(pairs) >= MIN_INLIER_RATIO)
    return score

def analyze(run, exclude=()):
    rows, receipt = read_outward_frames(run)
    rows = [row for row in rows if row["recorded_view"] not in exclude]
    if len(rows) < 2:
        raise ValueError("An overlap comparison needs at least two frames.")
    detector = cv2.SIFT_create(nfeatures=4000, contrastThreshold=.013)
    contrast = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(10, 10))
    features = [image_features(run / row["image"], detector, contrast) for row in rows]
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    links = [{"from_view": a["recorded_view"], "to_view": b["recorded_view"],
              **score_link(left, right, matcher)}
             for a, b, left, right in zip(rows, rows[1:], features, features[1:])]
    return {
        "run": str(run),
        "analyzed_outward_frames": len(rows),
        "excluded_view_ids": list(exclude),
        "outward_seconds": receipt.get("outward_seconds"),
        "first_to_last_frame_seconds": rows[-1]["host_monotonic_s"] - rows[0]["host_monotonic_s"],
        "turnaround_review_seconds": receipt.get("turnaround_review_seconds"),
        "return_seconds": receipt.get("return_seconds"),
        "return_views": receipt.get("return_views", []),
        "weakest": min(links, key=lambda item: item["inliers"]),
        "all_adjacent_links_pass": all(item["passed"] for item in links),
        "links": links,
    }

def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("runs", type=Path, nargs="+")
    cli.add_argument("--out", type=Path, required=True)
    cli.add_argument("--ablate-view", type=int, action="append", default=[])
    args = cli.parse_args()
    cv2.setNumThreads(4)
    result = {"scope": "Physical image overlap and timing, not robot registration or grasp success",
              "runs": [analyze(run.resolve()) for run in args.runs]}
    if args.ablate_view:
        ablation = analyze(args.runs[-1].resolve(), exclude=args.ablate_view)
        result["same_capture_ablation"] = {
            "purpose": "Recompute coverage on the exact fresh images with the added view removed.",
            "excluded_view_ids": ablation["excluded_view_ids"],
            "weakest": ablation["weakest"],
            "all_adjacent_links_pass": ablation["all_adjacent_links_pass"],
            "links": ablation["links"],
        }
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    for entry in result["runs"]:
        edge = entry["weakest"]
        print(Path(entry["run"]).name, "weakest", edge["from_view"], edge["to_view"],
              edge["inliers"], "inliers", "all_pass", entry["all_adjacent_links_pass"])

if __name__ == "__main__":
    main()
