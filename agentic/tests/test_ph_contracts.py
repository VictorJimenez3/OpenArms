"""Strict executable bindings forbid model-authored routes and extra parameters."""
import uuid
import pytest
from pydantic import ValidationError
from agentic.openarms_lab.contracts import SkillRequest, Parameters, Observation
from agentic.openarms_lab.recipes import PH_SKILL
from agentic.openarms_lab.skills import compute_skill_hash


def canonical():
    return dict(request_id=str(uuid.uuid4()), session_id=str(uuid.uuid4()), trial_id=str(uuid.uuid4()),
                proposal_version=1, generation=0, skill_id='red_cabbage_ph.v1', skill_version='1.0.0',
                skill_hash=compute_skill_hash(PH_SKILL), prediction='Pink', parameters=Parameters(condition_id='vinegar'))

@pytest.mark.parametrize('changes', [{'proposal_version': True}, {'proposal_version': '1'}, {'proposal_version': 0},
    {'generation': -1}, {'skill_id': 'move_servo'}, {'skill_version': '2.0.0'}, {'request_id': '../x'},
    {'session_id': ''}, {'trial_id': 'trial'}, {'raw_motor': [1]}, {'prediction': ''}, {'skill_hash': 'changed'}])
def test_request_strict_identity_version_and_allowed_artifact(changes):
    with pytest.raises(ValidationError):
        SkillRequest(**(canonical() | changes))


def test_bindings_and_skill_are_deeply_immutable():
    req = SkillRequest(**canonical())
    with pytest.raises(ValidationError):
        req.parameters.condition_id = 'water'
    with pytest.raises(ValidationError):
        PH_SKILL.destination = 'B'
    assert isinstance(PH_SKILL.steps, tuple)

@pytest.mark.parametrize('provenance', ['REAL', 'MOCK', 'SIMULATED'])
def test_new_ph_observation_cannot_claim_measured_provenance(provenance):
    with pytest.raises(ValidationError):
        Observation(request_id=str(uuid.uuid4()), trial_id=str(uuid.uuid4()), provenance=provenance,
                    text='pink', source='controller')
