import json

from bench_vision.demo import run_demo
from bench_vision.skills import load_candidate


def test_episode_to_candidate_to_rollback(tmp_path):
    output = tmp_path / "demo"
    receipt = run_demo(output)
    assert receipt["provenance"] == "synthetic"
    assert receipt["phase_count"] >= 6
    assert receipt["missing_phase_labels"] == []
    assert receipt["physical_outcome"] == "unknown"
    assert receipt["fake_validation"]["result"]["status"] == "executed"
    assert receipt["rollback_matches_baseline"]
    assert receipt["camera_alignment"][1]["dropped_reads"] == 3
    candidate = load_candidate(output / receipt["candidate"])
    baseline = load_candidate(output / receipt["baseline"])
    assert candidate["version"] != baseline["version"]
    assert candidate["poses"] == baseline["poses"]
    assert json.loads((output/"adaptation.json").read_text())["status"] == "rejected"
    assert (output/"summary"/"contact_sheet.jpg").stat().st_size > 1000
