"""Natural return phrasing is not a second pour destination; real contradictions still refuse."""
import pytest

from agentic.openarms_lab.request_intent import positive_pour_request


@pytest.mark.parametrize('text', [
    'Could you pour the beaker at A into the container at C and then bring it back to A and go home?',
    'I want the beaker at A poured into the container at C, then back to A and home.',
    'Pour A into C, take it back to A and go home.',
    'Pour the beaker from A into C, move the beaker back to A, then go HOME.',
    'Pour A into C and carry it back onto A.',
    'Pour beaker A into C a single time, return it to A, then go to home.',
    'Pour the beaker at A into the container at C once, put the beaker back at A and go home.',
])
def test_return_phrasing_is_accepted_for_the_a_to_c_pour(text):
    assert positive_pour_request(text, 'A', 'C')


@pytest.mark.parametrize('text', [
    'Pour the beaker from C into A.',
    'Pour A into B, then bring it back to A.',
    'Pour it back into A.',
    'Pour from A to C, not A to C.',
])
def test_contradicting_routes_still_refuse(text):
    with pytest.raises(ValueError):
        positive_pour_request(text, 'A', 'C')
