"""Fast deterministic checks for action-driven titration and negative control."""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("titration_run", HERE / "run.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def test_two_samples_stop_at_persistent_faint_endpoint(tmp_path):
    out = mod.run(tmp_path / "positive", speed=4, render=False)
    assert out["success"] is True
    assert [t["drops"] for t in out["trials"]] == [6, 9]
    assert [t["total_dose_ml"] for t in out["trials"]] == [0.72, 1.08]
    assert all(t["persistent_observations"] >= 2 for t in out["trials"])
    assert all(t["success"] for t in out["trials"])
    assert len([e for e in out["events"] if e["event"] == "dose"]) == 15
    assert out["initial_state"]["robot_pose"] == "HOME"
    assert [s["metered_drops"] for s in out["initial_state"]["samples"]] == [0, 0]

def test_disabled_action_does_not_change_samples(tmp_path):
    out = mod.run(tmp_path / "negative", speed=4, negative=True, render=False)
    assert out["success"] is False
    assert out["negative_control"] is True
    assert all(t["drops"] == 0 and t["endpoint"] is None for t in out["trials"])
    assert not [e for e in out["events"] if e["event"] == "dose"]
    assert len([e for e in out["events"] if e["event"] == "missed_action"]) >= 2
