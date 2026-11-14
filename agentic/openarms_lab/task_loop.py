"""Background task behavior for Lab. Session, consent and persistence are owned by Lab."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import math
import re
import time
import uuid
from pathlib import Path

from .contracts import MOCK_OPERATIONS, ImageReference, PlanDraft, SkillDefinition
from .skills import PRIMITIVE_SCHEMAS, compute_skill_hash

TASK_TERMINAL = {'completed', 'failed', 'cancelled', 'needs_clarification'}
TASK_BUSY = {'queued', 'running', 'executing', 'observing'}
FRAME_MAX_AGE = 180
CAMERA_FIELDS = ('camera_id', 'camera_config_id', 'calibration_id', 'coordinate_frame', 'units', 'clock')
VESSEL_LABELS = ('source', 'receiver')
TOOLS = {
    'inspect_scene': ('Acquire a timestamped primary or secondary view.', {'view': {'enum': ['primary', 'secondary']}}, []),
    'localize_objects': ('Localize exact label IDs from scene.recognition_labels in a frame already received by this task. Do not pass object descriptions.', {'evidence_id': {'type': 'string'}, 'labels': {'type': 'array', 'items': {'type': 'string'}}}, ['evidence_id', 'labels']),
    'list_skills': ('List active definitions.', {}, []),
    'get_skill': ('Read a registered version.', {'skill_id': {'type': 'string'}, 'version': {'type': 'string'}}, ['skill_id']),
    'validate_plan': ('Independently validate a PlanDraft.', {'plan': PlanDraft.model_json_schema()}, ['plan']),
    'propose_skill': ('Validate the skill and bindings in a PlanDraft without granting execution or activation.', {'plan': PlanDraft.model_json_schema()}, ['plan']),
    'evaluate_candidate': ('Read an existing evaluation decision for a version. The host evaluator creates receipts.', {'version': {'type': 'string'}}, ['version']),
}


class ExpertMissing(ValueError):
    code = 'unavailable'


def describe_step(step):
    args, operation = step['arguments'], step['operation']
    if operation == 'inspect_scene':
        return 'inspect the '+args['view']+' camera view'
    if operation == 'localize_objects':
        return 'locate '+', '.join(args['labels'])+' in the image'
    if operation == 'mock_prepared_sample':
        return 'test the prepared '+args['condition_id'].replace('_', ' ')+' sample from station A with the indicator at station C'
    if operation == 'mock_pick_up':
        return 'pick up the sample cup at station '+args['station']
    if operation == 'mock_put_down':
        return 'put the sample cup down at station '+args['station']
    if operation == 'mock_pour':
        return 'pour one prepared portion into the receiver at station C'
    if operation == 'observe':
        text = 'check the result using the '+args['view']+' camera'
        if args.get('fallback_view'):
            text += ', trying the '+args['fallback_view']+' camera if the first view is unreadable'
        return text
    raise ValueError('Unsupported proposal operation.')


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
        previous = s['tasks'][-1] if s.get('tasks') else None
        clarification = None
        if (not improvement and previous and previous['status'] == 'needs_clarification' and
                previous['trial_id'] == s['trial']['trial_id'] and previous['generation'] == s['generation'] and
                not previous.get('clarification_answered')):
            clarification = {'task_id': previous['task_id'], 'request': previous['request'],
                             'question': previous.get('summary'), 'answer': text}
            previous['clarification_answered'] = True
        self._invalidate(s, 'A new task replaced this proposal.')
        task_id = str(uuid.uuid4())
        task = {'task_id': task_id, 'session_id': s['session_id'], 'turn_id': turn_id,
                'trial_id': s['trial']['trial_id'], 'request': text, 'request_id': None,
                'generation': s['generation'], 'status': 'queued', 'replans': 0,
                'prediction': s['prediction'], 'condition_id': s['trial']['condition_id'],
                'route': None, 'plan': None, 'execution': [], 'observations': [],
                'feedback': [], 'expert_runs': [], 'evidence': {}, 'scene': None, 'images': [],
                'started_at': time.time(), 'dispatched_action': False,
                'improvement': copy.deepcopy(improvement), 'clarification': clarification}
        if hasattr(self.expert, 'snapshot'):
            try:
                task['expert_configuration'] = self.expert.snapshot()
            except RuntimeError as exc:
                task['expert_configuration'] = {'error_code': getattr(exc, 'code', 'configuration')}
        if clarification:
            task['feedback'].append({'type': 'student_clarification', **copy.deepcopy(clarification)})
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
            if (task['status'] in TASK_TERMINAL - {'needs_clarification'} or
                    (target and target not in (task['task_id'], task['request_id']))):
                continue
            task.update(status='cancelled', reason=reason)
            self._task_event(s, task, 'task_cancelled', status='cancelled', reason=reason)
            key = task['task_id']
            if hasattr(self.expert, 'release'):
                self.expert.release(key)
            if key in self.workers:
                self.cancel_signals[key].set()
                self.workers[key].cancel()

    async def _set_status(self, s, task, status, summary=None, **data):
        self._guard_task(s, task)
        task.update(status=status, summary=summary)
        if status in TASK_TERMINAL and hasattr(self.expert, 'release'):
            self.expert.release(task['task_id'])
        self._task_event(s, task, 'task_status', status=status, summary=summary, **data)
        if summary and status in TASK_TERMINAL:
            self._message(s, 'assistant', summary)
        await self.publish(s)

    @staticmethod
    def _same_timestamp(value, expected):
        return type(value) is type(expected) and value == expected

    def _check_image(self, sid, image, *, view=None):
        evidence_id = image['evidence_id']
        path = Path(image['path'])
        root = getattr(self.perception, 'artifact_dir', None)
        if root is not None:
            # Both live producers index their own session frames before returning them.
            owned = getattr(self.perception, 'frames', {}).get((sid, evidence_id))
            if isinstance(owned, tuple):  # MuJoCo also retains its view.
                owned, owned_view = owned
                if view is not None and view != owned_view:
                    raise ValueError('Image does not come from the requested camera.')
            if (owned != image or path.name != evidence_id+'.png' or
                    path.resolve().parent != (Path(root).resolve() / sid)):
                raise ValueError('Image does not match a frame owned by this session.')
        if hashlib.sha256(path.read_bytes()).hexdigest() != image['sha256']:
            raise ValueError('Evidence bytes changed after capture.')

    def _capture_updates(self, s, task, operation, arguments, result, *, started_at, outcome_after):
        """Validate the complete receipt before publishing or updating any evidence."""
        images = result['images']
        by_id = {image['evidence_id']: image for image in images}
        if len(by_id) != len(images):
            raise ValueError('Duplicate image IDs in a perception receipt.')
        evidence_id = result.get('evidence_id')
        if not isinstance(evidence_id, str) or not evidence_id:
            raise ValueError('Perception receipt must identify its frame.')
        prior = task['evidence'].get(evidence_id, {})
        scene = result.get('scene')
        provenance = result.get('provenance')
        if operation == 'localize_objects':
            prior_images = prior.get('images', [])
            if (evidence_id != arguments['evidence_id'] or not prior_images or
                    (images and (list(by_id) != [evidence_id] or images != prior_images)) or
                    ('scene' in result and scene != prior.get('scene')) or
                    ('frame_id' in result and result['frame_id'] != evidence_id) or
                    ('captured_at' in result and not self._same_timestamp(
                        result['captured_at'], prior_images[0]['captured_at'])) or
                    ('clock' in result and result['clock'] != (prior.get('scene') or {}).get('clock')) or
                    ('provenance' in result and provenance != prior_images[0]['provenance'])):
                raise ValueError('Localization did not refer to the original task frame.')
            image = prior_images[0]
            self._check_image(s['session_id'], image)
            labels = result.get('verified_labels', [])
            if (not isinstance(labels, list) or any(not isinstance(label, str) for label in labels) or
                    not set(labels).issubset(arguments['labels'])):
                raise ValueError('Localization verified labels outside the request.')
            detections = result.get('detections')
            if detections is not None:
                if (not isinstance(detections, list) or any(
                        not isinstance(d, dict) or d.get('object_id') not in arguments['labels'] or
                        d.get('frame_id') != evidence_id or
                        not self._same_timestamp(d.get('timestamp_s'), image['captured_at']) or
                        d.get('provenance') != image['provenance'] or
                        any(field in (prior.get('scene') or {}) and
                            d.get(field) != prior['scene'][field] for field in CAMERA_FIELDS)
                        for d in detections) or
                        set(labels) != {d['object_id'] for d in detections if d.get('status') == 'ok'}):
                    raise ValueError('Localization detections do not match the requested frame and labels.')
            elif getattr(self.perception, 'artifact_dir', None) is not None:
                raise ValueError('Localization did not return frame-bound detections.')
            # Localization may enrich an immutable frame, but cannot replace its
            # scene, observer receipt, image metadata, or a sibling fallback frame.
            by_label = {label: ds for label, ds in prior.get('detections_by_label', {}).items()
                        if label not in arguments['labels']}
            for detection in detections or []:
                by_label.setdefault(detection['object_id'], []).append(detection)
            merged = {**prior, 'localization': result, 'detections_by_label': by_label,
                      'verified_labels': sorted((set(prior.get('verified_labels', [])) -
                                                 set(arguments['labels'])) | set(labels))}
            return {evidence_id: merged}

        if (not isinstance(scene, dict) or scene.get('frame_id') != evidence_id or evidence_id not in by_id or
                ('frame_id' in result and result['frame_id'] != evidence_id) or
                ('provenance' in scene and scene['provenance'] != provenance) or
                any(image['provenance'] != provenance for image in images)):
            raise ValueError('Scene and image identities do not match.')
        attempts = result.get('attempts')
        if ((len(images) > 1 or attempts is not None) and
                (operation != 'observe' or len(images) != 2 or
                 arguments.get('fallback_view') in (None, arguments['view']) or
                 attempts != list(by_id) or attempts[-1] != evidence_id)):
            raise ValueError('Observation attempts do not match the returned images.')
        view = arguments.get('fallback_view') if len(images) > 1 else arguments.get('view')
        if scene.get('view') != view:
            raise ValueError('Scene view does not match the requested camera.')
        if (('captured_at' in result and not self._same_timestamp(
                result['captured_at'], by_id[evidence_id]['captured_at'])) or
                ('clock' in result and result['clock'] != scene.get('clock'))):
            raise ValueError('Perception receipt and scene clocks or timestamps do not match.')
        if 'captured_at' in scene and not self._same_timestamp(scene['captured_at'], by_id[evidence_id]['captured_at']):
            raise ValueError('Scene and image timestamps do not match.')
        if operation == 'observe' and (
                result.get('status') not in ('observed', 'unknown') or
                ('features' in result and not isinstance(result['features'], dict)) or
                (result['status'] == 'observed' and
                 (not isinstance(result.get('observer_version'), str) or not result['observer_version']))):
            raise ValueError('Invalid independent observer receipt.')
        updates = {}
        now = time.time()
        live = scene.get('clock') == 'unix_seconds'
        if getattr(self.perception, 'artifact_dir', None) is not None and not live:
            raise ValueError('Live perception requires a Unix producer clock.')
        earliest = max(started_at, now - FRAME_MAX_AGE)
        previous_time = earliest
        for fid, image in by_id.items():
            self._check_image(s['session_id'], image, view=view if fid == evidence_id else arguments['view'])
            if fid in task['evidence']:
                raise ValueError('Checkpoint did not return a fresh image: the evidence ID was already used.')
            if any(fid in other['evidence'] for other in s['tasks'] if other is not task):
                raise ValueError('Evidence ID belongs to another task.')
            if live:
                timestamp = image['captured_at']
                if (type(timestamp) not in (int, float) or not previous_time <= timestamp <= now or
                        (outcome_after is not None and timestamp <= outcome_after)):
                    raise ValueError('Live evidence timestamp is stale, future-dated, or predates execution.')
                previous_time = timestamp
            # Only the primary ID owns the scene and outcome; other attempts are
            # individually indexed images and can be localized by their own ID.
            record = result if fid == evidence_id else {'evidence_id': fid, 'provenance': provenance}
            updates[fid] = {**record, 'images': [image], 'verified_labels': []}
        if live and not self._fresh(scene):
            raise ValueError('The live scene is stale or lacks a valid source timestamp.')
        return updates

    async def _capture(self, s, task, operation, arguments, *, outcome_after=None):
        self._guard_task(s, task)
        if self.perception is None:
            raise ValueError('Independent scene and observation service is unavailable.')
        sid = s['session_id']
        started_at = time.time()
        if operation == 'inspect_scene':
            pending = self.perception.inspect_scene(sid, arguments['view'])
        elif operation == 'localize_objects':
            if arguments['evidence_id'] not in task['evidence']:
                raise ValueError('Localization requires evidence already received by this task.')
            pending = self.perception.localize_objects(sid, **arguments)
        else:
            # Observation must be independent of controller state or success.
            pending = self.perception.observe(sid, copy.deepcopy(arguments))
        result = await asyncio.wait_for(pending, self.execution_timeout)
        self._guard_task(s, task)
        if not isinstance(result, dict):
            raise ValueError('Perception receipt must be an object.')
        compute_skill_hash(result)
        raw_images = result.get('images', [])
        if not isinstance(raw_images, list) or len(raw_images) > 4:
            raise ValueError('Perception response exceeds the image budget.')
        images = [ImageReference.model_validate(i).model_dump(mode='json') for i in raw_images]
        result = {**result, 'images': images}
        updates = self._capture_updates(s, task, operation, arguments, result, started_at=started_at,
                                        outcome_after=outcome_after)
        task['evidence'].update(copy.deepcopy(updates))
        if operation != 'localize_objects':
            task['images'] = images
            task['scene'] = copy.deepcopy(result['scene'])
            s['scene'] = copy.deepcopy(task['scene'])
            s['scene_images'] = copy.deepcopy(images)
        await self._emit_task(s, task, 'perception_result', operation=operation, receipt=result,
                              evidence_ids=list(updates), provenance=result.get('provenance', 'UNKNOWN'))
        return result

    async def _run_expert(self, s, task, phase):
        if self.expert is None:
            raise ExpertMissing('Background expert unavailable. A configured expert adapter is required.')
        if hasattr(self.expert, 'bind'):
            selected = task.get('expert_configuration')
            if selected and selected.get('error_code'):
                from .codex_expert import ExpertUnavailable
                raise ExpertUnavailable(selected['error_code'], 'Host expert configuration is unavailable or invalid.')
            self.expert.bind(task['task_id'], selected)
        tool_calls = 0
        validated_draft = None
        started = time.perf_counter()

        async def tool_handler(name, arguments):
            nonlocal tool_calls, validated_draft
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
                try:
                    return await self._capture(s, task, name, args)
                except (ValueError, OSError, RuntimeError, TimeoutError) as exc:
                    return {'status': 'unavailable', 'error': self._perception_error(exc)}
            if name == 'list_skills':
                return {'skills': self.registry.list()}
            if name == 'get_skill':
                return self.registry.get(arguments['skill_id'], arguments.get('version'))
            if name == 'evaluate_candidate':
                return {'decisions': self.registry.evaluation_decisions(arguments['version'])}
            before = task['images']
            try:
                draft = PlanDraft.model_validate(arguments['plan'])
                if name == 'propose_skill' and not draft.skill_definition:
                    raise ValueError('propose_skill requires a skill_definition.')
                plan = await self._prepare_proposal(s, task, draft, phase)
            except (ValueError, KeyError) as exc:
                return {'valid': False, 'error': str(exc),
                        **({'images': task['images']} if task['images'] != before else {})}
            canonical = draft.model_dump(mode='json', exclude_none=True)
            if name == 'validate_plan':
                validated_draft = compute_skill_hash(canonical)
            return {'valid': True, 'validated_draft': canonical,
                    **({'images': task['images']} if task['images'] != before else {}),
                    'instruction': 'For the final plan/revision decision, return validated_draft unchanged as payload.',
                    'compiled_summary': {'skill_id': plan['skill_id'], 'skill_version': plan['skill_version'],
                                         'operations': [step['operation'] for step in plan['steps']]}}

        async def emit(event):
            # Adapter events are nested so untrusted fields cannot replace host correlation.
            kind = event.get('type') or event.get('kind') or event.get('event')
            if kind in {'expert_started', 'expert_call_started', 'expert_call_completed',
                        'expert_tool_started', 'expert_tool_completed', 'expert_finished'}:
                await self._emit_task(s, task, kind, adapter=event, provenance='EXPERT_ADAPTER')

        supported_operations = s['capabilities'].get('supported_operations', MOCK_OPERATIONS)
        primitives = {name: schema for name, schema in PRIMITIVE_SCHEMAS.items()
                      if name not in MOCK_OPERATIONS or name in supported_operations}
        context = {
            'task_id': task['task_id'], 'session_id': s['session_id'], 'request': task['request'],
            'conversation': [{k: m[k] for k in ('role', 'text')} for m in s['messages'][-20:] if m.get('final')],
            'phase': phase, 'scene': task['scene'], 'images': task['images'],
            'clarification': task.get('clarification'),
            'tools': [{'name': name, 'description': summary,
                       'input_schema': {'type': 'object', 'properties': properties,
                                        'required': required, 'additionalProperties': False}}
                      for name, (summary, properties, required) in TOOLS.items()],
            'skills': self.registry.list(), 'feedback': task['feedback'],
            'capability_limits': {**s['capabilities'], 'primitives': list(primitives),
                                  'primitive_arguments': {name: schema.model_json_schema()
                                                          for name, schema in primitives.items()},
                                  'replans_remaining': 2 - task['replans']},
            'instructions': ('Use raw scene evidence and tools. Return PlanDraft fields as payload for plan/revision, '
                             'or clarification/reject. Use only listed primitives. Never claim expected state as observed. '
                             'A prepared sample requires an explicit condition in its arguments. Use the requested sample '
                             'or the selected condition. Ask which sample when neither is specified. '
                             'Prediction is optional notebook context. '
                             'If clarification is present, interpret the answer with its original request and question; '
                             'a changed goal replaces the old goal, and all executable proposals require fresh consent. '
                             'For a repeatable supported task, author a parameterized skill_definition with useful '
                             'retrieval_examples, preconditions, independent outcome checks and explicit limitations. '
                             'Each declared parameter must be used as $parameter in step arguments and as {parameter} '
                             'in every retrieval example. Use only scene.observable_features for outcome checks. '
                             'Every action plan needs an inspect_scene step before its action and an observe step last. '
                             'Use localize_objects on the current image when object identity matters. '
                             'An observe step may specify fallback_view to try one alternate view only when the first '
                             'is unreadable. Do not add recovery without evidence of a relevant limitation. '
                             'For improvement, author a new version of the same pinned skill, preserving its intent, '
                             'parameter domain, expected state and outcome checks. '
                             'At execution checkpoints return complete with payload {"continue": true} to continue '
                             'the exact existing steps, or revision for a fresh proposal and consent. '
                             'If a mock action has been dispatched, revise only the remaining observation steps.'),
            'task_context': {'started_at': task['started_at'], 'expert_timeout_s': self.expert_timeout,
                             'prediction': task['prediction'], 'condition_id': task['condition_id'],
                             'approved_plan': task['plan'], 'improvement': task['improvement'],
                             'dispatched_action': task['dispatched_action']},
        }
        result = await asyncio.wait_for(self.expert.run(copy.deepcopy(context), tool_handler=tool_handler,
                                                        emit=emit, cancel_event=self.cancel_signals[task['task_id']]),
                                        timeout=self.expert_timeout)
        self._guard_task(s, task)
        metadata = {key: copy.deepcopy(result.get(key)) for key in
                    ('kind', 'summary', 'payload', 'provider', 'model', 'reasoning_effort', 'calls',
                     'usage', 'elapsed_ms', 'tool_receipts', 'requested_model', 'actual_model',
                     'model_verified', 'effort_source')}
        metadata['host_elapsed_ms'] = (time.perf_counter() - started) * 1000
        compute_skill_hash(metadata)
        task['expert_runs'].append(metadata)
        await self._emit_task(s, task, 'expert_result', phase=phase, run=metadata, provenance='EXPERT_ADAPTER')
        if not isinstance(result.get('payload'), dict) or not isinstance(result.get('summary'), str):
            raise ValueError('Expert result lacks a structured payload and summary.')
        return result, validated_draft == compute_skill_hash(result['payload'])

    @staticmethod
    def _fresh(scene):
        now = time.time()
        captured = scene.get('captured_at')
        expiry = scene.get('expires_at')
        return (scene.get('fresh') is True and scene.get('clock') == 'unix_seconds' and
                type(captured) in (int, float) and now - FRAME_MAX_AGE <= captured <= now and
                (expiry is None or (type(expiry) in (int, float) and now < expiry < math.inf)))

    @staticmethod
    def _perception_error(exc):
        if isinstance(exc, ValueError) and not hasattr(exc, 'errors'):
            return str(exc)
        return f'Independent image refresh failed ({type(exc).__name__}).'

    @staticmethod
    def _prepared_sample(plan):
        return next((step for step in plan['steps'] if step['operation'] == 'mock_prepared_sample'), None)

    @staticmethod
    def _known_labels(task):
        fid = (task['scene'] or {}).get('frame_id')
        if any(image['evidence_id'] == fid for image in task['images']):
            return set(task['evidence'][fid].get('verified_labels', []))
        return set()

    @staticmethod
    def _action(plan):
        return next((step for step in plan['steps'] if step['operation'] in MOCK_OPERATIONS), None)

    def _requires_fixture_perception(self, task):
        backend = self.backends.get(task['session_id'])
        return (getattr(backend, 'scene_service', None) is not None or
                getattr(self.perception, 'artifact_dir', None) is not None)

    def _fixture_state(self, task, frame_id, action):
        # The fixture checks use image coordinates. The plain mock backend
        # can still run with a minimal software test adapter.
        if not self._requires_fixture_perception(task):
            return None
        record = task['evidence'].get(frame_id) or {}
        scene = record.get('scene') or {}
        if (scene.get('fixture_registration_valid') is not True or
                scene.get('provenance') not in ('SYNTHETIC', 'SIMULATED') or
                getattr(self.perception, 'artifact_dir', None) is None or
                scene.get('physical_execution') is not False or
                scene.get('geometry_valid') is not False or scene.get('base_registration_id') is not None or
                scene.get('coordinate_frame') != 'image_pixels' or scene.get('units') != 'px' or
                any(not isinstance(scene.get(field), str) or not scene[field] for field in CAMERA_FIELDS)):
            raise ValueError('Camera and base fixture registration could not be verified.')
        detections = record.get('detections_by_label', {})
        vessels = {}
        for label in VESSEL_LABELS:
            matches = [d for d in detections.get(label, []) if d['status'] == 'ok' and
                       d.get('vessel_id') == label and d.get('fixture_registration_valid') is True and
                       d.get('geometry_valid') is False and d.get('grasp_pose') is None]
            if len(matches) != 1 or not matches[0].get('box_xyxy'):
                raise ValueError('The '+label+' vessel is missing, obscured, or ambiguous in the current frame.')
            vessels[label] = matches[0]
        source, receiver = vessels['source'], vessels['receiver']
        if receiver['dock_id'] != 'C' or receiver['held'] is not False:
            raise ValueError('The receiver vessel is out of dock C.')
        operation = action['operation']
        if operation in ('mock_put_down', 'mock_pour'):
            if source['held'] is not True or source['dock_id'] is not None:
                raise ValueError('The current frame does not show the sample cup held by the arm.')
        else:
            station = action['arguments'].get('station', 'A')
            if source['held'] is not False or source['dock_id'] != station:
                raise ValueError('The sample cup is out of dock '+station+'.')
        return {'camera': {field: scene[field] for field in CAMERA_FIELDS},
                'vessels': {label: {field: detection[field] for field in ('dock_id', 'held', 'box_xyxy')}
                            for label, detection in vessels.items()}}

    def _check_context(self, task, plan):
        scene = task['scene'] or {}
        action = self._action(plan)
        if action:
            # These capabilities have no executor/observer in this software
            # delivery. A model may not silently execute a supported subset of
            # a request that also asks for one of them.
            unsupported = re.search(r'\b(?:dilut(?:e|ion)|concentration|buoyancy|mandarin|'
                                    r'numeric(?:al)? ph|exact ph|measure (?:the )?ph|'
                                    r'heat(?:ing)?|temperature measurement)\b', task['request'], re.I)
            if unsupported:
                raise ValueError('This request includes an unsupported capability: '+unsupported.group(0)+
                                 '. Ask for the supported action separately; no partial action was approved.')
        feature_schema = getattr(self.perception, 'feature_schema', None)
        if feature_schema is not None and any(rule['feature'] not in feature_schema for rule in plan['outcome_checks']):
            raise ValueError('Use supported observer features: '+', '.join(feature_schema))
        expected = {}
        for check in plan['outcome_checks']:
            value = compute_skill_hash(check['expected'])
            if expected.setdefault(check['feature'], value) != value:
                raise ValueError('Conflicting outcome checks for '+check['feature']+'.')
        known_labels = self._known_labels(task)
        for rule in plan['preconditions']:
            if rule['fresh_scene'] and not TaskLoop._fresh(scene):
                raise ValueError('A fresh scene is required.')
            if not set(rule['labels']).issubset(known_labels):
                raise ValueError('Required scene labels have not been verified.')
        if set(plan['evidence_ids']) - set(task['evidence']):
            raise ValueError('Plan references evidence unavailable to this task.')
        sample = self._prepared_sample(plan)
        if sample and task['condition_id'] and sample['arguments']['condition_id'] != task['condition_id']:
            raise ValueError('The proposed mock sample differs from the selected condition.')
        if action:
            if task['dispatched_action']:
                raise ValueError('This task already dispatched its single mock action.')
            if not task['images'] or not TaskLoop._fresh(scene):
                raise ValueError('Mock execution requires fresh timestamped scene images.')
            backend = self.backends.get(task['session_id'])
            if backend is None:
                raise ValueError('Prepare a fresh simulation before proposing an action.')
            backend.check_step(action['operation'], action['arguments'])
            self._fixture_state(task, scene['frame_id'], action)
        if any(step['operation'] == 'localize_objects' and step['arguments']['evidence_id'] not in task['evidence']
               for step in plan['steps']):
            raise ValueError('Localization steps require evidence available to this task.')
        try:
            checked_images = {
                image['evidence_id']: image for image in task['images']
            } if action or any(rule['fresh_scene'] or rule['labels'] for rule in plan['preconditions']) else {}
            for fid in plan['evidence_ids']:
                checked_images.update((image['evidence_id'], image) for image in task['evidence'][fid]['images'])
            for image in checked_images.values():
                self._check_image(task['session_id'], image)
        except OSError as exc:
            raise ValueError(self._perception_error(exc)) from exc

    def _check_improvement(self, task, draft, plan):
        pinned = task['improvement']['baseline_plan'] or {}
        skill_id, version = pinned.get('skill_id'), pinned.get('skill_version')
        if not skill_id or not version:
            raise ValueError('Improvement requires a pinned baseline skill ID and version.')
        if not draft.skill_definition or plan['skill_id'] != skill_id:
            raise ValueError('Improvement must author a revision of the pinned baseline skill ID.')
        try:
            active = self.registry.get(skill_id)
        except KeyError:
            active = None
        if not active or active['version'] != version or active['status'] != 'active':
            raise ValueError('The active baseline changed; start improvement from its current version.')
        if plan['skill_version'] == version:
            raise ValueError('Improvement must author a new version of the pinned baseline.')
        baseline = SkillDefinition.model_validate({k: v for k, v in active.items() if k not in ('status', 'version')})
        revised = draft.skill_definition
        if baseline.model_dump(mode='json')['parameter_schema'] != revised.model_dump(mode='json')['parameter_schema']:
            raise ValueError('Improvement must preserve the baseline parameter domain.')
        if baseline.intent != revised.intent:
            raise ValueError('Improvement must preserve the baseline intent.')
        original_actions = [step for step in pinned['steps'] if step['operation'] in MOCK_OPERATIONS]
        revised_actions = [step for step in plan['steps'] if step['operation'] in MOCK_OPERATIONS]
        if (compute_skill_hash(pinned['bindings']) != compute_skill_hash(plan['bindings']) or
                original_actions != revised_actions):
            raise ValueError('Improvement must preserve the bound action for the original request.')
        # Compare the compiled checks as well as the definition checks so removing
        # a composed skill cannot quietly drop its expectations.
        for before, after in ((baseline.outcome_checks, revised.outcome_checks),
                              (pinned['outcome_checks'], plan['outcome_checks'])):
            if not {compute_skill_hash(c) for c in before}.issubset(compute_skill_hash(c) for c in after):
                raise ValueError('Improvement cannot weaken baseline outcome or final-state expectations.')
        if any(key not in revised.expected_state or
               compute_skill_hash(revised.expected_state[key]) != compute_skill_hash(value)
               for key, value in baseline.expected_state.items()):
            raise ValueError('Improvement cannot weaken baseline outcome or final-state expectations.')

    def _proposal_plan(self, s, task, draft, phase):
        """Pure phase, registry and improvement checks for a proposed draft."""
        self._guard_task(s, task)
        if phase == 'execution_feedback':
            if task['status'] not in ('executing', 'observing'):
                raise ValueError('A revision requires an execution checkpoint.')
            if task['replans'] >= 2:
                raise ValueError('Replan limit reached; the changed plan was not approved.')
        elif phase not in ('planning', 'improvement') or task['status'] != 'running':
            raise ValueError('A proposal requires an active planning phase.')
        plan = self.registry.compile(draft, task_id=task['task_id'])
        if task['improvement']:
            if phase == 'execution_feedback' and task['dispatched_action']:
                if plan['skill_id']:
                    raise ValueError('After the action, revise remaining observation steps without proposing another skill.')
            else:
                self._check_improvement(task, draft, plan)
        if draft.skill_definition:
            self.registry.check_candidate(task['task_id'], draft.skill_definition)
        return plan

    def _preflight(self, s, task, draft, phase):
        plan = self._proposal_plan(s, task, draft, phase)
        self._check_context(task, plan)
        return plan

    async def _prepare_proposal(self, s, task, draft, phase):
        plan = self._proposal_plan(s, task, draft, phase)
        # Evidence tools may acquire or localize a frame. The final check itself
        # writes nothing and can run again at commit without another acquisition.
        try:
            await self._verify_labels(s, task, plan, refresh=True)
        except (ValueError, OSError, RuntimeError, TimeoutError) as exc:
            raise ValueError(self._perception_error(exc)) from exc
        return self._preflight(s, task, draft, phase)

    async def _plan_task(self, s, task):
        began = time.perf_counter()
        try:
            await self._set_status(s, task, 'running')
            if self.perception:
                try:
                    await self._capture(s, task, 'inspect_scene', {'view': 'primary'})
                except (ValueError, RuntimeError, OSError, TimeoutError) as exc:
                    task['feedback'].append({'type': 'scene_unavailable', 'reason': self._perception_error(exc)})
                    await self._emit_task(s, task, 'scene_unavailable', code=type(exc).__name__)
            phase = 'improvement' if task['improvement'] else 'planning'
            route = None if task['improvement'] else self.registry.match(task['request'])
            if route:
                try:
                    await self._prepare_proposal(s, task, route, phase)
                except (ValueError, OSError, RuntimeError, TimeoutError, KeyError) as exc:
                    task['feedback'].append({'type': 'precondition_failed', 'reason': str(exc)})
                else:
                    task['route'] = 'active_skill'
                    await self._propose_task(s, task, route, phase, began)
                    return
            task['route'] = 'expert'
            response, validated = await self._run_expert(s, task, phase)
            if response['kind'] in ('plan', 'revision'):
                draft = PlanDraft.model_validate(response['payload'])
                if not validated:
                    await self._prepare_proposal(s, task, draft, phase)
                await self._propose_task(s, task, draft, phase, began)
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
                task['execution'].append({'request_id': task['request_id'], 'backend': s['backend'],
                                          'status': 'failed', 'reason': summary})
                s['trial']['state'] = 'stopped'
            details = exc.errors(include_input=False, include_url=False) if hasattr(exc, 'errors') else None
            await self._set_status(s, task, 'failed', summary, code=code, validation_errors=details)

    async def _propose_task(self, s, task, draft, phase, began, *, prior_request=None, prior_receipt=None):
        plan = self._preflight(s, task, draft, phase)
        summary = 'In the simulation, I will '+', then '.join(describe_step(step) for step in plan['steps'])+'.'
        if draft.skill_definition:
            version = self.registry.validate_for_task(task['task_id'], draft.skill_definition)
            self.registry.authorize(task['task_id'], plan['skill_id'], version)
        s['proposal_sequence'] += 1
        request_id = str(uuid.uuid4())
        bound_plan = {**plan, 'scene_hash': self._scene_hash(s), 'generation': s['generation'],
                      'trial_id': task['trial_id'], 'task_id': task['task_id']}
        action = self._action(plan)
        if action:
            presented_id = task['scene']['frame_id']
            bound_plan.update(scene_frame_id=presented_id,
                              fixture=self._fixture_state(task, presented_id, action))
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
        if prior_request is not None:
            prior_request.update(status='completed', result={**prior_receipt, 'status': 'superseded'})
            task['replans'] += 1
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
        warm = task['route'] == 'active_skill' and task['replans'] == 0
        receipt = {'request_id': request['request_id'], 'task_id': task['task_id'],
                   'trial_id': task['trial_id'], 'skill_id': plan['skill_id'], 'skill_version': plan['skill_version'],
                   'plan_hash': request['plan_hash'], 'backend': s['backend'], 'status': 'no_operation',
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
                if operation in MOCK_OPERATIONS:
                    try:
                        await self._verify_dispatch(s, task, request, step)
                    except (ValueError, OSError, RuntimeError, TimeoutError) as exc:
                        self._guard_task(s, task)
                        reason = self._perception_error(exc)
                        if self.expert is not None and await self._execution_feedback(s, task, request, receipt, reason):
                            return
                        raise ValueError(reason) from exc
                    receipt['dispatch_evidence_id'] = task['scene']['frame_id']

                    async def progress(phase):
                        await self._emit_task(s, task, 'execution_progress', step=index,
                                              operation=operation, phase=phase, provenance='SIMULATED' if s['backend'] == 'mujoco' else 'MOCK')

                    # Preserve the existing call signature for prepared-sample backend overrides.
                    options = {} if operation == 'mock_prepared_sample' else {'operation': operation}

                    async def dispatch():
                        self._guard_task(s, task)
                        task['dispatched_action'] = True
                        return await self._backend(s['session_id']).execute_step(
                            request['request_id'], arguments, progress, **options)

                    try:
                        result = await asyncio.wait_for(dispatch(), self.execution_timeout)
                    except (RuntimeError, ValueError, TimeoutError) as exc:
                        result = {'status': 'failed', 'controller_completed': False,
                                  'reason': f'Executor failed ({type(exc).__name__}).'}
                    receipt.update(result)
                    receipt['execution_finished_at'] = time.time()
                    task['execution'].append(copy.deepcopy(receipt))
                    task['feedback'].append({'type': 'execution', 'receipt': copy.deepcopy(receipt)})
                    await self._emit_task(s, task, 'execution_result', receipt=receipt, provenance='SIMULATED' if s['backend'] == 'mujoco' else 'MOCK')
                    continue

                await self._set_status(s, task, 'observing')
                previous_evidence = set(task['evidence'])
                observed = await self._observe_step(s, task, request, operation, arguments, index,
                                                    previous_evidence)
                fresh = self._fresh_checkpoint(observed, previous_evidence)
                if operation in ('inspect_scene', 'observe') and fresh:
                    try:
                        await self._verify_labels(s, task, plan)
                    except (ValueError, OSError, RuntimeError, TimeoutError) as exc:
                        task['feedback'].append({'type': 'precondition_failed', 'reason': str(exc)})
                is_final = index == len(plan['steps']) - 1
                failure = None
                if operation == 'observe':
                    latest = task['observations'][-1]
                    if receipt['status'] == 'failed':
                        failure = receipt.get('reason') or 'Executor reported failure.'
                    elif latest['status'] != 'observed' or (is_final and not all(latest['checks'].values())):
                        failure = 'Independent outcome is unknown or an outcome check failed.'
                elif operation == 'inspect_scene':
                    if not fresh:
                        failure = 'Checkpoint did not return a fresh image.'
                elif not set(arguments['labels']).issubset(observed.get('verified_labels') or []):
                    failure = 'Checkpoint did not verify the requested labels.'
                if failure or (not warm and (operation in ('inspect_scene', 'observe') or observed.get('images'))):
                    if await self._execution_feedback(s, task, request, receipt, failure, is_final=is_final):
                        return
                if not is_final:
                    await self._set_status(s, task, 'executing')

            status = 'failed' if receipt['status'] == 'failed' else 'completed'
            request.update(status=status, result=copy.deepcopy(receipt))
            s['trial']['state'] = 'reflecting' if task['observations'] else 'predicting'
            latest = task['observations'][-1] if task['observations'] else None
            summary = latest['text'] if latest else 'The approved scene inspection is complete.'
            if status == 'failed':
                summary = f"{receipt.get('reason') or 'Executor reported failure.'} {summary}"
            await self._set_status(s, task, status, summary)
            if status == 'completed':
                await self._evaluate_completed(s, task)
        except asyncio.CancelledError:
            if task['status'] not in TASK_TERMINAL and task['generation'] == s['generation']:
                await self._fail_task(s, task, RuntimeError('Adapter cancelled unexpectedly.'))
        except Exception as exc:
            await self._fail_task(s, task, exc)

    async def _verify_dispatch(self, s, task, request, action):
        plan = request['plan']
        presented_id = plan['scene_frame_id']
        presented = task['evidence'][presented_id]['scene']
        try:
            frame = await self._capture(s, task, 'inspect_scene', {'view': presented['view']})
        except (ValueError, OSError, RuntimeError, TimeoutError):
            self._guard_task(s, task)
            task.update(images=[], scene=None)
            s.update(scene_images=[], scene=None)
            raise
        if frame['scene']['captured_at'] <= request['confirmed_at']:
            raise ValueError('Dispatch requires a frame captured after confirmation.')
        await self._verify_labels(s, task, plan, allow_alternate=False)
        self._guard_task(s, task)
        self._check_context(task, plan)
        current_id = frame['evidence_id']
        current = self._fixture_state(task, current_id, action)
        if current != plan['fixture']:
            raise ValueError('Vessel position or camera registration changed since the proposal was presented.')

    async def _verify_labels(self, s, task, plan, *, refresh=False, allow_alternate=True):
        labels = {label for rule in plan['preconditions'] for label in rule['labels']}
        action = self._action(plan)
        if action and self._requires_fixture_perception(task):
            labels.update(VESSEL_LABELS)
        labels = sorted(labels)
        fresh = self._fresh(task['scene'] or {})
        needs_live_frame = action is not None or any(rule['fresh_scene'] for rule in plan['preconditions'])
        if refresh and needs_live_frame and (not task['images'] or not fresh):
            await self._capture(s, task, 'inspect_scene', {'view': 'primary'})
            fresh = self._fresh(task['scene'] or {})
        if (labels and task['images'] and (fresh or not needs_live_frame) and
                not set(labels).issubset(self._known_labels(task))):
            evidence_id = task['scene']['frame_id']
            found = await self._capture(s, task, 'localize_objects',
                                        {'evidence_id': evidence_id, 'labels': labels})
            alternate = next((step['arguments'].get('fallback_view') for step in plan['steps']
                              if step['operation'] == 'observe' and step['arguments'].get('fallback_view')), None)
            if allow_alternate and not set(labels).issubset(found.get('verified_labels') or []) and alternate:
                frame = await self._capture(s, task, 'inspect_scene', {'view': alternate})
                await self._capture(s, task, 'localize_objects',
                                    {'evidence_id': frame['evidence_id'], 'labels': labels})

    async def _execution_feedback(self, s, task, request, receipt, failure, *, is_final=False):
        if failure:
            task['feedback'].append({'type': 'checkpoint_failed', 'reason': failure})
        decision, validated = await self._run_expert(s, task, 'execution_feedback')
        kind, payload = decision['kind'], decision['payload']
        if kind in ('revision', 'plan'):
            proposed_at = time.perf_counter()
            draft = PlanDraft.model_validate(payload)
            if not validated:
                await self._prepare_proposal(s, task, draft, 'execution_feedback')
            await self._propose_task(s, task, draft, 'execution_feedback', proposed_at,
                                     prior_request=request, prior_receipt=receipt)
            return True
        if kind in ('clarification', 'reject'):
            status = 'needs_clarification' if kind == 'clarification' else 'failed'
            request.update(status='cancelled' if kind == 'clarification' else 'failed', result=receipt)
            s['trial']['state'] = 'stopped'
            await self._set_status(s, task, status, decision['summary'])
            return True
        if not is_final and failure:
            raise ValueError(failure)
        if kind != 'complete' or (not is_final and payload.get('continue') is not True):
            raise ValueError('Expert did not authorize continuing the exact approved plan.')
        return False

    @classmethod
    def _fresh_checkpoint(cls, observed, previous_evidence):
        return (cls._fresh(observed.get('scene') or observed) and
                observed.get('evidence_id') not in previous_evidence and
                any(image['evidence_id'] == observed.get('evidence_id') for image in observed['images']))

    async def _observe_step(self, s, task, request, operation, arguments, index, previous_evidence):
        try:
            outcome_after = None
            if operation == 'observe':
                outcome_after = max([request['confirmed_at'], *(r['execution_finished_at'] for r in task['execution']
                                     if 'execution_finished_at' in r)])
            observed = await self._capture(s, task, operation, arguments, outcome_after=outcome_after)
        except (ValueError, OSError, RuntimeError, TimeoutError) as exc:
            observed = {'status': 'unknown', 'provenance': 'UNKNOWN', 'images': [],
                        'reason': self._perception_error(exc)}
            if operation != 'localize_objects':
                task.update(images=[], scene=None)
                s.update(scene_images=[], scene=None)
        if operation == 'observe':
            plan = request['plan']
            features = observed.get('features') or {}
            checks = {rule['feature']: type(features.get(rule['feature'])) is type(rule['expected']) and
                      features.get(rule['feature']) == rule['expected'] for rule in plan['outcome_checks']}
            evidence_ids = [i['evidence_id'] for i in observed['images']]
            known = (observed.get('status') == 'observed' and bool(evidence_ids) and
                     observed.get('provenance') not in (None, 'UNKNOWN', 'MODEL-PREDICTED', 'MOCK') and
                     bool(observed.get('observer_version')) and
                     self._fresh_checkpoint(observed, previous_evidence))
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
