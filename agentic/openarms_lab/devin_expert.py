"""Devin CLI transport (ACP over stdio); inherits the exact Codex host/image/validator loop.

Uses the person's own logged-in Devin CLI. Each call is one fresh ACP session in an empty
temporary directory, in Ask mode, with every permission request denied. Any autonomous tool
use fails closed. Identity is verified from the session's own model, thought-level and speed
settings; a mismatch is reported, never relabelled. Devin authentication stays local.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from .codex_expert import CodexExpert, ExpertUnavailable, REPLY_SCHEMA, SYSTEM, _error

SPEED_SUFFIX = {'gpt-': '-priority', 'claude-': '-fast'}
INSTRUCTIONS = ('\n\nReturn exactly one JSON object and nothing else (no prose, no code fence). '
                'It must satisfy this JSON schema:\n')


def canonical_model(model, thought, speed):
    suffix = next((v for prefix, v in SPEED_SUFFIX.items() if model.startswith(prefix)), '')
    family = re.sub(r'-(low|medium|high|xhigh|max)$', '', model)
    return f'{family}-{thought}' + (suffix if speed == 'fast' else '')


class DevinExpert(CodexExpert):
    provider = 'devin_cli_acp'
    model = 'gpt-6-1-sol-medium-priority'

    def __init__(self, *args, model='gpt-6-1-sol-medium-priority', executable='devin', **kwargs):
        super().__init__(*args, model=model, executable=executable, **kwargs)

    def describe(self):
        return super().describe() | {'authentication_method': 'local_devin_cli_login', 'credential_configured': False}

    async def _complete(self, prompt: str, images: list[Path], cancel_event):
        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError
        if not shutil.which(self.executable):
            raise ExpertUnavailable('unavailable', 'The configured expert CLI could not start.')
        requested = self._resolved.get() or getattr(self, '_pinned_model', None) or self.model
        content = [{'type': 'text', 'text': SYSTEM + '\n\n' + prompt + INSTRUCTIONS + json.dumps(REPLY_SCHEMA)}]
        for image in images:
            data = image.read_bytes()
            media = ('image/png' if data.startswith(b'\x89PNG') else
                     'image/jpeg' if data.startswith(b'\xff\xd8\xff') else 'image/webp')
            content.append({'type': 'image', 'mimeType': media, 'data': base64.b64encode(data).decode('ascii')})
        env = {key: value for key, value in os.environ.items() if key in {
            'HOME', 'USER', 'PATH', 'TMPDIR', 'LANG', 'LC_ALL', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME',
            'SSL_CERT_FILE', 'SSL_CERT_DIR', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY'}}
        with tempfile.TemporaryDirectory(prefix='devin-', dir=self.work_dir) as folder:
            try:
                process = await asyncio.create_subprocess_exec(
                    self.executable, 'acp', '--model', requested, cwd=folder, env=env,
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL, start_new_session=True, limit=8 * 1024 * 1024)
            except OSError as exc:
                raise ExpertUnavailable('unavailable', 'The configured expert CLI could not start.') from exc
            session = _Session(process)
            work = asyncio.create_task(session.converse(folder, content))
            cancelled = asyncio.create_task(cancel_event.wait()) if cancel_event else None
            try:
                done, _ = await asyncio.wait([work] + ([cancelled] if cancelled else []),
                                             timeout=self.call_timeout, return_when=asyncio.FIRST_COMPLETED)
                if cancelled and cancelled in done:
                    raise asyncio.CancelledError
                if work not in done:
                    raise ExpertUnavailable('timeout', 'The expert did not respond before the deadline.')
                text, usage, config = work.result()
            finally:
                for pending in (work, cancelled):
                    if pending and not pending.done():
                        pending.cancel()
                await asyncio.gather(*[t for t in (work, cancelled) if t], return_exceptions=True)
                await self._kill(process)
        text = re.sub(r'^\s*```(?:json)?\s*|\s*```\s*$', '', text)
        if len(text) > 64_000:
            raise ExpertUnavailable('invalid_response', 'The expert decision exceeded its size budget.')
        actual = None
        if config.get('model') and config.get('thought_level') and config.get('speed'):
            actual = canonical_model(config['model'], config['thought_level'], config['speed'])
        return {'raw': text, 'usage': usage, 'actual_model': actual}


class _Session:
    def __init__(self, process):
        self.process, self.next_id = process, 0

    async def send(self, message):
        self.process.stdin.write((json.dumps(message) + '\n').encode())
        await self.process.stdin.drain()

    async def request(self, method, params, on_update=None):
        self.next_id += 1
        mid = self.next_id
        await self.send({'jsonrpc': '2.0', 'id': mid, 'method': method, 'params': params})
        while True:
            line = await self.process.stdout.readline()
            if not line:
                raise _error('Devin expert session ended unexpectedly.')
            try:
                message = json.loads(line)
            except ValueError as exc:
                raise ExpertUnavailable('invalid_response', 'Invalid expert stream.') from exc
            if not isinstance(message, dict):
                raise ExpertUnavailable('invalid_response', 'Invalid expert telemetry.')
            if 'method' in message and 'id' in message:
                await self.send({'jsonrpc': '2.0', 'id': message['id'],
                                 'error': {'code': -32601, 'message': 'Denied by the OpenArms host.'}})
                raise ExpertUnavailable('isolation', 'Expert requested an action outside the host catalog.')
            if message.get('id') == mid:
                if 'error' in message:
                    raise _error(json.dumps(message['error'])[:500])
                return message.get('result') or {}
            if on_update and 'method' in message:
                on_update(message)

    async def converse(self, folder, content):
        await self.request('initialize', {'protocolVersion': 1, 'clientCapabilities': {
            'fs': {'readTextFile': False, 'writeTextFile': False}, 'terminal': False}})
        created = await self.request('session/new', {'cwd': folder, 'mcpServers': []})
        sid = created.get('sessionId')
        if not isinstance(sid, str):
            raise ExpertUnavailable('invalid_response', 'Invalid expert session.')
        config = {o.get('id'): o.get('currentValue') for o in created.get('configOptions', []) if isinstance(o, dict)}
        if 'mode' in config:
            await self.request('session/set_config_option', {'sessionId': sid, 'configId': 'mode', 'value': 'ask'})
        chunks = []

        def on_update(message):
            update = (message.get('params') or {}).get('update') or {}
            kind = update.get('sessionUpdate')
            if kind in ('tool_call', 'tool_call_update'):
                raise ExpertUnavailable('isolation', 'Expert CLI attempted autonomous tool use.')
            if kind == 'agent_message_chunk' and (update.get('content') or {}).get('type') == 'text':
                chunks.append(update['content']['text'])

        result = await self.request('session/prompt', {'sessionId': sid, 'prompt': content}, on_update)
        if result.get('stopReason') != 'end_turn':
            raise _error('Devin expert stopped before completing its reply.')
        raw = result.get('usage') or {}
        usage = {name: raw[key] for key, name in (('inputTokens', 'input_tokens'), ('outputTokens', 'output_tokens'),
                                                  ('cachedReadTokens', 'cached_input_tokens'))
                 if isinstance(raw.get(key), int) and not isinstance(raw.get(key), bool)}
        return ''.join(chunks), usage, config
