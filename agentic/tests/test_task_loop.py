import asyncio
import copy
import hashlib
import tempfile
import time
import unittest
from pathlib import Path

from PIL import Image

from agentic.openarms_lab.backends import MockBackend
from agentic.openarms_lab.runtime import Lab, LabError

HASH = '1' * 64
DEFINITION = {
    'skill_id': 'sample_color', 'name': 'Prepared sample inspection',
    'intent': 'Run a mock sample and observe its qualitative color',
    'retrieval_examples': ['test prepared {condition}', 'run prepared {condition}'],
    'parameter_schema': {'condition': {'type': 'string', 'enum': ['vinegar', 'water']}},
    'preconditions': {'fresh_scene': True, 'labels': ['receiver']},
    'steps': [{'operation': 'inspect_scene'},
              {'operation': 'mock_prepared_sample', 'arguments': {'condition_id': '$condition'}},
              {'operation': 'observe'}],
    'expected_state': {'at': 'HOME'},
    'outcome_checks': [{'feature': 'readable', 'expected': True}],
    'limitations': ['Mock operation and recorded simulation only.'],
}


def draft():
    return {'skill_definition': copy.deepcopy(DEFINITION), 'bindings': {'condition': 'vinegar'}}


def decision(kind='plan', payload=None):
    return {'kind': kind, 'summary': 'Expert decision', 'payload': draft() if payload is None else payload,
            'provider': 'TEST_FAKE', 'model': 'TEST_FAKE', 'reasoning_effort': 'medium',
            'calls': 1, 'usage': {'total_tokens': 10}, 'elapsed_ms': 1, 'tool_receipts': []}


class TestPerception:
    def __init__(self, *, unknown=True, fresh=True):
        self.unknown, self.fresh = unknown, fresh
        self._frames = tempfile.TemporaryDirectory()
        self.captures = 0
        self.observation_inputs = []
        self.localized = []
        self.labels_visible = True

    async def inspect_scene(self, sid, view='primary'):
        captured_at = time.time()
        self.captures += 1
        fid = str(self.captures)
        path = Path(self._frames.name) / f'{fid}.png'
        Image.new('RGB', (8, 8), 'purple').save(path)
        return {'evidence_id': fid, 'captured_at': captured_at, 'provenance': 'SYNTHETIC',
                'scene': {'frame_id': fid, 'captured_at': captured_at, 'clock': 'unix_seconds',
                          'fresh': self.fresh, 'view': view},
                'images': [{'evidence_id': fid, 'path': str(path), 'captured_at': captured_at,
                            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'provenance': 'SYNTHETIC'}]}

    async def localize_objects(self, sid, evidence_id, labels):
        self.localized.append(evidence_id)
        return {'evidence_id': evidence_id, 'verified_labels': labels if self.labels_visible else [],
                'method': 'synthetic-test'}

    async def observe(self, sid, camera):
        self.observation_inputs.append(camera)
        frame = await self.inspect_scene(sid, camera['view'])
        return {**frame, 'status': 'unknown' if self.unknown else 'observed',
                'observer_version': 'synthetic-test', 'features': {'readable': not self.unknown}}


class TestExpert:
    def __init__(self, *, revise=False):
        self.contexts = []
        self.revise = revise

    async def run(self, context, *, tool_handler, emit, cancel_event):
        self.contexts.append(context)
        await emit({'type': 'expert_call_completed', 'task_id': 'cannot-overwrite'})
        if context['phase'] in ('planning', 'improvement'):
            if context['request'].lower().startswith(('do not', 'which')):
                return decision('clarification', {})
            if any(item['type'] == 'precondition_failed' for item in context['feedback']):
                return decision('clarification', {})
            await tool_handler('localize_objects',
                               {'evidence_id': context['images'][0]['evidence_id'], 'labels': ['receiver']})
            payload = draft()
            if context['task_context']['condition_id']:
                payload['bindings']['condition'] = context['task_context']['condition_id']
            return decision(payload=payload)
        if self.revise:
            return decision('revision', {
                'steps': [{'operation': 'observe', 'arguments': {'view': 'secondary'}}],
                'outcome_checks': [{'feature': 'readable', 'expected': True}],
            })
        if context['feedback'][-1]['type'] == 'perception':
            await tool_handler('localize_objects',
                               {'evidence_id': context['images'][0]['evidence_id'], 'labels': ['receiver']})
        return decision('complete', {'continue': True})


class TestEvaluator:
    def __init__(self, passed=True):
        self.passed = passed

    async def evaluate_candidate(self, sid, candidate, baseline):
        return {'evaluation_id': 'synthetic-evaluation', 'suite_hash': HASH,
                'candidate_hash': candidate['version'], 'baseline_hash': baseline['version'] if baseline else None,
                'artifact_hashes': [HASH], 'baseline_recovered': 0, 'candidate_recovered': 2,
                'regression_gates': {name: self.passed for name in ('routing', 'outcome', 'unknown', 'consent', 'stop')},
                'passed': self.passed, 'reasons': ['synthetic test receipt']}


class TaskLoopTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.expert, self.perception = TestExpert(), TestPerception()
        self.lab = Lab(self.root.name, expert=self.expert, perception=self.perception,
                       evaluator=TestEvaluator(), backend_factory=lambda: MockBackend(delay=0))
        self.sid = (await self.lab.create())['session_id']

    async def asyncTearDown(self):
        await self.lab.shutdown()
        self.root.cleanup()

    async def wait_status(self, status, task_id=None):
        async with asyncio.timeout(2):
            while True:
                snap = self.lab.snapshot(self.sid)
                task = next(t for t in reversed(snap['tasks']) if task_id is None or t['task_id'] == task_id)
                if task['status'] == status:
                    return snap, task
                if task['status'] == 'failed':
                    self.fail(task)
                await asyncio.sleep(0.001)

    async def approve(self, snap):
        p = snap['pending']
        await self.lab.present(self.sid, p['request_id'], p['proposal_version'])
        await self.lab.confirm(self.sid, p['request_id'], p['proposal_version'])
        return p

    async def test_cold_unknown_feedback_evaluation_and_warm(self):
        queue = asyncio.Queue()
        self.lab.subscribers[self.sid] = {queue}
        await self.lab.choose_condition(self.sid, 'vinegar')
        await self.lab.prediction(self.sid, 'pink')
        self.assertIsNone(self.lab.snapshot(self.sid)['pending'])
        initial = await self.lab.start_task(self.sid, 'Try a new prepared sample.', client_request_id='one')
        self.assertEqual(initial['status'], 'queued')
        self.assertEqual(initial, await self.lab.start_task(self.sid, 'Try a new prepared sample.', client_request_id='one'))
        snap, task = await self.wait_status('awaiting_confirmation')
        self.assertEqual(task['route'], 'expert')
        self.assertEqual(self.expert.contexts[0]['task_context']['prediction'], 'pink')
        self.assertIn('Try a new prepared sample.', [turn['text'] for turn in self.expert.contexts[0]['conversation']])
        version = snap['pending']['skill_version']
        self.assertEqual(self.lab.registry.get('sample_color', version)['status'], 'task_validated')
        self.assertEqual(self.lab.registry.list(), [])
        with self.assertRaises(LabError):
            await self.lab.evaluate_candidate(self.sid, 'sample_color', version)
        p = await self.approve(snap)
        with self.assertRaises(LabError):
            await self.lab.confirm(self.sid, p['request_id'], p['proposal_version'])
        snap, task = await self.wait_status('completed')
        self.assertEqual(self.perception.observation_inputs, [{'view': 'primary'}])
        self.assertIs(task['execution'][0]['controller_completed'], True)
        self.assertEqual(task['observations'][0]['status'], 'unknown')
        self.assertEqual(task['observations'][0]['source'], 'synthetic-test')
        self.assertTrue(task['observations'][0]['evidence'])
        self.assertEqual(snap['observations'][0]['provenance'], 'UNKNOWN')
        self.assertIsNone(snap['observations'][0]['value'])
        self.assertEqual([c['phase'] for c in self.expert.contexts], ['planning', 'execution_feedback', 'execution_feedback'])
        self.assertEqual([f['type'] for f in self.expert.contexts[-1]['feedback'] if f['type'] != 'execution_progress'],
                         ['perception', 'execution', 'observation', 'checkpoint_failed'])
        self.assertNotEqual(self.expert.contexts[0]['images'][0]['evidence_id'],
                            self.expert.contexts[-1]['images'][0]['evidence_id'])
        frames = [queue.get_nowait() for _ in range(queue.qsize())]
        events = frames[-1]['state']['notebook']
        self.assertTrue(any(e['kind'] == 'observation' and e['data']['task_id'] == task['task_id'] for e in events))
        self.assertTrue(any(e['kind'] == 'execution_result' and e['data']['task_id'] == task['task_id'] for e in events))
        with self.assertRaisesRegex(LabError, 'independently observed passing outcome'):
            await self.lab.evaluate_candidate(self.sid, 'sample_color', version)
        # UNKNOWN stays available for improvement; activation needs a separately
        # consented trial whose controller and independent outcome both passed.
        await self.lab.prepare(self.sid)
        self.perception.unknown = False
        clear = await self.lab.start_task(self.sid, 'Test the prepared sample with a clear camera')
        snap, _ = await self.wait_status('awaiting_confirmation', clear['task_id'])
        clear_proposal = await self.approve(snap)
        _, clear_task = await self.wait_status('completed', clear['task_id'])
        self.assertNotEqual(clear_proposal['request_id'], p['request_id'])
        self.assertEqual(clear_proposal['skill_version'], version)
        self.assertIs(clear_task['execution'][0]['controller_completed'], True)
        self.assertEqual(clear_task['observations'][0]['checks'], {'readable': True})
        promotion = await self.lab.evaluate_candidate(self.sid, 'sample_color', version)
        contexts_after_admission = len(self.expert.contexts)
        self.assertEqual(promotion['status'], 'promoted')
        await self.lab.prepare(self.sid)
        self.perception.unknown = False
        self.perception.labels_visible = False
        await self.lab.start_task(self.sid, 'Run prepared water')
        _, blocked = await self.wait_status('needs_clarification')
        self.assertEqual(blocked['route'], 'expert')
        self.assertEqual(blocked['feedback'][-1]['type'], 'precondition_failed')
        self.assertTrue(self.expert.contexts[-1]['images'])
        self.assertEqual(self.lab.backends[self.sid].executions, 2)
        self.perception.labels_visible = True
        await self.lab.converse(self.sid, 'Run prepared water', 'two')
        snap, warm = await self.wait_status('awaiting_confirmation')
        self.assertEqual(warm['route'], 'active_skill')
        self.assertEqual(snap['pending']['skill_version'], version)
        self.assertEqual(snap['pending']['metrics']['model_calls'], 0)
        self.assertEqual(snap['pending']['plan']['steps'][1]['arguments']['condition_id'], 'water')
        self.assertEqual(len(self.expert.contexts), contexts_after_admission + 1)
        self.assertGreaterEqual(snap['pending']['metrics']['planning_ms'], 0)
        planning_frame = warm['images'][0]['evidence_id']
        self.lab.expert = None
        await self.approve(snap)
        snap, warm = await self.wait_status('completed', warm['task_id'])
        self.assertEqual(warm['expert_runs'], [])
        self.assertEqual(warm['observations'][0]['checks'], {'readable': True})
        self.assertNotEqual(warm['observations'][0]['evidence'], [planning_frame])
        execution_frame = next(f['receipt']['evidence_id'] for f in warm['feedback'] if f['type'] == 'perception')
        self.assertIn(execution_frame, self.perception.localized)
        self.assertEqual(self.lab.backends[self.sid].executions, 3)
        self.assertIsNone(snap['trial']['condition_id'])
        self.assertEqual(snap['prediction'], '')

        # Same registered skill, fresh failed outcome. The expert revises the
        # remaining observation from the image while the dispatched action stays consumed.
        self.lab.expert = self.expert
        self.expert.revise = True
        self.perception.unknown = True
        await self.lab.start_task(self.sid, 'Run prepared water')
        snap, failed = await self.wait_status('awaiting_confirmation')
        first = await self.approve(snap)
        snap, revised = await self.wait_status('awaiting_confirmation', failed['task_id'])
        feedback = self.expert.contexts[-1]
        self.assertEqual(len(self.expert.contexts), contexts_after_admission + 2)
        self.assertEqual(feedback['phase'], 'execution_feedback')
        self.assertEqual(feedback['images'][0]['evidence_id'], revised['observations'][0]['evidence'][0])
        self.assertTrue(feedback['task_context']['dispatched_action'])
        self.assertEqual(revised['replans'], 1)
        self.assertEqual(snap['pending']['plan']['steps'],
                         [{'operation': 'observe', 'arguments': {'view': 'secondary'}}])
        self.assertEqual(self.lab.backends[self.sid].executions, 4)
        for proposal in (first, snap['pending']):
            with self.assertRaises(LabError):
                await self.lab.confirm(self.sid, proposal['request_id'], proposal['proposal_version'])
        self.expert.revise = False
        self.perception.unknown = False
        await self.approve(snap)
        _, revised = await self.wait_status('completed', failed['task_id'])
        self.assertEqual(revised['observations'][-1]['checks'], {'readable': True})
        self.assertEqual(self.lab.backends[self.sid].executions, 4)

    async def test_image_revisions_require_fresh_consent_and_stop_at_two(self):
        self.expert.revise = True
        await self.lab.start_task(self.sid, 'Run a visually checked task')
        snap, _ = await self.wait_status('awaiting_confirmation')
        p1 = await self.approve(snap)
        snap, task = await self.wait_status('awaiting_confirmation')
        self.assertEqual(task['replans'], 1)
        self.assertEqual(self.lab.backends[self.sid].executions, 0)
        self.assertEqual(snap['pending']['plan']['steps'][0]['arguments']['view'], 'secondary')
        self.assertNotEqual(snap['pending']['plan_hash'], p1['plan_hash'])
        with self.assertRaises(LabError):
            await self.lab.confirm(self.sid, p1['request_id'], p1['proposal_version'])
        p2 = snap['pending']
        with self.assertRaises(LabError):
            await self.lab.confirm(self.sid, p2['request_id'], p2['proposal_version'])
        await self.approve(snap)
        snap, task = await self.wait_status('awaiting_confirmation')
        self.assertEqual(task['replans'], 2)
        self.assertNotEqual(p2['request_id'], snap['pending']['request_id'])
        await self.approve(snap)
        async with asyncio.timeout(2):
            while self.lab.snapshot(self.sid)['tasks'][-1]['status'] != 'failed':
                await asyncio.sleep(0.001)
        task = self.lab.snapshot(self.sid)['tasks'][-1]
        self.assertEqual(task['replans'], 2)
        self.assertIn('Replan limit', task['summary'])

    async def test_repeated_image_cannot_authorize_mock_action(self):
        capture = self.perception.inspect_scene
        planning_frames = []

        async def capture_planning(sid, view='primary'):
            frame = await capture(sid, view)
            planning_frames.append(frame)
            return frame

        async def replay(sid, view='primary'):
            return planning_frames[0]

        self.perception.inspect_scene = capture_planning
        await self.lab.start_task(self.sid, 'A new sample request')
        snap, task = await self.wait_status('awaiting_confirmation')
        self.assertEqual(len(planning_frames), 1)
        self.assertEqual(task['images'][0]['evidence_id'], planning_frames[0]['evidence_id'])
        self.perception.inspect_scene = replay
        await self.approve(snap)
        await self.lab.workers[task['task_id']]
        final = self.lab.snapshot(self.sid)['tasks'][-1]
        self.assertEqual(final['status'], 'failed')
        self.assertIn('fresh image', final['summary'])
        checkpoint = next(f['receipt'] for f in final['feedback'] if f['type'] == 'perception')
        self.assertIn('evidence ID was already used', checkpoint['reason'])
        self.assertEqual(self.lab.backends[self.sid].executions, 0)

    async def test_negative_clarification_and_stale_confirmation(self):
        await self.lab.converse(self.sid, 'Do not run prepared water')
        snap, task = await self.wait_status('needs_clarification')
        self.assertIsNone(snap['pending'])
        self.assertEqual(task['route'], 'expert')
        await self.lab.start_task(self.sid, 'A supported new request')
        snap, _ = await self.wait_status('awaiting_confirmation')
        p = snap['pending']
        await self.lab.present(self.sid, p['request_id'], p['proposal_version'])
        await self.lab.converse(self.sid, 'Do not confirm')
        self.assertEqual(self.lab.backends[self.sid].executions, 0)
        await self.lab.prediction(self.sid, 'purple')
        self.assertIsNone(self.lab.snapshot(self.sid)['pending'])
        await self.lab.choose_condition(self.sid, 'water')
        with self.assertRaises(LabError):
            await self.lab.confirm(self.sid, p['request_id'], p['proposal_version'])

    async def test_provider_unavailable_and_restart_no_replay(self):
        self.lab.expert = None
        await self.lab.start_task(self.sid, 'New supported task')
        async with asyncio.timeout(2):
            while self.lab.snapshot(self.sid)['tasks'][-1]['status'] != 'failed':
                await asyncio.sleep(0.001)
        self.assertIn('unavailable', self.lab.snapshot(self.sid)['tasks'][-1]['summary'])
        self.lab.expert = self.expert
        await self.lab.start_task(self.sid, 'Fresh supported task')
        snap, _ = await self.wait_status('awaiting_confirmation')
        p = snap['pending']
        await self.lab.present(self.sid, p['request_id'], p['proposal_version'])
        # Reopen the persisted pending state without an orderly STOP.
        reopened = Lab(self.root.name, expert=self.expert, perception=self.perception)
        try:
            history = reopened.snapshot(self.sid)
            self.assertFalse(history['connected'])
            self.assertIsNone(history['pending'])
            self.assertEqual(history['tasks'][-1]['status'], 'cancelled')
            self.assertEqual(reopened.backends, {})
            self.assertEqual(reopened.registry.get(p['skill_id'], p['skill_version'])['status'], 'task_validated')
            await reopened.reconnected(self.sid)
            with self.assertRaises(LabError):
                await reopened.confirm(self.sid, p['request_id'], p['proposal_version'])
        finally:
            await reopened.shutdown()

    async def test_conversation_cannot_bypass_fresh_simulation_requirement(self):
        self.lab.get(self.sid)['requires_prepare'] = True
        state = await self.lab.converse(self.sid, 'Test the prepared vinegar sample')
        self.assertFalse(state['tasks'])
        self.assertIn('Prepare a fresh simulation', state['messages'][-1]['text'])
        self.assertFalse(self.expert.contexts)
        with self.assertRaises(LabError):
            await self.lab.start_task(self.sid, 'Test the prepared sample')
        await self.lab.converse(self.sid, 'stop')
        self.assertFalse(self.lab.snapshot(self.sid)['tasks'])

    async def test_stop_discards_late_provider_result(self):
        entered, released = asyncio.Event(), asyncio.Event()
        signals = []

        class LateExpert:
            async def run(self, context, *, tool_handler, emit, cancel_event):
                signals.append(cancel_event)
                entered.set()
                try:
                    await released.wait()
                except asyncio.CancelledError:
                    await released.wait()
                return decision()

        self.lab.expert = LateExpert()
        handle = await self.lab.start_task(self.sid, 'A slow request')
        await asyncio.wait_for(entered.wait(), 1)
        generation = self.lab.snapshot(self.sid)['generation']
        await self.lab.stop(self.sid)
        self.assertTrue(signals[0].is_set())
        released.set()
        await asyncio.sleep(0.02)
        snap, _ = await self.wait_status('cancelled', handle['task_id'])
        self.assertEqual(snap['generation'], generation + 1)
        self.assertIsNone(snap['pending'])
        self.assertEqual(self.lab.backends[self.sid].executions, 0)
