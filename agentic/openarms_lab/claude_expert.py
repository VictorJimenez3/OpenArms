"""Claude Code print transport; inherits the exact Codex host/image/validator loop.

Bare mode deliberately requires independent ANTHROPIC_API_KEY authentication.
No Codex environment or credentials are passed to Claude. See EXPERT_MODELS.md.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
from pathlib import Path

from .codex_expert import CodexExpert, ExpertUnavailable, REPLY_SCHEMA, SYSTEM, _error


class ClaudeExpert(CodexExpert):
    provider = 'anthropic_claude_cli'
    model = 'sonnet'

    def __init__(self, *args, model='sonnet', executable='claude', **kwargs):
        super().__init__(*args, model=model, executable=executable, **kwargs)

    def describe(self):
        return super().describe() | {'authentication_method': 'independent_anthropic_api_key',
                                    'credential_configured': bool(os.environ.get('ANTHROPIC_API_KEY'))}

    async def _complete(self, prompt: str, images: list[Path], cancel_event):
        if not shutil.which(self.executable):
            raise ExpertUnavailable('unavailable', 'The configured expert CLI could not start.')
        if not os.environ.get('ANTHROPIC_API_KEY'):
            raise ExpertUnavailable('authentication', 'The expert needs independent Anthropic API authentication for isolated bare mode.')
        content = [{'type': 'text', 'text': prompt}]
        for image in images:
            data = image.read_bytes()
            media = ('image/png' if data.startswith(b'\x89PNG') else
                     'image/jpeg' if data.startswith(b'\xff\xd8\xff') else 'image/webp')
            content.append({'type': 'image', 'source': {'type': 'base64', 'media_type': media,
                                                       'data': base64.b64encode(data).decode('ascii')}})
        message = {'type': 'user', 'message': {'role': 'user', 'content': content},
                   'parent_tool_use_id': None}
        env = {key: value for key, value in os.environ.items() if key in {
            'HOME', 'PATH', 'TMPDIR', 'LANG', 'LC_ALL', 'ANTHROPIC_API_KEY',
            'SSL_CERT_FILE', 'SSL_CERT_DIR', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY'}}
        with tempfile.TemporaryDirectory(prefix='claude-', dir=self.work_dir) as folder:
            command = [self.executable, '--bare', '--print', '--verbose',
                       '--input-format', 'stream-json', '--output-format', 'stream-json',
                       '--json-schema', json.dumps(REPLY_SCHEMA), '--tools', '',
                       '--disallowedTools', '*', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                       '--setting-sources', '', '--settings', '{"disableAllHooks":true}',
                       '--disable-slash-commands', '--no-chrome', '--no-session-persistence',
                       '--permission-mode', 'dontAsk', '--max-turns', '3',
                       '--model', self._resolved.get() or getattr(self, '_pinned_model', None) or self.model,
                       '--effort', self.reasoning_effort, '--system-prompt', SYSTEM]
            stdout, stderr, returncode = await self._invoke(
                command, (json.dumps(message)+'\n').encode(), cancel_event, cwd=folder, env=env)
        final, models = None, set()
        for line in stdout.decode(errors='replace').splitlines():
            try:
                event = json.loads(line)
            except ValueError as exc:
                raise ExpertUnavailable('invalid_response', 'Invalid expert stream.') from exc
            if not isinstance(event, dict):
                raise ExpertUnavailable('invalid_response', 'Invalid expert telemetry.')
            if event.get('type') == 'system' and event.get('subtype') == 'init':
                # A CLI that ignores isolation flags is not a compatible transport.
                if event.get('tools') or event.get('mcp_servers'):
                    raise ExpertUnavailable('isolation', 'Expert CLI did not disable autonomous tools.')
            if event.get('type') == 'assistant':
                message = event.get('message', {})
                if message.get('model'):
                    models.add(message['model'])
                for block in message.get('content', []):
                    if block.get('type') in ('tool_use', 'server_tool_use'):
                        # StructuredOutput is CLI schema formatting, never a host action.
                        if block.get('name') != 'StructuredOutput':
                            raise ExpertUnavailable('invalid_response', 'Expert attempted a tool outside the host catalog.')
            if event.get('type') == 'result':
                if final is not None:
                    raise ExpertUnavailable('invalid_response', 'Duplicate expert result.')
                final = event
        if returncode or not final or final.get('is_error') or final.get('subtype') != 'success':
            raise _error(stderr.decode(errors='replace') + json.dumps(final or {}))
        if final.get('permission_denials'):
            raise ExpertUnavailable('isolation', 'Expert attempted an autonomous tool.')
        model_usage = final.get('modelUsage', {})
        if isinstance(model_usage, dict):
            models.update(model_usage)
        if len(models) > 1:
            raise ExpertUnavailable('model_changed', 'Expert used multiple models; automatic substitution is unsupported.')
        value = final.get('structured_output')
        if not isinstance(value, dict):
            raise ExpertUnavailable('invalid_response', 'Expert CLI did not return structured JSON; text-only fallback is disabled.')
        return {'raw': json.dumps(value), 'usage': final.get('usage', {}),
                'actual_model': next(iter(models), None)}
