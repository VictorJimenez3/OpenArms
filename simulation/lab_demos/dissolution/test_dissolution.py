import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import dissolve


def test_equal_baseline_and_negative_control():
    for elapsed in (0, 1, 60, 180):
        still = dissolve(1, elapsed, False, None)
        unactivated = dissolve(1, elapsed, True, None)
        assert math.isclose(still, unactivated, rel_tol=0, abs_tol=1e-12)
        assert 0 <= still <= 1


def test_stirred_rate_applies_only_after_activation():
    assert dissolve(1, 10, True, 30) == dissolve(1, 10, False, None)
    assert math.isclose(dissolve(1, 30, True, 30), math.exp(-.004 * 30), rel_tol=1e-12)
    still = dissolve(1, 180, False, None)
    stirred = dissolve(1, 180, True, 0)
    assert 0 <= stirred < still <= 1


def test_partial_activation_integrates_piecewise_rates():
    expected = math.exp(-.004 * 40 - .030 * 60)
    assert math.isclose(dissolve(1, 100, True, 40), expected, rel_tol=1e-12)
