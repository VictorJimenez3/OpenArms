"""OFFLINE fake transport/CLI tests. These do not qualify any live provider."""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from openarms_lab.codex_expert import CodexExpert, ExpertUnavailable, _error
from openarms_lab.claude_expert import ClaudeExpert
from openarms_lab.expert_profiles import ConfiguredExpert, resolve_profile, write_config


def decision(kind='complete', name=None, payload=None):
    return json.dumps(dict(kind=kind, tool_name=name, arguments_json='{}', summary='Observed evidence',
                           payload_json=json.dumps(payload or {})))


async def handler(*args):
    return {}


@pytest.mark.parametrize('cls', [CodexExpert, ClaudeExpert])
async def test_identical_image_tool_and_validator_repair(cls, tmp_path):
    before = tmp_path/'before.png'
    after = tmp_path/'after.png'
    before.write_bytes(b'\x89PNG\r\n\x1a\nbefore')
    after.write_bytes(b'\x89PNG\r\n\x1a\nafter')
    def image(path):
        return dict(path=str(path), evidence_id=path.name, provenance='SYNTHETIC', captured_at='now')
    prompts, calls = [], []
    async def transport(prompt, images, stop):
        prompts.append(prompt)
        calls.append([p.read_bytes() for p in images])
        if len(prompts) == 1:
            return {'raw': decision('tool_call', 'inspect_scene')}
        return {'raw': decision('plan', payload={'valid': len(prompts) == 3}), 'usage': {'input_tokens': 4}}
    async def tool(name, args):
        if name == 'inspect_scene':
            return {'images': [image(after)], 'outcome': 'UNKNOWN'}
        return {'valid': args['plan']['valid'], 'validated_draft': {'canonical': True}, 'error': 'repair_required'}
    expert = cls(tmp_path/'calls', artifact_roots=[tmp_path], transport=transport)
    result = await expert.run({'images': [image(before)], 'tools': [{'name': 'inspect_scene'}, {'name': 'validate_plan'}]}, tool_handler=tool)
    assert calls == [[before.read_bytes()], [after.read_bytes()], [after.read_bytes()]]
    assert 'repair_required' in prompts[-1] and str(tmp_path) not in prompts[-1]
    assert result['calls'] == 3 and result['payload'] == {'canonical': True}
    assert result['usage']['input_tokens'] == 8
    assert result['actual_model'] is None and result['model_verified'] is False


@pytest.mark.parametrize('cls', [CodexExpert, ClaudeExpert])
async def test_illegal_host_tools_and_invalid_envelopes(cls, tmp_path):
    async def transport(*_):
        return {'raw': decision('tool_call', 'Bash')}
    expert = cls(tmp_path/'calls', artifact_roots=[tmp_path], transport=transport)
    async def prohibited(*_):
        pytest.fail('illegal tool reached host')
    with pytest.raises(ExpertUnavailable) as error:
        await expert.run({}, tool_handler=prohibited)
    assert error.value.code == 'invalid_response'


@pytest.mark.parametrize('config,code', [({'profile': 'gemini'}, 'unsupported_profile'),
    ({'profile': 'fable'}, 'unsupported_profile'),
    ({'profile': 'fable', 'bindings': {'fable': {'provider': 'codex', 'model': 'fable'}}}, 'unsupported_model'),
    ({'profile': 'fable', 'bindings': {'fable': {'provider': 'gemini', 'model': 'real-id'}}}, 'unsupported_profile'),
    ({'reasoning_effort': 'surprise'}, 'configuration')])
def test_unsupported_configuration_never_substitutes(config, code):
    with pytest.raises(ExpertUnavailable) as error:
        resolve_profile(config)
    assert error.value.code == code


def test_exact_profiles_and_explicit_binding():
    assert resolve_profile().model == 'gpt-6.1-sol'
    assert resolve_profile({'profile': 'astra'}).model == 'gpt-6-astra'
    assert resolve_profile({'profile': 'opus'}).model == 'opus'
    assert resolve_profile({'profile': 'sonnet'}).model == 'sonnet'
    assert resolve_profile({'profile': 'fable', 'bindings': {'fable': {'provider': 'claude', 'model': 'explicit-provider-id'}}}).model == 'explicit-provider-id'


async def test_atomic_hot_swap_keeps_active_task_through_checkpoints(tmp_path):
    config = tmp_path/'config.json'
    write_config(config, {'profile': 'sol'})
    router = ConfiguredExpert(tmp_path/'calls', artifact_roots=[tmp_path], config_path=config,
                              transports={'codex': lambda *_: None},
                              executables={'codex': 'codex2', 'claude': 'claude-local'})
    original = router.snapshot()
    write_config(config, {'profile': 'astra', 'reasoning_effort': 'high'})
    # Queue-time snapshot predates delayed first expert call.
    first = router.bind('active', original)
    assert first.model == 'gpt-6.1-sol'
    assert first.executable == 'codex2'
    assert router.bind('active').model == 'gpt-6.1-sol'
    second = router.bind('new')
    assert second.model == 'gpt-6-astra' and second.reasoning_effort == 'high'
    router.release('active')
    assert router.bind('active').model == 'gpt-6-astra'
    write_config(config, {'profile': 'opus'})
    assert router.bind('claude-task').executable == 'claude-local'
    assert router.bind('new') is second
    config.write_text('{')
    assert router.describe()['error_code'] == 'configuration'
    assert router.bind('new') is second
    with pytest.raises(ExpertUnavailable):
        router.bind('invalid-new')


async def test_actual_alias_metadata_and_checkpoint_model_pin(tmp_path):
    config = tmp_path/'config.json'
    write_config(config, {'profile': 'opus'})
    async def transport(*_):
        return {'raw': decision(), 'actual_model': 'claude-opus-fixture-id', 'usage': {'input_tokens': 11}}
    router = ConfiguredExpert(tmp_path/'calls', artifact_roots=[tmp_path], config_path=config,
                              transports={'claude': transport})
    result = await router.run({'task_id': 't'}, tool_handler=handler)
    assert result['requested_model'] == 'opus' and result['actual_model'] == 'claude-opus-fixture-id'
    assert result['model'] == result['actual_model'] and result['model_verified'] is True
    assert result['provider'] == 'anthropic_claude_cli'
    write_config(config, {'profile': 'sol'})
    assert router.bind('t')._pinned_model == 'claude-opus-fixture-id'
    assert (await router.run({'task_id': 't'}, tool_handler=handler))['requested_model'] == 'opus'


async def test_pinned_id_rejects_substitution(tmp_path):
    async def transport(*_):
        return {'raw': decision(), 'actual_model': 'other-model'}
    with pytest.raises(ExpertUnavailable) as error:
        await CodexExpert(tmp_path, artifact_roots=[], transport=transport).run({}, tool_handler=handler)
    assert error.value.code == 'model_changed'


def fake_cli(tmp_path, body):
    script = tmp_path/'fake-claude'
    script.write_text('#!'+sys.executable+'\n'+body)
    script.chmod(0o700)
    return str(script)


async def test_offline_claude_cli_images_isolation_and_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'offline-fixture-not-a-real-key')
    monkeypatch.setenv('OPENAI_API_KEY', 'must-not-cross-provider-boundary')
    executable = fake_cli(tmp_path, '''import json,sys,os,base64
args=sys.argv[1:]
assert '--bare' in args and '--print' in args and '--strict-mcp-config' in args
assert args[args.index('--tools')+1] == ''
assert '--disallowedTools' not in args  # a blanket deny also blocks the CLI's own structured reply
assert '--no-session-persistence' in args and '--json-schema' in args
assert 'OPENAI_API_KEY' not in os.environ and 'CODEX_HOME' not in os.environ
message=json.loads(sys.stdin.read())
content=message['message']['content']
assert content[1]['type']=='image' and content[1]['source']['media_type']=='image/png'
assert base64.b64decode(content[1]['source']['data']).endswith(b'pixels')
print(json.dumps({'type':'system','subtype':'init','tools':['StructuredOutput'],'mcp_servers':[]}))
print(json.dumps({'type':'assistant','message':{'model':'claude-sonnet-fixture-id','content':[{'type':'tool_use','name':'StructuredOutput'}]}}))
print(json.dumps({'type':'result','subtype':'success','usage':{'input_tokens':3},'modelUsage':{'claude-sonnet-fixture-id':{}},'structured_output':dict(kind='complete',tool_name=None,arguments_json='{}',summary='Seen',payload_json='{}')}))
''')
    image = tmp_path/'frame.png'
    image.write_bytes(b'\x89PNG\r\n\x1a\npixels')
    expert = ClaudeExpert(tmp_path/'calls', artifact_roots=[tmp_path], executable=executable)
    result = await expert.run({'images':[dict(path=str(image), evidence_id='f', provenance='SYNTHETIC', captured_at='now')]}, tool_handler=handler)
    assert result['model'] == 'claude-sonnet-fixture-id' and result['requested_model'] == 'sonnet'
    assert result['usage']['input_tokens'] == 3
    assert not list((tmp_path/'calls').iterdir())


@pytest.mark.parametrize('event,code', [
    ({'type':'system','subtype':'init','tools':['Bash']}, 'isolation'),
    ({'type':'assistant','message':{'content':[{'type':'tool_use','name':'Bash'}]}}, 'invalid_response'),
    ({'type':'result','subtype':'success','result':'text only'}, 'invalid_response'),
    ({'type':'result','subtype':'error','is_error':True,'result':'not logged in /private/secret'}, 'authentication')])
async def test_offline_claude_rejects_tools_text_only_and_credentials(tmp_path, monkeypatch, event, code):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'offline-fixture')
    executable = fake_cli(tmp_path, 'import sys,json\nsys.stdin.read()\nprint('+repr(json.dumps(event))+')\n')
    expert = ClaudeExpert(tmp_path/'calls', artifact_roots=[], executable=executable)
    with pytest.raises(ExpertUnavailable) as error:
        await expert.run({}, tool_handler=handler)
    assert error.value.code == code
    assert 'secret' not in str(error.value)


async def test_missing_claude_executable_and_credentials(tmp_path, monkeypatch):
    expert = ClaudeExpert(tmp_path/'calls', artifact_roots=[], executable='/nonexistent/claude')
    with pytest.raises(ExpertUnavailable) as error:
        await expert.run({}, tool_handler=handler)
    assert error.value.code == 'unavailable'
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    expert = ClaudeExpert(tmp_path/'calls', artifact_roots=[], executable=sys.executable)
    with pytest.raises(ExpertUnavailable) as error:
        await expert.run({}, tool_handler=handler)
    assert error.value.code == 'authentication'


@pytest.mark.parametrize('mode', ['timeout', 'cancel', 'overflow'])
async def test_shared_process_cleanup_offline(tmp_path, mode):
    pidfile = tmp_path/'pid'
    script = tmp_path/'sleeper.py'
    script.write_text("import os,time,sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(str(os.getpid()))\n" +
                      ("sys.stdout.write('x'*1100000);sys.stdout.flush()\n" if mode == 'overflow' else '') + 'time.sleep(30)\n')
    expert = CodexExpert(tmp_path/'calls', artifact_roots=[], call_timeout=.15)
    stop = asyncio.Event()
    operation = asyncio.create_task(expert._invoke([sys.executable, str(script), str(pidfile)], b'', stop,
                                                  cwd=tmp_path, env={'PATH': os.environ['PATH']}))
    if mode == 'cancel':
        for _ in range(100):
            if pidfile.exists():
                break
            await asyncio.sleep(.005)
        stop.set()
    with pytest.raises(asyncio.CancelledError if mode == 'cancel' else ExpertUnavailable) as error:
        await operation
    if mode != 'cancel':
        assert error.value.code == ('timeout' if mode == 'timeout' else 'invalid_response')
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


@pytest.mark.parametrize('message,code', [('401 secret/path','authentication'), ('quota secret','quota'),
                                         ('unknown model secret','unsupported_model'), ('oops secret','unavailable')])
def test_errors_are_provider_neutral_and_sanitized(message, code):
    error = _error(message)
    assert error.code == code and 'secret' not in str(error) and 'Codex' not in str(error)


async def test_lab_queue_snapshot_survives_swap_until_confirmed_execution(tmp_path):
    from openarms_lab.runtime import Lab
    from openarms_lab.scene import SceneService
    from openarms_lab.simulated_backend import SceneBackend
    from agentic.tests.test_task_evidence_review import draft
    config = tmp_path/'selected.json'
    write_config(config, {'profile': 'sol'})
    requests = []
    async def transport(prompt, *_):
        context = json.loads(prompt.split('HOST_CONTEXT\n', 1)[1].split('\nATTACHED_IMAGE_ORDER', 1)[0])
        requests.append(context['phase'])
        if context['phase'] == 'planning':
            return {'raw': decision('plan', payload=draft())}
        return {'raw': decision(payload={'continue': True})}
    scene = SceneService(tmp_path/'frames')
    router = ConfiguredExpert(tmp_path/'calls', artifact_roots=[scene.artifact_dir], config_path=config,
                              transports={'codex': transport})
    lab = Lab(tmp_path/'lab', expert=router, perception=scene, backend_factory=lambda: SceneBackend(scene, delay=0))
    sid = (await lab.create())['session_id']
    try:
        handle = await lab.start_task(sid, 'Test prepared vinegar', turn_id='one')
        # Mutation happens before the event loop runs planning.
        write_config(config, {'profile': 'astra'})
        await asyncio.wait_for(asyncio.shield(lab.workers[handle['task_id']]), 3)
        state = lab.snapshot(sid)
        task = state['tasks'][-1]
        assert task['status'] == 'awaiting_confirmation', task.get('summary')
        assert task['expert_configuration']['model'] == 'gpt-6.1-sol'
        proposal = state['pending']
        await lab.present(sid, proposal['request_id'], proposal['proposal_version'])
        await lab.confirm(sid, proposal['request_id'], proposal['proposal_version'])
        worker = lab.workers.get(handle['task_id'])
        if worker:
            await asyncio.wait_for(asyncio.shield(worker), 3)
        task = lab.snapshot(sid)['tasks'][-1]
        assert task['status'] == 'completed', task.get('summary')
        assert all(run['requested_model'] == 'gpt-6.1-sol' for run in task['expert_runs'])
        assert len(task['expert_runs']) > 1 and not router._tasks
        assert router.snapshot()['model'] == 'gpt-6-astra'
    finally:
        await lab.shutdown()
