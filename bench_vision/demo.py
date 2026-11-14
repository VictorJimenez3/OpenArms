"""Reproduce the offline teach → evidence → candidate → rollback demonstration."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import time

from .capture import make_fixture
from .episode import read_jsonl
from .geometry import fit_calibration, localize
from .keyframes import summarize_episode
from .skills import compile_candidate, preview_adaptation, rollback, write_candidate


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def run_demo(out: str | Path):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    episode = make_fixture(out / "episode")
    summary = summarize_episode(episode, out / "summary")
    poses = json.loads((episode.parent / "poses.json").read_text())
    trace = read_jsonl(episode.parent / "joint_trace.jsonl")
    context = {"calibration_id": "synthetic-calibration-unqualified", "fixture_id": "synthetic-A-C",
               "cup_id": "drawn-cup", "camera_mount_id": "synthetic-view", "robot_id": "FakeRobot",
               "provenance": "synthetic", "max_observation_age_s": .25,
               "joint_limits": {joint: [-90,90] for joint in poses["poses"]["HOME"]}}
    write(out / "context.json", context)
    baseline = compile_candidate(poses, trace, summary, context)
    baseline_path = write_candidate(baseline, out / "candidates")
    # A second evidence version keeps the taught controller byte-for-byte intact.
    revised_summary = copy.deepcopy(summary)
    revised_summary["review_note"] = "Offline phase/contact-sheet review; no physical outcome asserted"
    candidate = compile_candidate(poses, trace, revised_summary, context, baseline=baseline)
    candidate_path = write_candidate(candidate, out / "candidates")
    retained = rollback(candidate)
    assert retained["poses"] == baseline["poses"] == poses
    write(out / "rollback.json", retained)
    examples = Path(__file__).parent / "examples"
    calibration = fit_calibration(json.loads((examples / "calibration-spec.synthetic.json").read_text()))
    obs = json.loads((examples / "observation.synthetic.json").read_text())
    localized = localize(calibration, obs, now_s=50.1)
    moved = copy.deepcopy(obs)
    for anchor in moved["anchors"]:
        anchor["pixel"][0] += 30
    moved_result = localize(calibration, moved, now_s=50.1)
    assert localized["status"] == "ok" and moved_result["status"] == "unknown"
    adaptation = preview_adaptation(candidate, localized, context, now_s=50.1)
    assert adaptation["status"] == "rejected" and adaptation["motor_targets"] is None
    write(out / "geometry.json", {"calibration":calibration,"localized":localized,"moved_camera":moved_result})
    write(out / "adaptation.json", adaptation)
    report = {"schema_version":1, "provenance":"synthetic", "physical_outcome":"unknown",
              "episode_id":summary["episode_id"], "elapsed_ms":(time.perf_counter()-started)*1000,
              "phase_count":len(summary["phases"]), "missing_phase_labels":summary["missing_phase_labels"],
              "camera_alignment":summary["alignment"]["cameras"],
              "baseline":str(baseline_path.relative_to(out)), "candidate":str(candidate_path.relative_to(out)),
              "candidate_version":candidate["version"], "fake_validation":candidate["validation"],
              "rollback_matches_baseline":True, "relocation":"rejected_without_physical_geometry",
              "motor_hardware_access":False,
              "artifacts":{"contact_sheet":"summary/contact_sheet.jpg", "episode_review":"summary/index.html",
                           "rollback":"rollback.json", "geometry":"geometry.json", "adaptation":"adaptation.json"},
              "limitations":["Drawn cup and synthetic joints are software fixtures, not physical evidence",
                             "No live camera, robot movement, calibration or policy activation performed"]}
    write(out / "receipt.json",report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True,help="new output directory")
    args = parser.parse_args()
    report = run_demo(args.out)
    print(json.dumps({"receipt":str(args.out/'receipt.json'),"candidate_version":report['candidate_version'],
                      "physical_outcome":"unknown","phases":report['phase_count']},indent=2))


if __name__ == "__main__":
    main()
