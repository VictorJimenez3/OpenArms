"""Hardware-free mock pH executor. Physical app execution is explicitly disabled."""
from __future__ import annotations
import asyncio
import copy
import uuid
import time
from .contracts import ExecutionResult, MockSampleArguments, SkillRequest
from .recipes import PH_SKILL
from .skills import compute_skill_hash

class MockStopped(RuntimeError):
    pass


class MockBackend:
    mode = 'mock'

    def __init__(self, delay: float = .04, fault: str | None = None):
        if delay < 0:
            raise ValueError('Mock delay must be nonnegative.')
        self.delay, self.fault = delay, fault
        self._stopped = asyncio.Event()
        self._idle = asyncio.Event()
        self._idle.set()
        self._consumed: set[str] = set()
        self._running = False
        self.executions = 0
        self._state = self.home_state()

    @staticmethod
    def home_state():
        return {'at': 'HOME', 'holding': None, 'armed': True, 'phase': 'ready',
                'state_provenance': 'MOCK', 'physical_execution': False}

    @staticmethod
    def capabilities():
        return {'experiment_id': 'red_cabbage_ph', 'conditions': list(PH_SKILL.conditions),
                'routes': [['A', 'C']], 'mock_execution': True, 'physical_execution': False,
                'measurement': False, 'observation_provenance': 'independent_or_unknown',
                'limitations': PH_SKILL.limitations}

    def state(self):
        return copy.deepcopy(self._state)

    def prepare(self):
        if self._running:
            raise ValueError('Cannot reset an active mock trial.')
        self._state = self.home_state()
        self._stopped.clear()

    async def authorize(self, request):
        return True  # Mock dispatch only; never reports operator authorization.

    async def execute(self, request, progress):
        request = SkillRequest.model_validate(request)
        if (request.skill_hash != compute_skill_hash(PH_SKILL) or
                request.skill_id != PH_SKILL.skill_id or request.skill_version != PH_SKILL.version):
            raise ValueError('Execution does not match the reviewed pH skill.')
        try:
            result = await self.execute_step(request.request_id, {
                'condition_id': request.parameters.condition_id,
                'source': request.parameters.source,
                'destination': request.parameters.destination,
            }, progress)
            return ExecutionResult(request_id=request.request_id, trial_id=request.trial_id,
                                   status='completed', controller_completed=True,
                                   evidence_id=result['receipt_id'])
        except MockStopped:
            return ExecutionResult(request_id=request.request_id, trial_id=request.trial_id,
                                   status='stopped', reason='Mock STOP requested.',
                                   evidence_id='mock-' + uuid.uuid4().hex)

    async def execute_step(self, request_id, arguments, progress):
        """Run one validated prepared-sample operation in the mock fixture."""
        MockSampleArguments.model_validate(arguments)
        if request_id in self._consumed or self._running or self._state['at'] != 'HOME':
            raise ValueError('Mock execution already consumed or not ready.')
        self._consumed.add(request_id)
        self._running = True
        self._idle.clear()
        self.executions += 1
        self._stopped.clear()
        started = time.perf_counter()
        try:
            for phase in ('check_prepared_condition', 'mock_dose', 'return_home'):
                self._state.update(phase=phase, at='HOME' if phase == 'return_home' else 'MOCK_FIXTURE')
                await progress(phase)
                if self.fault == 'timeout':
                    await self._stopped.wait()
                elif self.delay:
                    try:
                        await asyncio.wait_for(self._stopped.wait(), timeout=self.delay)
                    except TimeoutError:
                        pass
                if self._stopped.is_set():
                    raise MockStopped('Mock STOP requested.')
                if self.fault in ('disconnect', 'failure'):
                    raise RuntimeError('Mock executor reported failure.')
            return {'receipt_id': 'mock-' + uuid.uuid4().hex, 'backend': self.mode,
                    'request_id': request_id, 'status': 'completed', 'controller_completed': True,
                    'elapsed_ms': (time.perf_counter() - started) * 1000,
                    'physical_execution': False}
        finally:
            self._running = False
            self._state = self.home_state()
            self._idle.set()

    def reference_available(self):
        return self.fault not in ('unknown', 'no_observation')

    async def stop(self):
        self._stopped.set()

    async def wait_idle(self):
        await self._idle.wait()

class TransferRunnerAdapter:
    """Explicit tombstone; loading app history never imports a hardware runner."""
    mode = 'physical'

    def __init__(self, *args, **kwargs):
        raise ValueError('Physical app execution is unavailable. Use the pH mock backend.')

    @classmethod
    def load(cls, *args, **kwargs):
        raise ValueError('Physical app execution is unavailable; no hardware was loaded.')
