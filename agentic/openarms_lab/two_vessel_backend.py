"""Shared lab backend for a confirmed MuJoCo water pour."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import time
import uuid

from .contracts import MockSampleArguments
from .mujoco_backend import MujocoBackend
from .two_vessel_worker import run_worker
from .two_vessel_scene import LIMITATIONS, PROVENANCE, SCENE

OPERATION = 'mock_prepared_sample'


class TwoVesselBackend(MujocoBackend):
    mode = 'mujoco'
    def worker(self, *args, **kwargs):
        # Looked up at call time so tests can patch run_worker; subclasses bind another setup's renderer.
        return run_worker(*args, **kwargs)

    def _reset_state(self):
        self._state = {
            'at': 'HOME', 'holding': None, 'armed': True, 'phase': 'ready',
            'cup_station': 'A', 'cup_portions': 1, 'receiver_portions': 0,
            'state_provenance': PROVENANCE, 'physical_execution': False,
            'simulation': {'engine': 'MuJoCo', **SCENE, 'status': 'ready', 'frame_name': None,
                           'video_name': None, 'frame_count': 0, 'motion_seconds': 0, 'dose_count': 0,
                           'warnings': list(LIMITATIONS), 'frame_evidence': None},
        }

    @staticmethod
    def capabilities():
        return {'experiment_id': 'two_vessel_water', 'conditions': ['water'],
                'routes': [['A', 'C']], 'mock_execution': False, 'physical_execution': False,
                'simulation_execution': True, 'supported_operations': [OPERATION], **SCENE,
                'measurement': False, 'observation_provenance': 'SIMULATED',
                'skill_admission': {
                    'required_expected_state': {'at': 'HOME'},
                    'expected_state_contract': 'SkillDefinition.expected_state describes the final controller state. '
                        'Declare at=HOME for this complete pour; it is not a camera-observed feature or physical success.',
                    'required_outcome_checks': [{'feature': 'receiver_appearance', 'expected': 'water_appearance'}],
                    'outcome_checks_contract': 'SkillDefinition.outcome_checks are checked independently against '
                        'fresh SIMULATED image features listed in scene.observable_features. '
                        'Controller HOME cannot replace the independent water-appearance check.',
                    'qualification': 'Initial admission of a reusable simulated water capability; '
                        'not substantive improvement, chemistry qualification, or physical readiness.',
                },
                'action_description': 'pour one premeasured water portion from A into C, return the donor to A and return HOME',
                'limitations': [*LIMITATIONS, 'One premeasured water pour from the small donor at A into the wide receiver at C.']}

    def check_step(self, operation, arguments):
        if operation != OPERATION:
            raise ValueError('MuJoCo supports only the complete two-vessel water pour.')
        request = MockSampleArguments.model_validate(arguments)
        if request.condition_id != 'water':
            raise ValueError('The two-vessel demonstration supports water only; no kit chemistry is qualified.')
        if self.session_id is None or self._state['simulation']['status'] != 'ready' or not self._idle.is_set():
            raise ValueError('Prepare a fresh MuJoCo trial before executing.')
        return request

    @staticmethod
    def _command(request):
        return {'condition': request.condition_id}

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
        simulation.update(status='running', frame_name=None, video_name=None, video_sha256=None)

        async def report(message):
            if self._stop_requested:
                raise asyncio.CancelledError()
            self._set_frame(simulation, message)
            self._state['phase'] = message['phase']
            await progress(message['phase'])

        command = {'kind': 'execute', **self._command(request),
                   'video_name': staging.name, 'generation': self.scene_service.generation(sid)}
        worker = self._worker = asyncio.create_task(self.worker(folder, command, report))
        final_state = None
        reason = None
        try:
            result = await asyncio.shield(worker)
            if self._stop_requested:
                raise asyncio.CancelledError()
            self._set_frame(simulation, result)
            simulation['warnings'].extend(result['warnings'])
            if result['video_name'] != staging.name:
                raise RuntimeError('MuJoCo worker returned unexpected scene or video metadata.')
            simulation.update(trace=result['trace'], dose_count=result['dose_count'],
                              returned_to_dock=result['returned_to_dock'], home_reached=result['home_reached'])
            if result['ok'] and result['dose_count'] == 1:
                if not staging.is_file() or not staging.stat().st_size or result['frame_count'] <= 0:
                    raise RuntimeError('MuJoCo video is missing or empty.')
                staging.replace(folder / video_name)
                final_state = result['state']
                simulation.update(status='completed', video_name=video_name,
                                  video_sha256=hashlib.sha256((folder / video_name).read_bytes()).hexdigest())
                self._state.update(at='HOME', cup_station='A', cup_portions=0, receiver_portions=1)
            else:
                reason = result['warnings'][0] if result['warnings'] else 'MuJoCo did not complete the water pour.'
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
