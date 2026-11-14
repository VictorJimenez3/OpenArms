import asyncio

import pytest

from agentic.openarms_lab.runtime import Lab, LabError
from agentic.tests.test_lab_runtime import lab, proposed, FakeEvaluator


@pytest.mark.asyncio
async def test_stop_cancels_pending_promotion_and_keeps_candidate_inactive(lab):
    entered, cancelled = asyncio.Event(), asyncio.Event()

    class PausedEvaluator(FakeEvaluator):
        async def evaluate_candidate(self, *args):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    sid, proposal = await proposed(lab)
    await lab.present(sid, proposal['request_id'], proposal['proposal_version'])
    await lab.confirm(sid, proposal['request_id'], proposal['proposal_version'])
    await lab.workers[proposal['task_id']]
    lab.evaluator = PausedEvaluator()
    evaluation = asyncio.create_task(lab.evaluate_candidate(sid, proposal['skill_id'], proposal['skill_version']))
    await entered.wait()
    await lab.stop(sid, disconnect=True)
    with pytest.raises(asyncio.CancelledError):
        await evaluation
    assert cancelled.is_set()
    assert not lab.registry.list()
    with pytest.raises(LabError, match='disconnected'):
        await lab.evaluate_candidate(sid, proposal['skill_id'], proposal['skill_version'])


@pytest.mark.asyncio
async def test_changed_execution_scope_restores_passive_history_without_backend(tmp_path):
    original = Lab(tmp_path, execution_scope='mock-v1')
    sid = (await original.create())['session_id']
    await original.shutdown()
    def forbidden():
        raise AssertionError('Restoring history initialized the new simulator')
    changed = Lab(tmp_path, backend_factory=forbidden, execution_scope='mujoco-new-apparatus')
    try:
        state = changed.snapshot(sid)
        assert state['history_only'] and state['backend'] == 'mock'
        assert state['execution_scope'] == 'mock-v1'
        with pytest.raises(LabError, match='read-only'):
            await changed.reconnected(sid)
        assert not changed.backends
    finally:
        await changed.shutdown()


@pytest.mark.asyncio
async def test_unbound_typed_confirmation_cannot_approve_a_replacement(lab):
    sid, first = await proposed(lab)
    await lab.present(sid, first['request_id'], first['proposal_version'])
    await lab.prediction(sid, 'A different prediction')
    assert lab.snapshot(sid)['pending'] is None
    _, second = await proposed(lab, sid)
    await lab.present(sid, second['request_id'], second['proposal_version'])
    await lab.converse(sid, 'confirm')
    assert lab.backends[sid].executions == 0
    with pytest.raises(LabError):
        await lab.confirm(sid, first['request_id'], first['proposal_version'])


@pytest.mark.asyncio
async def test_setup_revision_change_revokes_presented_proposal(lab):
    lab.execution_scope = 'setup-v1'
    sid, proposal = await proposed(lab)
    exact = (sid, proposal['request_id'], proposal['proposal_version'])
    await lab.present(*exact)
    lab.execution_scope = 'setup-v2'
    with pytest.raises(LabError, match='Proposal binding changed'):
        await lab.confirm(*exact)
    assert lab.snapshot(sid)['pending'] is None
    assert lab.backends[sid].executions == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['text', 'tool', 'task', 'request'])
@pytest.mark.parametrize('suppress_cancel', [False, True])
async def test_cancel_revokes_pending_promotion_even_if_evaluator_ignores_cancel(lab, method, suppress_cancel):
    entered, release = asyncio.Event(), asyncio.Event()
    class PausedEvaluator(FakeEvaluator):
        async def evaluate_candidate(self, *args):
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                if not suppress_cancel:
                    raise
                await release.wait()
            return await super().evaluate_candidate(*args)
    sid, proposal = await proposed(lab)
    await lab.present(sid, proposal['request_id'], proposal['proposal_version'])
    await lab.confirm(sid, proposal['request_id'], proposal['proposal_version'])
    await lab.workers[proposal['task_id']]
    lab.evaluator = PausedEvaluator()
    evaluation = asyncio.create_task(lab.evaluate_candidate(sid, proposal['skill_id'], proposal['skill_version']))
    await entered.wait()
    if method == 'text':
        await lab.converse(sid, 'cancel')
    elif method == 'tool':
        await lab.tool(sid, 'cancel_request', {})
    else:
        await lab.cancel(sid, proposal['task_id' if method == 'task' else 'request_id'])
    release.set()
    with pytest.raises((asyncio.CancelledError, LabError)):
        await evaluation
    assert not lab.registry.list()
    assert any(e['kind'] == 'skill_evaluation_cancelled' for e in lab.get(sid)['notebook'])


@pytest.mark.asyncio
async def test_targeted_evaluation_cancel_preserves_new_pending_task(lab):
    entered = asyncio.Event()
    class PausedEvaluator(FakeEvaluator):
        async def evaluate_candidate(self, *args):
            entered.set()
            await asyncio.Event().wait()
    sid, first = await proposed(lab)
    await lab.present(sid, first['request_id'], first['proposal_version'])
    await lab.confirm(sid, first['request_id'], first['proposal_version'])
    await lab.workers[first['task_id']]
    lab.evaluator = PausedEvaluator()
    evaluation = asyncio.create_task(lab.evaluate_candidate(sid, first['skill_id'], first['skill_version']))
    await entered.wait()
    await lab.prepare(sid)
    _, second = await proposed(lab, sid)
    generation = lab.get(sid)['generation']
    await lab.cancel(sid, first['task_id'])
    with pytest.raises(asyncio.CancelledError):
        await evaluation
    assert lab.get(sid)['generation'] == generation
    assert lab.snapshot(sid)['pending']['request_id'] == second['request_id']
