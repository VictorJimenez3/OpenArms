"""Mock execution and a bridge to the CURRENT hardware checkout's TransferRunner.

No controller module is imported and no hardware connection is made in mock mode.
The async runner boundary preserves the iPhone relay contract in docs/INTERFACES.md.
"""
from __future__ import annotations
import asyncio
import importlib
import sys
import types
from pathlib import Path
from .contracts import ExecutionResult, Observation, SkillRequest

class MockBackend:
    mode = 'mock'
    def __init__(self, delay: float = .18, fault: str | None = None):
        self.delay, self.fault = delay, fault
        self._stopped = asyncio.Event()
        self._consumed: set[str] = set()
        self._state = {'at': 'HOME', 'holding': None, 'armed': True,
                       'portions_left': {}, 'receiver_load': {},
                       'point_holds': {'A': 'sample', 'C': 'sample', 'B': None}}
    def capabilities(self):
        return {'routes': [['A','B'], ['C','B']], 'objects': ['mandarin','sample'],
                'controller': 'transfer', 'observation_provenance': 'MOCK'}
    def state(self):
        import copy
        return copy.deepcopy(self._state)
    async def authorize(self, request):
        return True  # mock has no physical operator; result does not claim one
    def prepare(self, obj='sample'):
        if not self._state['armed']:
            raise ValueError('Start a new mock session after a stop or fault.')
        self._state['point_holds'] = {'A': obj, 'C': obj, 'B': None}
        self._state.update(at='HOME', holding=None)
    async def execute(self, request, progress):
        p = request.parameters
        if request.request_id in self._consumed:
            raise ValueError('Execution request already consumed.')
        if [p.source,p.destination] not in self.capabilities()['routes']:
            raise ValueError('Unsupported route.')
        self._consumed.add(request.request_id)
        self._stopped.clear()
        for phase in ('approaching_source', 'grasping', 'carrying', 'placing', 'returning_home'):
            await progress(phase)
            if self.fault == 'timeout':
                await self._stopped.wait()
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.delay)
                self._state['armed'] = False
                return ExecutionResult(request_id=request.request_id, backend=self.mode, status='stopped',reason='STOP requested.')
            except TimeoutError:
                pass
            if self.fault == 'disconnect' and phase == 'carrying':
                self._state['armed'] = False
                raise ConnectionError('Injected mock controller disconnection.')
            if self.fault == 'failure' and phase == 'grasping':
                self._state['armed'] = False
                return ExecutionResult(request_id=request.request_id,backend=self.mode,status='failed',reason='Injected mock grasp failure.')
        self._state['point_holds'][p.source] = None
        self._state['point_holds'][p.destination] = p.object
        unknown = self.fault == 'unknown'
        return ExecutionResult(request_id=request.request_id,backend=self.mode,status='completed',controller_completed=True,
            observation=Observation(provenance='UNKNOWN' if unknown else 'MOCK',
                text='Controller finished; placement was not observed.' if unknown else f'Mock controller reports {p.object} at station {p.destination}.',
                source='mock fault scenario' if unknown else 'mock state inspection',value=None if unknown else p.destination))
    async def stop(self):
        self._stopped.set()

class TransferRunnerAdapter:
    mode = 'physical'
    def __init__(self, runner):
        if runner.mode != 'physical':
            raise ValueError('Transfer bridge requires a physical runner.')
        self.runner = runner
        self._authorization = None
        self._revoked = set()
        self._authorized = set()
        self._inflight_id = None
        self._state = {'at':'HOME','holding':None,'armed':True,'portions_left':{},'receiver_load':{},
                       'point_holds':{'A':'mandarin','C':'mandarin','B':None}}
    @classmethod
    def load(cls, checkout: str, factory: str):
        """Import under a private namespace so this checkout's firmware cannot shadow it."""
        root = Path(checkout).expanduser().resolve()
        if not (root/'firmware').is_dir():
            raise ValueError('OPENARMS_HARDWARE_CHECKOUT must contain firmware/.')
        import os
        if os.getenv('OPENARMS_FAKE_ROBOT') == '1':
            raise ValueError('FakeRobot is not a physical backend. Use OPENARMS_BACKEND=mock for the student app.')
        module, sep, name = factory.partition(':')
        if not sep or not module.startswith('firmware.'):
            raise ValueError('Runner factory must be firmware.module:create_runner.')
        namespace = '_openarms_hardware'
        pkg = types.ModuleType(namespace)
        pkg.__path__ = [str(root)]
        sys.modules[namespace] = pkg
        imported = importlib.import_module(namespace+'.'+module)
        return cls(getattr(imported,name)())
    def capabilities(self):
        # C is advertised only if this exact runner was configured with a C script.
        sources = list(getattr(self.runner,'scripts',{'A':None}))
        if getattr(self.runner,'dry_approach',False) or getattr(self.runner,'empty',False):
            sources=[]  # rehearsal scripts do not establish loaded-transfer capabilities
        return {'routes':[[s,'B'] for s in sources if s in ('A','C')], 'objects':['mandarin'],
                'controller':'transfer', 'observation_provenance':'UNKNOWN',
                'baseline_evidence':'A→B team reported; local connection validation required'}
    def state(self):
        import copy
        return copy.deepcopy(self._state)
    @staticmethod
    def plan(request):
        return {'plan_id':request.request_id, **request.parameters.model_dump()}
    async def authorize(self, request):
        if self._authorization is not None and not self._authorization.done():
            raise ValueError('A previous operator prompt is still open. Answer it before another request.')
        pid=request.request_id
        self._inflight_id=pid
        self._authorization=asyncio.create_task(self.runner.authorize(self.plan(request)))
        try:
            ok=await asyncio.shield(self._authorization)
        except asyncio.CancelledError:
            self._revoked.add(pid)
            # Retain the underlying input thread/future; a late yes cannot execute.
            def drain(task):
                try: task.result()
                except BaseException: pass
            self._authorization.add_done_callback(drain)
            raise
        if ok is True and pid not in self._revoked:
            self._authorized.add(pid)
            return True
        return False
    async def execute(self, request, progress):
        if request.request_id not in self._authorized or request.request_id in self._revoked:
            raise ValueError('Physical request was not authorized, or permission was revoked.')
        self._authorized.remove(request.request_id)
        await progress('controller_running')
        result = await self.runner.execute(self.plan(request))
        if result.plan_id != request.request_id or result.mode != 'physical' or result.operator_authorized is not True:
            await self.stop()
            raise ValueError('Runner result identity/mode/operator authorization mismatch.')
        status = result.status if result.status in ('completed','failed','stopped','unknown') else 'unknown'
        # Legacy placement has no independent evidence attached. Do not turn it into REAL success.
        self._state['armed'] = False  # require a new bench setup/observation, never assume post-run state
        return ExecutionResult(request_id=request.request_id,backend='physical',status=status,
            operator_authorized=True,controller_completed=status=='completed',physical_success=None,
            observation=Observation(provenance='UNKNOWN',text='Controller finished; independent physical placement evidence is not available.'
                if status=='completed' else 'Physical outcome is unknown; the operator must check the bench.',source='controller report'),
            reason=None if status=='completed' else f'Physical runner returned {status}.')
    async def stop(self):
        self._state['armed'] = False
        if self._inflight_id:
            self._revoked.add(self._inflight_id)
            self._authorized.discard(self._inflight_id)
        await self.runner.stop()
