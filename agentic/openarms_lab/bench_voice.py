"""Gemini Live voice for the Real bench panel.

Separate from live.py (the session voice guide), which stays as it is. Gemini only listens and talks:
what the student asks for goes to the same BenchLane.request() the text box uses, so Claude still plans,
the simulation still previews, and the real arm still needs Execute and the operator's Yes in the panel.

Safety rules kept in code, not in the prompt:
- "stop" heard in the student's speech stops the arm at once, before Gemini answers.
- Voice can run a simulated plan ("execute") only when an operator question follows on the real arm
  (OPENARMS_BENCH_CONFIRM panel or terminal), and only when the student's own words said it.
- The operator's Yes / No question can be answered aloud, in code and not by the model: only when the student's whole
  finished utterance is a plain yes (or no), the question has been open for a moment and Gemini is not speaking, so
  its own voice or a stray word cannot answer it. The Yes button still works.
- "stop the voice" ends the voice session without stopping the arm (unless the arm is working, then it stops too).
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import os
import re
import time

from .bench_lane import EXECUTE_WORDS, BenchError

NEGATION = re.compile(r"\b(?:don ?t|do not|dont|not|never|no|wait|cancel)\b", re.I)
STOP_WORDS = re.compile(r"\b(?:stop|halt|freeze)\b", re.I)
STOP_VOICE = re.compile(r"\b(?:stop|end|turn off|switch off|quit)\s+(?:the\s+|this\s+)?(?:voice|listening|microphone|mic)\b|\bvoice off\b", re.I)
YES_PHRASES = {'yes', 'yes please', 'yeah', 'yep', 'confirm', 'go ahead', 'yes go ahead', 'yes confirm', 'yes do it', 'do it', 'yes it is', 'yes it is held', 'yes the arm is at home', 'yes the path is clear', 'yes its clear', 'yes it is clear'}
NO_PHRASES = {'no', 'nope', 'no thanks', 'no dont', 'dont', 'do not', 'no do not', 'cancel', 'not yet'}
QUESTION_SETTLE_S = 1.5
TURN_SILENCE_S = 0.8  # a transcript that stops growing this long is a finished sentence, whether or not Gemini marks it so
MAX_AUDIO_BYTES = 6400  # 200 ms of 16 kHz mono PCM16


def key():
    return os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')


def model():
    return os.getenv('GEMINI_LIVE_MODEL', 'gemini-3.8-live')


def _decl(name, description, properties=None, required=None, nonblocking=False):
    d = {'name': name, 'description': description,
         'parameters': {'type': 'OBJECT', 'properties': properties or {}, 'required': required or []}}
    if nonblocking:
        d['behavior'] = 'NON_BLOCKING'
    return d


TOOLS = [{'function_declarations': [
    _decl('bench_request', 'Send what the student asked the arm to do, quoted verbatim from their words: a new action, a '
          'correction, or their own "execute" / "go ahead" to run the simulated plan. Updates arrive while it works.',
          {'text': {'type': 'STRING'}}, ['text'], nonblocking=True),
    _decl('bench_look', 'Take a fresh look with the overhead camera and read where the containers stand.', nonblocking=True),
    _decl('bench_state', 'Read the bench now: what it is doing, the plan waiting, the simulation result, the last result.'),
    _decl('bench_cancel', 'Cancel the simulated plan that is waiting. Nothing moves.'),
    _decl('bench_stop', 'Stop the arm at once. Use whenever the student asks to stop.'),
]}]
ALLOWED = {d['name'] for d in TOOLS[0]['function_declarations']}

SYSTEM = """You are the voice of a robot-arm lab bench. Speak to the student in one or two short sentences.
You do not plan or move anything yourself. When the student asks the arm to do something, call bench_request with \
their words exactly. A planner then decides, a simulation plays it first, and the student sees it on screen. \
Read out what the bench says in plain words; do not invent results, positions or colours.
The real arm moves only after Execute and after the bench operator presses Yes in the panel. When the bench is waiting \
for the operator, read the question and ask them to say yes or no, or press Yes or No on the screen. The bench \
hears their yes or no itself: never call a tool for it and never say yes for them.
If the student says stop, call bench_stop immediately. If they ask where things are, call bench_look or bench_state.
Say "in the simulation" for simulated results. If a request fails, say why in one sentence and suggest one thing to try.
At the start, greet the student in one sentence and say they can ask the arm to pour the beaker into the dish."""


def bench_brief(s, since=0):
    """What Gemini is told about the bench: short, and nothing from files or keys."""
    p = s.get('pending') or {}
    pv = p.get('preview') or {}
    return {
        'arm': s.get('arm'), 'armed': s.get('armed'), 'busy': s.get('busy'),
        'camera': (s.get('camera') or {}).get('text'),
        'plan': p.get('summary'), 'simulation': pv.get('status'), 'simulation_problems': (pv.get('blocks') or [])[:3],
        'simulation_problem_is_only_a_warning': bool(p.get('sim_block_overridden')),
        'can_execute': bool(p) and p.get('executable') is not False and (pv.get('status') == 'ready' or bool(p.get('sim_block_overridden'))),
        'waiting_for_operator_yes': (s.get('question') or {}).get('text'),
        'last_result': (s.get('last_result') or {}).get('text'),
        'bench_said': [m['text'] for m in (s.get('log') or [])[since:] if m.get('role') == 'assistant'][-4:],
    }


class BenchVoice:
    def __init__(self, bench, emit, *, client_factory=None):
        self.bench, self.emit, self.client_factory = bench, emit, client_factory
        self.incoming: asyncio.Queue = asyncio.Queue(maxsize=40)
        self.heard = ''  # the student's current turn, as transcribed
        self.last_turn = ''  # the student's last finished turn
        self.tasks: set = set()
        self.closed = False
        self.speaking = False  # Gemini is talking: its voice must not be mistaken for the student's answer
        self.question_seen: dict = {}
        self.heard_at = 0.0

    # ---- from the browser --------------------------------------------------------------
    async def audio(self, encoded):
        raw = base64.b64decode(encoded, validate=True)
        if not raw or len(raw) > MAX_AUDIO_BYTES or len(raw) % 2:
            raise ValueError('Audio frames must be at most 200 ms of 16 kHz mono PCM.')
        if self.incoming.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self.incoming.get_nowait()  # drop the oldest rather than queue a stale backlog
        self.incoming.put_nowait(raw)

    async def close(self):
        self.closed = True
        for t in list(self.tasks):
            t.cancel()

    # ---- the student's words -----------------------------------------------------------
    @staticmethod
    def _plain(text):
        return ' '.join(''.join(c for c in text.lower().replace("'", '') if c.isalpha() or c == ' ').split())

    async def _watch_question(self):
        while not self.closed:
            if self.heard.strip() and time.monotonic() - self.heard_at > TURN_SILENCE_S:
                await self._finish_turn()
            q = (self.bench.state().get('question') or {}).get('id')
            self.question_seen = {q: self.question_seen.get(q, time.monotonic())} if q else {}
            await asyncio.sleep(0.2)

    async def _spoken_answer(self, utterance):
        """Answers the operator's open question when the student's whole utterance is a plain yes or no."""
        word = self._plain(utterance)
        yes = word in YES_PHRASES
        if not yes and word not in NO_PHRASES:
            return False
        q = (self.bench.state().get('question') or {}).get('id')
        if not q:
            return False
        if self.speaking or time.monotonic() - self.question_seen.get(q, time.monotonic()) < QUESTION_SETTLE_S:
            await self.emit({'type': 'status', 'status': 'listening', 'message': 'Wait until Ollie has finished asking, then say yes or no.'})
            return True
        try:
            self.bench.answer(q, yes)
        except BenchError:
            return True
        await self.emit({'type': 'status', 'status': 'answered', 'message': 'Heard "yes".' if yes else 'Heard "no": nothing will move.'})
        return True

    async def _finish_turn(self):
        self.last_turn, self.heard = self.heard.strip(), ''
        await self._spoken_answer(self.last_turn)

    async def _heard(self, text, finished):
        self.heard += text or ''
        self.heard_at = time.monotonic()
        if STOP_VOICE.search(self.heard):
            if self.bench.state().get('busy') or (self.bench.state().get('question') or {}).get('id'):
                await self.bench.stop()
            self.heard = ''
            await self.emit({'type': 'status', 'status': 'ended', 'message': 'Heard "stop the voice": voice is off.'})
            await self.close()
            return
        if STOP_WORDS.search(self.heard):
            self.heard = ''
            await self.bench.stop()  # before Gemini answers: the words alone are enough
            await self.emit({'type': 'status', 'status': 'stopped', 'message': 'Heard "stop": the arm was stopped.'})
        if self.heard.strip():
            await self.emit({'type': 'transcript', 'role': 'user', 'text': self.heard.strip(), 'final': finished})
        if finished:
            await self._finish_turn()

    def _said_execute(self, text):
        word = ''.join(c for c in text.lower() if c.isalpha() or c == ' ').strip()
        if word not in EXECUTE_WORDS:
            return None
        if self.bench.real_arm and not self.bench.terminal_confirm:
            return ('On this server no operator question follows Execute, so voice cannot start the real arm. '
                    'Press Execute on the screen.')
        student = ' '.join(''.join(c for c in (self.last_turn + ' ' + self.heard).lower() if c.isalpha() or c == ' ').split())
        if not any(re.search(rf'\b{re.escape(w)}\b', student) for w in EXECUTE_WORDS):
            return 'Only the student saying execute (or go ahead) runs the plan. Ask them.'
        if NEGATION.search(student):
            return 'The student said not to, or it was unclear. Ask them plainly whether to execute.'
        return ''

    # ---- tools ---------------------------------------------------------------------------
    async def _tool(self, session, call):
        from google.genai import types

        async def reply(response, more=False, when='WHEN_IDLE'):
            await session.send_tool_response(function_responses=[types.FunctionResponse(
                id=call.id, name=call.name, response=response, will_continue=more, scheduling=when)])

        args = dict(call.args or {})
        since = len(self.bench.state().get('log') or [])
        try:
            if call.name not in ALLOWED:
                raise BenchError('Unsupported tool.')
            if call.name == 'bench_stop':
                await self.bench.stop()
                return await reply({'result': bench_brief(self.bench.state(), since)}, when='INTERRUPT')
            if call.name == 'bench_state':
                return await reply({'result': bench_brief(self.bench.state())})
            if call.name == 'bench_cancel':
                return await reply({'result': bench_brief(await self.bench.cancel(), since)})
            if call.name == 'bench_look':
                return await reply({'result': bench_brief(await self.bench.look_all(), since)})
            text = str(args.get('text') or '').strip()
            if (self.bench.state().get('question') or {}).get('id') and self._plain(text) in YES_PHRASES | NO_PHRASES:
                return await reply({'result': bench_brief(self.bench.state(), since)})  # the bench answers the question itself
            refused = self._said_execute(text)
            if refused:
                return await reply({'error': refused, 'result': bench_brief(self.bench.state())})
            work = asyncio.ensure_future(self.bench.request(text))
            told, asked = since, None
            while not work.done():  # tell Gemini what the bench says while it works, and when the operator is asked
                await asyncio.sleep(0.5)
                s = self.bench.state()
                q = (s.get('question') or {}).get('id')
                n = len(s.get('log') or [])
                if n > told or (q and q != asked):
                    await reply({'update': bench_brief(s, told)}, more=True)
                    told, asked = n, q or asked
            await reply({'result': bench_brief(work.result(), since)})  # the whole answer, so nothing hinges on an update
        except BenchError as exc:
            await reply({'error': str(exc), 'result': bench_brief(self.bench.state(), since)})
        except Exception as exc:  # noqa: BLE001 - told to Gemini, not raised into the socket
            logging.getLogger(__name__).warning('bench voice tool %s: %s', call.name, exc)
            await reply({'error': f'{type(exc).__name__}', 'result': bench_brief(self.bench.state(), since)})

    # ---- the Gemini Live session --------------------------------------------------------
    async def run(self):
        if not key() and not self.client_factory:
            await self.emit({'type': 'status', 'status': 'unavailable',
                             'message': 'Voice needs GEMINI_API_KEY in agentic/.env. Typing still works.'})
            return
        from google import genai
        from google.genai import types
        client = self.client_factory() if self.client_factory else genai.Client(api_key=key(), http_options={'api_version': 'v1beta'})
        config = types.LiveConnectConfig(response_modalities=['AUDIO'], system_instruction=SYSTEM, tools=TOOLS,
                                         input_audio_transcription={}, output_audio_transcription={})
        try:
            await self.emit({'type': 'status', 'status': 'connecting', 'model': model()})
            async with client.aio.live.connect(model=model(), config=config) as session:
                await self.emit({'type': 'status', 'status': 'listening', 'model': model()})
                await session.send_client_content(turns=types.Content(role='user', parts=[types.Part(text='Start voice.')]),
                                                  turn_complete=True)
                up = asyncio.create_task(self._upstream(session))
                watch = asyncio.create_task(self._watch_question())
                self.tasks.update((up, watch))
                try:
                    await self._downstream(session)
                finally:
                    up.cancel()
                    watch.cancel()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning('bench voice ended: %s', exc)
            await self.emit({'type': 'status', 'status': 'unavailable', 'message': f'Voice stopped ({type(exc).__name__}). Typing still works.'})
        finally:
            for t in list(self.tasks):
                t.cancel()
            with contextlib.suppress(Exception):
                await client.aio.aclose()

    async def _upstream(self, session):
        from google.genai import types
        while True:
            raw = await self.incoming.get()
            await session.send_realtime_input(audio=types.Blob(data=raw, mime_type='audio/pcm;rate=16000'))

    async def _downstream(self, session):
        said = ''
        while not self.closed:
            async for response in session.receive():
                content = response.server_content
                if content:
                    if content.interrupted:
                        self.speaking = False
                        await self.emit({'type': 'interrupted'})
                    heard = content.input_transcription
                    if heard:
                        await self._heard(heard.text, bool(getattr(heard, 'finished', False)))
                    for part in (content.model_turn.parts if content.model_turn else []):
                        if part.inline_data and part.inline_data.data:
                            self.speaking = True
                            await self.emit({'type': 'audio', 'data': base64.b64encode(part.inline_data.data).decode()})
                    out = content.output_transcription
                    if out and out.text:
                        said += out.text
                        await self.emit({'type': 'transcript', 'role': 'assistant', 'text': said, 'final': False})
                    if content.turn_complete:
                        self.speaking = False
                    if content.turn_complete and said:
                        await self.emit({'type': 'transcript', 'role': 'assistant', 'text': said, 'final': True})
                        said = ''
                if response.tool_call:
                    for call in response.tool_call.function_calls:
                        t = asyncio.create_task(self._tool(session, call))
                        self.tasks.add(t)
                        t.add_done_callback(self.tasks.discard)
            await asyncio.sleep(0)
