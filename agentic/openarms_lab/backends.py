"""Hardware-free mock pH executor. Physical app execution is explicitly disabled."""
from __future__ import annotations
import asyncio
import copy
import uuid
import time
from .contracts import ExecutionResult, PRIMITIVE_SCHEMAS, SkillRequest
from .recipes import PH_SKILL
from .skills import compute_skill_hash

MOCK_PHASES = {
    'mock_prepared_sample': ('check_prepared_condition', 'mock_dose', 'return_home'),
    'mock_pick_up': ('mock_pick_up',),
    'mock_put_down': ('mock_put_down',),
    'mock_pour': ('mock_pour',),
}

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
                'cup_station': 'A', 'cup_portions': 1, 'receiver_portions': 0,
                'state_provenance': 'MOCK', 'physical_execution': False}

    @staticmethod
    def capabilities():
        return {'experiment_id': 'indicator_ph', 'conditions': list(PH_SKILL.conditions),
                'routes': [['A', 'C']], 'mock_execution': True, 'physical_execution': False,
                'supported_operations': list(MOCK_PHASES),
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

    def check_step(self, operation, arguments):
        if operation not in MOCK_PHASES:
            raise ValueError('Unsupported mock action.')
        PRIMITIVE_SCHEMAS[operation].model_validate(arguments)
        state = self._state
        if operation == 'mock_pick_up':
            if state['holding'] or state['cup_station'] != arguments['station']:
                raise ValueError('Pick up requires the sample cup at the requested station and an empty gripper.')
        elif operation == 'mock_put_down':
            if not state['holding']:
                raise ValueError('Put down requires a held sample cup.')
        elif operation == 'mock_pour':
            if not state['holding'] or state['cup_portions'] != 1 or state['receiver_portions'] != 0:
                raise ValueError('Pour requires a held full cup and an empty receiver.')
        elif state['holding']:
            raise ValueError('Prepared sample execution requires an empty gripper.')

    async def execute_step(self, request_id, arguments, progress, *, operation='mock_prepared_sample'):
        """Run a bounded mock action once and commit its state after successful execution."""
        self.check_step(operation, arguments)
        if request_id in self._consumed or self._running or self._state['at'] != 'HOME':
            raise ValueError('Mock execution already consumed or not ready.')
        self._consumed.add(request_id)
        self._running = True
        self._idle.clear()
        self.executions += 1
        self._stopped.clear()
        started = time.perf_counter()
        try:
            for phase in MOCK_PHASES[operation]:
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
            if operation == 'mock_pick_up':
                self._state.update(holding='sample_cup', cup_station=None)
            elif operation == 'mock_put_down':
                self._state.update(holding=None, cup_station=arguments['station'])
            elif operation == 'mock_pour':
                self._state.update(cup_portions=0, receiver_portions=1)
            return {'receipt_id': 'mock-' + uuid.uuid4().hex, 'backend': self.mode,
                    'request_id': request_id, 'operation': operation,
                    'status': 'completed', 'controller_completed': True,
                    'elapsed_ms': (time.perf_counter() - started) * 1000,
                    'physical_execution': False}
        finally:
            self._running = False
            self._state.update(at='HOME', phase='ready')
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
