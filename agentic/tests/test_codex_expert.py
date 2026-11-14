import asyncio
import json
from pathlib import Path

import pytest

from openarms_lab.codex_expert import CodexExpert, ExpertUnavailable, parse_reply


def decision(kind='plan', *, name=None, arguments=None, payload=None):
    return json.dumps(dict(kind=kind, tool_name=name, arguments_json=json.dumps(arguments or {}),
                           summary='A decision grounded in scene evidence.', payload_json=json.dumps(payload or {})))


def frame(root, name, marker=b'a'):
    path = root / (name + '.png')
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + marker)
    return dict(path=str(path), evidence_id=name, captured_at='2026-11-14T15:00:00Z', provenance='SIMULATED')


@pytest.mark.asyncio
async def test_image_tool_feedback_reaches_next_decision(tmp_path):
    before, after = frame(tmp_path, 'before'), frame(tmp_path, 'after', b'b')
    seen, events = [], []
    async def transport(prompt, images, cancellation):
        seen.append((prompt, [p.read_bytes() for p in images]))
        if len(seen) == 1:
            return dict(raw=decision('tool_call', name='inspect_scene', arguments={'view': 'alternate'}),
                        usage={'input_tokens': 10, 'output_tokens': 5})
        assert 'grasp_unknown' in prompt
        assert 'after' in prompt and str(tmp_path) not in prompt
        return dict(raw=decision('revision', payload={'change': 'inspect an alternate view before carrying'}),
                    usage={'input_tokens': 12, 'output_tokens': 7})
    async def handler(name, arguments):
        assert name == 'inspect_scene' and arguments == {'view': 'alternate'}
        return {'outcome': 'grasp_unknown', 'images': [after]}
    async def emit(event):
        events.append(event)
    expert = CodexExpert(tmp_path/'calls', artifact_roots=[tmp_path], transport=transport)
    result = await expert.run({'task_id': 't1', 'request': 'Continue the transfer', 'images': [before],
                               'tools': [{'name': 'inspect_scene'}]}, tool_handler=handler, emit=emit)
    assert result['kind'] == 'revision' and result['calls'] == 2
    assert result['usage'] == {'input_tokens': 22, 'output_tokens': 12}
    assert seen[0][1][0] != seen[1][1][0]
    assert result['model'] == 'gpt-6.1-sol' and result['reasoning_effort'] == 'medium'
    assert result['tool_receipts'][0]['result']['images'][0]['sha256']
    assert all(event['task_id'] == 't1' for event in events)
    assert not list((tmp_path/'calls').iterdir())


@pytest.mark.asyncio
async def test_undeclared_tool_never_reaches_host(tmp_path):
    async def transport(*_):
        return {'raw': decision('tool_call', name='execute_arbitrary_motor_code')}
    async def handler(*_):
        pytest.fail('An undeclared tool reached execution')
    expert = CodexExpert(tmp_path/'calls', artifact_roots=[tmp_path], transport=transport)
    with pytest.raises(ExpertUnavailable) as error:
        await expert.run({'tools': [{'name': 'inspect_scene'}]}, tool_handler=handler)
    assert error.value.code == 'invalid_response'


@pytest.mark.asyncio
async def test_cancellation_interrupts_pending_observation_and_queued_task(tmp_path):
    entered, cancelled = asyncio.Event(), asyncio.Event()
    async def transport(*_):
        return {'raw': decision('tool_call', name='inspect_scene')}
    async def handler(*_):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    expert = CodexExpert(tmp_path/'calls', artifact_roots=[tmp_path], transport=transport)
    stop_first, stop_queued = asyncio.Event(), asyncio.Event()
    context = {'tools': [{'name': 'inspect_scene'}]}
    first = asyncio.create_task(expert.run(context, tool_handler=handler, cancel_event=stop_first))
    await entered.wait()
    second = asyncio.create_task(expert.run(context, tool_handler=handler, cancel_event=stop_queued))
    stop_queued.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(second, .2)
    stop_first.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(first, .2)
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_evidence_path_and_hash_checked_before_model(tmp_path):
    root = tmp_path/'allowed'
    root.mkdir()
    outside = frame(tmp_path, 'secret')
    async def transport(*_):
        pytest.fail('Invalid evidence reached provider')
    async def handler(*_):
        return {}
    expert = CodexExpert(root/'calls', artifact_roots=[root], transport=transport)
    with pytest.raises(ExpertUnavailable, match='artifact validation'):
        await expert.run({'images': [outside]}, tool_handler=handler)
    forged = frame(root, 'forged') | {'sha256': '0'*64}
    with pytest.raises(ExpertUnavailable, match='artifact validation'):
        await expert.run({'images': [forged]}, tool_handler=handler)


@pytest.mark.asyncio
async def test_call_budget_and_timeout_do_not_fabricate_a_plan(tmp_path):
    async def transport(*_):
        return {'raw': decision('tool_call', name='inspect_scene')}
    async def handler(*_):
        return {'outcome': 'UNKNOWN'}
    expert = CodexExpert(tmp_path/'calls', artifact_roots=[tmp_path], transport=transport, max_calls=2)
    with pytest.raises(ExpertUnavailable) as error:
        await expert.run({'tools': [{'name': 'inspect_scene'}]}, tool_handler=handler)
    assert error.value.code == 'budget'
    async def slow(*_):
        await asyncio.Event().wait()
    expert = CodexExpert(tmp_path/'calls', artifact_roots=[tmp_path], transport=slow, task_timeout=.02)
    with pytest.raises(ExpertUnavailable) as error:
        await expert.run({}, tool_handler=handler)
    assert error.value.code == 'timeout'


def test_reply_requires_consistent_typed_decision():
    with pytest.raises(ExpertUnavailable):
        parse_reply(decision('plan', name='inspect_scene'))
    with pytest.raises(ExpertUnavailable):
        parse_reply(decision('tool_call', name='inspect_scene', payload={'invented_result': True}))
    with pytest.raises(ExpertUnavailable):
        parse_reply('{"kind": "plan"}')


@pytest.mark.asyncio
async def test_invalid_final_plan_is_repaired_by_expert_with_actual_validation_feedback(tmp_path):
    calls, validated = [], []
    async def transport(prompt, *_):
        calls.append(prompt)
        if len(calls) == 1:
            return {'raw': decision(payload={'skill_definition': {}, 'steps': ['override']})}
        assert 'A skill proposal cannot override its definition' in prompt
        return {'raw': decision(payload={'skill_definition': {'repaired': True}})}
    async def handler(name, arguments):
        assert name == 'validate_plan'
        validated.append(arguments['plan'])
        if 'steps' in arguments['plan']:
            return {'valid': False, 'error': 'A skill proposal cannot override its definition.'}
        return {'valid': True, 'validated_draft': arguments['plan']}
    expert = CodexExpert(tmp_path/'calls', artifact_roots=[tmp_path], transport=transport)
    result = await expert.run({'tools': [{'name': 'validate_plan'}]}, tool_handler=handler)
    assert result['calls'] == 2 and result['payload'] == validated[1]
    assert len(result['tool_receipts']) == 2
    assert result['tool_receipts'][0]['result']['valid'] is False


@pytest.mark.asyncio
async def test_invalid_final_plan_cannot_escape_call_budget(tmp_path):
    calls = 0
    async def transport(*_):
        nonlocal calls
        calls += 1
        return {'raw': decision(payload={'invalid': True})}
    async def handler(*_):
        return {'valid': False, 'error': 'Invalid proposal'}
    expert = CodexExpert(tmp_path/'calls', artifact_roots=[tmp_path], transport=transport, max_calls=2)
    with pytest.raises(ExpertUnavailable) as error:
        await expert.run({'tools': [{'name': 'validate_plan'}]}, tool_handler=handler)
    assert error.value.code == 'budget' and calls == 2


@pytest.mark.asyncio
async def test_real_process_transport_lifecycle_and_provider_errors(tmp_path, monkeypatch):
    # Exercise the actual subprocess boundary without an external provider call.
    fixture = tmp_path/'fake-codex'
    fixture.write_text('''#!/usr/bin/env python3
import json, sys
from pathlib import Path
args=sys.argv[1:]
assert args[args.index('-m')+1] == 'gpt-6.1-sol'
assert 'model_reasoning_effort="medium"' in args
assert '--ignore-user-config' in args and 'shell_tool' in args
sys.stdin.read()
answer=Path(args[args.index('--output-last-message')+1])
answer.write_text(json.dumps(dict(kind='plan', tool_name=None, arguments_json='{}', summary='Ready', payload_json='{}')))
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':1}}))
''')
    fixture.chmod(0o700)
    expert = CodexExpert(tmp_path/'calls', artifact_roots=[tmp_path], executable=str(fixture))
    async def handler(*_):
        return {}
    result = await expert.run({}, tool_handler=handler)
    assert result['kind'] == 'plan'
    fixture.write_text('''#!/usr/bin/env python3
import json,sys
sys.stdin.read()
print(json.dumps({'type':'turn.failed','error':{'message':"You've hit your usage limit."}}))
sys.exit(1)
''')
    with pytest.raises(ExpertUnavailable) as error:
        await expert.run({}, tool_handler=handler)
    assert error.value.code == 'quota'
    assert not list((tmp_path/'calls').iterdir())
