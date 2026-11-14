"""Student voice controls. Consent comes from input transcription, never model arguments."""
from __future__ import annotations
import asyncio
import re
import time

MUTATING_TOOLS = {'request_action', 'record_prediction', 'answer_question',
                  'select_experiment', 'prepare_next_trial', 'student_confirm', 'cancel_request'}
CONFIRMATIONS = {'yes', 'yes please', 'confirm', 'yes confirm', 'yes i confirm',
                 'confirm it', 'confirm the request', 'confirm this request', 'confirm that request'}


def normalized(text):
    return re.sub(r'[^a-z0-9 ]', '', text.lower()).strip()


class VoiceControls:
    """One connection/turn's trusted input; no reusable consent survives a state change."""
    def __init__(self, context, callback):
        self.context, self.callback = context, callback
        self.text = ''
        self.request_id = None
        self.generation = context().get('generation', 0)
        self.finished = asyncio.Event()
        self.started = 0
        self.consumed = True

    def input(self, text, *, finished=False):
        if self.finished.is_set() or not self.started:
            snap = self.context()
            self.text = ''
            self.request_id = (snap.get('pending') or {}).get('request_id')
            self.generation = snap.get('generation', 0)
            self.finished.clear()
            self.started = time.monotonic()
            self.consumed = False
        self.text = (self.text + text)[-4000:]
        if finished:
            self.finished.set()

    async def dispatch(self, name, arguments):
        # Provider arguments can never supply trusted internal fields.
        args = {k: v for k, v in arguments.items() if not k.startswith('_')}
        if name in MUTATING_TOOLS:
            args['_voice_generation'] = self.generation
        if name == 'student_confirm':
            try:
                await asyncio.wait_for(self.finished.wait(), timeout=3)
            except TimeoutError:
                raise ValueError('Wait for a complete student confirmation. Say "confirm" after reviewing the proposal.') from None
            snap = self.context()
            request_id = args.get('request_id')
            if (self.consumed or time.monotonic() - self.started > 20 or
                    normalized(self.text) not in CONFIRMATIONS or
                    not request_id or request_id != self.request_id or
                    request_id != (snap.get('pending') or {}).get('request_id') or
                    self.generation != snap.get('generation', 0)):
                raise ValueError('Confirmation requires a fresh explicit student yes/confirm for this exact current proposal.')
            self.consumed = True
            args['_voice_consent'] = {'request_id': request_id, 'text': self.text}
        elif name in MUTATING_TOOLS:
            # A correction/prediction/reset cannot carry consent into a new proposal.
            self.consumed = True
        if name == 'request_action' and arguments.get('_tool_call_id'):
            args['_tool_call_id'] = arguments['_tool_call_id']
        return await self.callback(name, args)
