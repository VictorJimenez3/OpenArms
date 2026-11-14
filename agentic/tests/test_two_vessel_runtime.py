"""Actual rendered water pour through the shared consent, task and evidence loop."""
import asyncio
import copy
import os
from pathlib import Path

import pytest

from agentic.openarms_lab.runtime import Lab, LabError
from agentic.openarms_lab.two_vessel_backend import TwoVesselBackend
from agentic.openarms_lab.two_vessel_scene import TwoVesselSceneService
from agentic.openarms_lab import two_vessel_worker

DEFINITION = {
    'skill_id': 'two_vessel_water', 'name': 'One water pour A to C',
    'intent': 'Pour one premeasured water portion from A into C and return HOME',
    'retrieval_examples': ['pour {condition} from A to C'],
    'parameter_schema': {'condition': {'type': 'string', 'enum': ['water']}},
    'preconditions': {'fresh_scene': True, 'labels': ['source', 'receiver']},
    'steps': [{'operation': 'inspect_scene'},
              {'operation': 'mock_prepared_sample', 'arguments': {'condition_id': '$condition'}},
              {'operation': 'observe'}],
    'expected_state': {'at': 'HOME'},
    'outcome_checks': [{'feature': 'receiver_appearance', 'expected': 'water_appearance'},
                       {'feature': 'sample_cup_station', 'expected': 'A'}],
    'limitations': ['SIMULATED water motion only; no physical or kit recipe qualification.'],
}


class WaterExpert:
    """Deterministic planner, explicitly not a live provider qualification."""
    def __init__(self):
        self.contexts = []

    async def run(self, context, *, tool_handler, **_):
        self.contexts.append(copy.deepcopy(context))
        if context['phase'] == 'planning':
            await tool_handler('localize_objects', {
                'evidence_id': context['images'][0]['evidence_id'], 'labels': ['source', 'receiver']})
            return {'kind': 'plan', 'summary': 'Pour water from A to C, return donor and HOME.',
                    'payload': {'skill_definition': DEFINITION, 'bindings': {'condition': 'water'}},
                    'provider': 'TEST_FAKE', 'model': 'deterministic-water-planner', 'calls': 1,
                    'usage': {}, 'elapsed_ms': 1, 'tool_receipts': []}
        return {'kind': 'complete', 'summary': 'Check the independent overview.', 'payload': {'continue': True},
                'provider': 'TEST_FAKE', 'model': 'deterministic-water-planner', 'calls': 1,
                'usage': {}, 'elapsed_ms': 1, 'tool_receipts': []}


async def settled(lab, handle):
    await asyncio.wait_for(asyncio.shield(lab.workers[handle['task_id']]), 90)


@pytest.mark.asyncio
async def test_real_two_vessel_water_full_lab_consent_and_fresh_outcome(tmp_path):
    scene, expert = TwoVesselSceneService(tmp_path/'frames'), WaterExpert()
    lab = Lab(tmp_path/'lab', expert=expert, perception=scene,
              backend_factory=lambda: TwoVesselBackend(scene), execution_scope='two-vessel-test')
    try:
        sid = (await lab.create())['session_id']
        handle = await lab.start_task(sid, 'Pour water from A into C.')
        await settled(lab, handle)
        snapshot = lab.snapshot(sid)
        assert snapshot['tasks'][-1]['status'] == 'awaiting_confirmation', snapshot['tasks'][-1]['summary']
        proposal = snapshot['pending']
        exact = (sid, proposal['request_id'], proposal['proposal_version'])
        backend = lab.backends[sid]
        assert backend.executions == 0
        with pytest.raises(LabError):
            await lab.confirm(*exact)
        await lab.present(*exact)
        await lab.confirm(*exact)
        await settled(lab, handle)
        snapshot = lab.snapshot(sid)
        task = snapshot['tasks'][-1]
        assert task['status'] == 'completed', task['summary']
        assert backend.executions == 1
        outcome = task['observations'][-1]
        assert outcome['features']['receiver_appearance'] == 'water_appearance'
        assert outcome['features']['sample_cup_station'] == 'A'
        assert outcome['provenance'] == 'SIMULATED'
        sim = backend.state()['simulation']
        assert sim['status'] == 'completed' and 19 < sim['motion_seconds'] < 21
        assert sim['dose_count'] == 1 and sim['returned_to_dock'] and sim['home_reached']
        assert sim['frame_count'] > 500
        assert (scene.folder(sid)/sim['video_name']).stat().st_size > 1000
        # Independent capture is a new raw image, taken after final controller frame.
        observed_id = outcome['evidence'][-1]
        final_frame = scene.frames[sid, observed_id][0]
        assert observed_id != sim['frame_evidence']['evidence_id']
        assert final_frame['captured_at'] > sim['frame_evidence']['captured_at']
        assert Path(final_frame['path']).name == observed_id+'.png'
        assert expert.contexts[-1]['phase'] != 'planning'
        with pytest.raises(LabError, match='consumed'):
            await lab.confirm(*exact)
        assert backend.executions == 1
        await lab.prepare(sid)
        reset = await scene.observe(sid, {'controller_completed': True, 'color': 'purple'})
        assert reset['features']['receiver_appearance'] == 'dark_base_visible'
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_raw_registration_integrity_reset_and_water_only(tmp_path):
    scene = TwoVesselSceneService(tmp_path)
    backend = TwoVesselBackend(scene)
    backend.bind_session('s'); backend.prepare()
    for condition in ('vinegar', 'baking_soda'):
        with pytest.raises(ValueError, match='water only'):
            backend.check_step('mock_prepared_sample', {'condition_id': condition})
    for variant in ('nominal', 'camera_shift', 'missing', 'swapped', 'occluded'):
        scene.variant = variant
        frame = await scene.observe('s', {'controller_completed': True, 'receiver_appearance': 'water_appearance'})
        assert (frame['status'] == 'observed') == (variant == 'nominal')
        located = await scene.localize_objects('s', frame['evidence_id'], ['source','receiver'])
        assert located['verified_labels'] == (['source','receiver'] if variant == 'nominal' else [])
    scene.variant = 'nominal'
    frame = await scene.inspect_scene('s')
    with pytest.raises(ValueError, match='not owned'):
        await scene.localize_objects('other', frame['evidence_id'], ['source'])
    backend.prepare()
    assert not (await scene.localize_objects('s',frame['evidence_id'],['source']))['verified_labels']
    Path(frame['images'][0]['path']).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='hash changed'):
        await scene.localize_objects('s',frame['evidence_id'],['source'])


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel_task', [False, True])
async def test_stop_reaps_renderer_and_blocks_late_publication(tmp_path, monkeypatch, cancel_task):
    scene = TwoVesselSceneService(tmp_path)
    backend = TwoVesselBackend(scene)
    backend.bind_session('s'); backend.prepare()
    started = asyncio.Event()
    pids = []
    spawn = asyncio.create_subprocess_exec
    async def record(*args, **kwargs):
        proc = await spawn(*args, **kwargs); pids.append(proc.pid); return proc
    monkeypatch.setattr(two_vessel_worker.asyncio,'create_subprocess_exec',record)
    async def progress(_):
        started.set()
        await asyncio.sleep(30)
    task = asyncio.create_task(backend.execute_step('stop-test',{'condition_id':'water'},progress))
    try:
        await asyncio.wait_for(started.wait(), 30)
        if cancel_task:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)
        else:
            await asyncio.wait_for(backend.stop(),3)
            assert (await asyncio.wait_for(task,3))['status']=='stopped'
        await asyncio.wait_for(backend.wait_idle(),3)
        with pytest.raises(ProcessLookupError):
            os.kill(pids[0],0)
        assert backend.state()['simulation']['video_name'] is None
        assert not list(scene.folder('s').glob('*.mp4'))
        with pytest.raises(RuntimeError, match='fresh trial'):
            await scene.inspect_scene('s')
    finally:
        await backend.stop()
        await asyncio.gather(task,return_exceptions=True)
