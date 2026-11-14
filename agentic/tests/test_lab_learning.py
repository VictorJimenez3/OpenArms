"""Qualitative classroom reference and reflection are separate from execution."""
import uuid
import re
import pytest
from agentic.openarms_lab.learning import (CONDITIONS, get_experiment, condition,
    reference_observation, reflection_feedback, science_reply)

@pytest.mark.parametrize('cid,color,classification', [('vinegar', 'pink', 'acidic'), ('baking_soda', 'blue-green', 'basic'), ('water', 'purple', 'near neutral')])
def test_qualitative_reference_has_provenance_ids_and_no_numeric_ph(cid, color, classification):
    request_id, trial_id = str(uuid.uuid4()), str(uuid.uuid4())
    obs = reference_observation(request_id, trial_id, cid)
    assert obs['request_id'] == request_id and obs['trial_id'] == trial_id
    assert obs['provenance'] == 'MODEL-PREDICTED' and obs['evidence']
    assert obs['value'] == {'color': color, 'classification': classification, 'condition_id': cid}
    assert 'not a measured' in obs['text'] and 'pH' not in obs['value']


def test_no_readable_reference_stays_unknown_and_reflection_cannot_invent_measurement():
    obs = reference_observation(str(uuid.uuid4()), str(uuid.uuid4()), 'water', available=False)
    assert obs['provenance'] == 'UNKNOWN' and obs['value'] is None and obs['evidence'] == []
    feedback = reflection_feedback('I measured pink at pH 2', [obs])
    assert 'UNKNOWN' in feedback['feedback'] and 'pink' not in feedback['feedback']
    assert feedback['correct'] is None and feedback['evidence'] == []


def test_feedback_quotes_only_recorded_reference_not_student_assertion():
    obs = reference_observation(str(uuid.uuid4()), str(uuid.uuid4()), 'baking_soda')
    feedback = reflection_feedback('It was red and strongly acidic', [obs])
    assert 'blue-green' in feedback['feedback'] and not re.search(r'\bred\b', feedback['feedback'].lower())
    assert feedback['evidence'] == obs['evidence']
    assert feedback['request_ids'] == [obs['request_id']]
    assert feedback['correct'] is None


def test_single_experiment_and_copies_are_isolated():
    assert len(CONDITIONS) == 3
    exp = get_experiment('indicator_ph')
    exp['id'] = 'changed'
    assert get_experiment('indicator_ph')['id'] == 'indicator_ph'
    c = condition('water')
    c['color'] = 'changed'
    assert condition('water')['color'] == 'purple'
    with pytest.raises(ValueError):
        get_experiment('buoyancy')
    with pytest.raises(ValueError):
        condition('bleach')


def test_science_explanation_and_no_observations_remain_reference_only():
    assert 'qualitative' in science_reply('Why is vinegar pink?', []).lower()
    assert 'control' in science_reply('Why use water?', []).lower()
    assert 'UNKNOWN' in reflection_feedback('It turned pink.', [])['feedback']
