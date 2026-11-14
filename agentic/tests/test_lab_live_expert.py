"""SDK-shaped Live composition tests; no network, audio playback, or robot calls."""
import asyncio
import os
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import types

from agentic.openarms_lab import live_expert


def steps():
    return [
        {"action": "transfer", "args": {"source": "$source", "destination": "$destination", "object": "$object"}},
        {"action": "observe", "args": {"station": "$destination"}},
    ]


def proposal(arguments=None, name=live_expert.TOOL_NAME):
    return types.LiveServerMessage(tool_call=types.LiveServerToolCall(function_calls=[
        types.FunctionCall(id="candidate-1", name=name, args={"steps": steps()} if arguments is None else arguments),
    ]))


class FakeConnection:
    def __init__(self, session):
        self.session = session
        self.exited = False

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        self.exited = True


def fake_client(messages, *, block=False):
    async def receive():
        for message in messages:
            yield message
        if block:
            await asyncio.Event().wait()
    session = NS(receive=receive, send_client_content=AsyncMock(), send_tool_response=AsyncMock())
    connection = FakeConnection(session)
    client = NS(aio=NS(live=NS(connect=MagicMock(return_value=connection)), aclose=AsyncMock()))
    return client, connection, session


@pytest.fixture(autouse=True)
def fake_credentials():
    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-test-key", "GEMINI_LIVE_MODEL": "test-live-model"}):
        yield


def test_live_expert_uses_real_sdk_types_and_returns_bound_artifact():
    messages = [
        types.LiveServerMessage(server_content=types.LiveServerContent(
            model_turn=types.Content(role="model", parts=[types.Part(text="Checking calibrated primitives.")]))),
        proposal(),
        types.LiveServerMessage(usage_metadata=types.UsageMetadata(total_token_count=83)),
        types.LiveServerMessage(usage_metadata=types.UsageMetadata(total_token_count=97),
                                server_content=types.LiveServerContent(turn_complete=True)),
    ]
    client, connection, session = fake_client(messages)
    instruction = "transfer sample from A to B and observe the destination"
    result = asyncio.run(live_expert.compose_live(instruction, client_factory=lambda: client))
    assert result == {"steps": steps(), "model_calls": 1, "tokens": 97, "model": "test-live-model"}
    config = client.aio.live.connect.call_args.kwargs["config"]
    assert config.response_modalities == [types.Modality.AUDIO]
    declaration = config.tools[0].function_declarations[0]
    assert declaration.name == "propose_reusable_skill"
    schema = declaration.parameters.properties["steps"].items
    assert schema.properties["action"].enum == ["transfer", "observe"]
    session.send_client_content.assert_awaited_once()
    assert session.send_client_content.await_args.kwargs["turns"].parts[0].text == instruction
    session.send_tool_response.assert_awaited_once()
    response = session.send_tool_response.await_args.kwargs["function_responses"][0]
    assert response.id == "candidate-1" and response.response["executed"] is False
    assert connection.exited
    client.aio.aclose.assert_awaited_once()


@pytest.mark.parametrize("arguments", [
    {}, {"steps": []}, {"steps": steps(), "speed": 10},
    {"steps": [{"action": "set_servo", "args": {"angle": 180}}]},
    {"steps": list(reversed(steps()))},
    {"steps": [
        {"action": "transfer", "args": {"source": "A", "destination": "B", "object": "sample"}},
        {"action": "observe", "args": {"station": "$destination"}},
    ]},
    {"steps": [
        {"action": "transfer", "args": {"source": "$source", "destination": "$destination", "object": "$object", "pwm": 255}},
        {"action": "observe", "args": {"station": "$destination"}},
    ]},
    {"steps": [steps()[0], {"action": "observe", "args": {"station": "$source"}}]},
])
def test_arbitrary_controls_and_bindings_rejected(arguments):
    client, connection, session = fake_client([proposal(arguments)])
    with pytest.raises(ValueError, match="unsupported steps or parameter bindings"):
        asyncio.run(live_expert.compose_live("transfer and observe", client_factory=lambda: client))
    session.send_tool_response.assert_not_awaited()
    assert connection.exited
    client.aio.aclose.assert_awaited_once()


@pytest.mark.parametrize("messages", [
    [proposal(name="execute_robot")],
    [proposal(), proposal()],
    [types.LiveServerMessage(tool_call_cancellation=types.LiveServerToolCallCancellation(ids=["candidate-1"]))],
    [types.LiveServerMessage(server_content=types.LiveServerContent(interrupted=True))],
    [types.LiveServerMessage(server_content=types.LiveServerContent(turn_complete=True))],
    [types.LiveServerMessage(server_content=types.LiveServerContent(model_turn=types.Content(
        role="model", parts=[types.Part(text='{"steps": "this is prose, never a tool artifact"}')])))]
])
def test_no_arbitrary_tool_or_prose_fallback(messages):
    client, connection, _ = fake_client(messages)
    with pytest.raises(ValueError):
        asyncio.run(live_expert.compose_live("transfer and observe", client_factory=lambda: client))
    assert connection.exited
    client.aio.aclose.assert_awaited_once()


def test_timeout_closes_live_session_and_client():
    client, connection, _ = fake_client([], block=True)
    with patch.object(live_expert, "REQUEST_TIMEOUT_SECONDS", 0.01):
        with pytest.raises(TimeoutError):
            asyncio.run(live_expert.compose_live("transfer and observe", client_factory=lambda: client))
    assert connection.exited
    client.aio.aclose.assert_awaited_once()
    assert live_expert.REQUEST_TIMEOUT_SECONDS + live_expert.CLOSE_TIMEOUT_SECONDS <= 30


def test_cancellation_closes_live_session_and_client():
    client, connection, _ = fake_client([], block=True)
    async def run():
        task = asyncio.create_task(live_expert.compose_live("transfer and observe", client_factory=lambda: client))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert connection.exited
    client.aio.aclose.assert_awaited_once()


def test_no_key_fails_before_any_client_created():
    factory = MagicMock()
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="credentials"):
            asyncio.run(live_expert.compose_live("transfer and observe", client_factory=factory))
    factory.assert_not_called()


def test_provider_usage_missing_stays_unknown_and_not_zero():
    client, _, _ = fake_client([proposal()])
    result = asyncio.run(live_expert.compose_live("transfer and observe", client_factory=lambda: client))
    assert result["tokens"] is None
    assert result["model_calls"] == 1


def test_default_model_and_google_key_are_backend_only():
    client, _, _ = fake_client([proposal()])
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "fake-google-key"}, clear=True):
        with patch.object(live_expert.genai, "Client", return_value=client) as factory:
            result = asyncio.run(live_expert.compose_live("transfer and observe"))
    assert result["model"] == "gemini-3.8-live"
    assert "fake-google-key" not in str(result)
    factory.assert_called_once_with(api_key="fake-google-key", http_options={"api_version": "v1beta"})


def test_multiple_calls_in_one_batch_are_rejected_before_acknowledgment():
    call = proposal().tool_call.function_calls[0]
    batch = types.LiveServerMessage(tool_call=types.LiveServerToolCall(function_calls=[call, call]))
    client, connection, session = fake_client([batch])
    with pytest.raises(ValueError, match="exactly one"):
        asyncio.run(live_expert.compose_live("transfer and observe", client_factory=lambda: client))
    session.send_tool_response.assert_not_awaited()
    assert connection.exited
    client.aio.aclose.assert_awaited_once()


def test_connection_error_still_closes_client():
    client, _, _ = fake_client([])
    client.aio.live.connect.side_effect = ConnectionError("injected connection failure")
    with pytest.raises(ConnectionError, match="injected"):
        asyncio.run(live_expert.compose_live("transfer and observe", client_factory=lambda: client))
    client.aio.aclose.assert_awaited_once()


@pytest.mark.parametrize("instruction", ["", " ", "x" * 4001, None])
def test_invalid_instruction_never_creates_client(instruction):
    factory = MagicMock()
    with pytest.raises(ValueError, match="instruction"):
        asyncio.run(live_expert.compose_live(instruction, client_factory=factory))
    factory.assert_not_called()
