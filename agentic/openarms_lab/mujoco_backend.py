"""Shared lab backend for a confirmed MuJoCo metered dose."""
from __future__ import annotations

import asyncio
import copy
import time
import uuid

from .contracts import MockSampleArguments
from .mujoco_process import run_worker
from .mujoco_scene import CONDITIONS, LIMITATIONS, PROVENANCE, SCENE

OPERATION = 'mock_prepared_sample'


class MujocoBackend:
    mode = 'mujoco'

    def __init__(self, scene_service):
        self.scene_service = scene_service
        self.session_id = None
        self._worker = None
        self._stop_requested = False
        self._idle = asyncio.Event()
        self._idle.set()
        self._consumed = set()
        self.executions = 0
        self._reset_state()

    def _reset_state(self):
        self._state = {
            'at': 'HOME', 'holding': None, 'armed': True, 'phase': 'ready',
            'cup_station': 'A', 'cup_portions': 1, 'receiver_portions': 0,
            'state_provenance': PROVENANCE, 'physical_execution': False,
            'simulation': {'engine': 'MuJoCo', **SCENE, 'status': 'ready', 'frame_name': None,
                           'video_name': None, 'frame_count': 0, 'motion_seconds': 0, 'dose_count': 0,
                           'warnings': list(LIMITATIONS), 'frame_evidence': None},
        }

    def bind_session(self, session_id):
        if self.session_id is not None and session_id != self.session_id:
            raise ValueError('A MuJoCo backend is bound to one session.')
        self.scene_service.folder(session_id)
        self.session_id = session_id

    def prepare(self):
        if not self._idle.is_set():
            raise ValueError('Cannot prepare during MuJoCo execution.')
        if self.session_id is None:
            raise ValueError('MuJoCo backend has no session binding.')
        self.scene_service.reset(self.session_id)
        self._reset_state()

    @staticmethod
    def capabilities():
        return {'experiment_id': 'red_cabbage_ph', 'conditions': list(CONDITIONS),
                'routes': [['A', 'C']], 'mock_execution': False, 'physical_execution': False,
                'simulation_execution': True, 'supported_operations': [OPERATION], **SCENE,
                'measurement': False, 'observation_provenance': 'SIMULATED',
                'limitations': [*LIMITATIONS, 'The A and C route labels identify the fixed source dropper and receiver.']}

    def state(self):
        state = copy.deepcopy(self._state)
        if state['simulation']['status'] == 'ready':
            reference = self.scene_service.latest_frame(self.session_id)
            if reference:
                state['simulation'].update(frame_name=reference['evidence_id'] + '.png',
                                           frame_evidence=self._public_reference(reference))
        return state

    def check_step(self, operation, arguments):
        if operation != OPERATION:
            raise ValueError('MuJoCo supports only a complete prepared-sample dose.')
        request = MockSampleArguments.model_validate(arguments)
        if self.session_id is None or self._state['simulation']['status'] != 'ready' or not self._idle.is_set():
            raise ValueError('Prepare a fresh MuJoCo trial before executing.')
        return request

    async def execute_step(self, request_id, arguments, progress, *, operation=OPERATION):
        request = self.check_step(operation, arguments)
        if request_id in self._consumed:
            raise ValueError('MuJoCo request already consumed.')
        sid = self.session_id
        folder = self.scene_service.folder(sid)
        video_name = uuid.uuid4().hex + '.mp4'
        staging = folder / ('.' + video_name)
        started = time.perf_counter()
        self._consumed.add(request_id)
        self.executions += 1
        self._stop_requested = False
        self._idle.clear()
        self.scene_service.begin(sid)
        simulation = self._state['simulation']
        self._state.update(at='MUJOCO', phase='starting', armed=False)
        simulation.update(status='running', frame_name=None, video_name=None)

        async def report(message):
            self._set_frame(simulation, message)
            self._state['phase'] = message['phase']
            await progress(message['phase'])

        command = {'kind': 'execute', 'condition': request.condition_id,
                   'video_name': staging.name}
        worker = self._worker = asyncio.create_task(run_worker(folder, command, report))
        final_state = None
        reason = None
        try:
            result = await asyncio.shield(worker)
            if self._stop_requested:
                raise asyncio.CancelledError()
            self._set_frame(simulation, result)
            simulation['warnings'].extend(result['warnings'])
            if result['scene'] != SCENE or result['video_name'] != staging.name:
                raise RuntimeError('MuJoCo worker returned unexpected scene or video metadata.')
            simulation.update(trace=result['trace'], joint_names=result['joint_names'], dose_count=result['dose_count'])
            if result['ok'] and result['dose_count'] == 1:
                if not staging.is_file() or not staging.stat().st_size or result['frame_count'] <= 0:
                    raise RuntimeError('MuJoCo video is missing or empty.')
                staging.replace(folder / video_name)
                final_state = result['state']
                simulation.update(status='completed', video_name=video_name)
                self._state.update(at='HOME', cup_station='A', cup_portions=0, receiver_portions=1)
            else:
                reason = result['warnings'][0] if result['warnings'] else 'MuJoCo did not deliver a dose.'
                simulation['status'] = 'failed'
        except asyncio.CancelledError:
            simulation['status'] = 'stopped'
            reason = 'MuJoCo STOP or cancellation requested.'
            await self._cancel_worker(worker)
            if asyncio.current_task().cancelling():
                raise
        except (RuntimeError, OSError, ValueError) as exc:
            simulation['status'] = 'failed'
            reason = str(exc) if isinstance(exc, RuntimeError) else 'MuJoCo evidence could not be retained.'
            simulation['warnings'].append(reason)
        finally:
            self._worker = None
            self._state['phase'] = simulation['status']
            if simulation['status'] != 'completed':
                self._state.update(at='UNKNOWN', holding=None, cup_station=None,
                                   cup_portions=None, receiver_portions=None)
            try:
                staging.unlink(missing_ok=True)
            finally:
                self.scene_service.finish(sid, final_state)
                self._idle.set()

        return {'receipt_id': uuid.uuid4().hex, 'backend': self.mode, 'request_id': request_id,
                'operation': operation, 'status': simulation['status'],
                'controller_completed': simulation['status'] == 'completed', 'reason': reason,
                'elapsed_ms': (time.perf_counter() - started) * 1000, 'physical_execution': False,
                'provenance': PROVENANCE, 'simulation': copy.deepcopy(simulation)}

    def _set_frame(self, simulation, message):
        reference = self.scene_service.record_frame(self.session_id, message)
        simulation.update(frame_name=message['frame_name'], frame_count=message['frame_count'],
                          motion_seconds=message['motion_seconds'], frame_evidence=self._public_reference(reference))

    @staticmethod
    def _public_reference(reference):
        return {key: value for key, value in reference.items() if key != 'path'}

    @staticmethod
    async def _cancel_worker(worker):
        if not worker.done() and not worker.cancelling():
            worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)

    async def stop(self):
        worker = self._worker
        if worker is not None:
            self._stop_requested = True
            await self._cancel_worker(worker)
        if self.session_id is not None:
            await self.scene_service.cancel_captures(self.session_id)

    async def wait_idle(self):
        await self._idle.wait()
