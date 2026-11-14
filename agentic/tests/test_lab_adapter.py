"""Safety regression checks with stand-in runners only; never connects hardware."""
import asyncio
import threading
from types import SimpleNamespace

import pytest

from agentic.openarms_lab.backends import MockBackend, TransferRunnerAdapter
from agentic.openarms_lab.contracts import SkillRequest
from agentic.openarms_lab.runtime import Lab


def request(pid='plan-1', source='A', session='student-1', obj='mandarin'):
    return SkillRequest(request_id=pid, session_id=session, skill_id='transfer',
                        parameters={'object': obj, 'source': source, 'destination': 'B'})


async def progress(_phase):
    pass


class StandInRunner:
    mode = 'physical'

    def __init__(self, *, answer=True, result=None):
        self.scripts = {'A': None}
        self.answer = answer
        self.result = result
        self.calls = []
        self.stops = 0

    async def authorize(self, plan):
        self.calls.append(('authorize', plan))
        return self.answer

    async def execute(self, plan):
        self.calls.append(('execute', plan))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result or SimpleNamespace(plan_id=plan['plan_id'], mode='physical',
                                              status='completed', operator_authorized=True,
                                              placement='B')

    async def stop(self):
        self.stops += 1


@pytest.mark.asyncio
async def test_student_confirmation_and_operator_permission_are_independent(tmp_path):
    runner = StandInRunner(answer=False)
    lab = Lab(tmp_path, backend_factory=lambda: TransferRunnerAdapter(runner))
    sid = (await lab.create())['session_id']
    await lab.prediction(sid, 'The mandarin may reach B; placement needs observation.')
    proposal = await lab.request(sid, 'move orange from A to B', 'student-request')
    assert runner.calls == []
    await lab.confirm(sid, proposal['pending']['request_id'])
    await lab.tasks[sid]
    trial = lab.snapshot(sid)['requests'][-1]
    assert trial['student_confirmed'] is True
    assert trial['operator_authorized'] is False
    assert trial['status'] == 'rejected'
    assert [call[0] for call in runner.calls] == ['authorize']


@pytest.mark.asyncio
@pytest.mark.parametrize('answer', [False, None, 1, 'yes'])
async def test_only_exact_operator_true_authorizes(answer):
    runner = StandInRunner(answer=answer)
    adapter = TransferRunnerAdapter(runner)
    assert await adapter.authorize(request()) is False
    with pytest.raises(ValueError, match='not authorized'):
        await adapter.execute(request(), progress)
    assert not any(kind == 'execute' for kind, _ in runner.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [{'source': 'C'}, {'session': 'other-student'}])
async def test_operator_permission_binds_whole_request_and_is_consumed(change):
    runner = StandInRunner()
    runner.scripts['C'] = None
    adapter = TransferRunnerAdapter(runner)
    assert await adapter.authorize(request()) is True
    with pytest.raises(ValueError, match='not authorized'):
        await adapter.execute(request(**change), progress)
    with pytest.raises(ValueError, match='not authorized'):
        await adapter.execute(request(), progress)
    assert not any(kind == 'execute' for kind, _ in runner.calls)


@pytest.mark.asyncio
async def test_concurrent_authorization_and_stop_before_motion_are_blocked():
    runner = StandInRunner()
    adapter = TransferRunnerAdapter(runner)
    assert await adapter.authorize(request()) is True
    with pytest.raises(ValueError, match='already authorized'):
        await adapter.authorize(request('plan-2'))

    async def stop_during_progress(_phase):
        await adapter.stop()

    with pytest.raises(ValueError, match='revoked'):
        await adapter.execute(request(), stop_during_progress)
    assert not any(kind == 'execute' for kind, _ in runner.calls)
    assert adapter.state()['armed'] is False


@pytest.mark.asyncio
async def test_cancelled_terminal_prompt_is_shielded_drained_and_cannot_execute():
    entered = asyncio.Event()
    answer = threading.Event()

    class TerminalRunner(StandInRunner):
        async def authorize(self, plan):
            self.calls.append(('authorize', plan))
            entered.set()
            return await asyncio.to_thread(answer.wait)

    runner = TerminalRunner()
    adapter = TransferRunnerAdapter(runner)
    task = asyncio.create_task(adapter.authorize(request()))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not adapter._authorization.done()
        with pytest.raises(ValueError, match='prompt is still open'):
            await adapter.authorize(request('plan-2'))
        answer.set()  # late terminal yes completes the original prompt only
        await asyncio.wait_for(adapter._authorization, timeout=1)
        with pytest.raises(ValueError, match='not authorized'):
            await adapter.execute(request(), progress)
        with pytest.raises(ValueError, match='restart'):
            await adapter.authorize(request('plan-3'))
        assert not any(kind == 'execute' for kind, _ in runner.calls)
    finally:
        answer.set()
        await asyncio.wait_for(adapter._authorization, timeout=1)


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('plan_id', 'other-plan'), ('mode', 'mock'),
                                        ('operator_authorized', False), ('operator_authorized', 1),
                                        ('status', 'success')])
async def test_mismatched_runner_result_fails_closed(field, value):
    result = SimpleNamespace(plan_id='plan-1', mode='physical', status='completed', operator_authorized=True)
    setattr(result, field, value)
    runner = StandInRunner(result=result)
    adapter = TransferRunnerAdapter(runner)
    await adapter.authorize(request())
    with pytest.raises(ValueError, match='mismatch'):
        await adapter.execute(request(), progress)
    assert runner.stops == 1
    assert not adapter.state()['armed']
    with pytest.raises(ValueError):
        await adapter.execute(request(), progress)
    assert sum(kind == 'execute' for kind, _ in runner.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['completed', 'failed', 'stopped', 'unknown'])
async def test_controller_status_never_fabricates_physical_observation(status):
    runner = StandInRunner(result=SimpleNamespace(plan_id='plan-1', mode='physical', status=status,
                                                 operator_authorized=True, placement='B'))
    adapter = TransferRunnerAdapter(runner)
    await adapter.authorize(request())
    result = await adapter.execute(request(), progress)
    assert result.status == status
    assert result.controller_completed is (status == 'completed')
    assert result.physical_success is None
    assert result.observation.provenance == 'UNKNOWN'
    assert result.observation.value is None
    assert result.observation.evidence == []
    assert adapter.state()['point_holds']['B'] is None
    assert adapter.state()['state_provenance'] == 'UNKNOWN'
    with pytest.raises(ValueError):
        await adapter.authorize(request())


@pytest.mark.asyncio
async def test_execution_exception_never_retries_or_rearms():
    runner = StandInRunner(result=ConnectionError('stand-in disconnected'))
    adapter = TransferRunnerAdapter(runner)
    await adapter.authorize(request())
    with pytest.raises(ConnectionError):
        await adapter.execute(request(), progress)
    with pytest.raises(ValueError):
        await adapter.execute(request(), progress)
    assert sum(kind == 'execute' for kind, _ in runner.calls) == 1
    assert runner.stops == 1
    assert not adapter.state()['armed']


@pytest.mark.asyncio
async def test_capabilities_only_expose_configured_loaded_transfer_routes():
    runner = StandInRunner()
    adapter = TransferRunnerAdapter(runner)
    assert adapter.capabilities()['routes'] == [['A', 'B']]
    with pytest.raises(ValueError, match='Unsupported'):
        await adapter.authorize(request(source='C'))
    with pytest.raises(ValueError, match='Unsupported'):
        await adapter.authorize(request(obj='sample'))
    assert runner.calls == []
    runner.scripts.update(C=None, arbitrary_pose=None)
    assert adapter.capabilities()['routes'] == [['A', 'B'], ['C', 'B']]
    for flag in ('dry_approach', 'empty'):
        setattr(runner, flag, True)
        assert adapter.capabilities()['routes'] == []
        setattr(runner, flag, False)


def test_firmware_fake_robot_is_not_physical():
    class FakeRobot:
        pass

    class ChildFake(FakeRobot):
        pass

    runner = StandInRunner()
    runner.robot = ChildFake()
    with pytest.raises(ValueError, match='FakeRobot'):
        TransferRunnerAdapter(runner)


def test_loader_reads_selected_checkout_without_stale_module_singletons(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENARMS_FAKE_ROBOT', raising=False)
    for token in ('first-checkout', 'current-checkout'):
        root = tmp_path / token
        firmware = root / 'firmware'
        firmware.mkdir(parents=True)
        (firmware / '__init__.py').write_text('')
        (firmware / 'source.py').write_text(f'TOKEN = {token!r}\n')
        (firmware / 'runner.py').write_text(
            'from types import SimpleNamespace\nfrom .source import TOKEN\n'
            'def create_runner():\n    return SimpleNamespace(mode="physical", token=TOKEN)\n')
        adapter = TransferRunnerAdapter.load(str(root), 'firmware.runner:create_runner')
        assert adapter.runner.token == token


def test_loader_refuses_fake_mode_before_factory(tmp_path, monkeypatch):
    (tmp_path / 'firmware').mkdir()
    monkeypatch.setenv('OPENARMS_FAKE_ROBOT', '1')
    with pytest.raises(ValueError, match='FakeRobot'):
        TransferRunnerAdapter.load(str(tmp_path), 'firmware.not_imported:create_runner')


@pytest.mark.asyncio
async def test_mock_mode_never_loads_hardware(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENARMS_BACKEND', 'mock')
    monkeypatch.setenv('OPENARMS_HARDWARE_CHECKOUT', '/hardware/must/not/be/loaded')

    def forbidden_load(*_args):
        pytest.fail('mock session tried to load physical hardware')

    monkeypatch.setattr(TransferRunnerAdapter, 'load', forbidden_load)
    lab = Lab(tmp_path)
    state = await lab.create()
    assert state['backend'] == 'mock'
    assert isinstance(lab._backend(state['session_id']), MockBackend)
