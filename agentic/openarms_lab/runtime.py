"""Session lifecycle, consent and background task orchestration for the mock lab."""
from __future__ import annotations
import asyncio
import copy
import os
import re
import time
import uuid
from pathlib import Path
from .backends import MockBackend
from .learning import (CONDITIONS, EXPERIMENT, condition,
                       reflection_feedback, science_reply, unknown_observation)
from .skills import SkillRegistry, compute_skill_hash
from .store import Store
from .task_loop import TASK_BUSY, TASK_TERMINAL, TaskLoop

TERMINAL = {'completed', 'failed', 'stopped', 'unknown', 'cancelled', 'expired', 'rejected'}
ACTIVE = {'approved', 'executing', 'stopping'}
AFFIRMATIONS = {'yes', 'yes please', 'confirm', 'yes confirm', 'yes i confirm',
                'i confirm', 'confirm it', 'confirm the request', 'confirm this request',
                'confirm that request', 'confirm the proposal', 'yes go ahead', 'go ahead', 'run it'}

class LabError(ValueError):
    pass

def _id(value, label='ID'):
    if not isinstance(value, str):
        raise LabError(f'Invalid {label}.')
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        raise LabError(f'Invalid {label}.') from None
    if str(parsed) != value:
        raise LabError(f'Invalid {label}.')
    return value

def _text(value, label='text'):
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise LabError(f'Enter nonempty {label} of at most 4000 characters.')
    return value.strip()

def _normalized(value):
    return re.sub(r'[^a-z0-9 ]', '', value.lower()).strip()

def _affirmative(value):
    # A question, quotation, negation or appended instruction is not consent.
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z ,.!]+', value.strip()):
        return False
    value = re.sub(r',\s*', ' ', value.lower().strip().rstrip('.!')).strip()
    return value in AFFIRMATIONS

class Lab(TaskLoop):
    def __init__(self, data_dir: Path, *, backend_factory=None, registry=None,
                 execution_timeout=60, confirmation_ttl=120, expert_timeout=90,
                 expert=None, perception=None, evaluator=None):
        if min(execution_timeout, confirmation_ttl, expert_timeout) <= 0:
            raise ValueError('Execution and confirmation timeouts must be positive.')
        data_dir = Path(data_dir)
        self.store = Store(data_dir / 'lab.sqlite3')
        # The existing registry file remains historical; new entries use the validated format.
        self.registry = registry or SkillRegistry(data_dir / 'task-skills.json')
        self.expert, self.perception, self.evaluator = expert, perception, evaluator
        self.expert_timeout = expert_timeout
        self.backend_factory = backend_factory
        self.execution_timeout, self.confirmation_ttl = execution_timeout, confirmation_ttl
        self.sessions, self.backends, self.workers, self.subscribers, self.locks = {}, {}, {}, {}, {}
        self.cancel_signals = {}
        self._closed = False

    def _lock(self, sid):
        _id(sid, 'session ID')
        return self.locks.setdefault(sid, asyncio.Lock())

    def _backend(self, sid):
        """Called only when starting or preparing an authorized mock trial, never for history."""
        if sid not in self.backends:
            if self.backend_factory is None and os.getenv('OPENARMS_BACKEND', 'mock') != 'mock':
                raise LabError('Physical app execution is unavailable. Use OPENARMS_BACKEND=mock.')
            backend = self.backend_factory() if self.backend_factory else MockBackend()
            if not isinstance(backend, MockBackend) or backend.mode != 'mock':
                raise LabError('Only the hardware-free mock backend is supported.')
            self.backends[sid] = backend
        return self.backends[sid]

    def _event(self, s, kind, **data):
        data.setdefault('trial_id', (s.get('trial') or {}).get('trial_id'))
        for field in ('turn_id', 'task_id', 'request_id', 'skill_id', 'skill_version', 'evidence_ids'):
            data.setdefault(field, None)
        data.setdefault('provenance', 'RUNTIME')
        data['revision'] = s['revision'] + 1
        data['sequence'] = len(s['notebook']) + 1
        event = self.store.event(s['session_id'], kind, **copy.deepcopy(data))
        s['notebook'].append(event)
        return event

    def _message(self, s, role, text, *, turn_id=None, final=True):
        message = {'id': str(uuid.uuid4()), 'role': role, 'text': text,
                   'turn_id': turn_id or str(uuid.uuid4()), 'final': final}
        s['messages'].append(message)
        self._event(s, 'message', **message)
        return message

    @staticmethod
    def _trial():
        return {'trial_id': str(uuid.uuid4()), 'condition_id': None,
                'state': 'choosing_condition', 'mode': 'MOCK', 'reflection': None}

    def get(self, sid):
        _id(sid, 'session ID')
        if sid not in self.sessions:
            s = self.store.load(sid)
            if s is None:
                raise KeyError('Session not found.')
            # Snapshot retrieval must never construct a backend, even for old physical histories.
            s.setdefault('notebook', [])
            s.setdefault('messages', [])
            s.setdefault('requests', [])
            s.setdefault('tasks', [])
            s.setdefault('scene', None)
            s.setdefault('scene_images', [])
            s.setdefault('observations', [])
            s.setdefault('revision', 0)
            s.setdefault('generation', 0)
            s.setdefault('dedupe', {})
            s.setdefault('proposal_sequence', 0)
            s['connected'] = False
            s['generation'] += 1
            s['pending'] = None
            self._cancel_tasks(s, 'Server restarted; tasks are never replayed.')
            s['history_only'] = ((s.get('experiment') or {}).get('id') != EXPERIMENT['id'] or s.get('backend') != 'mock')
            for r in s['requests']:
                if r.get('status') not in TERMINAL:
                    was_active = r.get('status') in ACTIVE
                    r.update(status='unknown' if was_active else 'cancelled',
                             reason='Server restarted; approvals and execution are never replayed.')
                    r['presented'] = False
                    if was_active and r.get('trial_id') and not any(o.get('request_id') == r['request_id'] for o in s['observations']):
                        obs = unknown_observation(r['request_id'], r['trial_id'], 'Server restarted during mock execution.')
                        s['observations'].append(obs)
                        self._event(s, 'observation', **obs)
            if not s['history_only']:
                s.setdefault('trial', self._trial())
                trial_requests = [r for r in s['requests'] if r.get('trial_id') == s['trial']['trial_id']]
                if s['trial']['state'] not in ('complete', 'reflecting'):
                    s['trial']['state'] = 'stopped' if any(r.get('result') or r['status'] == 'unknown' for r in trial_requests) else ('predicting' if s['trial']['condition_id'] else 'choosing_condition')
                s['state'] = MockBackend.home_state()
                s['capabilities'] = self._capabilities(MockBackend.capabilities())
                s['conditions'] = copy.deepcopy(list(CONDITIONS))
            else:
                # Preserve original backend, observations, sources and evidence verbatim.
                s['capabilities'] = {'mock_execution': False, 'physical_execution': False,
                                     'history_only': True, 'reason': 'Historical experiment; read-only.'}
            self.sessions[sid] = s
            self._event(s, 'recovery', text='History restored; prior approvals revoked. No hardware initialized.')
            s['revision'] += 1
            self.store.save(s)
        return self.sessions[sid]

    def snapshot(self, sid):
        return copy.deepcopy(self.get(sid))

    async def publish(self, s):
        if self._closed:
            raise LabError('Lab is shut down.')
        if self.sessions.get(s['session_id']) is not s:
            raise LabError('Publish requires the active session object.')
        # Parent may set connected=True before publishing; snapshot reads remain passive.
        if s['session_id'] in self.backends and not s.get('history_only'):
            s['state'] = self.backends[s['session_id']].state()
        s['revision'] = s.get('revision', 0) + 1
        self.store.save(s)
        snap = self.snapshot(s['session_id'])
        for queue in tuple(self.subscribers.get(s['session_id'], ())):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            # Separate copies prevent a subscriber from mutating another subscriber's state.
            queue.put_nowait({'type': 'state', 'state': copy.deepcopy(snap)})
        return snap

    def _capabilities(self, backend):
        return {**backend, 'expert_available': self.expert is not None,
                'perception_available': self.perception is not None,
                'evaluator_available': self.evaluator is not None}

    async def start_task(self, sid, text, *, turn_id=None, client_request_id=None, record_turn=True):
        text = _text(text)
        async with self._lock(sid):
            s = self.get(sid)
            self._editable(s)
            if client_request_id is not None:
                if not isinstance(client_request_id, str) or not client_request_id.strip() or len(client_request_id) > 128:
                    raise LabError('Invalid client_request_id.')
                previous = s['dedupe'].get(client_request_id)
                if previous:
                    if previous['text'] != text or not previous.get('task_id'):
                        raise LabError('client_request_id already used for a different operation.')
                    task = next(t for t in s['tasks'] if t['task_id'] == previous['task_id'])
                    return {'task_id': task['task_id'], 'status': task['status']}
            self._idle(s)
            if turn_id is None and record_turn:
                turn_id = self._message(s, 'user', text, turn_id=client_request_id)['turn_id']
            task = self._queue_task(s, text, turn_id)
            if client_request_id is not None:
                s['dedupe'][client_request_id] = {'text': text, 'task_id': task['task_id']}
            await self.publish(s)
            return {'task_id': task['task_id'], 'status': task['status']}

    async def start_improvement(self, sid, task_id, limitation):
        """Provide recorded independent failure and a pinned target to the expert."""
        limitation = _text(limitation, 'limitation')
        async with self._lock(sid):
            s = self.get(sid)
            prior = next((t for t in s['tasks'] if t['task_id'] == task_id), None)
            if not prior or prior['status'] not in TASK_TERMINAL or not prior['observations']:
                raise LabError('Improvement requires a completed task with independent feedback.')
            observed = prior['observations'][-1]
            if observed['status'] != 'unknown' and (not observed['checks'] or all(observed['checks'].values())):
                raise LabError('Improvement requires a recorded unknown outcome or failed outcome check.')
            improvement = {'task_id': task_id, 'limitation': limitation, 'feedback': copy.deepcopy(prior['feedback']),
                           'baseline_plan': copy.deepcopy(prior['plan']),
                           'baseline_task_request': prior['request']}
            task = self._queue_task(s, prior['request'], None, improvement=improvement)
            task['feedback'].extend(copy.deepcopy(prior['feedback']))
            await self.publish(s)
            return {'task_id': task['task_id'], 'status': task['status']}

    async def evaluate_candidate(self, sid, skill_id, version):
        """Run an injected evaluator and let the registry decide promotion."""
        if self.evaluator is None:
            raise LabError('Independent skill evaluator unavailable.')
        s = self.get(sid)
        candidate = self.registry.get(skill_id, version)
        if candidate['status'] != 'task_validated':
            raise LabError('Candidate must first pass task validation.')
        if not any(t['status'] == 'completed' and any(o['skill_version'] == version for o in t['observations'])
                   for t in s['tasks']):
            raise LabError('Candidate must complete a consented task with independent observer feedback.')
        try:
            baseline = self.registry.get(skill_id)
        except KeyError:
            baseline = None
        raw = await asyncio.wait_for(self.evaluator.evaluate_candidate(sid, candidate, baseline), self.expert_timeout)
        decision = self.registry.record_evaluation(skill_id, version, raw)
        self._event(s, 'skill_evaluation', skill_id=skill_id, skill_version=version,
                    decision=decision, provenance='EVALUATOR')
        await self.publish(s)
        return decision

    async def create(self):
        if self._closed:
            raise LabError('Lab is shut down.')
        sid = str(uuid.uuid4())
        b = self._backend(sid)
        b.prepare()
        s = {'session_id': sid, 'backend': 'mock', 'experiment': copy.deepcopy(EXPERIMENT),
             'revision': 0, 'generation': 0, 'connected': True, 'trial': self._trial(),
             'conditions': copy.deepcopy(list(CONDITIONS)), 'prediction': '', 'pending': None,
             'requests': [], 'tasks': [], 'scene': None, 'scene_images': [],
             'observations': [], 'messages': [], 'notebook': [],
             'state': b.state(), 'capabilities': self._capabilities(b.capabilities()), 'dedupe': {},
             'proposal_sequence': 0, 'history_only': False}
        self.sessions[sid] = s
        self._event(s, 'session_created', backend='mock', experiment_id=EXPERIMENT['id'])
        self._message(s, 'assistant', 'This is a MOCK red-cabbage pH investigation. Choose vinegar, mild baking-soda solution, or the water control. What color or acid/base result do you predict?')
        return await self.publish(s)

    def _editable(self, s):
        if s.get('history_only'):
            raise LabError('This historical session is read-only; create a new pH session.')
        if not s['connected']:
            raise LabError('Session disconnected. Reconnect before starting a fresh trial or proposal.')

    def _idle(self, s):
        self._editable(s)
        if (any(r['status'] in ACTIVE for r in s['requests']) or
                any(t['status'] in TASK_BUSY for t in s['tasks'])):
            raise LabError('A mock trial is active. Use STOP or wait for it to finish.')

    def _planning(self, s):
        self._idle(s)
        if s['trial']['state'] in ('reflecting', 'complete', 'stopped'):
            raise LabError('Prepare a new trial before choosing a condition or prediction.')

    def _invalidate(self, s, reason):
        r = s.get('pending')
        if r:
            r.update(status='cancelled', reason=reason, presented=False)
            self._cancel_tasks(s, reason, target=r['request_id'])
            self._task_event(s, self._task_for_request(s, r), 'request_cancelled',
                             proposal_version=r['proposal_version'], reason=reason)
            s['pending'] = None
            s['trial']['state'] = 'predicting' if s['trial']['condition_id'] else 'choosing_condition'

    def _choose(self, s, condition_id):
        self._planning(s)
        try:
            c = condition(condition_id)
        except ValueError as exc:
            raise LabError(str(exc)) from None
        if s['trial']['condition_id'] == condition_id:
            return
        self._invalidate(s, 'Condition corrected.')
        s['trial'].update(condition_id=c['id'], state='predicting')
        self._event(s, 'condition_selected', condition_id=c['id'])
        self._message(s, 'assistant', f"Selected {c['title']} for this MOCK trial. What color or classification do you predict, and why?")

    async def choose_condition(self, sid, condition_id):
        async with self._lock(sid):
            s = self.get(sid)
            self._choose(s, condition_id)
            return await self.publish(s)

    def _predict(self, s, text):
        self._planning(s)
        text = _text(text, 'prediction')
        if s['prediction'] == text:
            return
        self._invalidate(s, 'Prediction corrected.')
        s['prediction'] = text
        self._event(s, 'prediction', text=text)
        self._message(s, 'assistant', 'Prediction saved. Request a task when you are ready.')

    async def prediction(self, sid, text):
        async with self._lock(sid):
            s = self.get(sid)
            self._predict(s, text)
            return await self.publish(s)

    def _pending(self, s, request_id, proposal_version):
        self._editable(s)
        _id(request_id, 'request ID')
        if type(proposal_version) is not int or proposal_version < 1:
            raise LabError('An exact positive integer proposal_version is required.')
        r = s['pending']
        if (not r or r['request_id'] != request_id or r['proposal_version'] != proposal_version or r['status'] != 'requested'):
            raise LabError('Stale or consumed proposal. Review the current proposal.')
        if r['expires_at'] <= time.time():
            r.update(status='expired', reason='Confirmation expired.', presented=False)
            s['pending'] = None
            s['trial']['state'] = 'predicting'
            self._cancel_tasks(s, 'Confirmation expired.', target=request_id)
            self._task_event(s, self._task_for_request(s, r), 'request_expired')
            s['revision'] += 1
            self.store.save(s)
            raise LabError('Proposal expired; request a fresh proposal.')
        task = self._task_for_request(s, r)
        if (r['generation'] != s['generation'] or r['trial_id'] != s['trial']['trial_id'] or
                r['condition_id'] != s['trial']['condition_id'] or r['prediction'] != s['prediction'] or
                r['plan']['scene_hash'] != self._scene_hash(s) or
                r['plan_hash'] != compute_skill_hash(r['plan']) or r['plan'] != task['plan'] or task['status'] != 'awaiting_confirmation'):
            self._invalidate(s, 'Proposal binding changed.')
            s['revision'] += 1
            self.store.save(s)
            raise LabError('Proposal binding changed. Request a fresh proposal.')
        return r

    async def present(self, sid, request_id, proposal_version, channel='text', reply_id=None):
        async with self._lock(sid):
            s = self.get(sid)
            if channel not in ('text', 'audio'):
                raise LabError('Presentation channel must be text or audio.')
            if reply_id is not None and (not isinstance(reply_id, str) or not reply_id.strip() or len(reply_id) > 128):
                raise LabError('Invalid reply ID.')
            r = self._pending(s, request_id, proposal_version)
            if r['presented']:
                return self.snapshot(sid)
            r['presented'] = True
            r['presentation'] = {'channel': channel, 'reply_id': reply_id, 'generation': s['generation'],
                                 'proposal_version': proposal_version, 'time': time.time()}
            self._task_event(s, self._task_for_request(s, r), 'proposal_presented', **r['presentation'])
            return await self.publish(s)

    def _confirm(self, s, request_id, proposal_version):
        r = self._pending(s, request_id, proposal_version)
        if not r['presented'] or r['presentation']['generation'] != s['generation']:
            raise LabError('The exact proposal must be presented before a new completed confirmation.')
        task = self._task_for_request(s, r)
        try:
            self._check_context(task, r['plan'])
            if r['skill_id']:
                self.registry.authorize(task['task_id'], r['skill_id'], r['skill_version'], consume=True)
        except (KeyError, ValueError) as exc:
            raise LabError(str(exc)) from None
        r.update(status='approved', student_confirmed=True, confirmed_at=time.time())
        task['status'] = 'executing'
        s['pending'] = None
        s['trial']['state'] = 'executing'
        self._task_event(s, task, 'student_confirmed', proposal_version=proposal_version)
        self._spawn(s, task, self._execute_task(s, task, r))

    async def confirm(self, sid, request_id, proposal_version=None):
        async with self._lock(sid):
            s = self.get(sid)
            self._confirm(s, request_id, proposal_version)
            return await self.publish(s)

    def _cancel_session_tasks(self, s, reason, *, target=None):
        self._cancel_tasks(s, reason, target=target)
        stopped_execution = False
        for r in s['requests']:
            if r['status'] in ACTIVE and (not target or target in (r['request_id'], r.get('task_id'))):
                stopped_execution = True
                r.update(status='stopped', reason=reason, presented=False)
                task = self._task_for_request(s, r)
                receipt = {'request_id': r['request_id'], 'backend': 'mock', 'status': 'stopped', 'reason': reason}
                r['result'] = receipt
                task['execution'].append(receipt)
                self._task_event(s, task, 'execution_result', receipt=receipt, provenance='MOCK')
                s['trial']['state'] = 'stopped'
        return stopped_execution

    async def _stop_backend(self, sid):
        backend = self.backends.get(sid)
        if backend:
            await backend.stop()
            await backend.wait_idle()

    async def cancel(self, sid, request_id=None):
        async with self._lock(sid):
            s = self.get(sid)
            self._editable(s)
            if request_id is not None:
                _id(request_id, 'request or task ID')
                if not any(t['status'] not in TASK_TERMINAL and request_id in (t['task_id'], t['request_id'])
                           for t in s['tasks']):
                    raise LabError('That task or proposal is stale.')
            if s['pending'] and request_id in (None, s['pending']['request_id'], s['pending']['task_id']):
                self._invalidate(s, 'Student cancelled.')
            if self._cancel_session_tasks(s, 'Student cancelled.', target=request_id):
                await self._stop_backend(sid)
            return await self.publish(s)

    async def stop(self, sid, disconnect=False):
        if type(disconnect) is not bool:
            raise LabError('disconnect must be boolean.')
        async with self._lock(sid):
            s = self.get(sid)
            reason = 'Session disconnected.' if disconnect else 'STOP requested.'
            self._invalidate(s, reason)
            self._cancel_session_tasks(s, reason)
            s['generation'] += 1
            if disconnect:
                s['connected'] = False
            if not s.get('history_only') and not disconnect:
                s['trial']['state'] = 'stopped'
            self._event(s, 'stop_requested', disconnect=disconnect)
            await self._stop_backend(sid)
            return await self.publish(s)

    async def reconnected(self, sid):
        # A new lease revokes even an approval issued just before the socket swap.
        await self.stop(sid, disconnect=True)
        async with self._lock(sid):
            s = self.get(sid)
            if s.get('history_only'):
                raise LabError('Historical session is read-only; create a pH session.')
            s['connected'] = True
            self._event(s, 'reconnected', generation=s['generation'])
            return await self.publish(s)

    def _prepare(self, s):
        self._idle(s)
        self._invalidate(s, 'New trial prepared.')
        previous = copy.deepcopy(s['trial'])
        self._backend(s['session_id']).prepare()
        s.update(trial=self._trial(), prediction='')
        self._event(s, 'trial_prepared', previous_trial=previous)
        self._message(s, 'assistant', 'A fresh MOCK trial is ready at HOME. Choose a condition and make a new prediction; your notebook is preserved.')

    async def prepare(self, sid):
        async with self._lock(sid):
            s = self.get(sid)
            self._prepare(s)
            return await self.publish(s)

    def _reflect(self, s, text):
        self._idle(s)
        text = _text(text, 'reflection')
        if s['trial']['state'] not in ('reflecting', 'complete', 'stopped'):
            raise LabError('Run a trial before reflecting on its evidence.')
        observations = [o for o in s['observations'] if o.get('trial_id') == s['trial']['trial_id']]
        if not observations:
            raise LabError('This trial has no execution or observation evidence yet.')
        feedback = reflection_feedback(text, observations)
        s['trial'].update(state='complete', reflection={'text': text, **feedback})
        self._event(s, 'reflection', text=text, feedback=feedback)
        self._message(s, 'assistant', feedback['feedback'])

    async def reflection(self, sid, text):
        async with self._lock(sid):
            s = self.get(sid)
            self._reflect(s, text)
            return await self.publish(s)

    @staticmethod
    def _condition_input(text):
        """Recognize one complete choice/correction, never execute a supported subset."""
        norm = text.lower().strip().rstrip('.!')
        aliases = {'vinegar': 'vinegar', 'baking soda': 'baking_soda', 'baking-soda': 'baking_soda',
                   'baking_soda': 'baking_soda', 'water': 'water', 'water control': 'water'}
        pattern = (r'(?:actually[, ]*|instead[, ]*|no[, ]*)?'
                   r'(?:(?:i (?:choose|pick|want|would like)|choose|pick|select|use|try|switch to|change to|make that|let[’\']s (?:use|try))\s+)?'
                   r'(?:the\s+)?(?P<condition>vinegar|baking[-_ ]soda|water(?: control)?)(?: solution)?(?:\s+(?:please|instead))?')
        match = re.fullmatch(pattern, norm)
        return aliases.get(match['condition']) if match else None

    async def converse(self, sid, text, client_request_id=None):
        text = _text(text)
        if client_request_id is not None and (not isinstance(client_request_id, str) or not client_request_id.strip() or len(client_request_id) > 128):
            raise LabError('Invalid client_request_id.')
        # A duplicate must be detected before STOP, correction, reflection, or confirmation.
        normalized = _normalized(text)
        async with self._lock(sid):
            s = self.get(sid)
            self._editable(s)
            if client_request_id in s['dedupe']:
                if s['dedupe'][client_request_id]['text'] != text:
                    raise LabError('client_request_id reused for different input.')
                return self.snapshot(sid)
            turn = self._message(s, 'user', text, turn_id=client_request_id)
            if client_request_id:
                s['dedupe'][client_request_id] = {'text': text, 'trial_id': s['trial']['trial_id']}
            if normalized in ('stop', 'stop now', 'emergency stop'):
                stop = True
            else:
                stop = False
                c = self._condition_input(text)
                try:
                    if normalized in ('cancel', 'cancel it', 'cancel the request', 'cancel the proposal',
                                      'never mind', 'nevermind'):
                        self._invalidate(s, 'Student cancelled.')
                        if self._cancel_session_tasks(s, 'Student cancelled.'):
                            await self._stop_backend(sid)
                        self._message(s, 'assistant', 'Task cancelled.')
                    elif _affirmative(text):
                        r = s['pending']
                        if r:
                            self._confirm(s, r['request_id'], r['proposal_version'])
                        else:
                            self._message(s, 'assistant', 'There is no current presented proposal to confirm.')
                    elif re.search(r'\b(confirm|approve|go ahead|run it)\b', normalized):
                        self._message(s, 'assistant', 'Send a separate completed “confirm” after reviewing the current proposal.')
                    elif c:
                        self._choose(s, c)
                    elif normalized in ('new trial', 'next trial', 'prepare next trial', 'start over', 'try again'):
                        self._prepare(s)
                    elif normalized.startswith('reflection '):
                        self._reflect(s, text.partition(' ')[2])
                    elif (re.match(r'^(?:i (?:predict|think|expect|guess)\b)', normalized) or
                          re.fullmatch(r'(?:it (?:will|might|should) (?:be|turn) )?(?:pink|purple|blue|green|blue green|acidic|basic|neutral|near neutral)', normalized)):
                        self._predict(s, text)
                    elif re.match(r'^(?:what|why|how|explain|tell me)\b', normalized) and re.search(
                            r'\b(?:ph|indicator|acidic|basic|alkaline|cabbage|control|evidence|result)\b', normalized):
                        current = [o for o in s['observations'] if o.get('trial_id') == s['trial']['trial_id']]
                        self._message(s, 'assistant', science_reply(text, current))
                    else:
                        task = self._queue_task(s, text, turn['turn_id'])
                        if client_request_id:
                            s['dedupe'][client_request_id]['task_id'] = task['task_id']
                except LabError as exc:
                    self._message(s, 'assistant', str(exc))
            result = await self.publish(s)
        if stop:
            return await self.stop(sid)
        return result

    async def request(self, sid, text, client_request_id=None):
        """The request endpoint is conversation; it cannot accept action parameters."""
        return await self.converse(sid, text, client_request_id)

    async def tool(self, sid, name, args):
        if not isinstance(args, dict):
            raise LabError('Tool arguments must be an object.')
        schemas = {'get_lab_state': set(), 'choose_condition': {'condition_id'},
                   'record_prediction': {'text'}, 'request_action': {'text'}, 'start_task': {'text'},
                   'student_confirm': {'request_id', 'proposal_version'}, 'cancel_request': {'request_id'},
                   'prepare_next_trial': set(), 'record_reflection': {'text'}, 'stop_lab': set(),
                   '_record_transcript': {'role', 'text', 'turn_id', 'final'},
                   '_record_usage': {'model', 'model_calls', 'tokens', 'usage', 'turn_id'},
                   '_cancel_tool_request': {'request_id', 'tool_call_id'}}
        if name not in schemas:
            raise LabError('Unknown pH lab tool.')
        internal = {'_voice_generation', '_voice_consent', '_voice_turn_id', '_tool_call_id'}
        if set(args) - schemas[name] - internal:
            raise LabError('Unexpected pH tool arguments.')
        s = self.get(sid)
        if '_voice_generation' in args and (type(args['_voice_generation']) is not int or args['_voice_generation'] != s['generation']):
            raise LabError('Stale voice generation; start a fresh turn.')
        clean = {key: value for key, value in args.items() if key in schemas[name]}
        required = schemas[name] if name in ('choose_condition', 'record_prediction', 'request_action', 'start_task', 'student_confirm', 'record_reflection', '_record_transcript') else set()
        if required - set(clean):
            raise LabError('Required pH tool argument missing.')
        if name == 'get_lab_state':
            return self.snapshot(sid)
        if name == 'choose_condition':
            return await self.choose_condition(sid, clean['condition_id'])
        if name == 'record_prediction':
            return await self.prediction(sid, clean['text'])
        if name == 'start_task' or (name == 'request_action' and '_voice_generation' in args):
            turn_id = args.get('_voice_turn_id')
            if turn_id is not None and not any(m['turn_id'] == turn_id and m['role'] == 'user' and m.get('final')
                                               for m in s['messages']):
                raise LabError('Voice task requires a completed user turn ID.')
            return await self.start_task(sid, clean['text'], turn_id=turn_id, record_turn=False,
                                         client_request_id='live:' + args['_tool_call_id'] if args.get('_tool_call_id') else None)
        if name == 'request_action':
            return await self.converse(sid, clean['text'], 'live:' + args['_tool_call_id'] if args.get('_tool_call_id') else None)
        if name == 'student_confirm':
            # Gateway must validate the completed input against the proposal presented at turn start.
            consent = args.get('_voice_consent')
            if consent is not None and (not isinstance(consent, dict) or consent.get('request_id') != clean['request_id'] or not _affirmative(consent.get('text'))):
                raise LabError('Trusted voice input is not an unambiguous confirmation.')
            return await self.confirm(sid, **clean)
        if name == 'cancel_request':
            return await self.cancel(sid, **clean)
        if name == 'prepare_next_trial':
            return await self.prepare(sid)
        if name == 'record_reflection':
            return await self.reflection(sid, **clean)
        if name == 'stop_lab':
            return await self.stop(sid)
        async with self._lock(sid):
            s = self.get(sid)
            if name == '_record_transcript':
                role, text, turn_id, final = (clean[k] for k in ('role', 'text', 'turn_id', 'final'))
                if role not in ('user', 'assistant') or type(final) is not bool:
                    raise LabError('Transcript requires user/assistant role and boolean final.')
                text = _text(text, 'transcript')
                if not isinstance(turn_id, str) or not turn_id.strip() or len(turn_id) > 128:
                    raise LabError('Invalid transcript turn ID.')
                old = next((m for m in s['messages'] if m.get('turn_id') == turn_id), None)
                if old:
                    if old['role'] != role or (old.get('final') and (old['text'] != text or not final)):
                        raise LabError('Completed transcript or turn role cannot be rewritten.')
                    if old['text'] == text and old.get('final') == final:
                        return self.snapshot(sid)
                    old.update(text=text, final=final)
                    self._event(s, 'transcript_updated', role=role, text=text, turn_id=turn_id, final=final)
                else:
                    self._message(s, role, text, turn_id=turn_id, final=final)
            elif name == '_record_usage':
                self._event(s, 'model_usage', **clean)
            elif name == '_cancel_tool_request':
                r = s['pending']
                key = 'live:' + clean['tool_call_id'] if clean.get('tool_call_id') else None
                target = clean.get('request_id') or s['dedupe'].get(key, {}).get('task_id')
                if target:
                    if r and target in (r['request_id'], r['task_id']):
                        self._invalidate(s, 'Voice tool interrupted.')
                    if self._cancel_session_tasks(s, 'Voice tool interrupted.', target=target):
                        await self._stop_backend(sid)
                elif r and (clean.get('request_id') == r['request_id'] or
                          clean.get('tool_call_id') and r.get('client_request_id') == 'live:' + clean['tool_call_id']):
                    self._invalidate(s, 'Voice tool interrupted.')
            return await self.publish(s)

    async def shutdown(self):
        if self._closed:
            return
        for sid in list(self.sessions):
            await self.stop(sid, disconnect=True)
        self.store.close()
        self._closed = True
