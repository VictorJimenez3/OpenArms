"""Dilution requests must preserve every requested action across lesson routing."""
import pytest

from agentic.openarms_lab.backends import MockBackend
from agentic.openarms_lab.runtime import Lab, LabError


async def prepared_lab(tmp_path, monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    backend = MockBackend(delay=0)
    lab = Lab(tmp_path, backend_factory=lambda: backend)
    candidate = await lab.registry.compose('transfer sample from A to B and observe the destination')
    evidence = lab.registry.test_candidate(candidate['skill_id'])
    lab.registry.promote(candidate['skill_id'], evidence['evidence_id'])
    session = await lab.create('color_dilution')
    sid = session['session_id']
    await lab.prediction(sid, 'Adding water should make the dye lighter.')
    return lab, backend, sid


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['A', 'C'])
@pytest.mark.parametrize('suffix', ['then inspect', 'and observe'])
@pytest.mark.parametrize('entry', ['text', 'tool'])
async def test_dilution_does_not_silently_drop_requested_inspection(tmp_path, monkeypatch, source, suffix, entry):
    lab, backend, sid = await prepared_lab(tmp_path, monkeypatch)
    try:
        before = backend.state()
        instruction = f'add water from {source} into B {suffix}'
        if entry == 'tool':
            result = await lab.tool(sid, 'request_action', {'text': instruction})
        else:
            result = await lab.request(sid, instruction)

        assert result['pending'] is None
        assert result['requests'] == []
        assert result['observations'] == []
        assert backend.state() == before
        assert sid not in lab.tasks
        reply = result['messages'][-1]['text'].lower()
        assert 'cannot' in reply and 'nothing has started' in reply
        routing = [event['data'] for event in result['notebook'] if event['kind'] == 'routing']
        assert routing[-1]['instruction'] == instruction
        assert routing[-1]['result']['status'] != 'resolved'
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_unsupported_dilution_revision_revokes_previous_dose(tmp_path, monkeypatch):
    lab, backend, sid = await prepared_lab(tmp_path, monkeypatch)
    try:
        before = backend.state()
        first = await lab.request(sid, 'add water from A into B')
        old_id = first['pending']['request_id']
        revised = await lab.request(sid, 'add water from A into B then inspect')

        assert revised['pending'] is None
        with pytest.raises(LabError, match='Stale'):
            await lab.confirm(sid, old_id)
        assert backend.state() == before
        assert revised['requests'][0]['status'] == 'cancelled'
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['A', 'C'])
async def test_supported_dilution_still_runs_with_composite_skill_registered(tmp_path, monkeypatch, source):
    lab, backend, sid = await prepared_lab(tmp_path, monkeypatch)
    try:
        result = await lab.request(sid, f'add water from {source} into B')
        request_id = result['pending']['request_id']
        await lab.confirm(sid, request_id)
        await lab.tasks[sid]

        result = lab.snapshot(sid)
        assert result['requests'][-1]['status'] == 'completed'
        assert backend.state()['portions_left'][source] == 0
        assert backend.state()['receiver_load']['B'] == 1
    finally:
        await lab.shutdown()
