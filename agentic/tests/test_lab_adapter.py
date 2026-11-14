"""The app's hardware boundary is closed; mock execution is symbolic and one-use."""
import asyncio
import uuid
import pytest
from pydantic import ValidationError
from agentic.openarms_lab.backends import MockBackend, TransferRunnerAdapter
from agentic.openarms_lab.contracts import Parameters, SkillRequest
from agentic.openarms_lab.recipes import PH_SKILL
from agentic.openarms_lab.skills import compute_skill_hash
from agentic.openarms_lab.runtime import Lab, LabError


def request(**changes):
    fields = dict(request_id=str(uuid.uuid4()), session_id=str(uuid.uuid4()), trial_id=str(uuid.uuid4()),
                  proposal_version=1, generation=0, skill_id=PH_SKILL.skill_id,
                  skill_version=PH_SKILL.version, skill_hash=compute_skill_hash(PH_SKILL),
                  prediction='Pink and acidic', parameters=Parameters(condition_id='vinegar'))
    return SkillRequest(**(fields | changes))

async def progress(_):
    pass

@pytest.mark.asyncio
async def test_mock_reuses_skill_but_consumes_each_request_once_and_returns_home():
    backend = MockBackend(delay=0)
    req = request()
    receipt = await backend.execute(req, progress)
    assert receipt.status == 'completed' and receipt.controller_completed
    assert receipt.physical_success is None and not receipt.operator_authorized
    assert 'observation' not in receipt.model_dump()
    assert backend.state()['at'] == 'HOME'
    with pytest.raises(ValueError, match='consumed'):
        await backend.execute(req, progress)
    receipt2 = await backend.execute(request(), progress)
    assert receipt2.status == 'completed'
    assert receipt2.evidence_id != receipt.evidence_id and backend.executions == 2

@pytest.mark.asyncio
async def test_changed_hash_and_parameters_fail_before_execution():
    backend = MockBackend(delay=0)
    with pytest.raises(ValueError, match='reviewed'):
        await backend.execute(request(skill_hash='0' * 64), progress)
    for parameters in ({'condition_id': 'water', 'source': 'B'}, {'condition_id': 'bleach'}, {'condition_id': 'water', 'volume': 50}):
        with pytest.raises(ValidationError):
            request(parameters=parameters)
    assert backend.executions == 0

@pytest.mark.asyncio
async def test_stop_during_mock_and_no_state_leak_between_trials():
    backend = MockBackend(delay=.1)
    async def stop_on_progress(phase):
        if phase == 'mock_dose':
            await backend.stop()
    receipt = await backend.execute(request(), stop_on_progress)
    assert receipt.status == 'stopped' and not receipt.controller_completed
    assert backend.state()['at'] == 'HOME'
    backend.prepare()
    backend.delay = 0
    assert (await backend.execute(request(), progress)).status == 'completed'

@pytest.mark.asyncio
async def test_concurrent_requests_are_not_queued_or_replayed():
    backend = MockBackend(delay=.01)
    started, gate = asyncio.Event(), asyncio.Event()
    async def hold(_):
        started.set()
        await gate.wait()
    task = asyncio.create_task(backend.execute(request(), hold))
    await started.wait()
    with pytest.raises(ValueError, match='not ready'):
        await backend.execute(request(), progress)
    gate.set()
    await task
    assert backend.executions == 1

@pytest.mark.parametrize('entry', ['constructor', 'loader'])
def test_physical_is_explicitly_unavailable_without_touching_runner(entry):
    class NeverInspect:
        def __getattribute__(self, name):
            raise AssertionError('Hardware runner was inspected')
    with pytest.raises(ValueError, match='unavailable'):
        TransferRunnerAdapter(NeverInspect()) if entry == 'constructor' else TransferRunnerAdapter.load('/does/not/exist', 'hardware:create')

@pytest.mark.asyncio
async def test_physical_environment_blocks_new_sessions_without_hardware(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENARMS_BACKEND', 'physical')
    lab = Lab(tmp_path)
    with pytest.raises(LabError, match='unavailable'):
        await lab.create()
    assert lab.backends == {}
    await lab.shutdown()
