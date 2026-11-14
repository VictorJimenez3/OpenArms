"""Gemini Live speech bridge. The application session outlives its voice provider.

State reaches the provider through paired tool results, never fabricated student turns.
Audio and transcripts carry reply/turn identities through actual client playback.
"""
from __future__ import annotations
import asyncio
import array
import base64
import contextlib
import json
import logging
import os
import time
import traceback
import uuid

from google import genai
from google.genai import types
from .voice_controls import MUTATING_TOOLS, VoiceControls


def declaration(name, description, properties=None, required=None, *, nonblocking=False):
    result = {'name': name, 'description': description,
              'parameters': {'type': 'OBJECT', 'properties': properties or {}, 'required': required or []}}
    if nonblocking:
        result['behavior'] = 'NON_BLOCKING'
    return result


S = {'type': 'STRING'}
TOOLS = [{'function_declarations': [
    declaration('watch_lab_events', 'Subscribe once to actual expert progress, proposals, execution and observed outcomes. '
                'The gateway restores this subscription when the provider session resumes. '
                'Call at voice start or on your first turn in a fresh provider session.', nonblocking=True),
    declaration('get_lab_state', 'Read authoritative current pH trial, proposal and evidence. Always read before stating progress.'),
    declaration('choose_condition', 'Record the student choice. Only vinegar, baking_soda or water. Never choose for them.', {'condition_id': S}, ['condition_id']),
    declaration('record_prediction', 'Optionally record a student prediction in their words. This is not an execution prerequisite or consent.', {'text': S}, ['text']),
    declaration('request_action', 'Quote the entire student request verbatim for the separate image-aware Codex expert or validated reusable skill. '
                'One mutation per completed student turn. Watch for progress. Never invent motion parameters.', {'text': S}, ['text'], nonblocking=True),
    declaration('improve_skill', 'When the student asks to improve a failed or limited skill, quote their entire request verbatim. '
                'The server supplies the recorded failure and unchanged baseline. This only proposes a revision.',
                {'limitation': S}, ['limitation'], nonblocking=True),
    declaration('student_confirm', 'Report/accept fresh completed student confirmation of the exact presented proposal. Cannot create consent.', {'request_id': S, 'proposal_version': {'type': 'INTEGER'}}, ['request_id', 'proposal_version']),
    declaration('cancel_request', 'Cancel a pending proposal; never grants consent.', {'request_id': S}),
    declaration('prepare_next_trial', 'Start the next mock pH trial after the student asks; preserve notebook and reset materials.'),
    declaration('record_reflection', 'Optionally record the student explanation after an observed outcome.', {'text': S}, ['text']),
    declaration('stop_lab', 'Stop the mock action immediately. Physical hardware is disabled.'),
]}]
ALLOWED = {item['name'] for item in TOOLS[0]['function_declarations']}
EVENT_BATCH = 12
INITIAL_REPLAY = 24
PLAYBACK_ACK_TIMEOUT = 15

OBSERVATION_FIELDS = ('observation_id', 'task_id', 'trial_id', 'request_id', 'plan_hash',
                      'skill_version', 'status', 'text', 'provenance', 'source',
                      'features', 'checks', 'reason', 'evidence', 'evidence_id', 'color')
RECEIPT_FIELDS = ('receipt_id', 'task_id', 'trial_id', 'request_id', 'skill_id', 'skill_version',
                  'plan_hash', 'backend', 'operation', 'status', 'controller_completed', 'physical_execution',
                  'elapsed_ms', 'provenance', 'evidence_id', 'reason', 'code', 'failure_code', 'error_code')
PROPOSAL_FIELDS = ('request_id', 'task_id', 'trial_id', 'proposal_version', 'summary', 'presented', 'expires_at')
EVENT_FIELDS = ('event_id', 'sequence', 'revision', 'kind', 'turn_id', 'task_id', 'trial_id',
                'request_id', 'skill_id', 'skill_version', 'provenance', 'evidence_ids')
# Host notebook events are the authority, including actual failure codes. Do not
# forward arbitrary tool payloads, validation inputs or local paths.
EVENT_DATA = {
    'task_queued': ('status',),
    'task_status': ('status', 'summary', 'code', 'failure_code', 'error_code'),
    'task_cancelled': ('status', 'reason'),
    'scene_unavailable': ('code',),
    'expert_result': ('phase',),
    'request_proposed': (),
    'request_cancelled': ('reason',),
    'request_expired': (),
    'student_confirmed': ('proposal_version',),
    'execution_progress': ('step', 'operation', 'phase'),
    'execution_result': ('step', 'operation', 'phase', 'code', 'failure_code', 'error_code'),
    'execution_checkpoint': ('step', 'operation'),
    'observation': (),
}


def key():
    return os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')


def brief(item, keys):
    return {key: item[key] for key in keys if key in item}


def feedback_event(event):
    kind = event.get('kind')
    if kind not in EVENT_DATA:
        return None
    data = event.get('data') or {}
    result = {**brief(event, EVENT_FIELDS), **brief(data, EVENT_DATA[kind])}
    if kind == 'execution_result':
        result['receipt'] = brief(data.get('receipt') or {}, RECEIPT_FIELDS)
    elif kind == 'observation':
        result['observation'] = brief(data.get('observation') or data, OBSERVATION_FIELDS)
    elif kind == 'request_proposed':
        result['proposal'] = brief(data.get('request') or {}, PROPOSAL_FIELDS)
    elif kind == 'expert_result':
        result['expert'] = brief(data.get('run') or {}, ('provider', 'model', 'kind', 'summary', 'calls'))
    # The controller receipt and independent observation share request/task/trial
    # and plan identities. A controller status is never an observed outcome.
    return result


def compact(context):
    return compact_snapshot(context())


def compact_snapshot(snap):
    names = ('session_id', 'backend', 'experiment', 'trial', 'conditions', 'prediction', 'pending', 'generation',
             'scene', 'voice_control')
    result = {k: snap.get(k) for k in names}
    result['observations'] = [brief(item, OBSERVATION_FIELDS) for item in snap.get('observations', [])[-3:]]
    result['requests'] = [brief(item, (*PROPOSAL_FIELDS, 'status', 'reason'))
                          for item in snap.get('requests', [])[-2:]]
    result['tasks'] = []
    for task in snap.get('tasks', [])[-2:]:
        summary = brief(task, ('task_id', 'trial_id', 'turn_id', 'request_id', 'request', 'status',
                               'route', 'summary', 'reason', 'replans', 'code'))
        if task.get('execution'):
            summary['execution'] = [brief(r, RECEIPT_FIELDS) for r in task['execution'][-3:]]
        result['tasks'].append(summary)
    result['skills'] = [brief(item, ('skill_id', 'name', 'version', 'status', 'retrieval_examples'))
                        for item in snap.get('skills', [])[-6:]]
    result['skill_decisions'] = snap.get('skill_decisions', [])[-3:]
    if result['pending']:
        result['pending'] = brief(result['pending'], PROPOSAL_FIELDS)
    if result.get('scene'):
        result['scene'] = brief(result['scene'], ('frame_id', 'captured_at', 'fresh', 'view', 'provenance', 'limitations'))
    result['messages'] = snap.get('messages', [])[-8:]
    return result


def system_prompt(context):
    return (
        'You are OpenArms, the continuous conversational voice agent. A SEPARATE OpenAI Codex expert '
        '(gpt-6.1-sol, medium reasoning) inspects camera evidence, makes tool-level decisions, runs supported skills '
        'and proposes revisions during execution. You remain responsive while that background task runs. '
        'The main demonstration is red-cabbage indicator qualitative pH. Hardware is disabled in this software run. '
        'Results may be simulated image observations, recorded evidence, reference expectations or UNKNOWN; '
        'preserve the provenance reported by tools. Never claim simulated or recorded evidence is live physical success. '
        'The student chooses individual supported actions. Predictions and reflection are optional, never gates '
        'before an action. Speak naturally in one or two short sentences. '
        'Call watch_lab_events once at voice start or on your first turn in a fresh provider session; '
        'a resumed session restores the previous subscription. '
        'For a natural task request, call request_action with the entire student transcript verbatim. If a task is already running, '
        'answer follow-ups and communicate its progress without starting duplicate work. '
        'Explain uncertainty, clarification, failure, cancellation and a revised proposal when the server reports them. '
        'Use tools for every state change. A student prediction is not a movement request or consent. '
        'Use choose_condition for a standalone sample choice. For an action that includes a sample choice, '
        'send the whole request through request_action. If they volunteer a prediction, '
        'call record_prediction with their words. Do not require them to complete a lesson sequence. '
        'Only ask for confirmation for the current pending proposal. Read its summary VERBATIM, then say "Say confirm or cancel." '
        'Read a given proposal once; repeat only if the student asks or playback was interrupted. '
        'On a fresh student confirm, call student_confirm using the exact pending request_id and proposal_version. '
        'The server independently consumes valid consent and may already have executed it; use the returned evidence. '
        'Never say an action started merely because you heard confirm. Only authoritative executing or completed '
        'task status proves it started. A voice_control rejection means nothing was approved; explain its reason '
        'and ask for fresh confirmation after the current proposal is fully heard. '
        'Do not repeat a prediction request already satisfied. Do not claim the robot moved. '
        'When the student asks a science question, answer it without changing the trial. For open conversation, be helpful and brief. '
        'Never infer observed color from selected condition or controller completion. Explain what the observer reports '
        'and distinguish MODEL-PREDICTED references from image observations. '
        'When speaking any SIMULATED or SYNTHETIC outcome, explicitly say "In the simulation". '
        'For recorded evidence, say "In the recording"; for MODEL-PREDICTED say "The reference predicts". '
        'No numeric pH estimates. Acid reference may be pink/red, water purple, mild baking-soda reference blue/green; actual preparation matters. '
        'Follow-up and reflection are conversation, not new action requests. Cancellation and STOP are handled by the server. '
        'You do not authorize hardware or choose fixtures. Never fabricate tool results. '
        'At voice start, greet briefly and ask what the student would like to do, or acknowledge their active task.\n'
        + json.dumps(compact(context), ensure_ascii=False)
    )


class GeminiBridge:
    def __init__(self, context, tool_call, emit, *, client_factory=None, reconnect_delay=.5):
        self.context, self.tool_call, self.emit = context, tool_call, emit
        self.client_factory, self.reconnect_delay = client_factory, reconnect_delay
        self.controls = VoiceControls(context, tool_call, self._playback_idle)
        self.recorded_turn = asyncio.Event()
        self.recorded_turn_id = None
        self.recording_turn_id = None
        self.incoming = asyncio.Queue(maxsize=40)
        self.closed = False
        self.muted = False
        self.ready = False
        self.reply_id = None
        self.reply_text = ''
        self.reply_proposal = None
        self.reply_seconds = 0.
        self.replies = {}
        self.playback_changed = asyncio.Event()
        self.seen_tools = {}
        self.pending_tools = {}
        self.cancelled_tools = set()
        self.resume_handle = None
        self.resume_watch = (None, None)
        self.voice_epoch = 0
        self.last_error = None
        self.suppress_output = False
        self.discard_transcript = False
        self.state_updates = asyncio.Queue(maxsize=1)
        self.watcher_id = None
        self.resume_watcher_id = None
        self.watch_cursor = None
        self.watch_failure = None
        self.last_state_signature = None
        self.speech_active = False
        self.silence_seconds = 0.
        self.input_boundary = None
        self.last_transcription = 0.

    async def audio(self, encoded):
        if self.closed or self.muted or not self.ready:
            return
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception:
            raise ValueError('Invalid audio frame.') from None
        if not raw or len(raw) > 6400 or len(raw) % 2:
            raise ValueError('Audio frames must be at most 200 ms of 16 kHz mono PCM.')
        samples = array.array('h', raw)
        voiced = sum(value*value for value in samples)/len(samples) > 320**2
        if voiced:
            if self.input_boundary:
                self.input_boundary.cancel()
                self.input_boundary = None
            if not self.speech_active:
                # Bind consent at audible input onset, before delayed ASR arrives.
                self.controls.begin_input()
            self.speech_active = True
            self.silence_seconds = 0.
        elif self.speech_active:
            self.silence_seconds += len(raw)/32000
            if self.silence_seconds >= .65:
                self._end_speech()
        if self.incoming.full():
            # Never let an old microphone backlog become a future confirmation.
            self._discard_input()
            self.controls.revoke()
            await self.emit({'type': 'error', 'code': 'audio_backpressure', 'message': 'Audio connection is slow. Please repeat your last sentence.', 'recoverable': True})
            return
        self.incoming.put_nowait(('audio', raw, self.voice_epoch))

    def _discard_input(self):
        while not self.incoming.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                self.incoming.get_nowait()

    async def end_audio(self):
        if self.ready and not self.incoming.full():
            self.incoming.put_nowait(('end', None, self.voice_epoch))
            self._end_speech()

    def _end_speech(self):
        self.speech_active = False
        if self.input_boundary or not self.controls.started or self.controls.finished.is_set():
            return
        self.input_boundary = asyncio.create_task(self._finish_input(
            self.controls.turn_id, self.voice_epoch, self.context().get('generation', 0)))

    async def _finish_input(self, turn_id, epoch, generation):
        try:
            deadline = time.monotonic()+3
            while time.monotonic() < deadline:
                await asyncio.sleep(.1)
                if (self.closed or self.muted or epoch != self.voice_epoch or
                        generation != self.context().get('generation', 0) or self.controls.turn_id != turn_id or
                        self.controls.finished.is_set() or self.speech_active):
                    return
                # The PCM utterance has ended independently of the model. Allow
                # delayed transcription fragments to settle before closing it.
                if self.controls.text.strip() and time.monotonic()-self.last_transcription >= .5:
                    await self._finish_transcript()
                    return
        finally:
            if self.input_boundary is asyncio.current_task():
                self.input_boundary = None

    async def mute(self, muted):
        self.muted = muted
        self.voice_epoch += 1
        self._discard_input()
        self.controls.revoke()
        self.discard_transcript = True
        if muted:
            await self.interrupt(None)
        await self.end_audio()
        await self.emit({'type': 'status', 'status': 'muted' if muted else ('listening' if self.ready else 'connecting')})

    async def interrupt(self, reply_id):
        if reply_id and reply_id != self.reply_id and reply_id not in self.replies:
            return
        if reply_id is None:
            # Both clients clear all playback on a null interruption, even
            # when Gemini already marked the last reply generation complete.
            self.replies.clear()
        else:
            self.replies.pop(reply_id, None)
        if self.reply_id and (reply_id is None or reply_id == self.reply_id):
            self.suppress_output = True
            self._clear_reply()
        self.playback_changed.set()
        await self.emit({'type': 'interrupted', 'reply_id': reply_id})

    def _clear_reply(self):
        self.reply_id = None
        self.reply_text = ''
        self.reply_proposal = None
        self.reply_seconds = 0.

    def _expire_replies(self):
        now = time.monotonic()
        for rid, record in tuple(self.replies.items()):
            if record.get('expires', float('inf')) <= now:
                del self.replies[rid]

    def _playback_idle(self):
        self._expire_replies()
        return not self.reply_id and not self.replies

    async def played(self, reply_id):
        self._expire_replies()
        record = self.replies.pop(reply_id, None)
        if not record or not record['complete']:
            return
        try:
            proposal = record.get('proposal')
            if proposal:
                pending = self.context().get('pending') or {}
                if (pending.get('request_id') == proposal['request_id'] and
                        pending.get('proposal_version') == proposal['proposal_version']):
                    await self.tool_call('_present_audio', {**proposal, 'reply_id': reply_id})
            await self.emit({'type': 'status', 'status': 'muted' if self.muted else 'listening'})
        finally:
            self.playback_changed.set()

    async def close(self):
        self.closed = True
        self.ready = False
        self.voice_epoch += 1
        self._discard_input()
        self.controls.revoke()
        await self.interrupt(None)

    async def _finish_transcript(self):
        turn_id, text = self.controls.turn_id, self.controls.text
        if self.recorded_turn_id == turn_id or self.recording_turn_id == turn_id:
            return
        self.controls.input('', finished=True)
        self.recording_turn_id = turn_id
        try:
            await self._record('user', text, turn_id, True)
        finally:
            if self.recording_turn_id == turn_id:
                self.recording_turn_id = None
        if turn_id != self.controls.turn_id:
            return
        self.recorded_turn_id = turn_id
        self.recorded_turn.set()
        try:
            await self.controls.complete_control()
        except (ValueError, TimeoutError) as exc:
            await self._rejected_control(exc)

    async def _record(self, role, text, turn_id, final):
        if not text:
            return
        if final:
            await self.tool_call('_record_transcript', {'role': role, 'text': text, 'turn_id': turn_id, 'final': True})
        await self.emit({'type': 'transcript', 'role': role, 'text': text, 'turn_id': turn_id, 'final': final})

    async def state_changed(self):
        """Coalesce wakeups, never the underlying sequenced notebook events."""
        snap = self.context()
        state = compact_snapshot(snap)
        meaningful = {name: state.get(name) for name in (
            'pending', 'generation', 'trial', 'prediction', 'tasks', 'observations', 'requests',
            'skills', 'skill_decisions', 'voice_control')}
        if meaningful.get('pending'):
            # Playback acknowledgment is for consent validation, not a new
            # proposal. Narrating it again can overlap the student's confirm.
            meaningful['pending'] = {k: v for k, v in meaningful['pending'].items() if k != 'presented'}
        meaningful['requests'] = [{k: v for k, v in r.items() if k != 'presented'} for r in state['requests']]
        meaningful['event_sequence'] = next((e.get('sequence') for e in reversed(snap.get('notebook', []))
                                             if e.get('kind') in EVENT_DATA), None)
        signature = json.dumps(meaningful, sort_keys=True, default=str)
        if signature == self.last_state_signature:
            return
        self.last_state_signature = signature
        if self.state_updates.full():
            self.state_updates.get_nowait()
        self.state_updates.put_nowait(state)

    async def _rejected_control(self, error):
        await self.tool_call('_voice_control_rejected', {
            'turn_id': self.controls.turn_id, 'reason': str(error)[:240]})
        await self.state_changed()
        await self.emit({'type': 'error', 'message': str(error), 'recoverable': True})

    async def _wait_for_playback(self):
        self.playback_changed.clear()
        while not self._playback_idle():
            deadline = min((r['expires'] for r in self.replies.values() if 'expires' in r), default=None)
            try:
                await asyncio.wait_for(self.playback_changed.wait(), timeout=(
                    max(0, deadline - time.monotonic()) if deadline is not None else None))
            except TimeoutError:
                pass
            self.playback_changed.clear()

    async def _watch(self, session, cid, *, resumed=False):
        first = True
        previous_control = None
        try:
            await self.state_changed()
            while not self.closed and cid not in self.cancelled_tools:
                if not first:
                    await self.state_updates.get()
                await self._wait_for_playback()
                # Consume at most one wakeup just before the fresh snapshot.
                if not self.state_updates.empty():
                    self.state_updates.get_nowait()
                snap = self.context()
                state = compact_snapshot(snap)
                notebook = snap.get('notebook', [])
                if self.watch_cursor is None:
                    recent = [e for e in notebook if e.get('kind') in EVENT_DATA][-INITIAL_REPLAY:]
                    self.watch_cursor = recent[0]['sequence'] - 1 if recent else 0
                events = [event for raw in notebook if raw.get('sequence', 0) > self.watch_cursor
                          if (event := feedback_event(raw)) is not None]
                cursor = notebook[-1]['sequence'] if notebook else self.watch_cursor
                pending = state.get('pending') or {}
                control = state.get('voice_control')
                # Once presented, keep passive updates from talking over the
                # student's next confirmation. A new rejection still needs a reply.
                quiet = pending.get('presented') and (first or control == previous_control)
                for offset in range(0, max(1, len(events)), EVENT_BATCH):
                    batch = events[offset:offset + EVENT_BATCH]
                    more = offset + EVENT_BATCH < len(events)
                    through = batch[-1]['sequence'] if more else cursor
                    await session.send_tool_response(function_responses=[types.FunctionResponse(
                        id=cid, name='watch_lab_events', response={
                            'subscription': 'resumed' if first and resumed else 'current',
                            'state': state, 'events': batch, 'after_sequence': self.watch_cursor,
                            'through_sequence': through,
                            'instruction': 'Use the current state and new events. Ignore already reported sequences and superseded proposals. '
                                           'Report significant changes only, including actual failure codes when present. '
                                           'Controller completion does not establish an observed outcome. '
                                           'Say "In the simulation" for simulated or synthetic results and '
                                           '"In the recording" for recorded evidence. Reflection is optional.'},
                        will_continue=True, scheduling='SILENT' if quiet or more else 'WHEN_IDLE')])
                    self.watch_cursor = through
                    first = False
                previous_control = control
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self.watch_failure and not self.watch_failure.done():
                self.watch_failure.set_result(exc)
            else:
                raise
        finally:
            if self.watcher_id == cid:
                self.watcher_id = None

    async def _tool(self, session, call, *, cid=None, turn_id=None):
        cid = cid or call.id or str(uuid.uuid4())
        try:
            if cid in self.cancelled_tools:
                return
            if call.name == 'watch_lab_events':
                if self.watcher_id:
                    await session.send_tool_response(function_responses=[types.FunctionResponse(
                        id=cid, name='watch_lab_events', response={'subscribed': True, 'duplicate': True},
                        will_continue=False, scheduling='SILENT')])
                    return
                self.resume_watcher_id = self.watcher_id = cid
                await self._watch(session, cid)
                return
            if cid in self.seen_tools:
                result = self.seen_tools[cid]
            else:
                try:
                    if call.name not in ALLOWED:
                        raise ValueError('Unsupported tool.')
                    if call.name in MUTATING_TOOLS:
                        turn_id = turn_id or self.controls.turn_id
                        async with asyncio.timeout(4):
                            while self.recorded_turn_id != turn_id and turn_id == self.controls.turn_id and self.controls.started:
                                self.recorded_turn.clear()
                                await self.recorded_turn.wait()
                        if self.recorded_turn_id != turn_id:
                            raise ValueError('Wait for a completed student turn.')
                    await self.controls.dispatch(call.name, {**dict(call.args or {}), '_tool_call_id': cid}, turn_id=turn_id)
                    result = compact(self.context)
                    pending = result.get('pending')
                    if (pending and not pending.get('presented') and call.name != 'student_confirm'
                            and not self.watcher_id):
                        result['speech_instruction'] = 'Read this exact preview once, then ask confirm or cancel: ' + pending['summary']
                except Exception as exc:
                    result = {'error': str(exc)[:240], 'state': compact(self.context)}
                self.seen_tools[cid] = result
            if cid not in self.cancelled_tools:
                await session.send_tool_response(function_responses=[types.FunctionResponse(id=cid, name=call.name, response={'result': result})])
        finally:
            self.pending_tools.pop(cid, None)

    async def _upstream(self, session):
        while True:
            kind, data, epoch = await self.incoming.get()
            if epoch != self.voice_epoch:
                continue
            if kind == 'audio' and not self.muted:
                await session.send_realtime_input(audio=types.Blob(data=data, mime_type='audio/pcm;rate=16000'))
            elif kind == 'end':
                await session.send_realtime_input(audio_stream_end=True)

    async def _downstream(self, session):
        while True:
            async for response in session.receive():
                if response.session_resumption_update:
                    update = response.session_resumption_update
                    if update.resumable and update.new_handle:
                        self.resume_handle = update.new_handle
                        self.resume_watch = (self.resume_watcher_id, self.watch_cursor)
                if response.go_away:
                    raise ConnectionError('Provider renewal')
                cancellation = response.tool_call_cancellation
                if cancellation:
                    for cid in cancellation.ids:
                        self.cancelled_tools.add(cid)
                        if cid == self.resume_watcher_id:
                            self.resume_watcher_id = None
                        if cid == self.resume_watch[0]:
                            self.resume_watch = (None, None)
                        task = self.pending_tools.get(cid)
                        if task:
                            task.cancel()
                        await self.tool_call('_cancel_tool_request', {'tool_call_id': cid})
                    await self.interrupt(None)
                content = response.server_content
                if content:
                    if content.interrupted:
                        await self.interrupt(None)
                        self.suppress_output = False
                        self.discard_transcript = False
                    transcription = content.input_transcription
                    if transcription and not self.muted and not self.discard_transcript:
                        self.last_transcription = time.monotonic()
                        if transcription.text or not self.controls.finished.is_set():
                            self.controls.input(transcription.text or '')
                        if getattr(transcription, 'finished', False):
                            await self._finish_transcript()
                        else:
                            await self._record('user', self.controls.text, self.controls.turn_id, False)
                    audio_parts = [p.inline_data.data for p in (content.model_turn.parts if content.model_turn else []) if p.inline_data and p.inline_data.data]
                    output = content.output_transcription
                    if not self.reply_id and (audio_parts or (output and output.text)):
                        self._expire_replies()
                        if any(r.get('proposal') for r in self.replies.values()):
                            # WHEN_IDLE covers Gemini generation, not playback.
                            # A reply already scheduled upstream must not start
                            # a new stream that cuts off the phone's preview.
                            self.suppress_output = True
                    if not self.suppress_output and (audio_parts or (output and output.text)):
                        if not self.reply_id:
                            self.reply_id = str(uuid.uuid4())
                            self.reply_text = ''
                            pending = self.context().get('pending')
                            self.reply_proposal = ({k: pending[k] for k in ('request_id', 'proposal_version')} if pending else None)
                            await self.emit({'type': 'reply_start', 'reply_id': self.reply_id, 'proposal': self.reply_proposal})
                            await self.emit({'type': 'status', 'status': 'speaking'})
                        rid = self.reply_id
                        if rid and output and output.text:
                            self.reply_text += output.text
                            await self._record('assistant', self.reply_text, rid, False)
                        for raw in audio_parts:
                            if rid is None or self.reply_id != rid:
                                break
                            self.reply_seconds += len(raw) / 48000  # 24 kHz PCM16
                            await self.emit({'type': 'audio', 'data': base64.b64encode(raw).decode(), 'reply_id': rid})
                    if content.turn_complete:
                        self.suppress_output = False
                        self.discard_transcript = False
                    if content.turn_complete and self.reply_id:
                        rid = self.reply_id
                        text = self.reply_text
                        await self._record('assistant', text, rid, True)
                        # A readout acknowledgment is valid only if its transcript contains
                        # the exact canonical preview. Generation completion alone is not presentation.
                        def words(s):
                            return ' '.join(''.join(c.lower() if c.isalnum() else ' ' for c in s).split())
                        pending = self.context().get('pending') or {}
                        proposal = self.reply_proposal
                        if (not pending.get('summary') or not proposal or
                                any(pending.get(k) != v for k, v in proposal.items()) or
                                words(pending['summary']) not in words(text)):
                            proposal = None
                        if self.reply_id == rid and self.reply_seconds:
                            # Reply UUIDs are one-use playback tokens. A delayed ACK
                            # for a dropped/expired reply cannot present a new one.
                            self.replies[rid] = {'complete': True, 'proposal': proposal,
                                                 'expires': time.monotonic() + PLAYBACK_ACK_TIMEOUT}
                        if self.reply_id == rid:
                            self._clear_reply()
                        self.playback_changed.set()
                        await self.emit({'type': 'reply_end', 'reply_id': rid})
                if response.tool_call:
                    for call in response.tool_call.function_calls:
                        cid = call.id or str(uuid.uuid4())
                        if cid not in self.pending_tools and cid not in self.cancelled_tools:
                            self.pending_tools[cid] = asyncio.create_task(
                                self._tool(session, call, cid=cid, turn_id=self.controls.turn_id))
                if response.usage_metadata:
                    await self.tool_call('_record_usage', {'usage': response.usage_metadata.model_dump(mode='json', exclude_none=True)})
            await asyncio.sleep(0)

    async def run(self):
        if not key() and not self.client_factory:
            await self.emit({'type': 'status', 'status': 'unavailable', 'message': 'Voice is not configured on this host. Your text trial is ready.'})
            return
        client = self.client_factory() if self.client_factory else genai.Client(api_key=key(), http_options={'api_version': 'v1beta'})
        try:
            for attempt in range(4):
                if self.closed:
                    return
                handle = self.resume_handle
                if handle:
                    # Replay from the checkpoint paired with the provider's
                    # handle, not the potentially newer local send cursor.
                    self.resume_watcher_id, self.watch_cursor = self.resume_watch
                else:
                    self.resume_watcher_id, self.watch_cursor = None, None
                    self.seen_tools.clear()
                    self.cancelled_tools.clear()
                connected = False
                try:
                    await self.emit({'type': 'status', 'status': 'connecting' if attempt == 0 else 'reconnecting'})
                    config = types.LiveConnectConfig(response_modalities=['AUDIO'], system_instruction=system_prompt(self.context),
                        tools=TOOLS, input_audio_transcription={}, output_audio_transcription={},
                        session_resumption=types.SessionResumptionConfig(handle=handle),
                        context_window_compression=types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow()))
                    async with client.aio.live.connect(model=os.getenv('GEMINI_LIVE_MODEL', 'gemini-3.8-live'), config=config) as session:
                        connected = True
                        tasks = []
                        self.watch_failure = asyncio.get_running_loop().create_future()
                        try:
                            self.ready = True
                            self.suppress_output = self.discard_transcript = False
                            await self.emit({'type': 'status', 'status': 'muted' if self.muted else 'listening'})
                            if attempt == 0:
                                # The student's actual Start Voice gesture.
                                await session.send_client_content(turns=types.Content(role='user', parts=[types.Part(text='Start voice.')]), turn_complete=True)
                            if handle and self.resume_watcher_id:
                                # The model already subscribed. Reattach the same
                                # outstanding tool on the resumed transport.
                                cid = self.watcher_id = self.resume_watcher_id
                                self.pending_tools[cid] = asyncio.create_task(self._watch(session, cid, resumed=True))
                            tasks = [asyncio.create_task(self._upstream(session)), asyncio.create_task(self._downstream(session))]
                            done, _ = await asyncio.wait([*tasks, self.watch_failure], return_when=asyncio.FIRST_COMPLETED)
                            for task in tasks:
                                if task in done:
                                    task.result()
                            if self.watch_failure in done:
                                raise self.watch_failure.result()
                        finally:
                            self.ready = False
                            workers = [*tasks, *self.pending_tools.values(), self.watch_failure]
                            for worker in workers:
                                worker.cancel()
                            await asyncio.gather(*workers, return_exceptions=True)
                            self.pending_tools.clear()
                            self.watcher_id = None
                            self.watch_failure = None
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.last_error = type(exc).__name__
                    if handle and not connected:
                        # A rejected/expired resumption handle must not prevent
                        # the remaining attempts from opening a fresh session.
                        self.resume_handle = None
                    provider_code = getattr(exc, 'code', None)
                    failure = {'code': provider_code} if isinstance(provider_code, int) else {}
                    logging.getLogger(__name__).warning('Voice reconnect: %s at %s', self.last_error,
                        [(frame.name, frame.lineno) for frame in traceback.extract_tb(exc.__traceback__)[-4:]])
                    self.ready = False
                    self.voice_epoch += 1
                    self._discard_input()
                    self.controls.revoke()
                    await self.interrupt(None)
                    await self.tool_call('stop_lab', {})
                    if attempt == 3:
                        await self.emit({'type': 'status', 'status': 'unavailable', **failure,
                                         'message': 'Voice connection is unavailable. Continue by text or start voice again.'})
                        return
                    await self.emit({'type': 'status', 'status': 'reconnecting', **failure,
                                     'message': 'Reconnecting voice. Your notebook is saved; review a fresh proposal before confirming.'})
                await asyncio.sleep(self.reconnect_delay * (attempt + 1))
        finally:
            self.ready = False
            if self.input_boundary:
                self.input_boundary.cancel()
                await asyncio.gather(self.input_boundary, return_exceptions=True)
            await client.aio.aclose()
