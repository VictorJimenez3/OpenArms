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
from .voice_controls import VoiceControls


def declaration(name, description, properties=None, required=None, *, nonblocking=False):
    result = {'name': name, 'description': description,
              'parameters': {'type': 'OBJECT', 'properties': properties or {}, 'required': required or []}}
    if nonblocking:
        result['behavior'] = 'NON_BLOCKING'
    return result


S = {'type': 'STRING'}
TOOLS = [{'function_declarations': [
    declaration('watch_lab_events', 'Subscribe once to actual expert progress, proposals, execution and observed outcomes. '
                'This continues in the background while you converse. Call at voice start.', nonblocking=True),
    declaration('get_lab_state', 'Read authoritative current pH trial, proposal and evidence. Always read before stating progress.'),
    declaration('choose_condition', 'Record the student choice. Only vinegar, baking_soda or water. Never choose for them.', {'condition_id': S}, ['condition_id']),
    declaration('record_prediction', 'Optionally record a student prediction in their words. This is not an execution prerequisite or consent.', {'text': S}, ['text']),
    declaration('request_action', 'Send the student natural request to the separate image-aware Codex expert or validated reusable skill. '
                'It returns a task promptly; watch_lab_events provides progress. Never invent motion parameters.', {'text': S}, ['text'], nonblocking=True),
    declaration('improve_skill', 'When the student asks to improve a failed or limited skill, send their requested improvement. '
                'The server supplies the recorded failure and unchanged baseline. This only proposes a revision.',
                {'limitation': S}, ['limitation'], nonblocking=True),
    declaration('student_confirm', 'Report/accept fresh completed student confirmation of the exact presented proposal. Cannot create consent.', {'request_id': S, 'proposal_version': {'type': 'INTEGER'}}, ['request_id', 'proposal_version']),
    declaration('cancel_request', 'Cancel a pending proposal; never grants consent.', {'request_id': S}),
    declaration('prepare_next_trial', 'Start the next mock pH trial after the student asks; preserve notebook and reset materials.'),
    declaration('record_reflection', 'Optionally record the student explanation after an observed outcome.', {'text': S}, ['text']),
    declaration('stop_lab', 'Stop the mock action immediately. Physical hardware is disabled.'),
]}]
ALLOWED = {item['name'] for item in TOOLS[0]['function_declarations']}


def key():
    return os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')


def compact(context):
    snap = context()
    names = ('session_id', 'backend', 'experiment', 'trial', 'conditions', 'prediction', 'pending', 'generation',
             'scene')
    result = {k: snap.get(k) for k in names}
    def brief(item, keys):
        return {key: item[key] for key in keys if key in item}
    result['observations'] = [brief(item, ('observation_id', 'status', 'text', 'provenance', 'features', 'reason', 'evidence', 'evidence_id', 'color'))
                              for item in snap.get('observations', [])[-3:]]
    result['requests'] = [brief(item, ('request_id', 'proposal_version', 'status', 'summary'))
                          for item in snap.get('requests', [])[-2:]]
    result['tasks'] = [brief(item, ('task_id', 'request', 'status', 'route', 'summary', 'reason', 'replans'))
                       for item in snap.get('tasks', [])[-2:]]
    result['skills'] = [brief(item, ('skill_id', 'name', 'version', 'status', 'retrieval_examples'))
                        for item in snap.get('skills', [])[-6:]]
    result['skill_decisions'] = snap.get('skill_decisions', [])[-3:]
    if result['pending']:
        result['pending'] = brief(result['pending'], ('request_id', 'proposal_version', 'summary', 'presented', 'expires_at'))
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
        'At voice start, call watch_lab_events once to receive background progress and observations. '
        'For a natural task request, call request_action with the student words. If a task is already running, '
        'answer follow-ups and communicate its progress without starting duplicate work. '
        'Explain uncertainty, clarification, failure, cancellation and a revised proposal when the server reports them. '
        'Use tools for every state change. A student prediction is not a movement request or consent. '
        'Use choose_condition for a standalone sample choice. For an action that includes a sample choice, '
        'send the whole request through request_action. If they volunteer a prediction, '
        'call record_prediction with their words. Do not require them to complete a lesson sequence. '
        'Never ask for confirmation unless a tool result contains pending. Read its summary VERBATIM, then say "Say confirm or cancel." '
        'Read a given proposal once; repeat only if the student asks or playback was interrupted. '
        'On a fresh student confirm, call student_confirm using the exact pending request_id and proposal_version. '
        'The server independently consumes valid consent and may already have executed it; use the returned evidence. '
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
        self.controls = VoiceControls(context, tool_call, lambda: not self.reply_id and not self.replies)
        self.incoming = asyncio.Queue(maxsize=40)
        self.closed = False
        self.muted = False
        self.ready = False
        self.reply_id = None
        self.reply_text = ''
        self.reply_proposal = None
        self.replies = {}
        self.seen_tools = {}
        self.pending_tools = {}
        self.cancelled_tools = set()
        self.resume_handle = None
        self.voice_epoch = 0
        self.last_error = None
        self.suppress_output = False
        self.discard_transcript = False
        self.state_updates = asyncio.Queue(maxsize=1)
        self.watcher_id = None
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
                    self.controls.input('', finished=True)
                    await self._record('user', self.controls.text, turn_id, True)
                    try:
                        await self.controls.complete_control()
                    except (ValueError, TimeoutError) as exc:
                        await self.emit({'type': 'error', 'message': str(exc), 'recoverable': True})
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
        await self.end_audio()
        await self.emit({'type': 'status', 'status': 'muted' if muted else ('listening' if self.ready else 'connecting')})

    async def interrupt(self, reply_id):
        if reply_id and reply_id != self.reply_id and reply_id not in self.replies:
            return
        target = reply_id or self.reply_id
        if target == self.reply_id and target is not None:
            self.suppress_output = True
        if target:
            self.replies.pop(target, None)
        if self.reply_id == target:
            self.reply_id = None
            self.reply_text = ''
            self.reply_proposal = None
        await self.emit({'type': 'interrupted', 'reply_id': target})

    async def played(self, reply_id):
        record = self.replies.pop(reply_id, None)
        if not record or not record['complete']:
            return
        proposal = record.get('proposal')
        if proposal:
            pending = self.context().get('pending') or {}
            if (pending.get('request_id') == proposal['request_id'] and
                    pending.get('proposal_version') == proposal['proposal_version']):
                await self.tool_call('_present_audio', {**proposal, 'reply_id': reply_id})
        await self.emit({'type': 'status', 'status': 'muted' if self.muted else 'listening'})

    async def close(self):
        self.closed = True
        self.ready = False
        self.voice_epoch += 1
        self._discard_input()
        self.controls.revoke()
        self.replies.clear()
        await self.interrupt(None)

    async def _record(self, role, text, turn_id, final):
        if not text:
            return
        await self.emit({'type': 'transcript', 'role': role, 'text': text, 'turn_id': turn_id, 'final': final})
        if final:
            await self.tool_call('_record_transcript', {'role': role, 'text': text, 'turn_id': turn_id, 'final': True})

    async def state_changed(self):
        """Coalesce host events; transcript-only updates must not trigger speech loops."""
        state = compact(self.context)
        meaningful = {name: state.get(name) for name in (
            'pending', 'generation', 'task', 'active_task', 'tasks', 'observations', 'requests', 'scene',
            'skills', 'skill_decisions')}
        signature = json.dumps(meaningful, sort_keys=True, default=str)
        if signature == self.last_state_signature:
            return
        self.last_state_signature = signature
        if self.state_updates.full():
            self.state_updates.get_nowait()
        self.state_updates.put_nowait(state)

    async def _watch(self, session, cid):
        if self.watcher_id and self.watcher_id != cid:
            await session.send_tool_response(function_responses=[types.FunctionResponse(
                id=cid, name='watch_lab_events', response={'subscribed': True, 'duplicate': True},
                will_continue=False, scheduling='SILENT')])
            return
        self.watcher_id = cid
        try:
            await self.state_changed()
            while not self.closed and cid not in self.cancelled_tools:
                state = await self.state_updates.get()
                await session.send_tool_response(function_responses=[types.FunctionResponse(
                    id=cid, name='watch_lab_events', response={'state': state,
                    'instruction': 'Report meaningful new task progress, clarification, exact proposal or observed outcome. '
                                   'Do not repeat unchanged information or claim an unobserved result. '
                                   'Explicitly prefix simulated/synthetic results with "In the simulation" '
                                   'and recorded results with "In the recording". Reflection is optional.'},
                    will_continue=True, scheduling='WHEN_IDLE')])
        finally:
            if self.watcher_id == cid:
                self.watcher_id = None

    async def _tool(self, session, call):
        cid = call.id or str(uuid.uuid4())
        try:
            if cid in self.cancelled_tools:
                return
            if call.name == 'watch_lab_events':
                await self._watch(session, cid)
                return
            if cid in self.seen_tools:
                result = self.seen_tools[cid]
            else:
                try:
                    if call.name not in ALLOWED:
                        raise ValueError('Unsupported tool.')
                    await self.controls.dispatch(call.name, {**dict(call.args or {}), '_tool_call_id': cid})
                    result = compact(self.context)
                    pending = result.get('pending')
                    if pending:
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
                if response.go_away:
                    raise ConnectionError('Provider renewal')
                cancellation = response.tool_call_cancellation
                if cancellation:
                    for cid in cancellation.ids:
                        self.cancelled_tools.add(cid)
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
                        self.controls.input(transcription.text or '', finished=bool(getattr(transcription, 'finished', False)))
                        await self._record('user', self.controls.text, self.controls.turn_id, self.controls.finished.is_set())
                        if self.controls.finished.is_set():
                            try:
                                await self.controls.complete_control()
                            except Exception as exc:
                                await self.emit({'type': 'error', 'message': str(exc), 'recoverable': True})
                    audio_parts = [p.inline_data.data for p in (content.model_turn.parts if content.model_turn else []) if p.inline_data and p.inline_data.data]
                    output = content.output_transcription
                    if not self.suppress_output and (audio_parts or (output and output.text)):
                        if not self.reply_id:
                            self.reply_id = str(uuid.uuid4())
                            self.reply_text = ''
                            pending = self.context().get('pending')
                            self.reply_proposal = ({k: pending[k] for k in ('request_id', 'proposal_version')} if pending else None)
                            await self.emit({'type': 'reply_start', 'reply_id': self.reply_id, 'proposal': self.reply_proposal})
                            await self.emit({'type': 'status', 'status': 'speaking'})
                        if output and output.text:
                            self.reply_text += output.text
                            await self._record('assistant', self.reply_text, self.reply_id, False)
                        for raw in audio_parts:
                            await self.emit({'type': 'audio', 'data': base64.b64encode(raw).decode(), 'reply_id': self.reply_id})
                    if content.turn_complete:
                        self.suppress_output = False
                        self.discard_transcript = False
                    if content.turn_complete and self.reply_id:
                        rid = self.reply_id
                        await self._record('assistant', self.reply_text, rid, True)
                        pending = self.context().get('pending') or {}
                        # A readout acknowledgment is valid only if its transcript contains
                        # the exact canonical preview. Generation completion alone is not presentation.
                        def words(s):
                            return ' '.join(''.join(c.lower() if c.isalnum() else ' ' for c in s).split())
                        proposal = self.reply_proposal
                        if not pending.get('summary') or words(pending['summary']) not in words(self.reply_text):
                            proposal = None
                        self.replies[rid] = {'complete': True, 'proposal': proposal}
                        self.replies = dict(list(self.replies.items())[-16:])
                        await self.emit({'type': 'reply_end', 'reply_id': rid})
                        self.reply_id = None
                        self.reply_text = ''
                        self.reply_proposal = None
                if response.tool_call:
                    for call in response.tool_call.function_calls:
                        cid = call.id
                        if cid not in self.pending_tools and cid not in self.cancelled_tools:
                            self.pending_tools[cid] = asyncio.create_task(self._tool(session, call))
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
                tasks = []
                try:
                    await self.emit({'type': 'status', 'status': 'connecting' if attempt == 0 else 'reconnecting'})
                    config = types.LiveConnectConfig(response_modalities=['AUDIO'], system_instruction=system_prompt(self.context),
                        tools=TOOLS, input_audio_transcription={}, output_audio_transcription={},
                        session_resumption=types.SessionResumptionConfig(handle=self.resume_handle),
                        context_window_compression=types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow()))
                    async with client.aio.live.connect(model=os.getenv('GEMINI_LIVE_MODEL', 'gemini-3.8-live'), config=config) as session:
                        self.ready = True
                        await self.emit({'type': 'status', 'status': 'muted' if self.muted else 'listening'})
                        if attempt == 0:
                            # This is the student's actual Start Voice gesture, not a state update.
                            await session.send_client_content(turns=types.Content(role='user', parts=[types.Part(text='Start voice.')]), turn_complete=True)
                        tasks = [asyncio.create_task(self._upstream(session)), asyncio.create_task(self._downstream(session))]
                        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        for task in done:
                            task.result()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.last_error = type(exc).__name__
                    logging.getLogger(__name__).warning('Voice reconnect: %s at %s', self.last_error,
                        [(frame.name, frame.lineno) for frame in traceback.extract_tb(exc.__traceback__)[-4:]])
                    self.ready = False
                    self.voice_epoch += 1
                    self._discard_input()
                    self.controls.revoke()
                    self.replies.clear()
                    await self.interrupt(None)
                    await self.tool_call('stop_lab', {})
                    if attempt == 3:
                        await self.emit({'type': 'status', 'status': 'unavailable', 'message': 'Voice connection is unavailable. Continue by text or start voice again.'})
                        return
                    await self.emit({'type': 'status', 'status': 'reconnecting', 'message': 'Reconnecting voice. Your notebook is saved; review a fresh proposal before confirming.'})
                finally:
                    for task in tasks + list(self.pending_tools.values()):
                        task.cancel()
                    await asyncio.gather(*tasks, *list(self.pending_tools.values()), return_exceptions=True)
                    self.pending_tools.clear()
                await asyncio.sleep(self.reconnect_delay * (attempt + 1))
        finally:
            self.ready = False
            if self.input_boundary:
                self.input_boundary.cancel()
                await asyncio.gather(self.input_boundary, return_exceptions=True)
            await client.aio.aclose()
