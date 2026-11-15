"""Intent constraints must survive paraphrases without granting consent."""
import copy

import pytest

from agentic.openarms_lab.conversation import explicit_action, read_only_turn
from agentic.openarms_lab.contracts import SkillDefinition
from agentic.openarms_lab.skills import SkillRegistry
from agentic.openarms_lab.task_loop import TaskLoop
from agentic.tests.test_demo_bench_runtime import DEFINITION


@pytest.mark.parametrize('text', [
    'Actually, pour from A into C, not C into A.',
    'Pour A into C, not from C to A.',
    'Could you transfer from beaker A to container C, not from C into A?',
    'Pour the beaker from A into C again.',
    'Please repeat the A-to-C pour, then return the beaker and go home.',
    'Use A as the source and C as the destination.',
    'Pour the liquid in A into C.',
])
def test_supported_correction_and_single_repeat_keep_the_positive_intent(text):
    TaskLoop._check_demo_request([text], 'add_sample')
    TaskLoop._check_water_request(text, liquids=True)


@pytest.mark.parametrize('text', [
    'Actually, use C as the source and A as the destination instead.',
    'The source is C and the destination is A.',
    'Pour C-to-A.',
    'Decant the beaker at C into A.',
    'Pour A into C, not A into C.',
    'Not C into A.',
    'Pour A into C but do not return HOME.',
    'Pour A into C but don\u2019t go HOME.',
    'Pour A into C again and again.',
    'Pour two pours from A into C.',
    'Pour five milliliters from A into C.',
    'Pour the liquid in B into C.',
    'Pour A in B.',
])
def test_wrong_or_unresolved_intent_never_accepts_a_supported_subset(text):
    with pytest.raises(ValueError):
        TaskLoop._check_water_request(text, liquids=True)


@pytest.mark.parametrize('text', [
    'Please repeat the A-to-C pour, then return the beaker and go home.',
    'Could you repeat the transfer from A to C?',
    'Repeat the pour.',
    'Please decant the beaker from A into C.',
    'Transfer the contents from A to C.',
])
def test_action_repetition_is_not_a_request_to_repeat_speech(text):
    assert not read_only_turn(text)
    assert explicit_action(text)


@pytest.mark.parametrize('text', [
    'Can you repeat that?', 'Could you say that again?', 'Repeat your proposal.',
    'Please repeat what you said.', 'Tell me more.',
    'Could you repeat your explanation of the pour?',
    'Please repeat what you said about the transfer.',
])
def test_repeating_speech_still_cannot_start_an_action(text):
    assert read_only_turn(text)
    assert not explicit_action(text)


def test_repeated_retrieval_slots_require_the_same_binding(tmp_path):
    definition = copy.deepcopy(DEFINITION)
    definition['retrieval_examples'] = [
        'pour from {source} into {into}, return the beaker to {source}']
    registry = SkillRegistry(tmp_path/'registry.json')
    version = registry.candidate(SkillDefinition.model_validate(definition))
    active = {definition['skill_id']: version}
    match = registry.match('pour from A into C, return the beaker to A', active_versions=active)
    assert match is not None and match.bindings == {'source': 'A', 'into': 'C'}
    assert registry.match('pour from A into C, return the beaker to C', active_versions=active) is None
    assert registry.match('do not pour from A into C, return the beaker to A', active_versions=active) is None
    assert registry._routing_admission(definition['skill_id'], version)['passed']


@pytest.mark.parametrize(('source', 'into'), [('B', 'D'), ('X', 'Y')])
def test_route_constraints_do_not_hardcode_the_demo_stations(source, into):
    TaskLoop._check_water_request(
        f'Use {source} as the source and {into} as the destination.',
        liquids=True, source=source, into=into)
    with pytest.raises(ValueError):
        TaskLoop._check_water_request(
            f'Use {into} as the source and {source} as the destination.',
            liquids=True, source=source, into=into)
