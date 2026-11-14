"""Background task behavior for Lab. Session, consent and persistence are owned by Lab."""
from __future__ import annotations

import asyncio
import copy
import time
import uuid

from .contracts import ImageReference, PlanDraft
from .skills import PRIMITIVE_SCHEMAS, compute_skill_hash

TASK_TERMINAL = {'completed', 'failed', 'cancelled', 'needs_clarification'}
TASK_BUSY = {'queued', 'running', 'executing', 'observing'}
TOOLS = {
    'inspect_scene': ('Acquire a timestamped primary or secondary view.', {'view': {'enum': ['primary', 'secondary']}}, []),
    'localize_objects': ('Localize labels in a frame already received by this task.', {'evidence_id': {'type': 'string'}, 'labels': {'type': 'array', 'items': {'type': 'string'}}}, ['evidence_id', 'labels']),
    'list_skills': ('List active definitions.', {}, []),
    'get_skill': ('Read a registered version.', {'skill_id': {'type': 'string'}, 'version': {'type': 'string'}}, ['skill_id']),
    'validate_plan': ('Independently validate a PlanDraft.', {'plan': PlanDraft.model_json_schema()}, ['plan']),
    'propose_skill': ('Validate the skill and bindings in a PlanDraft without granting execution or activation.', {'plan': PlanDraft.model_json_schema()}, ['plan']),
    'evaluate_candidate': ('Read an existing evaluation decision for a version. The host evaluator creates receipts.', {'version': {'type': 'string'}}, ['version']),
}


class ExpertMissing(ValueError):
    code = 'unavailable'


class TaskLoop:
    def _task_event(self, s, task, kind, **data):
        plan = task.get('plan') or {}
        return self._event(s, kind, task_id=task['task_id'], request_id=task.get('request_id'),
                           trial_id=task['trial_id'], turn_id=task.get('turn_id'),
                           skill_id=plan.get('skill_id'), skill_version=plan.get('skill_version'),
                           evidence_ids=data.pop('evidence_ids', []),
                           provenance=data.pop('provenance', 'RUNTIME'), **data)

    async def _emit_task(self, s, task, kind, **data):
        self._guard_task(s, task)
        self._task_event(s, task, kind, **data)
        await self.publish(s)

    @staticmethod
    def _guard_task(s, task):
        if (task['status'] in TASK_TERMINAL or task['generation'] != s['generation'] or
                not s['connected']):
            raise asyncio.CancelledError()

    def _queue_task(self, s, text, turn_id, *, improvement=None):
        self._idle(s)
        self._invalidate(s, 'A new task replaced this proposal.')
        task_id = str(uuid.uuid4())
        task = {'task_id': task_id, 'session_id': s['session_id'], 'turn_id': turn_id,
                'trial_id': s['trial']['trial_id'], 'request': text, 'request_id': None,
                'generation': s['generation'], 'status': 'queued', 'replans': 0,
                'prediction': s['prediction'], 'condition_id': s['trial']['condition_id'],
                'route': None, 'plan': None, 'execution': [], 'observations': [],
                'feedback': [], 'expert_runs': [], 'evidence': {}, 'scene': None, 'images': [],
                'started_at': time.time(), 'consumed_sample': False,
                'improvement': copy.deepcopy(improvement)}
        s['tasks'].append(task)
        self._task_event(s, task, 'task_queued', status='queued')
        self._spawn(s, task, self._plan_task(s, task))
        return task

    def _spawn(self, s, task, coroutine):
        task_id = task['task_id']
        future = asyncio.create_task(coroutine, name='lab-task-' + task_id)
        self.workers[task_id] = future
        self.cancel_signals[task_id] = asyncio.Event()

        def finished(done):
            if self.workers.get(task_id) is done:
                self.workers.pop(task_id, None)
                self.cancel_signals.pop(task_id, None)
        future.add_done_callback(finished)

    def _cancel_tasks(self, s, reason, *, target=None):
        for task in s.get('tasks', []):
            if task['status'] in TASK_TERMINAL or (target and target not in (task['task_id'], task['request_id'])):
                continue
            task.update(status='cancelled', reason=reason)
            self._task_event(s, task, 'task_cancelled', status='cancelled', reason=reason)
            key = task['task_id']
            if key in self.workers:
                self.cancel_signals[key].set()
                self.workers[key].cancel()

    async def _set_status(self, s, task, status, summary=None, **data):
        self._guard_task(s, task)
        task.update(status=status, summary=summary)
        self._task_event(s, task, 'task_status', status=status, summary=summary, **data)
        if summary and status in TASK_TERMINAL:
            self._message(s, 'assistant', summary)
        await self.publish(s)

    async def _capture(self, s, task, operation, arguments, receipt=None):
        self._guard_task(s, task)
        if self.perception is None:
            raise ValueError('Independent scene and observation service is unavailable.')
        sid = s['session_id']
        if operation == 'inspect_scene':
            pending = self.perception.inspect_scene(sid, arguments['view'])
        elif operation == 'localize_objects':
            if arguments['evidence_id'] not in task['evidence']:
                raise ValueError('Localization requires evidence already received by this task.')
            pending = self.perception.localize_objects(sid, **arguments)
        else:
            pending = self.perception.observe(sid, copy.deepcopy({**receipt, 'view': arguments['view']}))
        result = await asyncio.wait_for(pending, self.execution_timeout)
        self._guard_task(s, task)
        if not isinstance(result, dict):
            raise ValueError('Perception receipt must be an object.')
        compute_skill_hash(result)
        images = [ImageReference.model_validate(i).model_dump(mode='json') for i in result.get('images', [])]
        if len(images) > 4:
            raise ValueError('Perception response exceeds the image budget.')
        result = {**result, 'images': images}
        ids = [i['evidence_id'] for i in images]
        if isinstance(result.get('evidence_id'), str):
            ids.append(result['evidence_id'])
        for evidence_id in ids:
            prior = task['evidence'].get(evidence_id, {})
            if operation == 'localize_objects':
                merged = {**prior, **result, 'images': images or prior.get('images', [])}
            else:
                previous_images = {image['evidence_id']: image['sha256'] for image in prior.get('images', [])}
                if any(image['evidence_id'] in previous_images and
                       previous_images[image['evidence_id']] != image['sha256'] for image in images):
                    raise ValueError('A perception evidence ID referred to different image bytes.')
                merged = result
            task['evidence'][evidence_id] = copy.deepcopy(merged)
        if images or operation != 'localize_objects':
            task['images'] = images
        if operation != 'localize_objects':
            task['scene'] = copy.deepcopy(result.get('scene', {k: v for k, v in result.items() if k != 'images'}))
            s['scene'] = copy.deepcopy(task['scene'])
            s['scene_images'] = copy.deepcopy(images)
        await self._emit_task(s, task, 'perception_result', operation=operation, receipt=result,
                              evidence_ids=list(dict.fromkeys(ids)), provenance=result.get('provenance', 'UNKNOWN'))
        return result

    async def _run_expert(self, s, task, phase):
        if self.expert is None:
            raise ExpertMissing('Background expert unavailable. An OpenAI Codex adapter is required.')
        tool_calls = 0
        started = time.perf_counter()

        async def tool_handler(name, arguments):
            nonlocal tool_calls
            self._guard_task(s, task)
            tool_calls += 1
            if tool_calls > 12:
                raise ValueError('Expert tool budget exceeded.')
            if name not in TOOLS or not isinstance(arguments, dict):
                raise ValueError('Undeclared expert tool.')
            _, properties, required = TOOLS[name]
            if set(arguments) - set(properties) or set(required) - set(arguments):
                raise ValueError('Invalid expert tool arguments.')
            if name in ('inspect_scene', 'localize_objects'):
                args = PRIMITIVE_SCHEMAS[name].model_validate(arguments).model_dump(mode='json')
                return await self._capture(s, task, name, args)
            if name == 'list_skills':
                return {'skills': self.registry.list()}
            if name == 'get_skill':
                return self.registry.get(arguments['skill_id'], arguments.get('version'))
            if name == 'evaluate_candidate':
                return {'decisions': self.registry.evaluation_decisions(arguments['version'])}
            try:
                draft = PlanDraft.model_validate(arguments['plan'])
                if name == 'propose_skill' and not draft.skill_definition:
                    raise ValueError('propose_skill requires a skill_definition.')
                plan = self.registry.compile(draft, task_id=task['task_id'])
                self._check_context(task, plan)
            except (ValueError, KeyError) as exc:
                return {'valid': False, 'error': str(exc)}
            return {'valid': True, 'plan': plan}

        async def emit(event):
            # Adapter events are nested so untrusted fields cannot replace host correlation.
            kind = event.get('type') or event.get('kind') or event.get('event')
            if kind in {'expert_started', 'expert_call_started', 'expert_call_completed',
                        'expert_tool_started', 'expert_tool_completed', 'expert_finished'}:
                await self._emit_task(s, task, kind, adapter=event, provenance='EXPERT_ADAPTER')

        context = {
            'task_id': task['task_id'], 'session_id': s['session_id'], 'request': task['request'],
            'conversation': [{k: m[k] for k in ('role', 'text')} for m in s['messages'][-20:] if m.get('final')],
            'phase': phase, 'scene': task['scene'], 'images': task['images'],
            'tools': [{'name': name, 'description': summary,
                       'input_schema': {'type': 'object', 'properties': properties,
                                        'required': required, 'additionalProperties': False}}
                      for name, (summary, properties, required) in TOOLS.items()],
            'skills': self.registry.list(), 'feedback': task['feedback'],
            'capability_limits': {**s['capabilities'], 'primitives': list(PRIMITIVE_SCHEMAS),
                                  'replans_remaining': 2 - task['replans']},
            'instructions': ('Use raw scene evidence and tools. Return PlanDraft fields as payload for plan/revision, '
                             'or clarification/reject. Use only listed primitives. Never claim expected state as observed. '
                             'At execution checkpoints return complete with payload {"continue": true} to continue '
                             'the exact existing steps, or revision for a fresh proposal and consent. '
                             'Do not repeat a mock sample operation after it has run.'),
            'task_context': {'started_at': task['started_at'], 'expert_timeout_s': self.expert_timeout,
                             'prediction': task['prediction'], 'condition_id': task['condition_id'],
                             'approved_plan': task['plan'], 'improvement': task['improvement']},
        }
        result = await asyncio.wait_for(self.expert.run(copy.deepcopy(context), tool_handler=tool_handler,
                                                        emit=emit, cancel_event=self.cancel_signals[task['task_id']]),
                                        timeout=self.expert_timeout)
        self._guard_task(s, task)
        metadata = {key: copy.deepcopy(result.get(key)) for key in
                    ('kind', 'summary', 'provider', 'model', 'reasoning_effort', 'calls',
                     'usage', 'elapsed_ms', 'tool_receipts')}
        metadata['host_elapsed_ms'] = (time.perf_counter() - started) * 1000
        compute_skill_hash(metadata)
        task['expert_runs'].append(metadata)
        await self._emit_task(s, task, 'expert_result', phase=phase, run=metadata, provenance='EXPERT_ADAPTER')
        if not isinstance(result.get('payload'), dict) or not isinstance(result.get('summary'), str):
            raise ValueError('Expert result lacks a structured payload and summary.')
        return result

    @staticmethod
    def _fresh(scene):
        expiry = scene.get('expires_at')
        return scene.get('fresh') is True and (expiry is None or
               (type(expiry) in (int, float) and expiry > time.time()))

    @staticmethod
    def _check_context(task, plan):
        scene = task['scene'] or {}
        known_labels = set()
        for receipt in task['evidence'].values():
            if not set(i['evidence_id'] for i in task['images']).intersection(
                    [receipt.get('evidence_id'), *(i['evidence_id'] for i in receipt.get('images', []))]):
                continue
            known_labels.update(label for label in receipt.get('verified_labels', []) if isinstance(label, str))
        for rule in plan['preconditions']:
            if rule['fresh_scene'] and not TaskLoop._fresh(scene):
                raise ValueError('A fresh scene is required.')
            if not set(rule['labels']).issubset(known_labels):
                raise ValueError('Required scene labels have not been verified.')
        if set(plan['evidence_ids']) - set(task['evidence']):
            raise ValueError('Plan references evidence unavailable to this task.')
        sample = next((step for step in plan['steps'] if step['operation'] == 'mock_prepared_sample'), None)
        if sample:
            if task['condition_id'] and sample['arguments']['condition_id'] != task['condition_id']:
                raise ValueError('The proposed mock sample differs from the selected condition.')
            if task['consumed_sample']:
                raise ValueError('This task already ran its single prepared-sample operation.')
            if not task['images'] or not TaskLoop._fresh(scene):
                raise ValueError('Mock sample execution requires fresh timestamped scene images.')
        if any(step['operation'] == 'localize_objects' and step['arguments']['evidence_id'] not in task['evidence']
               for step in plan['steps']):
            raise ValueError('Localization steps require evidence available to this task.')

    async def _plan_task(self, s, task):
        began = time.perf_counter()
        try:
            await self._set_status(s, task, 'running')
            if self.perception:
                try:
                    await self._capture(s, task, 'inspect_scene', {'view': 'primary'})
                except (ValueError, RuntimeError, OSError, TimeoutError) as exc:
                    await self._emit_task(s, task, 'scene_unavailable', code=type(exc).__name__)
            route = None if task['improvement'] else self.registry.match(task['request'])
            if route:
                try:
                    plan = self.registry.compile(route, task_id=task['task_id'])
                    self._check_context(task, plan)
                except (ValueError, KeyError):
                    route = None
                else:
                    task['route'] = 'active_skill'
                    await self._propose_task(s, task, route, plan, began)
                    return
            task['route'] = 'expert'
            response = await self._run_expert(s, task, 'improvement' if task['improvement'] else 'planning')
            if response['kind'] in ('plan', 'revision'):
                draft = PlanDraft.model_validate(response['payload'])
                await self._propose_task(s, task, draft, self.registry.compile(draft, task_id=task['task_id']), began)
            elif response['kind'] in ('clarification', 'reject', 'complete'):
                status = {'clarification': 'needs_clarification', 'reject': 'failed', 'complete': 'completed'}[response['kind']]
                await self._set_status(s, task, status, response['summary'])
            else:
                raise ValueError('Expert returned an invalid planning decision.')
        except asyncio.CancelledError:
            if task['status'] not in TASK_TERMINAL and task['generation'] == s['generation']:
                await self._fail_task(s, task, RuntimeError('Adapter cancelled unexpectedly.'))
        except Exception as exc:
            await self._fail_task(s, task, exc)

    async def _fail_task(self, s, task, exc):
        code = getattr(exc, 'code', None)
        if code is None:
            code = 'timeout' if isinstance(exc, TimeoutError) else 'invalid_task' if isinstance(exc, (KeyError, ValueError)) else 'failed'
        summary = str(exc) if isinstance(exc, ValueError) and not hasattr(exc, 'errors') else f'Background task failed ({code}).'
        if task['status'] not in TASK_TERMINAL and task['generation'] == s['generation']:
            if task.get('request_id') and task['status'] in ('executing', 'observing'):
                request = next(r for r in s['requests'] if r['request_id'] == task['request_id'])
                request.update(status='failed', reason=summary)
                task['execution'].append({'request_id': task['request_id'], 'backend': 'mock',
                                          'status': 'failed', 'reason': summary})
                s['trial']['state'] = 'stopped'
            await self._set_status(s, task, 'failed', summary, code=code)

    async def _propose_task(self, s, task, draft, plan, began):
        self._guard_task(s, task)
        self._check_context(task, plan)
        if draft.skill_definition:
            version = self.registry.validate_for_task(task['task_id'], draft.skill_definition)
            self.registry.authorize(task['task_id'], plan['skill_id'], version)
        s['proposal_sequence'] += 1
        steps = ' → '.join(f"{step['operation']}({', '.join(f'{k}={v}' for k, v in step['arguments'].items())})"
                           for step in plan['steps'])
        summary = 'Mock or observation-only plan: ' + steps
        request_id = str(uuid.uuid4())
        bound_plan = {**plan, 'scene_hash': self._scene_hash(s), 'generation': s['generation'],
                      'trial_id': task['trial_id'], 'task_id': task['task_id']}
        request = {'request_id': request_id, 'task_id': task['task_id'], 'session_id': s['session_id'],
                   'trial_id': task['trial_id'], 'turn_id': task['turn_id'], 'generation': s['generation'],
                   'proposal_version': s['proposal_sequence'], 'plan_hash': compute_skill_hash(bound_plan),
                   'plan': bound_plan, 'skill_id': plan['skill_id'], 'skill_version': plan['skill_version'],
                   'condition_id': task['condition_id'], 'prediction': task['prediction'], 'summary': summary,
                   'status': 'requested', 'presented': False, 'presentation': None,
                   'student_confirmed': False, 'expires_at': time.time() + self.confirmation_ttl,
                   'metrics': {'dispatch': task['route'], 'planning_ms': (time.perf_counter() - began) * 1000,
                               'model_calls': sum(run['calls'] or 0 for run in task['expert_runs']),
                               'tokens': sum((run['usage'] or {}).get('total_tokens',
                                             sum((run['usage'] or {}).get(k, 0) for k in ('input_tokens', 'output_tokens')))
                                             for run in task['expert_runs'])},
                   'result': None}
        task.update(plan=copy.deepcopy(bound_plan), request_id=request_id, status='awaiting_confirmation')
        s['requests'].append(request)
        s['pending'] = request
        s['trial']['state'] = 'awaiting_confirmation'
        await self._emit_task(s, task, 'request_proposed', request=request, evidence_ids=plan['evidence_ids'])

    @staticmethod
    def _scene_hash(s):
        return compute_skill_hash({'scene': s.get('scene'), 'images': s.get('scene_images', [])})

    def _task_for_request(self, s, r):
        return next(t for t in s['tasks'] if t['task_id'] == r['task_id'])

    async def _execute_task(self, s, task, request):
        plan = request['plan']
        receipt = {'request_id': request['request_id'], 'task_id': task['task_id'],
                   'trial_id': task['trial_id'], 'skill_id': plan['skill_id'], 'skill_version': plan['skill_version'],
                   'plan_hash': request['plan_hash'], 'backend': 'mock', 'status': 'no_operation',
                   'prior_execution': [r for r in task['execution'] if r['status'] == 'completed']}
        try:
            self._guard_task(s, task)
            request['status'] = 'executing'
            await self._set_status(s, task, 'executing')
            for index, step in enumerate(plan['steps']):
                self._guard_task(s, task)
                operation, arguments = step['operation'], step['arguments']
                progress_data = {'step': index, 'operation': operation, 'request_id': request['request_id']}
                task['feedback'].append({'type': 'execution_progress', **progress_data})
                await self._emit_task(s, task, 'execution_progress', step=index, operation=operation)
                if operation == 'mock_prepared_sample':
                    self._check_context(task, plan)
                    task['consumed_sample'] = True

                    async def progress(phase):
                        await self._emit_task(s, task, 'execution_progress', step=index,
                                              operation=operation, phase=phase, provenance='MOCK')

                    result = await asyncio.wait_for(self._backend(s['session_id']).execute_step(
                        request['request_id'], arguments, progress), self.execution_timeout)
                    receipt.update(result)
                    task['execution'].append(copy.deepcopy(receipt))
                    task['feedback'].append({'type': 'execution', 'receipt': copy.deepcopy(receipt)})
                    await self._emit_task(s, task, 'execution_result', receipt=receipt, provenance='MOCK')
                    continue

                await self._set_status(s, task, 'observing')
                observation = await self._observe_step(s, task, request, operation, arguments, receipt, index)
                is_final = index == len(plan['steps']) - 1
                if operation in ('inspect_scene', 'observe') or observation.get('images'):
                    decision = await self._run_expert(s, task, 'execution_feedback')
                    kind, payload = decision['kind'], decision['payload']
                    if kind in ('revision', 'plan'):
                        if task['replans'] >= 2:
                            raise ValueError('Replan limit reached; the changed plan was not approved.')
                        task['replans'] += 1
                        proposed_at = time.perf_counter()
                        draft = PlanDraft.model_validate(payload)
                        revised = self.registry.compile(draft, task_id=task['task_id'])
                        self._check_context(task, revised)
                        request.update(status='completed', result={**receipt, 'status': 'superseded'})
                        await self._propose_task(s, task, draft, revised, proposed_at)
                        return
                    if kind in ('clarification', 'reject'):
                        status = 'needs_clarification' if kind == 'clarification' else 'failed'
                        request.update(status='cancelled' if kind == 'clarification' else 'failed', result=receipt)
                        s['trial']['state'] = 'stopped'
                        await self._set_status(s, task, status, decision['summary'])
                        return
                    if kind != 'complete' or (not is_final and payload.get('continue') is not True):
                        raise ValueError('Expert did not authorize continuing the exact approved plan.')
                if not is_final:
                    await self._set_status(s, task, 'executing')

            request.update(status='completed', result=copy.deepcopy(receipt))
            s['trial']['state'] = 'reflecting' if task['observations'] else 'predicting'
            latest = task['observations'][-1] if task['observations'] else None
            summary = latest['text'] if latest else 'The approved scene inspection is complete.'
            await self._set_status(s, task, 'completed', summary)
        except asyncio.CancelledError:
            if task['status'] not in TASK_TERMINAL and task['generation'] == s['generation']:
                await self._fail_task(s, task, RuntimeError('Adapter cancelled unexpectedly.'))
        except Exception as exc:
            await self._fail_task(s, task, exc)

    async def _observe_step(self, s, task, request, operation, arguments, receipt, index):
        try:
            observed = await self._capture(s, task, operation, arguments, receipt)
        except (ValueError, OSError, RuntimeError, TimeoutError) as exc:
            if operation != 'observe':
                raise
            observed = {'status': 'unknown', 'provenance': 'UNKNOWN', 'images': [],
                        'reason': f'Independent observation unavailable ({type(exc).__name__}).'}
        if operation == 'observe':
            plan = request['plan']
            features = observed.get('features') or {}
            checks = {rule['feature']: type(features.get(rule['feature'])) is type(rule['expected']) and
                      features.get(rule['feature']) == rule['expected'] for rule in plan['outcome_checks']}
            evidence_ids = [i['evidence_id'] for i in observed['images']]
            known = (observed.get('status') == 'observed' and bool(evidence_ids) and
                     observed.get('provenance') not in (None, 'UNKNOWN', 'MODEL-PREDICTED', 'MOCK') and
                     bool(observed.get('observer_version')) and
                     self._fresh(observed.get('scene') or observed))
            observation = {
                'observation_id': str(uuid.uuid4()), 'task_id': task['task_id'],
                'request_id': request['request_id'], 'trial_id': task['trial_id'],
                'status': 'observed' if known else 'unknown',
                'provenance': observed['provenance'] if known else 'UNKNOWN',
                'text': (observed.get('text') or 'Independent observation recorded.') if known
                        else 'Trial outcome UNKNOWN. The independent observer did not establish a readable result.',
                'plan_hash': request['plan_hash'], 'skill_version': plan['skill_version'],
                'source': observed.get('observer_version') or 'independent observation unavailable',
                'evidence': evidence_ids, 'features': features if known else {},
                'value': features if known else None, 'checks': checks if known else {},
                'reason': observed.get('reason'), 'receipt': observed,
            }
            s['observations'].append(observation)
            task['observations'].append(observation)
            task['feedback'].append({'type': 'observation', 'receipt': copy.deepcopy(observation)})
            await self._emit_task(s, task, 'observation', observation=observation,
                                  evidence_ids=evidence_ids, provenance=observation['provenance'])
        else:
            task['feedback'].append({'type': 'perception', 'step': index,
                                     'operation': operation, 'receipt': copy.deepcopy(observed)})
            await self._emit_task(s, task, 'execution_checkpoint', step=index, operation=operation)
        return observed
