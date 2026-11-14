"""Proposal/session regressions around the background task loop."""
import asyncio
import uuid

import pytest

from agentic.openarms_lab.backends import MockBackend
from agentic.openarms_lab.contracts import SkillDefinition
from agentic.openarms_lab.runtime import Lab, LabError
from agentic.tests.test_task_loop import (TestEvaluator as FakeEvaluator, TestExpert as FakeExpert,
                                         TestPerception as FakePerception)


@pytest.fixture
async def lab(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENARMS_BACKEND', 'mock')
    lab = Lab(tmp_path, backend_factory=lambda: MockBackend(delay=0),
              expert=FakeExpert(), perception=FakePerception(unknown=False))
    yield lab
    await lab.shutdown()


async def proposed(lab, sid=None):
    if sid is None:
        sid = (await lab.create())['session_id']
        await lab.choose_condition(sid, 'vinegar')
        await lab.prediction(sid, 'I predict pink')
    queued = await lab.start_task(sid, 'Make a prepared sample proposal')
    worker = lab.workers[queued['task_id']]
    await asyncio.wait_for(worker, 1)
    return sid, lab.snapshot(sid)['pending']


@pytest.mark.asyncio
async def test_trial_and_reflection_preserve_independent_provenance(lab):
    sid, r = await proposed(lab)
    assert r['condition_id'] == 'vinegar'
    assert not r['presented']
    await lab.present(sid, r['request_id'], r['proposal_version'])
    await lab.confirm(sid, r['request_id'], r['proposal_version'])
    await lab.workers[r['task_id']]
    s = lab.snapshot(sid)
    assert s['trial']['state'] == 'reflecting' and s['state']['at'] == 'HOME'
    result = s['requests'][0]['result']
    assert result['controller_completed'] and not result['physical_execution']
    assert 'observation' not in result
    obs = s['observations'][0]
    assert (obs['request_id'], obs['trial_id']) == (r['request_id'], r['trial_id'])
    assert obs['provenance'] == 'SYNTHETIC' and obs['checks'] == {'readable': True}
    s = await lab.reflection(sid, 'The fixture provided a readable observation.')
    assert s['trial']['state'] == 'complete'
    assert s['trial']['reflection']['evidence'] == obs['evidence']
    assert 'SYNTHETIC' in s['messages'][-1]['text']


@pytest.mark.asyncio
async def test_presentation_exact_version_and_concurrent_confirmation(lab):
    sid, r = await proposed(lab)
    with pytest.raises(LabError, match='presented'):
        await lab.confirm(sid, r['request_id'], r['proposal_version'])
    for version in (None, True, '1', 0, r['proposal_version'] + 1):
        with pytest.raises(LabError):
            await lab.confirm(sid, r['request_id'], version)
    await lab.present(sid, r['request_id'], r['proposal_version'])
    outcomes = await asyncio.gather(
        *(lab.confirm(sid, r['request_id'], r['proposal_version']) for _ in range(5)),
        return_exceptions=True)
    assert sum(not isinstance(item, Exception) for item in outcomes) == 1
    if r['task_id'] in lab.workers:
        await lab.workers[r['task_id']]
    assert lab.backends[sid].executions == 1


@pytest.mark.asyncio
async def test_correction_cancel_reconnect_and_expiry_revoke_presentations(lab):
    sid, first = await proposed(lab)
    await lab.present(sid, first['request_id'], first['proposal_version'])
    s = await lab.choose_condition(sid, 'water')
    assert s['pending'] is None and s['requests'][0]['status'] == 'cancelled'
    with pytest.raises(LabError):
        await lab.confirm(sid, first['request_id'], first['proposal_version'])
    _, second = await proposed(lab, sid)
    assert second['condition_id'] == 'water' and second['proposal_version'] > first['proposal_version']
    await lab.cancel(sid, second['task_id'])
    assert lab.snapshot(sid)['pending'] is None
    _, third = await proposed(lab, sid)
    await lab.present(sid, third['request_id'], third['proposal_version'], 'audio', 'reply-id')
    s = await lab.reconnected(sid)
    assert s['pending'] is None and s['generation'] > third['generation']
    with pytest.raises(LabError):
        await lab.confirm(sid, third['request_id'], third['proposal_version'])
    _, fourth = await proposed(lab, sid)
    lab.get(sid)['pending']['expires_at'] = 0
    with pytest.raises(LabError, match='expired'):
        await lab.present(sid, fourth['request_id'], fourth['proposal_version'])
    persisted = lab.store.load(sid)
    assert persisted['pending'] is None and persisted['requests'][-1]['status'] == 'expired'
    assert lab.backends[sid].executions == 0


@pytest.mark.asyncio
async def test_stop_before_dispatch_keeps_home_and_allows_prepare(lab):
    sid, r = await proposed(lab)
    await lab.present(sid, r['request_id'], r['proposal_version'])
    await lab.confirm(sid, r['request_id'], r['proposal_version'])
    s = await lab.stop(sid)
    assert lab.backends[sid].executions == 0
    assert s['requests'][0]['status'] == 'stopped'
    assert s['state']['at'] == 'HOME'
    assert (await lab.prepare(sid))['trial']['state'] == 'choosing_condition'


@pytest.mark.asyncio
async def test_stop_during_dispatch_releases_controller(lab):
    sid, r = await proposed(lab)
    lab.backends[sid].delay = 5
    await lab.present(sid, r['request_id'], r['proposal_version'])
    await lab.confirm(sid, r['request_id'], r['proposal_version'])
    async with asyncio.timeout(1):
        while not lab.backends[sid].executions:
            await asyncio.sleep(0)
    stopped = await asyncio.wait_for(lab.reconnected(sid), 1)
    assert stopped['connected'] and stopped['requests'][0]['status'] == 'stopped'
    assert stopped['state']['at'] == 'HOME'
    await lab.prepare(sid)
    assert lab.backends[sid].executions == 1


@pytest.mark.asyncio
async def test_subscribers_receive_latest_independent_snapshots(lab):
    sid = (await lab.create())['session_id']
    q1, q2 = asyncio.Queue(maxsize=1), asyncio.Queue(maxsize=1)
    lab.subscribers[sid] = {q1, q2}
    a = await lab.choose_condition(sid, 'water')
    b = await lab.prediction(sid, 'purple')
    first, second = q1.get_nowait(), q2.get_nowait()
    assert b['revision'] > a['revision']
    assert first['state']['revision'] == b['revision']
    first['state']['prediction'] = 'corrupted'
    assert second['state']['prediction'] == lab.snapshot(sid)['prediction'] == 'purple'


@pytest.mark.asyncio
async def test_invalid_ids_inputs_and_tools_fail(lab):
    with pytest.raises(LabError):
        lab.snapshot('../etc')
    with pytest.raises(KeyError):
        lab.snapshot(str(uuid.uuid4()))
    sid = (await lab.create())['session_id']
    for condition in ('acid', '', {'id': 'water'}, None):
        with pytest.raises(LabError):
            await lab.choose_condition(sid, condition)
    for prediction in ('', ' ', 1, None, 'x' * 4001):
        with pytest.raises(LabError):
            await lab.prediction(sid, prediction)
    with pytest.raises(LabError):
        await lab.tool(sid, 'request_action', {'text': 'run it', 'parameters': {'source': 'B'}})
    with pytest.raises(LabError):
        await lab.tool(sid, 'choose_condition', {})


@pytest.mark.asyncio
async def test_backend_binding_precedes_prepare_and_is_isolated(tmp_path):
    class BoundBackend(MockBackend):
        def bind_session(self, sid):
            assert not hasattr(self, 'sid')
            self.sid = sid
            self.prepares = 0

        def prepare(self):
            assert self.sid
            self.prepares += 1
            super().prepare()

    lab = Lab(tmp_path, backend_factory=BoundBackend)
    try:
        first = (await lab.create())['session_id']
        second = (await lab.create())['session_id']
        assert first != second
        await lab.prepare(first)
        assert (lab.backends[first].sid, lab.backends[first].prepares) == (first, 2)
        assert (lab.backends[second].sid, lab.backends[second].prepares) == (second, 1)
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_individual_warm_mock_commands_keep_fixture_state(lab):
    lab.expert = None
    sid = (await lab.create())['session_id']
    other = (await lab.create())['session_id']
    commands = [
        ('pick up the cup at a', 'mock_pick_up', 'A', 'sample_cup', None, 0),
        ('pour into c', 'mock_pour', 'C', 'sample_cup', None, 1),
        ('put the cup down at b', 'mock_put_down', 'B', None, 'B', 1),
    ]
    for text, op, station, holding, cup_station, receiver_portions in commands:
        definition = SkillDefinition.model_validate({
            'skill_id': op, 'name': op, 'intent': text, 'retrieval_examples': [text],
            'steps': [{'operation': 'inspect_scene'},
                      {'operation': op, 'arguments': {'fixture': 'sample_cup', 'station': station}},
                      {'operation': 'observe'}],
            'outcome_checks': [{'feature': 'readable', 'expected': True}],
            'limitations': ['Synthetic fixture and test observer.'],
        })
        version = lab.registry.validate_for_task('fixture-setup', definition)
        candidate = lab.registry.get(op, version)
        evaluation = await FakeEvaluator().evaluate_candidate(sid, candidate, None)
        evaluation['evaluation_id'] += '-' + op
        lab.registry.record_evaluation(op, version, evaluation)
        queued = await lab.converse(sid, text)
        await lab.workers[queued['tasks'][-1]['task_id']]
        snap = lab.snapshot(sid)
        p = snap['pending']
        if op == 'mock_pick_up':
            # Optional settings remain usable without changing this proposal's consent.
            await lab.choose_condition(sid, 'water')
            await lab.prediction(sid, 'purple')
            assert lab.snapshot(sid)['pending']['request_id'] == p['request_id']
        await lab.present(sid, p['request_id'], p['proposal_version'])
        await lab.converse(sid, 'confirm')
        await lab.workers[p['task_id']]
        snap = lab.snapshot(sid)
        assert snap['tasks'][-1]['status'] == 'completed'
        assert snap['tasks'][-1]['expert_runs'] == []
        assert snap['requests'][-1]['result']['operation'] == op
        assert (snap['state']['holding'], snap['state']['cup_station'],
                snap['state']['receiver_portions']) == (holding, cup_station, receiver_portions)
    assert lab.backends[sid].executions == 3 and lab.backends[other].executions == 0
    assert lab.snapshot(other)['state'] == MockBackend.home_state()
    await lab.converse(sid, 'pour into c')
    await lab.workers[lab.snapshot(sid)['tasks'][-1]['task_id']]
    assert lab.snapshot(sid)['tasks'][-1]['status'] == 'failed'
    assert lab.backends[sid].executions == 3
