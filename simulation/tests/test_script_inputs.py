"""Generic preview holds and labels preserve the existing transfer defaults."""
import pytest
from openarms_sim.script import _segments, GRIPPER
from openarms_sim.config import ARM_JOINTS

class JointMap:
    def pose_to_model(self, pose):
        return [pose[j] for j in ARM_JOINTS]

@pytest.fixture
def home():
    return {j: 0. for j in ARM_JOINTS}

@pytest.mark.parametrize('value', [-1, float('nan'), float('inf'), True, 61])
def test_invalid_holds_are_rejected(home, value):
    with pytest.raises(ValueError, match='Hold duration'):
        _segments([value], home, JointMap(), 1.5, 'A', 'B')

@pytest.mark.parametrize('value', [0, 0.25, 60])
def test_finite_holds_and_labels(home, value):
    segment = _segments([value], home, JointMap(), 1.5, 'A', 'B', ['wait'])[0]
    assert segment.duration == value
    assert segment.step == 'wait'

@pytest.mark.parametrize('labels', [[], [''], 'wait'])
def test_each_target_needs_a_nonempty_label(home, labels):
    with pytest.raises(ValueError, match='labels'):
        _segments([1], home, JointMap(), 1.5, 'A', 'B', labels)

def test_initial_gripper_preserves_first_target_default(home):
    combined = {**home, GRIPPER: 75.}
    assert _segments([combined], home, JointMap(), 1.5, 'A', 'B')[0].grip0 == 75.
    assert _segments([home, {GRIPPER: 0.}], home, JointMap(), 1.5, 'A', 'B')[0].grip0 == 50.
