"""Consent is a completed student input, bound at utterance start to a presentation."""
from __future__ import annotations
import asyncio
import re
import time
import uuid

MUTATING_TOOLS = {'request_action', 'improve_skill', 'choose_condition', 'record_prediction', 'record_reflection',
                  'prepare_next_trial', 'student_confirm', 'cancel_request'}
CONFIRMATIONS = {'yes', 'yes please', 'confirm', 'yes confirm', 'yes i confirm', 'i confirm',
                 'confirm it', 'confirm the request', 'confirm this request', 'confirm that request',
                 'go ahead', 'yes go ahead'}
CANCELLATIONS = {'cancel', 'cancel it', 'cancel the trial', 'cancel the request', 'never mind', 'nevermind'}
STOPS = {'stop', 'stop now', 'emergency stop'}


def normalized(text):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', '', text.lower())).strip()


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
        self.started = 0
        self.text = ''
        self.last_confirmation = None

    async def complete_control(self):
        """Act on exact controls without waiting for a model to choose a tool."""
        if not self.finished.is_set() or self.consumed:
            return None
        text = normalized(self.text)
        if text in STOPS:
            self.consumed = True
            return await self.callback('stop_lab', {})
        if text in CANCELLATIONS:
            self.consumed = True
            return await self.callback('cancel_request', {'request_id': self.request_id})
        if text in CONFIRMATIONS:
            return await self.dispatch('student_confirm', {'request_id': self.request_id, 'proposal_version': self.proposal_version})
        return None

    async def dispatch(self, name, arguments):
        args = {k: v for k, v in arguments.items() if not k.startswith('_')}
        if name == 'student_confirm':
            await asyncio.wait_for(self.finished.wait(), timeout=4)
            snap = self.context()
            pending = snap.get('pending') or {}
            rid = args.get('request_id')
            version = args.get('proposal_version')
            # A tool may follow the deterministic completed-input handler; report the result,
            # never execute a second time. A different turn cannot reuse this receipt.
            if self.last_confirmation == (self.turn_id, rid, version):
                return snap
            if (self.consumed or time.monotonic() - self.started > 30 or
                    isinstance(version, bool) or
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
            args['_voice_consent'] = {'request_id': rid, 'proposal_version': version,
                                      'text': self.text, 'turn_id': self.turn_id}
            result = await self.callback(name, args)
            self.last_confirmation = (self.turn_id, rid, version)
            return result
        if name in MUTATING_TOOLS:
            await asyncio.wait_for(self.finished.wait(), timeout=4)
            if not self.text.strip():
                raise ValueError('Wait for a completed student turn.')
            if self.generation != self.context().get('generation', 0):
                raise ValueError('This input was revoked. Please give a new instruction.')
            if normalized(self.text) in CONFIRMATIONS | CANCELLATIONS | STOPS:
                # Model interpretation cannot turn control speech into another operation.
                if name == 'cancel_request' and normalized(self.text) in CANCELLATIONS:
                    return self.context()
                raise ValueError('That control cannot create or change a trial.')
            self.consumed = True
            args['_voice_generation'] = self.generation
            args['_voice_turn_id'] = self.turn_id
            if arguments.get('_tool_call_id'):
                args['_tool_call_id'] = arguments['_tool_call_id']
        return await self.callback(name, args)
