"""Voice/typed consent and passive historical-recovery regressions."""
import uuid

import pytest

from agentic.openarms_lab.runtime import Lab, LabError
from agentic.tests.test_lab_runtime import lab, proposed


@pytest.mark.asyncio
@pytest.mark.parametrize('text', [
    "don't confirm", 'do not confirm', 'yes but no', 'yes, but use water',
    'confirm then move the robot', 'I might confirm later',
    'the assistant said confirm', 'not yet', 'no', 'confirm?',
])
async def test_ambiguous_consent_never_executes(lab, text):
    sid, proposal = await proposed(lab)
    await lab.present(sid, proposal['request_id'], proposal['proposal_version'])
    await lab.converse(sid, text)
    assert not any(r['student_confirmed'] for r in lab.snapshot(sid)['requests'])
    assert lab.backends[sid].executions == 0


@pytest.mark.asyncio
async def test_duplicate_confirmation_input_cannot_approve_later_trial(lab):
    sid, first = await proposed(lab)
    await lab.present(sid, first['request_id'], first['proposal_version'])
    await lab.converse(sid, 'confirm', 'single-yes')
    await lab.workers[first['task_id']]
    await lab.prepare(sid)
    _, second = await proposed(lab, sid)
    await lab.present(sid, second['request_id'], second['proposal_version'])
    state = await lab.converse(sid, 'confirm', 'single-yes')
    assert state['pending']['request_id'] == second['request_id']
    assert lab.backends[sid].executions == 1


@pytest.mark.asyncio
async def test_old_physical_history_is_read_only_and_provenance_untouched(tmp_path):
    def forbidden():
        raise AssertionError('Hardware initialized from history')
    lab = Lab(tmp_path, backend_factory=forbidden)
    sid = str(uuid.uuid4())
    original = {'session_id': sid, 'backend': 'physical', 'experiment': {'id': 'mandarin_transfer'},
                'observations': [{'provenance': 'REAL', 'source': 'original image', 'evidence': ['frame-1']}],
                'requests': [], 'pending': None, 'messages': [], 'notebook': []}
    lab.store.save(original)
    s = lab.snapshot(sid)
    assert s['backend'] == 'physical' and s['history_only'] and not s['capabilities']['physical_execution']
    assert s['observations'] == original['observations'] and lab.backends == {}
    with pytest.raises(LabError, match='read-only'):
        await lab.prepare(sid)
    await lab.shutdown()
    assert lab.backends == {}

@pytest.mark.asyncio
async def test_transcript_upserts_completed_turn_without_action_or_fake_user_turn(lab):
    sid = (await lab.create())['session_id']
    before = len(lab.snapshot(sid)['messages'])
    for text, final in [('I pre', False), ('I predict pink', False), ('I predict pink.', True)]:
        await lab.tool(sid, '_record_transcript', {'role': 'user', 'text': text, 'turn_id': 'turn-1', 'final': final})
    s = lab.snapshot(sid)
    assert len(s['messages']) == before + 1
    assert s['messages'][-1]['text'] == 'I predict pink.' and s['messages'][-1]['final']
    assert s['prediction'] == '' and s['pending'] is None
    await lab.tool(sid, '_record_transcript', {'role': 'assistant', 'text': 'Confirm', 'turn_id': 'turn-2', 'final': True})
    assert lab.backends[sid].executions == 0
    with pytest.raises(LabError, match='rewritten'):
        await lab.tool(sid, '_record_transcript', {'role': 'user', 'text': 'Changed', 'turn_id': 'turn-1', 'final': True})
    with pytest.raises(LabError):
        await lab.tool(sid, '_record_transcript', {'role': 'assistant', 'text': 'I predict pink.', 'turn_id': 'turn-1', 'final': True})

@pytest.mark.asyncio
async def test_stale_generation_and_negated_trusted_voice_input_rejected(lab):
    sid, p = await proposed(lab)
    await lab.present(sid, p['request_id'], p['proposal_version'])
    with pytest.raises(LabError, match='generation'):
        await lab.tool(sid, 'record_prediction', {'text': 'purple', '_voice_generation': 999})
    with pytest.raises(LabError, match='unambiguous'):
        await lab.tool(sid, 'student_confirm', {'request_id': p['request_id'], 'proposal_version': p['proposal_version'],
                       '_voice_consent': {'request_id': p['request_id'], 'text': 'do not confirm'}})
    assert lab.backends[sid].executions == 0
