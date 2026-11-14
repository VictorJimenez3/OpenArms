"""Host-owned expert selection. No HTTP API; immutable task snapshots survive swaps."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .codex_expert import CodexExpert, ExpertUnavailable
from .claude_expert import ClaudeExpert

PROFILES = {'sol': ('codex', 'gpt-6.1-sol'), 'astra': ('codex', 'gpt-6-astra'),
            'opus': ('claude', 'opus'), 'sonnet': ('claude', 'sonnet')}


@dataclass(frozen=True)
class ExpertProfile:
    profile: str
    provider: str
    model: str
    reasoning_effort: str = 'medium'

    def describe(self):
        return dict(profile=self.profile, provider=self.provider, requested_model=self.model,
                    model=self.model, reasoning_effort=self.reasoning_effort)


def resolve_profile(config=None):
    config = {} if config is None else config
    if not isinstance(config, dict) or set(config) - {'profile', 'bindings', 'reasoning_effort'}:
        raise ExpertUnavailable('configuration', 'Invalid host expert configuration.')
    profile = config.get('profile', 'sol')
    bindings = config.get('bindings', {})
    if not isinstance(profile, str) or profile not in {*PROFILES, 'fable'}:
        raise ExpertUnavailable('unsupported_profile', 'Unknown expert profile; no substitution was made.')
    if not isinstance(bindings, dict) or set(bindings) - {*PROFILES, 'fable'}:
        raise ExpertUnavailable('configuration', 'Invalid expert profile bindings.')
    binding = bindings.get(profile)
    if binding is not None:
        if not isinstance(binding, dict) or set(binding) != {'provider', 'model'}:
            raise ExpertUnavailable('configuration', 'An expert binding requires provider and real model ID.')
        provider, model = binding['provider'], binding['model']
    elif profile == 'fable':
        raise ExpertUnavailable('unsupported_profile', 'Fable is unconfigured; supply an explicit provider and real model ID.')
    else:
        provider, model = PROFILES[profile]
    if provider not in ('codex', 'claude'):
        raise ExpertUnavailable('unsupported_profile', 'Unsupported expert provider; no substitution was made.')
    # Sol/Astra retain their verified Codex identities; Opus/Sonnet accept pinned Claude IDs.
    if profile in ('sol', 'astra') and (provider, model) != PROFILES[profile]:
        raise ExpertUnavailable('configuration', 'Sol and Astra profiles use their verified Codex model IDs.')
    if profile in ('opus', 'sonnet') and provider != 'claude':
        raise ExpertUnavailable('configuration', 'Opus and Sonnet profiles require Claude.')
    import re
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,159}', model):
        raise ExpertUnavailable('unsupported_model', 'An explicit supported expert model ID is required.')
    if profile == 'fable' and model.lower() in {'fable', 'sol', 'astra', 'opus', 'sonnet', 'default'}:
        raise ExpertUnavailable('unsupported_model', 'Fable requires a real model ID, not an inferred alias.')
    effort = config.get('reasoning_effort', 'medium')
    if effort not in ('low', 'medium', 'high', 'xhigh', 'max', 'ultra') or (provider == 'claude' and effort == 'ultra'):
        raise ExpertUnavailable('configuration', 'Unsupported expert reasoning effort.')
    return ExpertProfile(profile, provider, model, effort)


def write_config(path: Path, config: dict):
    """Operator-only atomic write; no credentials belong in this file."""
    resolve_profile(config)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.expert-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(config, handle)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class ConfiguredExpert:
    """One host router. bind(task_id, snapshot) pins all checkpoint/follow-up runs.

    Snapshot is plain JSON kept on the host task record, not a second model loop.
    release only after task termination (not while waiting for confirmation).
    Existing direct adapter.run() callers remain supported.
    """
    def __init__(self, work_dir, *, artifact_roots, config_path=None, profile='sol',
                 reasoning_effort='medium', executable=None, transports=None, **limits):
        self.work_dir, self.roots = Path(work_dir), artifact_roots
        self.config_path = Path(config_path) if config_path else None
        self.default = {'profile': profile, 'reasoning_effort': reasoning_effort}
        self.executable, self.transports, self.limits = executable, transports or {}, limits
        self._tasks = {}
        self._semaphore = asyncio.Semaphore(limits.pop('max_concurrent', 1))

    def snapshot(self):
        config = self.default
        if self.config_path:
            try:
                if self.config_path.stat().st_size > 16384:
                    raise ValueError('oversized')
                config = json.loads(self.config_path.read_text())
            except (OSError, ValueError, TypeError) as exc:
                raise ExpertUnavailable('configuration', 'Host expert configuration is unavailable or invalid.') from exc
        selected = resolve_profile(config)
        return selected.describe()

    def bind(self, task_id, snapshot=None):
        if task_id not in self._tasks:
            selected = snapshot or self.snapshot()
            # Revalidate stored snapshots; no executable or arbitrary provider may enter them.
            profile = resolve_profile({'profile': selected['profile'], 'reasoning_effort': selected['reasoning_effort'],
                                       'bindings': {selected['profile']: {'provider': selected['provider'],
                                                                       'model': selected['requested_model']}}})
            cls = CodexExpert if profile.provider == 'codex' else ClaudeExpert
            kwargs = dict(self.limits, model=profile.model, reasoning_effort=profile.reasoning_effort,
                          transport=self.transports.get(profile.provider))
            if self.executable:
                kwargs['executable'] = self.executable
            adapter = cls(self.work_dir, artifact_roots=self.roots, **kwargs)
            adapter._semaphore = self._semaphore
            self._tasks[task_id] = adapter
        return self._tasks[task_id]

    def release(self, task_id):
        self._tasks.pop(task_id, None)

    async def run(self, context, **kwargs):
        key = context.get('task_id')
        ephemeral = key is None
        key = object() if ephemeral else key
        try:
            adapter = self.bind(key)
            result = await adapter.run(context, **kwargs)
            if result.get('actual_model'):
                adapter._pinned_model = result['actual_model']
            return result
        finally:
            if ephemeral:
                self.release(key)

    def describe(self):
        try:
            selected = self.snapshot()
            cls = CodexExpert if selected['provider'] == 'codex' else ClaudeExpert
            import shutil
            executable = self.executable or ('codex' if cls is CodexExpert else 'claude')
            return selected | {'provider': cls.provider, 'configured': True,
                               'active_task_bindings': len(self._tasks),
                               'executable_available': shutil.which(executable) is not None,
                               'authentication_verified': False, 'live_qualified': False}
        except ExpertUnavailable as exc:
            return {'configured': False, 'error_code': exc.code, 'live_qualified': False}

    @property
    def provider(self):
        return self.describe().get('provider')

    @property
    def model(self):
        return self.describe().get('model')

    @property
    def reasoning_effort(self):
        return self.describe().get('reasoning_effort')


def add_expert_arguments(parser):
    parser.add_argument('--expert-profile', choices=[*PROFILES, 'fable'], default='sol')
    parser.add_argument('--expert-config', type=Path)
    parser.add_argument('--reasoning-effort', default='medium')
    parser.add_argument('--executable', default=None)


def expert_from_arguments(args, work_dir, *, artifact_roots, **kwargs):
    return ConfiguredExpert(work_dir, artifact_roots=artifact_roots, config_path=args.expert_config,
                            profile=args.expert_profile, reasoning_effort=args.reasoning_effort,
                            executable=args.executable, **kwargs)
