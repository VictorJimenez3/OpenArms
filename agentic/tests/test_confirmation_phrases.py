"""Natural spoken confirmations are accepted; anything that adds content, doubts or negates is not."""
import pytest

from agentic.openarms_lab.runtime import _affirmative
from agentic.openarms_lab.voice_controls import is_confirmation


@pytest.mark.parametrize('text', ['yes', 'Yes, I confirm. Go ahead.', 'yes go ahead please', 'confirm', 'I confirm',
                                  'go ahead', 'yes please', 'yeah go ahead', 'confirm the proposal', 'run it',
                                  'yes, do it', 'okay, go ahead', 'yes confirm it', 'confirmed'])
def test_unambiguous_confirmations(text):
    assert is_confirmation(text) and _affirmative(text)


@pytest.mark.parametrize('text', ['yes but use water', 'do not confirm', 'I predict yes', 'say confirm', '“confirm”',
                                  'confirm?', '', 'okay', 'sure', 'go', 'no', "don't go ahead", 'yes and pour B too',
                                  'confirm then pour again', 'wait', 'yes wait', 'it', 'please'])
def test_anything_else_is_not_consent(text):
    assert not is_confirmation(text) and not _affirmative(text)
