import asyncio
import copy
import tempfile
import unittest

from agentic.openarms_lab.backends import MockBackend
from agentic.openarms_lab.runtime import Lab, LabError

HASH = '1' * 64
DEFINITION = {
    'skill_id': 'sample_color', 'name': 'Prepared sample inspection',
    'intent': 'Run a mock sample and observe its qualitative color',
    'retrieval_examples': ['test prepared {condition}', 'run prepared {condition}'],
    'parameter_schema': {'condition': {'type': 'string', 'enum': ['vinegar', 'water']}},
    'preconditions': {'fresh_scene': True},
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
        self.captures = 0
        self.receipts = []

    async def inspect_scene(self, sid, view='primary'):
        self.captures += 1
        fid = str(self.captures)
        return {'evidence_id': fid, 'provenance': 'SYNTHETIC',
                'scene': {'frame_id': fid, 'fresh': self.fresh, 'view': view},
                'images': [{'evidence_id': fid, 'path': '/synthetic-fixture.png',
                            'captured_at': 123, 'sha256': HASH, 'provenance': 'SYNTHETIC'}]}

    async def localize_objects(self, sid, evidence_id, labels):
        return {'evidence_id': evidence_id, 'verified_labels': labels, 'method': 'synthetic-test'}

    async def observe(self, sid, execution_receipt):
        self.receipts.append(execution_receipt)
        frame = await self.inspect_scene(sid, execution_receipt['view'])
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
            await tool_handler('localize_objects',
                               {'evidence_id': context['images'][0]['evidence_id'], 'labels': ['receiver']})
            payload = draft()
            if context['task_context']['condition_id']:
                payload['bindings']['condition'] = context['task_context']['condition_id']
            return decision(payload=payload)
        if self.revise:
            return decision('revision', {'steps': [{'operation': 'observe', 'arguments': {'view': 'secondary'}}]})
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
        self.assertTrue(self.perception.receipts[0]['controller_completed'])
        self.assertEqual(task['observations'][0]['status'], 'unknown')
        self.assertEqual(snap['observations'][0]['provenance'], 'UNKNOWN')
        self.assertIsNone(snap['observations'][0]['value'])
        self.assertEqual([c['phase'] for c in self.expert.contexts], ['planning', 'execution_feedback', 'execution_feedback'])
        self.assertEqual([f['type'] for f in self.expert.contexts[-1]['feedback'] if f['type'] != 'execution_progress'],
                         ['perception', 'execution', 'observation'])
        self.assertNotEqual(self.expert.contexts[0]['images'][0]['evidence_id'],
                            self.expert.contexts[-1]['images'][0]['evidence_id'])
        frames = [queue.get_nowait() for _ in range(queue.qsize())]
        events = frames[-1]['state']['notebook']
        self.assertTrue(any(e['kind'] == 'observation' and e['data']['task_id'] == task['task_id'] for e in events))
        self.assertTrue(any(e['kind'] == 'execution_result' and e['data']['task_id'] == task['task_id'] for e in events))
        promotion = await self.lab.evaluate_candidate(self.sid, 'sample_color', version)
        self.assertEqual(promotion['status'], 'promoted')
        await self.lab.prepare(self.sid)
        await self.lab.converse(self.sid, 'Run prepared water', 'two')
        snap, warm = await self.wait_status('awaiting_confirmation')
        self.assertEqual(warm['route'], 'active_skill')
        self.assertEqual(snap['pending']['skill_version'], version)
        self.assertEqual(snap['pending']['metrics']['model_calls'], 0)
        self.assertEqual(snap['pending']['plan']['steps'][1]['arguments']['condition_id'], 'water')
        self.assertEqual(len(self.expert.contexts), 3)
        self.assertGreaterEqual(snap['pending']['metrics']['planning_ms'], 0)

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
