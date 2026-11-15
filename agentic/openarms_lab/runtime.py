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
from .contracts import LabExecutor
from .conversation import condition_input, controller_state, conversation_reply, explicit_action, prediction_input, read_only_turn, reset_input, stop_input, words
from .learning import CONDITIONS, EXPERIMENT, reflection_feedback, unknown_observation
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

def _affirmative(value):
    # A question, quotation, negation or appended instruction is not consent.
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z ,.!]+', value.strip()):
        return False
    value = re.sub(r',\s*', ' ', value.lower().strip().rstrip('.!')).strip()
    return value in AFFIRMATIONS

class Lab(TaskLoop):
    def __init__(self, data_dir: Path, *, backend_factory=None, registry=None,
                 execution_timeout=60, confirmation_ttl=120, expert_timeout=90,
                 expert=None, perception=None, evaluator=None, auto_evaluate=False, execution_scope=None,
                 experiment=None, conditions=None):
        if min(execution_timeout, confirmation_ttl, expert_timeout) <= 0:
            raise ValueError('Execution and confirmation timeouts must be positive.')
        data_dir = Path(data_dir)
        self.store = Store(data_dir / 'lab.sqlite3')
        # The existing registry file remains historical; new entries use the validated format.
        self.registry = registry or SkillRegistry(data_dir / 'task-skills.json')
        self.expert, self.perception, self.evaluator = expert, perception, evaluator
        self.auto_evaluate = auto_evaluate
        self.execution_scope = execution_scope
        self.experiment = copy.deepcopy(EXPERIMENT if experiment is None else experiment)
        self.conditions = copy.deepcopy(list(CONDITIONS) if conditions is None else conditions)
        self.evaluations = {}
        self.expert_timeout = expert_timeout
        self.backend_factory = backend_factory
        self.execution_timeout, self.confirmation_ttl = execution_timeout, confirmation_ttl
        self.sessions, self.backends, self.workers, self.subscribers, self.locks = {}, {}, {}, {}, {}
        self.cancel_signals = {}
        self._closed = False

    def _lock(self, sid):
        _id(sid, 'session ID')
        return self.locks.setdefault(sid, asyncio.Lock())

    def _backend(self, sid) -> LabExecutor:
        """Called only when starting or preparing an authorized mock trial, never for history."""
        if sid not in self.backends:
            if self.backend_factory is None and os.getenv('OPENARMS_BACKEND', 'mock') != 'mock':
                raise LabError('Physical app execution is unavailable. Use OPENARMS_BACKEND=mock.')
            backend = self.backend_factory() if self.backend_factory else MockBackend()
            supported = isinstance(backend, MockBackend) and backend.mode == 'mock'
            if backend.mode == 'mujoco':
                from .mujoco_backend import MujocoBackend
                supported = isinstance(backend, MujocoBackend)
            if not supported or backend.capabilities().get('physical_execution') is not False:
                raise LabError('Only the hardware-free mock and MuJoCo backends are supported.')
            bind_session = getattr(backend, 'bind_session', None)
            if bind_session is not None:
                bind_session(sid)
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
            s['history_only'] = ((s.get('experiment') or {}).get('id') != self.experiment['id'] or
                                 s.get('backend') not in ('mock', 'mujoco') or
                                 (self.execution_scope is not None and s.get('execution_scope') != self.execution_scope))
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
                if s.get('backend') == 'mujoco':
                    s['requires_prepare'] = True
                    s['state']['armed'] = False
                    s['state']['simulation'] = {'engine': 'MuJoCo', 'status': 'unavailable',
                                               'warnings': ['Server restarted. Prepare a fresh simulation.']}
                else:
                    s['state'] = MockBackend.home_state()
                    s['capabilities'] = self._capabilities(MockBackend.capabilities())
                s['conditions'] = copy.deepcopy(self.conditions)
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
        state = copy.deepcopy(self.get(sid))
        owned = {version for task in state['tasks']
                 for version in self.registry.data['validations'].get(task['task_id'], {})}
        visible = owned | set(self.registry.data['active'].values())
        state['skills'] = [self.registry.get(entry['definition']['skill_id'], version)
                           for version, entry in self.registry.data['versions'].items() if version in visible]
        evaluation_ids = {e['data']['decision']['evaluation_id'] for e in state['notebook']
                          if e['kind'] == 'skill_evaluation' and 'decision' in e['data']}
        state['evaluations'] = copy.deepcopy([e for e in self.registry.data['evaluations']
                                              if e['evaluation_id'] in evaluation_ids])
        state['skill_decisions'] = copy.deepcopy([d for d in self.registry.data['decisions']
                                                 if d['evaluation_id'] in evaluation_ids])
        return state

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
            if s.get('requires_prepare'):
                raise LabError('Prepare a fresh simulation after the server restart.')
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

    @staticmethod
    def _voice_generation(s, expected):
        if expected is not None and (type(expected) is not int or expected != s['generation']):
            raise LabError('Stale voice generation; start a fresh turn.')

    async def start_improvement(self, sid, task_id, limitation, *, voice_generation=None):
        """Provide recorded independent failure and a pinned target to the expert."""
        limitation = _text(limitation, 'limitation')
        async with self._lock(sid):
            s = self.get(sid)
            self._voice_generation(s, voice_generation)
            self._editable(s)
            if s.get('requires_prepare'):
                raise LabError('Prepare a fresh simulation after the server restart.')
            prior = next((t for t in s['tasks'] if t['task_id'] == task_id), None)
            if not prior or prior['status'] not in TASK_TERMINAL or not prior['observations']:
                raise LabError('Improvement requires a completed task with independent feedback.')
            observed = next((o for o in prior['observations'] if o['status'] == 'unknown' or
                             (o['checks'] and not all(o['checks'].values()))), None)
            if not observed:
                raise LabError('Improvement requires a recorded unknown outcome or failed outcome check.')
            original = next((r['plan'] for r in s['requests'] if r.get('task_id') == task_id and
                             (r.get('plan') or {}).get('skill_id')), prior['plan'])
            improvement = {'task_id': task_id, 'limitation': limitation, 'feedback': copy.deepcopy(prior['feedback']),
                           'baseline_plan': copy.deepcopy(original), 'failure_observation': copy.deepcopy(observed),
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
        self._editable(s)
        generation = s['generation']
        candidate = self.registry.get(skill_id, version)
        if candidate['status'] != 'task_validated':
            raise LabError('Candidate must first pass task validation.')
        completed = [t for t in s['tasks'] if t['status'] == 'completed' and any(
            o['skill_version'] == version and o['status'] == 'observed' and o['checks'] and all(o['checks'].values())
            and any(r['request_id'] == o['request_id'] and r['plan_hash'] == o['plan_hash']
                    and r['skill_version'] == version and r['status'] == 'completed'
                    and (r.get('result') or {}).get('controller_completed') is True for r in s['requests'])
            for o in t['observations'])]
        if not completed:
            raise LabError('Candidate needs a consented successful execution and independently observed passing outcome.')
        try:
            baseline = self.registry.get(skill_id)
        except KeyError:
            baseline = None
        improvement = next((t.get('improvement') for t in reversed(completed) if t.get('improvement')), None)
        if improvement:
            pinned = improvement['baseline_plan']
            if not baseline or baseline['skill_id'] != pinned['skill_id'] or baseline['version'] != pinned['skill_version']:
                raise LabError('The pinned improvement baseline changed; request a fresh comparison.')
        evaluation = asyncio.create_task(self.evaluator.evaluate_candidate(sid, candidate, baseline))
        running = self.evaluations.setdefault(sid, {})
        owner = {'task_id': completed[-1]['task_id'], 'request_id': completed[-1]['request_id'], 'cancelled': False}
        running[evaluation] = owner
        try:
            raw = await asyncio.wait_for(evaluation, self.expert_timeout)
            async with self._lock(sid):
                self._editable(s)
                if s['generation'] != generation or owner['cancelled']:
                    raise LabError('Evaluation was revoked by STOP or reconnection; no skill was promoted.')
                try:
                    current_baseline = self.registry.get(skill_id)
                except KeyError:
                    current_baseline = None
                if ((current_baseline or {}).get('version') != (baseline or {}).get('version') or
                        self.registry.get(skill_id, version)['status'] != 'task_validated'):
                    raise LabError('The active skill changed during evaluation; request a fresh comparison.')
                evaluated_scope = (raw.get('metrics') or {}).get('source_scope')
                if (self.execution_scope is not None and evaluated_scope is not None and
                        evaluated_scope != self.execution_scope):
                    raise LabError('Evaluation source scope differs from this session; restart with the current implementation.')
                decision = self.registry.record_evaluation(skill_id, version, raw)
                self._event(s, 'skill_evaluation', skill_id=skill_id, skill_version=version,
                            decision=decision, provenance='EVALUATOR', execution_scope=self.execution_scope)
                await self.publish(s)
                return decision
        finally:
            running.pop(evaluation, None)

    def _learn_route(self, s, task):
        """After a consented, independently observed success, route the student's own words to that skill."""
        plan = task.get('plan') or {}
        version = plan.get('skill_version')
        succeeded = task['status'] == 'completed' and any(
            o['skill_version'] == version and o['status'] == 'observed' and o['checks'] and all(o['checks'].values())
            and any(r['request_id'] == o['request_id'] and r['plan_hash'] == o['plan_hash'] and r.get('student_confirmed')
                    and r['status'] == 'completed' and (r.get('result') or {}).get('controller_completed') is True
                    for r in s['requests'])
            for o in task['observations'])
        if not succeeded or task.get('route') != 'expert' or not isinstance(task.get('request'), str):
            return
        route = self.registry.learn_route(task['request'], plan['skill_id'], version, plan.get('bindings') or {})
        if route:
            self._event(s, 'skill_route_learned', task_id=task['task_id'], skill_id=plan['skill_id'],
                        skill_version=version, template=route['template'], provenance='HOST')

    async def _evaluate_completed(self, s, task):
        plan = task.get('plan') or {}
        if not plan.get('skill_id'):
            return
        skill = self.registry.get(plan['skill_id'], plan['skill_version'])
        if skill['status'] == 'active':
            self._learn_route(s, task)
            await self.publish(s)
            return
        if not self.auto_evaluate or not self.evaluator or skill['status'] != 'task_validated':
            return
        self._event(s, 'skill_evaluation_started', task_id=task['task_id'],
                    skill_id=plan['skill_id'], skill_version=plan['skill_version'])
        await self.publish(s)
        try:
            decision = await self.evaluate_candidate(s['session_id'], plan['skill_id'], plan['skill_version'])
            if decision['status'] == 'promoted':
                self._learn_route(s, task)
            self._message(s, 'assistant', 'Skill evaluation '+decision['status']+'. '+
                          ('Equivalent supported requests can now reuse it.' if decision['status'] == 'promoted'
                           else 'The existing active skill remains unchanged.'))
        except (ValueError, RuntimeError, TimeoutError) as exc:
            self._event(s, 'skill_evaluation_failed', task_id=task['task_id'],
                        reason=str(exc), skill_id=plan['skill_id'], skill_version=plan['skill_version'])
            self._message(s, 'assistant', 'Skill registration is incomplete: '+str(exc))
        await self.publish(s)

    async def create(self):
        if self._closed:
            raise LabError('Lab is shut down.')
        sid = str(uuid.uuid4())
        b = self._backend(sid)
        b.prepare()
        s = {'session_id': sid, 'backend': b.mode, 'execution_scope': self.execution_scope,
             'experiment': copy.deepcopy(self.experiment),
             'revision': 0, 'generation': 0, 'connected': True, 'trial': self._trial(),
             'conditions': copy.deepcopy(self.conditions), 'prediction': '', 'pending': None,
             'requests': [], 'tasks': [], 'scene': None, 'scene_images': [],
             'observations': [], 'messages': [], 'notebook': [],
             'state': b.state(), 'capabilities': self._capabilities(b.capabilities()), 'dedupe': {},
             'proposal_sequence': 0, 'history_only': False}
        self.sessions[sid] = s
        s['trial']['mode'] = 'SIMULATED' if b.mode == 'mujoco' else 'MOCK'
        self._event(s, 'session_created', backend=b.mode, experiment_id=self.experiment['id'])
        self._message(s, 'assistant', 'The MuJoCo simulation is ready.' if b.mode == 'mujoco' else 'The mock lab is ready.')
        if b.mode == 'mujoco' and self.perception is not None:
            try:
                frame = await asyncio.wait_for(self.perception.inspect_scene(sid), min(15, self.execution_timeout))
                s.update(scene=frame['scene'], scene_images=frame['images'])
            except (ValueError, RuntimeError, OSError, TimeoutError) as exc:
                self._event(s, 'scene_unavailable', code=type(exc).__name__)
                self._message(s, 'assistant', 'The simulation camera is unavailable. A task will report the problem before proposing an action.')
        return await self.publish(s)

    def _editable(self, s):
        if s.get('history_only'):
            raise LabError('This historical session is read-only; create a new session.')
        if not s['connected']:
            raise LabError('Session disconnected. Reconnect before starting a fresh trial or proposal.')

    def _idle(self, s):
        self._editable(s)
        if (any(r['status'] in ACTIVE for r in s['requests']) or
                any(t['status'] in TASK_BUSY for t in s['tasks'])):
            raise LabError('A mock trial is active. Use STOP or wait for it to finish.')

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
        self._idle(s)
        c = next((item for item in self.conditions if item['id'] == condition_id), None)
        if c is None:
            pending = s.get('pending')
            if pending and self._prepared_sample(pending['plan']) and condition_id != pending['condition_id']:
                self._invalidate(s, 'Requested condition is unsupported; previous proposal revoked.')
            raise LabError('Choose a condition supported by this configured experiment: '+
                           ', '.join(item['title'] for item in self.conditions)+'.')
        if s['trial']['condition_id'] == condition_id:
            return
        pending = s['pending']
        if pending and self._prepared_sample(pending['plan']):
            self._invalidate(s, 'Condition corrected.')
        s['trial']['condition_id'] = c['id']
        if s['trial']['state'] == 'choosing_condition':
            s['trial']['state'] = 'predicting'
        self._event(s, 'condition_selected', condition_id=c['id'])
        trial_kind = 'simulated' if s['backend'] == 'mujoco' else 'mock'
        self._message(s, 'assistant', f"Selected {c['title']} for this {trial_kind} trial.")

    async def choose_condition(self, sid, condition_id, *, turn_id=None, voice_generation=None):
        async with self._lock(sid):
            s = self.get(sid)
            if voice_generation is not None:
                if voice_generation != s['generation']:
                    raise LabError('Stale voice generation; start a fresh turn.')
                message = self._completed_student_turn(s, turn_id)
                if not message or condition_input(message['text']) != condition_id:
                    raise LabError('Use the completed student choice verbatim.')
                key = 'voice:' + turn_id
                if key not in s['dedupe']:
                    task = self._conversational_choice(s, condition_id, message['text'], turn_id)
                    s['dedupe'][key] = {'text': message['text'], 'task_id': task['task_id'] if task else None}
                    return await self.publish(s)
                return self.snapshot(sid)
            pending_before = s.get('pending')
            try:
                self._choose(s, condition_id)
            except LabError:
                if pending_before is not None and s.get('pending') is None:
                    await self.publish(s)
                raise
            prior = s['tasks'][-1] if s['tasks'] else None
            if prior and prior['status'] == 'needs_clarification':
                message = next((m for m in reversed(s['messages']) if m['turn_id'] == turn_id
                                and m['role'] == 'user' and m.get('final')), None)
                answer = message['text'] if message else next(item['title'] for item in self.conditions if item['id'] == condition_id)
                self._queue_task(s, answer, turn_id)
            return await self.publish(s)

    def _predict(self, s, text):
        self._editable(s)
        text = _text(text, 'prediction')
        if s['prediction'] == text:
            return
        if any(t['status'] in ('executing', 'observing') for t in s['tasks']):
            raise LabError('Save a prediction before execution or after this trial finishes.')
        self._invalidate(s, 'Prediction changed; review a fresh proposal.')
        self._cancel_tasks(s, 'Prediction changed during planning.')
        s['prediction'] = text
        self._event(s, 'prediction', text=text)
        self._message(s, 'assistant', 'Prediction saved.')

    async def prediction(self, sid, text, *, voice_generation=None):
        async with self._lock(sid):
            s = self.get(sid)
            self._voice_generation(s, voice_generation)
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
        sample = self._prepared_sample(r['plan'])
        if (r['generation'] != s['generation'] or r['trial_id'] != s['trial']['trial_id'] or
                r['plan'].get('execution_scope') != self.execution_scope or
                (sample and r['condition_id'] != s['trial']['condition_id']) or
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
        if (not r['presented'] or r['presentation']['generation'] != s['generation'] or
                r['presentation']['proposal_version'] != proposal_version):
            raise LabError('The exact proposal must be presented before a new completed confirmation.')
        task = self._task_for_request(s, r)
        try:
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
        for evaluation, owner in tuple(self.evaluations.get(s['session_id'], {}).items()):
            if not owner['cancelled'] and target in (None, owner['task_id'], owner['request_id']):
                owner['cancelled'] = True
                evaluation.cancel()
                self._event(s, 'skill_evaluation_cancelled', task_id=owner['task_id'],
                            request_id=owner['request_id'], reason=reason)
        stopped_execution = False
        for r in s['requests']:
            if r['status'] in ACTIVE and (not target or target in (r['request_id'], r.get('task_id'))):
                stopped_execution = True
                r.update(status='stopped', reason=reason, presented=False)
                task = self._task_for_request(s, r)
                receipt = {'request_id': r['request_id'], 'backend': s['backend'], 'status': 'stopped', 'reason': reason}
                r['result'] = receipt
                task['execution'].append(receipt)
                self._task_event(s, task, 'execution_result', receipt=receipt,
                                 provenance='SIMULATED' if s['backend'] == 'mujoco' else 'MOCK')
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
                task_live = any(t['status'] not in TASK_TERMINAL - {'needs_clarification'}
                                and request_id in (t['task_id'], t['request_id']) for t in s['tasks'])
                evaluation_live = any(not owner['cancelled'] and request_id in (owner['task_id'], owner['request_id'])
                                      for owner in self.evaluations.get(sid, {}).values())
                if not task_live and not evaluation_live:
                    raise LabError('That task or proposal is stale.')
            if s['pending'] and request_id in (None, s['pending']['request_id'], s['pending']['task_id']):
                self._invalidate(s, 'Student cancelled.')
            if self._cancel_session_tasks(s, 'Student cancelled.', target=request_id):
                await self._stop_backend(sid)
            if request_id is None:
                s['generation'] += 1
            return await self.publish(s)

    async def stop(self, sid, disconnect=False):
        if type(disconnect) is not bool:
            raise LabError('disconnect must be boolean.')
        async with self._lock(sid):
            s = self.get(sid)
            reason = 'Session disconnected.' if disconnect else 'STOP requested.'
            pending_task = any(t['status'] not in TASK_TERMINAL - {'needs_clarification'} for t in s['tasks'])
            controller_active = any(r['status'] in ACTIVE and
                                    controller_state(s, self._task_for_request(s, r)) == 'in_progress'
                                    for r in s['requests'])
            self._invalidate(s, reason)
            self._cancel_session_tasks(s, reason)
            evaluations = tuple(self.evaluations.get(sid, ()))
            for evaluation in evaluations:
                evaluation.cancel()
            s['generation'] += 1
            if disconnect:
                s['connected'] = False
            effect = 'execution_stopped' if controller_active else ('task_cancelled' if pending_task else 'idle')
            if not s.get('history_only') and not disconnect and effect != 'idle':
                s['trial']['state'] = 'stopped'
            self._event(s, 'stop_requested', disconnect=disconnect, effect=effect)
            await self._stop_backend(sid)
            snapshot = await self.publish(s)
        await asyncio.gather(*evaluations, return_exceptions=True)
        return snapshot

    async def reconnected(self, sid):
        # A new lease revokes even an approval issued just before the socket swap.
        await self.stop(sid, disconnect=True)
        async with self._lock(sid):
            s = self.get(sid)
            if s.get('history_only'):
                raise LabError('Historical session is read-only; create a new session.')
            s['connected'] = True
            self._event(s, 'reconnected', generation=s['generation'])
            return await self.publish(s)

    def _prepare(self, s):
        self._idle(s)
        self._invalidate(s, 'New trial prepared.')
        previous = copy.deepcopy(s['trial'])
        self._backend(s['session_id']).prepare()
        s.update(trial=self._trial(), prediction='', requires_prepare=False)
        s['trial']['mode'] = 'SIMULATED' if s['backend'] == 'mujoco' else 'MOCK'
        self._event(s, 'trial_prepared', previous_trial=previous)
        self._message(s, 'assistant', 'A fresh simulation is ready.' if s['backend'] == 'mujoco' else 'A fresh mock trial is ready.')

    async def prepare(self, sid, *, voice_generation=None):
        async with self._lock(sid):
            s = self.get(sid)
            self._voice_generation(s, voice_generation)
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

    async def reflection(self, sid, text, *, voice_generation=None):
        async with self._lock(sid):
            s = self.get(sid)
            self._voice_generation(s, voice_generation)
            self._reflect(s, text)
            return await self.publish(s)

    def _conversational_choice(self, s, condition_id, text, turn_id):
        prior = s['tasks'][-1] if s['tasks'] else None
        pending = s.get('pending')
        sample = self._prepared_sample(pending['plan']) if pending else None
        correcting = bool(sample and condition_id != sample['arguments']['condition_id'])
        supported = any(item['id'] == condition_id for item in self.conditions)
        explicit_correction = bool(re.match(r'^(?:actually|instead|no|switch to|change to|make that)\b', words(text)))
        if not supported and prior and prior['status'] in ('queued', 'running') and not explicit_correction:
            raise LabError('Choose a condition supported by this configured experiment: '+
                           ', '.join(item['title'] for item in self.conditions)+'.')
        if (prior and prior['status'] in ('queued', 'running') and
                (condition_id != prior.get('condition_id') or explicit_correction)):
            # The student can correct the condition while planning. No action
            # has started, and the old worker can never publish a proposal.
            self._cancel_tasks(s, 'Sample changed during planning.', target=prior['task_id'])
            correcting = True
        self._choose(s, condition_id)
        if correcting and pending and s.get('pending') is pending:
            self._invalidate(s, 'Condition corrected.')
        if correcting or (prior and prior['status'] == 'needs_clarification' and
                          not prior.get('clarification_answered')):
            intent = text
            correction = None
            if correcting and prior:
                intent = (prior.get('clarification') or {}).get('request', prior['request'])
                correction = {'task_id': prior['task_id'], 'request': intent,
                              'text': text, 'sample': condition_id}
            return self._queue_task(s, intent, turn_id, correction=correction)
        return None

    async def converse(self, sid, text, client_request_id=None):
        text = _text(text)
        if client_request_id is not None and (not isinstance(client_request_id, str) or not client_request_id.strip() or len(client_request_id) > 128):
            raise LabError('Invalid client_request_id.')
        # A duplicate must be detected before STOP, correction, reflection, or confirmation.
        normalized = words(text)
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
            if stop_input(text):
                stop = True
            else:
                stop = False
                c = condition_input(text)
                try:
                    if normalized in ('cancel', 'cancel it', 'cancel the request', 'cancel the proposal',
                                      'never mind', 'nevermind'):
                        self._invalidate(s, 'Student cancelled.')
                        if self._cancel_session_tasks(s, 'Student cancelled.'):
                            await self._stop_backend(sid)
                        s['generation'] += 1
                        self._message(s, 'assistant', 'Task cancelled.')
                    elif _affirmative(text):
                        self._message(s, 'assistant', 'Use the Confirm button on the exact proposal, or confirm aloud after hearing it.')
                    elif re.search(r'\b(confirm|approve|go ahead|run it)\b', normalized):
                        self._message(s, 'assistant', 'Send a separate completed “confirm” after reviewing the current proposal.')
                    elif c:
                        task = self._conversational_choice(s, c, text, turn['turn_id'])
                        if task and client_request_id:
                            s['dedupe'][client_request_id]['task_id'] = task['task_id']
                    elif reset_input(text):
                        self._prepare(s)
                    elif normalized.startswith('reflection '):
                        self._reflect(s, text.partition(' ')[2])
                    elif prediction_input(text):
                        self._predict(s, text)
                    elif read_only_turn(text):
                        self._message(s, 'assistant', conversation_reply(text, s))
                    else:
                        if s.get('requires_prepare'):
                            raise LabError('Prepare a fresh simulation after the server restart.')
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

    @staticmethod
    def _completed_student_turn(s, turn_id):
        return next((m for m in reversed(s['messages']) if m['turn_id'] == turn_id
                     and m['role'] == 'user' and m.get('final')), None)

    async def _start_voice_task(self, sid, text, args):
        async with self._lock(sid):
            s = self.get(sid)
            if args['_voice_generation'] != s['generation']:
                raise LabError('Stale voice generation; start a fresh turn.')
            turn_id = args.get('_voice_turn_id')
            message = self._completed_student_turn(s, turn_id)
            if not message or message['text'] != _text(text):
                raise LabError('Voice task requires a completed user turn ID with matching text.')
            if read_only_turn(text):
                raise LabError('Answer this conversational turn without starting a task.')
            key = 'voice:' + turn_id
            if key in s['dedupe']:
                previous = s['dedupe'][key]
                task = next((t for t in s['tasks'] if t['task_id'] == previous['task_id']), None)
                if task is None:
                    raise LabError('This student turn already recorded a sample choice.')
            else:
                if s.get('requires_prepare'):
                    raise LabError('Prepare a fresh simulation after the server restart.')
                choice = condition_input(text)
                prior = s['tasks'][-1] if s['tasks'] else None
                if choice and (s.get('pending') or (prior and prior['status'] in ('queued', 'running', 'needs_clarification'))):
                    task = self._conversational_choice(s, choice, text, turn_id)
                else:
                    task = self._queue_task(s, text, turn_id)
                receipt = {'text': text, 'task_id': task['task_id'] if task else None}
                s['dedupe'][key] = receipt
                if args.get('_tool_call_id'):
                    s['dedupe']['live:' + args['_tool_call_id']] = receipt
                await self.publish(s)
                if task is None:
                    return {'task_id': None, 'status': 'selected'}
            return {'task_id': task['task_id'], 'status': task['status']}

    async def tool(self, sid, name, args):
        if not isinstance(args, dict):
            raise LabError('Tool arguments must be an object.')
        schemas = {'get_lab_state': set(), 'choose_condition': {'condition_id'},
                   'record_prediction': {'text'}, 'request_action': {'text'}, 'start_task': {'text'},
                   'improve_skill': {'limitation'},
                   'student_confirm': {'request_id', 'proposal_version'}, 'cancel_request': {'request_id'},
                   'prepare_next_trial': set(), 'record_reflection': {'text'}, 'stop_lab': set(),
                   '_record_transcript': {'role', 'text', 'turn_id', 'final'},
                   '_record_usage': {'model', 'model_calls', 'tokens', 'usage', 'turn_id'},
                   '_voice_control_rejected': {'reason', 'turn_id'},
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
        required = schemas[name] if name in ('choose_condition', 'record_prediction', 'request_action', 'start_task', 'improve_skill', 'student_confirm', 'record_reflection', '_record_transcript') else set()
        if required - set(clean):
            raise LabError('Required pH tool argument missing.')
        if name == 'get_lab_state':
            return self.snapshot(sid)
        if name == '_voice_control_rejected':
            s['voice_control'] = {**clean, 'accepted': False}
            self._event(s, 'voice_control_rejected', **clean)
            return await self.publish(s)
        if name == 'improve_skill':
            target = next((task for task in reversed(s['tasks']) if task['status'] in TASK_TERMINAL and
                           any(o['status'] == 'unknown' or (o['checks'] and not all(o['checks'].values()))
                               for o in task['observations'])), None)
            if target is None:
                raise LabError('No recorded skill limitation is available for improvement.')
            return await self.start_improvement(sid, target['task_id'], clean['limitation'],
                                                voice_generation=args.get('_voice_generation'))
        if name == 'choose_condition':
            return await self.choose_condition(sid, clean['condition_id'], turn_id=args.get('_voice_turn_id'),
                                               voice_generation=args.get('_voice_generation'))
        if name == 'record_prediction':
            return await self.prediction(sid, clean['text'], voice_generation=args.get('_voice_generation'))
        if name == 'start_task' or (name == 'request_action' and '_voice_generation' in args):
            if '_voice_generation' in args:
                return await self._start_voice_task(sid, clean['text'], args)
            return await self.start_task(sid, clean['text'], record_turn=False,
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
            return await self.prepare(sid, voice_generation=args.get('_voice_generation'))
        if name == 'record_reflection':
            return await self.reflection(sid, **clean, voice_generation=args.get('_voice_generation'))
        if name == 'stop_lab':
            return await self.stop(sid)
        async with self._lock(sid):
            s = self.get(sid)
            self._voice_generation(s, args.get('_voice_generation'))
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
                if role == 'user' and final and '_voice_generation' in args:
                    # Commit a completed choice/action with its transcript. A
                    # later confirmation must never see the superseded plan,
                    # even if provider tools or client transcript delivery lag.
                    choice = condition_input(text)
                    key = 'voice:' + turn_id
                    reset = reset_input(text)
                    if key not in s['dedupe'] and (choice or reset or explicit_action(text)):
                        self._editable(s)
                        if s.get('requires_prepare') and not reset:
                            raise LabError('Prepare a fresh simulation after the server restart.')
                        if reset:
                            self._prepare(s)
                            task = None
                        else:
                            task = (self._conversational_choice(s, choice, text, turn_id) if choice else
                                    self._queue_task(s, text, turn_id))
                        s['dedupe'][key] = {'text': text, 'task_id': task['task_id'] if task else None,
                                           'mutation': 'prepare_next_trial' if reset else
                                                       ('choose_condition' if choice else 'request_action')}
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
