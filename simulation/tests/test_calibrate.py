"""The table-touch fit recovers a known joint map, and says so when it cannot."""

import numpy as np
import pytest
import yaml

pytest.importorskip("scipy")
from scipy.optimize import brentq  # noqa: E402

from openarms_sim import calibrate  # noqa: E402
from openarms_sim.calibrate import Arm, _jaw, fit, verdict  # noqa: E402
from openarms_sim.config import ARM_JOINTS, load_joint_map  # noqa: E402

CFG = load_joint_map()


@pytest.fixture(scope="module")
def arm():
    return Arm()


def touches(arm, sign, off, table, n, seed, alike=False, noise_deg=0.3):
    """Readings the real arm would give if its true joint map were (sign, off)."""
    rng = np.random.default_rng(seed)
    rows = []
    while len(rows) < n:
        pan, roll, g = rng.uniform(-40, 40), rng.uniform(-30, 30), rng.uniform(5, 90)
        lift, elbow = (rng.uniform(20, 30), rng.uniform(-10, 0)) if alike else (rng.uniform(-20, 80), rng.uniform(-80, 60))
        height = lambda w: arm.lowest(np.array([pan, lift, elbow, w, roll]), _jaw(CFG, g)) - table  # noqa: E731
        ws = np.linspace(-95, 95, 39)
        vals = [height(w) for w in ws]
        roots = [brentq(height, ws[i], ws[i + 1]) for i in range(len(ws) - 1) if vals[i] * vals[i + 1] < 0]
        if not roots:
            continue
        model = [pan, lift, elbow, float(rng.choice(roots)), roll]
        rows.append([(model[i] - off.get(j, 0)) / sign.get(j, 1) + rng.normal(0, noise_deg) for i, j in enumerate(ARM_JOINTS)] + [g])
    return np.array(rows)


def test_recovers_signs_and_offsets_from_varied_touches(arm):
    sign = {"shoulder_lift": -1, "elbow_flex": 1, "wrist_flex": 1}
    off = {"shoulder_lift": -8.0, "elbow_flex": 3.0, "wrist_flex": -12.0}
    result = fit(touches(arm, sign, off, 0.02, 14, seed=3), CFG, arm)
    assert result["signs"] == sign
    for j, true in off.items():
        assert abs(result["offset_deg"][j] - true) < 2.5, (j, result)
    assert abs(result["table_height_cm"] - 2.0) < 0.6
    assert result["rms_mm"] < 3 and result["before_rms_mm"] > 20
    assert verdict(result)[0] == "good"


def test_touches_that_are_too_alike_are_not_trusted(arm):
    off = {"shoulder_lift": 6.0, "elbow_flex": -4.0, "wrist_flex": 9.0}
    result = fit(touches(arm, {}, off, 0.004, 12, seed=1, alike=True), CFG, arm)
    grade, why = verdict(result)
    assert grade == "poor" and "too alike" in why


def test_too_few_touches_is_an_error(arm):
    with pytest.raises(ValueError, match="at least 6"):
        fit(np.zeros((4, 6)), CFG, arm)


def test_writing_keeps_the_other_settings_and_marks_it_measured(tmp_path, monkeypatch):
    (tmp_path / "joint_map.yaml").write_text(yaml.safe_dump(CFG))
    monkeypatch.setattr(calibrate, "CONFIG_DIR", tmp_path)
    result = {"signs": {"shoulder_lift": 1, "elbow_flex": -1, "wrist_flex": 1},
              "offset_deg": {"shoulder_lift": 4.2, "elbow_flex": -3.1, "wrist_flex": 7.7},
              "touches": 14, "rms_mm": 2.1, "worst_mm": 4.0, "table_height_cm": 0.3}
    saved = yaml.safe_load(calibrate.write_joint_map(result).read_text())
    assert saved["measured"] is True
    assert saved["joints"]["elbow_flex"] == {"sign": -1, "offset_deg": -3.1}
    assert saved["joints"]["shoulder_pan"] == CFG["joints"]["shoulder_pan"] and saved["gripper"] == CFG["gripper"]
    assert saved["measurement"]["not_measured"] == ["shoulder_pan", "wrist_roll"]
