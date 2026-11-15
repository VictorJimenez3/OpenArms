import asyncio
import json
import sys
import textwrap

import pytest

from openarms_lab.codex_expert import ExpertUnavailable
from openarms_lab.devin_expert import DevinExpert
from openarms_lab.expert_profiles import ConfiguredExpert, resolve_profile

REPLY = {'kind': 'reject', 'summary': 'Fake reply.', 'payload': {'reason': 'test'}}


def fake_devin(tmp_path, *, speed='fast', thought='medium', model='gpt-6-1-sol-medium', label='GPT-6.1 Sol Medium Thinking Fast',
               tool_call=False, permission=False, fenced=False):
    script = tmp_path / 'devin'
    log = tmp_path / 'acp-log.jsonl'
    reply = json.dumps(REPLY)
    if fenced:
        reply = '```json\n' + reply + '\n```'
    script.write_text(textwrap.dedent(f'''\
        #!{sys.executable}
        import json, sys
        log = open({str(log)!r}, 'a')
        log.write(json.dumps({{'argv': sys.argv[1:]}}) + '\\n')
        def send(message):
            sys.stdout.write(json.dumps(message) + '\\n'); sys.stdout.flush()
        def update(sid, value):
            send({{'jsonrpc': '2.0', 'method': 'session/update', 'params': {{'sessionId': sid, 'update': value}}}})
        for line in sys.stdin:
            message = json.loads(line)
            log.write(json.dumps(message)[:4000] + '\\n'); log.flush()
            method, mid = message.get('method'), message.get('id')
            if method == 'initialize':
                send({{'jsonrpc': '2.0', 'id': mid, 'result': {{'protocolVersion': 1,
                      'agentCapabilities': {{'promptCapabilities': {{'image': True}}}}}}}})
            elif method == 'session/new':
                send({{'jsonrpc': '2.0', 'id': mid, 'result': {{'sessionId': 's1', 'configOptions': [
                    {{'id': 'mode', 'currentValue': 'accept-edits'}}, {{'id': 'model', 'currentValue': {model!r}}},
                    {{'id': 'thought_level', 'currentValue': {thought!r}}}, {{'id': 'speed', 'currentValue': {speed!r}}}]}}}})
            elif method == 'session/set_config_option':
                send({{'jsonrpc': '2.0', 'id': mid, 'result': {{}}}})
            elif method == 'session/prompt':
                if {permission!r}:
                    send({{'jsonrpc': '2.0', 'id': 77, 'method': 'session/request_permission', 'params': {{'sessionId': 's1'}}}})
                    answer = json.loads(sys.stdin.readline())
                    log.write(json.dumps(answer) + '\\n'); log.flush()
                if {tool_call!r}:
                    update('s1', {{'sessionUpdate': 'tool_call', 'toolCallId': 't', 'title': 'read'}})
                text = {reply!r}
                for i in range(0, len(text), 7):
                    update('s1', {{'sessionUpdate': 'agent_message_chunk', 'content': {{'type': 'text', 'text': text[i:i+7]}}}})
                send({{'jsonrpc': '2.0', 'method': '_cognition.ai/turn_stats', 'params': {{'sessionId': 's1',
                      'responseDimensions': [{{'uid': 'model', 'kind': {{'type': 'metric', 'value': {label!r}}}}}]}}}})
                send({{'jsonrpc': '2.0', 'id': mid, 'result': {{'stopReason': 'end_turn',
                      'usage': {{'inputTokens': 100, 'outputTokens': 7, 'cachedReadTokens': 3}}}}}})
        '''))
    script.chmod(0o755)
    return script, log


def expert(tmp_path, script, **kwargs):
    return DevinExpert(tmp_path / 'work', artifact_roots=[tmp_path], executable=str(script),
                       model='gpt-6-1-sol-medium-priority', **kwargs)


def test_devin_profiles_resolve_to_exact_devin_model_slugs():
    assert resolve_profile({'profile': 'devin-sol-fast'}).describe()['requested_model'] == 'gpt-6-1-sol-medium-priority'
    assert resolve_profile({'profile': 'devin-sol-fast', 'reasoning_effort': 'low'}).model == 'gpt-6-1-sol-low-priority'
    assert resolve_profile({'profile': 'devin-astra-fast', 'reasoning_effort': 'high'}).model == 'gpt-6-astra-high-priority'
    assert resolve_profile({'profile': 'devin-opus-fast'}).model == 'claude-opus-5-5-medium-fast'
    assert resolve_profile({'profile': 'devin-sol'}).model == 'gpt-6-1-sol-medium'
    assert resolve_profile({'profile': 'devin-sol-fast'}).provider == 'devin'
    with pytest.raises(ExpertUnavailable):
        resolve_profile({'profile': 'devin-sol-fast', 'bindings': {'devin-sol-fast': {'provider': 'devin', 'model': 'gpt-6-astra-medium'}}})
    with pytest.raises(ExpertUnavailable):
        resolve_profile({'profile': 'sol', 'bindings': {'sol': {'provider': 'devin', 'model': 'gpt-6-1-sol-medium-priority'}}})


@pytest.mark.asyncio
async def test_devin_transport_returns_reply_usage_and_verified_identity(tmp_path):
    script, log = fake_devin(tmp_path, fenced=True)
    image = tmp_path / 'frame.png'
    image.write_bytes(b'\x89PNG\r\n\x1a\nfake')
    result = await expert(tmp_path, script)._complete('Plan it.', [image], None)
    assert json.loads(result['raw']) == REPLY
    assert result['actual_model'] == 'gpt-6-1-sol-medium-priority'
    assert result['usage'] == {'input_tokens': 100, 'output_tokens': 7, 'cached_input_tokens': 3}
    sent = [json.loads(line) for line in log.read_text().splitlines()]
    assert sent[0]['argv'][:3] == ['acp', '--model', 'gpt-6-1-sol-medium-priority']
    prompt = next(m for m in sent if m.get('method') == 'session/prompt')['params']['prompt']
    assert prompt[0]['type'] == 'text' and 'Plan it.' in prompt[0]['text'] and '"kind"' in prompt[0]['text']
    assert prompt[1] == {'type': 'image', 'mimeType': 'image/png', 'data': 'iVBORw0KGgpmYWtl'}
    assert {'configId': 'mode', 'value': 'ask'}.items() <= next(
        m for m in sent if m.get('method') == 'session/set_config_option')['params'].items()


@pytest.mark.asyncio
async def test_devin_transport_reports_substituted_speed_instead_of_hiding_it(tmp_path):
    script, _ = fake_devin(tmp_path, speed='standard')
    result = await expert(tmp_path, script)._complete('Plan it.', [], None)
    assert result['actual_model'] == 'gpt-6-1-sol-medium'


@pytest.mark.asyncio
async def test_devin_transport_fails_closed_on_autonomous_tool_use(tmp_path):
    script, _ = fake_devin(tmp_path, tool_call=True)
    with pytest.raises(ExpertUnavailable) as error:
        await expert(tmp_path, script)._complete('Plan it.', [], None)
    assert error.value.code == 'isolation'


@pytest.mark.asyncio
async def test_devin_transport_denies_permission_requests_and_fails_closed(tmp_path):
    script, log = fake_devin(tmp_path, permission=True)
    with pytest.raises(ExpertUnavailable) as error:
        await expert(tmp_path, script)._complete('Plan it.', [], None)
    assert error.value.code == 'isolation'
    assert any('"id": 77' in line and 'error' in line for line in log.read_text().splitlines())


@pytest.mark.asyncio
async def test_devin_transport_honours_cancellation(tmp_path):
    script, _ = fake_devin(tmp_path)
    cancel = asyncio.Event()
    cancel.set()
    with pytest.raises(asyncio.CancelledError):
        await expert(tmp_path, script)._complete('Plan it.', [], cancel)


def test_configured_expert_binds_devin_profiles_to_devin_transport(tmp_path):
    configured = ConfiguredExpert(tmp_path, artifact_roots=[tmp_path], profile='devin-sol-fast',
                                  executables={'devin': '/bin/echo'})
    adapter = configured.bind('task')
    assert isinstance(adapter, DevinExpert)
    assert adapter.model == 'gpt-6-1-sol-medium-priority' and adapter.executable == '/bin/echo'
    assert configured.describe()['provider'] == DevinExpert.provider
