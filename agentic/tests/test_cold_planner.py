from types import SimpleNamespace

import pytest

from agentic.openarms_agent.cold_planner import ClaudePlanner, Draft, PlanningRequest


STATIONS = {
    "A": {"kind": "source", "contents": "vinegar", "portions": 2},
    "C": {"kind": "receiver", "contents": "indicator", "capacity": 3},
}
STATE = {
    "at": "HOME",
    "holding": None,
    "portions_left": {"A": 2},
    "receiver_load": {"C": 0},
    "armed": True,
}


def request(text="add a sample"):
    return PlanningRequest(text=text, state=STATE, stations=STATIONS, history=[])


def response(value, *, input_tokens=12, output_tokens=7):
    return SimpleNamespace(
        stop_reason="tool_use",
        content=[SimpleNamespace(type="tool_use", name="submit_or_decline", input=value)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


class FakeMessages:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class FakeClient:
    def __init__(self, result):
        self.messages = FakeMessages(result)


def test_submit_returns_allowlisted_steps_and_usage_from_one_call():
    client = FakeClient(response({
        "decision": "submit",
        "steps": [{"action": "add_sample", "args": {"source": "A", "into": "C", "portions": 1}}],
    }))

    draft = ClaudePlanner(client=client)(request())

    assert draft == Draft(
        steps=[{"action": "add_sample", "args": {"source": "A", "into": "C", "portions": 1}}],
        input_tokens=12,
        output_tokens=7,
    )
    assert len(client.messages.calls) == 1
    call = client.messages.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "submit_or_decline"}
    assert call["tools"][0]["name"] == "submit_or_decline"


def test_decline_returns_none_and_preserves_one_call():
    client = FakeClient(response({"decision": "decline", "reason": "ambiguous destination"}))

    assert ClaudePlanner(client=client)(request("do something with the sample")) is None
    assert len(client.messages.calls) == 1


@pytest.mark.parametrize(
    "value",
    [
        {"decision": "submit", "steps": []},
        {"decision": "submit", "steps": [{"action": "invent", "args": {}}]},
        {"decision": "submit", "steps": [{"action": "add_sample", "args": {"source": "A", "into": "C", "portions": 1, "unsafe": True}}]},
        {"decision": "submit", "steps": [{"action": "add_sample", "args": {"source": "A", "into": "unknown", "portions": 1}}]},
        {"decision": "submit", "steps": [{"action": "wait", "args": {"seconds": 0}}]},
    ],
)
def test_invalid_tool_payload_is_rejected(value):
    client = FakeClient(response(value))

    assert ClaudePlanner(client=client)(request()) is None


def test_strict_response_rejects_extra_text_or_multiple_tool_blocks():
    result = response({"decision": "decline", "reason": "unclear"})
    result.content.insert(0, SimpleNamespace(type="text", text="I will decide."))
    client = FakeClient(result)

    assert ClaudePlanner(client=client)(request()) is None


def test_planner_does_not_retry_on_api_failure():
    class FailingMessages:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            raise RuntimeError("offline")

    client = SimpleNamespace(messages=FailingMessages())
    with pytest.raises(RuntimeError, match="offline"):
        ClaudePlanner(client=client)(request())
    assert client.messages.calls == 1
