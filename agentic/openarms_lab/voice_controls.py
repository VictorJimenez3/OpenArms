"""Consent is a completed student input, bound at utterance start to a presentation."""
from __future__ import annotations
import asyncio
import re
import time
import uuid

from .conversation import STOP_PHRASES, condition_input, prediction_input, read_only_turn, reset_input

TASK_TEXT = {'request_action': 'text', 'start_task': 'text', 'improve_skill': 'limitation'}
MUTATING_TOOLS = {*TASK_TEXT, 'choose_condition', 'record_prediction', 'record_reflection',
                  'prepare_next_trial', 'student_confirm', 'cancel_request', 'stop_lab'}
CONFIRMATIONS = {'yes', 'yes please', 'confirm', 'yes confirm', 'yes i confirm', 'i confirm',
                 'confirm it', 'confirm the request', 'confirm this request', 'confirm that request',
                 'go ahead', 'yes go ahead'}
CANCELLATIONS = {'cancel', 'cancel it', 'cancel the trial', 'cancel the request', 'cancel the proposal',
                 'never mind', 'nevermind'}
STOPS = STOP_PHRASES


def normalized(text):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', '', text.lower())).strip()


def quoted_words(text):
    # Ignore transcription casing, outer punctuation, and whitespace, but keep
    # all words and internal punctuation (including decimal points).
    return ' '.join(text.strip().rstrip('.!?').casefold().split())


class VoiceControls:
    def __init__(self, context, callback, can_confirm=lambda: True):
        self.context, self.callback = context, callback
        self.can_confirm = can_confirm
        self.text = ''
        self.turn_id = str(uuid.uuid4())
        self.finished = asyncio.Event()
        self.started = 0.0
        self.consumed = True
        self.request_id = self.proposal_version = None
        self.generation = context().get('generation', 0)
        self.presented = False
        self.last_confirmation = None
        self.confirmation_lock = asyncio.Lock()

    def begin_input(self):
        if self.finished.is_set() or not self.started:
            snap = self.context()
            pending = snap.get('pending') or {}
            self.text = ''
            self.turn_id = str(uuid.uuid4())
            self.request_id = pending.get('request_id')
            self.proposal_version = pending.get('proposal_version')
            self.presented = bool(pending.get('presented')) and self.can_confirm()
            self.generation = snap.get('generation', 0)
            self.finished.clear()
            self.started = time.monotonic()
            self.consumed = False
            self.last_confirmation = None

    def input(self, text, *, finished=False):
        if not text and finished and self.finished.is_set():
            return
        self.begin_input()
        self.text = (self.text + text)[-4000:]
        if finished:
            self.finished.set()

    def revoke(self):
        self.consumed = True
        self.finished.clear()
        self.turn_id = str(uuid.uuid4())
        self.started = 0
        self.text = ''
        self.last_confirmation = None

    def completed_control(self):
        if not self.finished.is_set() or not re.fullmatch(r'[a-zA-Z ,.!]+', self.text.strip()):
            return None
        norm = normalized(self.text)
        if norm in STOPS:
            return 'stop_lab'
        if norm in CANCELLATIONS:
            return 'cancel_request'
        if norm in CONFIRMATIONS:
            return 'student_confirm'
        return None

    async def complete_control(self):
        """Act on exact controls without waiting for a model to choose a tool."""
        if self.consumed:
            return None
        control = self.completed_control()
        if control == 'stop_lab':
            self.consumed = True
            return await self.callback(control, {})
        if control == 'cancel_request':
            self.consumed = True
            return await self.callback(control, {'request_id': self.request_id})
        if control == 'student_confirm':
            return await self.dispatch(control, {'request_id': self.request_id, 'proposal_version': self.proposal_version})
        return None

    async def dispatch(self, name, arguments, *, turn_id=None):
        args = {k: v for k, v in arguments.items() if not k.startswith('_')}
        if name in MUTATING_TOOLS:
            bound_turn = turn_id if turn_id is not None else self.turn_id
            if bound_turn != self.turn_id or not self.started:
                raise ValueError('Wait for a completed student turn.')
            await asyncio.wait_for(self.finished.wait(), timeout=4)
            if bound_turn != self.turn_id or not self.finished.is_set():
                raise ValueError('This input was revoked. Please give a new instruction.')
        if name == 'student_confirm':
            async with self.confirmation_lock:
                if bound_turn != self.turn_id or not self.finished.is_set():
                    raise ValueError('This input was revoked. Please give a new instruction.')
                return await self._confirm(args)
        if name in MUTATING_TOOLS:
            if not self.text.strip():
                raise ValueError('Wait for a completed student turn.')
            if name in ('cancel_request', 'stop_lab'):
                if self.completed_control() != name:
                    raise ValueError('A completed student stop or cancel instruction is required.')
                # The deterministic handler owns these controls.
                return self.context()
            if self.generation != self.context().get('generation', 0) or time.monotonic() - self.started > 30:
                raise ValueError('This input was revoked. Please give a new instruction.')
            if normalized(self.text) in CONFIRMATIONS | CANCELLATIONS | STOPS:
                # Model interpretation cannot turn control speech into another operation.
                raise ValueError('That control cannot create or change a trial.')
            if self.consumed:
                raise ValueError('This student turn already used its mutation. Wait for a new instruction.')
            if read_only_turn(self.text):
                raise ValueError('Answer this conversational turn without changing the trial.')
            if name == 'choose_condition' and condition_input(self.text) != args.get('condition_id'):
                raise ValueError('Use the student’s stated sample choice.')
            if name == 'prepare_next_trial' and not reset_input(self.text):
                raise ValueError('Wait for the student to request a fresh trial.')
            if name == 'record_prediction' and not prediction_input(self.text):
                raise ValueError('Wait for a student prediction.')
            field = TASK_TEXT.get(name)
            if name in ('record_prediction', 'record_reflection'):
                field = 'text'
            if field:
                supplied = args.get(field)
                if not isinstance(supplied, str) or quoted_words(supplied) != quoted_words(self.text):
                    raise ValueError('Use the completed student request verbatim.')
                args[field] = self.text.strip()
            applied = (self.context().get('dedupe') or {}).get('voice:' + self.turn_id, {})
            if applied.get('mutation'):
                if name != applied['mutation'] and not (name == 'request_action' and applied['mutation'] == 'choose_condition'):
                    raise ValueError('This student turn already used its mutation. Wait for a new instruction.')
                self.consumed = True
                return self.context()
            # Claim before awaiting the callback, including if it fails after dispatch.
            self.consumed = True
            args['_voice_generation'] = self.generation
            args['_voice_turn_id'] = self.turn_id
            if arguments.get('_tool_call_id'):
                args['_tool_call_id'] = arguments['_tool_call_id']
        return await self.callback(name, args)

    async def _confirm(self, args):
        snap = self.context()
        pending = snap.get('pending') or {}
        rid = args.get('request_id')
        version = args.get('proposal_version')
        # A tool may follow the deterministic completed-input handler; report the result,
        # never execute a second time. A different turn cannot reuse this receipt.
        if not isinstance(version, bool) and self.last_confirmation == (self.turn_id, rid, version):
            return snap
        if (self.consumed or time.monotonic() - self.started > 30 or
                isinstance(version, bool) or
                not re.fullmatch(r'[a-zA-Z ,.!]+', self.text.strip()) or
                normalized(self.text) not in CONFIRMATIONS or not self.presented or
                not rid or rid != self.request_id or rid != pending.get('request_id') or
                version != self.proposal_version or version != pending.get('proposal_version') or
                self.generation != snap.get('generation', 0)):
            raise ValueError('Review the current proposal, then say confirm in a new turn.')
        self.consumed = True
        # Gemini function arguments travel through a protobuf Struct, where
        # integral numbers may arrive as floats. Use the already matched,
        # server-owned version; never forward a provider numeric coercion.
        args['proposal_version'] = self.proposal_version
        turn_id = self.turn_id
        args['_voice_consent'] = {'request_id': rid, 'proposal_version': self.proposal_version,
                                  'text': self.text, 'turn_id': self.turn_id}
        result = await self.callback('student_confirm', args)
        if self.turn_id == turn_id:
            self.last_confirmation = (turn_id, rid, version)
        return result
