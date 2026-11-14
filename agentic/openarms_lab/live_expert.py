"""Optional Gemini Live composition transport; proposals never execute a robot.

Uses the installed google-genai Live tool-call boundary, as in live.py. The
caller still owns request-intent validation, candidate testing and promotion.
No audio is played, and generated prose is never parsed as a skill definition.
"""
from __future__ import annotations

import asyncio
import copy
import os
from typing import Any, Callable

from google import genai
from google.genai import types

DEFAULT_MODEL = "gemini-3.8-live"
REQUEST_TIMEOUT_SECONDS = 25.0
CLOSE_TIMEOUT_SECONDS = 5.0
TOOL_NAME = "propose_reusable_skill"
_CANONICAL_STEPS = [
    {"action": "transfer", "args": {
        "source": "$source", "destination": "$destination", "object": "$object"}},
    {"action": "observe", "args": {"station": "$destination"}},
]
_EXPECTED_PROPOSAL = {"recipe": "transfer_then_observe"}
TOOLS = [{"function_declarations": [{
    "name": TOOL_NAME,
    "description": "Propose a reusable candidate from calibrated primitives. Does not execute or approve anything.",
    "parameters": {
        "type": "OBJECT", "required": ["recipe"],
        "properties": {
            "recipe": {
                "type": "STRING", "enum": ["transfer_then_observe"],
                "description": "Fixed reusable transfer with source/destination/object parameters, then observe destination.",
            },
        },
    },
}]}]
SYSTEM_PROMPT = """You are the OpenArms reusable-skill composition expert.
Reason from the student's requested intent using only the known calibrated
primitives: transfer(source=$source, destination=$destination, object=$object),
then observe(station=$destination). Source may be A or C, destination B, and
object mandarin (orange alias) or sample. No new objects, motion settings,
raw controls, parameters, stations, physical evidence or scientific claims.
For a requested transfer followed by destination observation, compose those
two primitives in order and call propose_reusable_skill exactly once with
{"recipe":"transfer_then_observe"}. The application binds this fixed recipe to
the reusable source, destination, and object parameters shown above, in that
exact order. Do not supply bindings, a steps array, concrete values or extra
fields. Otherwise explain that the request is unsupported
without calling the tool. The tool proposes a candidate only; it never executes,
tests, promotes, or physically authorizes a robot. You may acknowledge briefly.
After the tool response, end your turn without further tool calls.
"""


def _validate_proposal(arguments: Any) -> list[dict[str, Any]]:
    # Models select one task-specific recipe, never actions or argument shapes.
    # Reject extras rather than repairing them; only application-owned canonical
    # steps and reusable placeholder bindings can cross this boundary.
    if not isinstance(arguments, dict) or arguments != _EXPECTED_PROPOSAL:
        raise ValueError("Live expert proposed unsupported steps or parameter bindings.")
    return copy.deepcopy(_CANONICAL_STEPS)


async def compose_live(instruction: str, *, client_factory: Callable | None = None) -> dict[str, Any]:
    """Get one strictly validated candidate proposal through an AUDIO Live session.

    Missing provider usage stays None. The returned model_calls counts this one
    composition interaction, including its tool acknowledgment, not audio chunks.
    Request/connection work is bounded to 25 seconds, with up to 5 seconds for
    client cleanup. A configured key is required even for an injected client.
    """
    if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 4000:
        raise ValueError("Provide a nonempty composition instruction of at most 4000 characters.")
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("Gemini credentials are not configured for the Live expert.")
    model = os.getenv("GEMINI_LIVE_MODEL", DEFAULT_MODEL)
    client = client_factory() if client_factory else genai.Client(
        api_key=api_key, http_options={"api_version": "v1beta"})
    proposal = None
    tokens = None
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
            config = types.LiveConnectConfig(
                response_modalities=["AUDIO"], system_instruction=SYSTEM_PROMPT, tools=TOOLS)
            async with client.aio.live.connect(model=model, config=config) as session:
                await session.send_client_content(
                    turns=types.Content(role="user", parts=[types.Part(text=instruction)]), turn_complete=True)
                # receive() yields one model turn. Tool responses are sent explicitly;
                # audio/prose is ignored while collecting the validated tool artifact.
                async for message in session.receive():
                    usage = getattr(message, "usage_metadata", None)
                    count = getattr(usage, "total_token_count", None)
                    if type(count) is int and count >= 0:
                        # Provider totals are snapshots, not independent chunk counts.
                        tokens = count
                    if getattr(message, "tool_call_cancellation", None):
                        raise ValueError("Live expert cancelled its proposal.")
                    if getattr(message, "go_away", None):
                        raise ConnectionError("Live expert session ended before completion.")
                    server_content = getattr(message, "server_content", None)
                    if server_content and getattr(server_content, "interrupted", False):
                        raise ValueError("Live expert composition was interrupted.")
                    tool_call = getattr(message, "tool_call", None)
                    if tool_call:
                        calls = tool_call.function_calls or []
                        if proposal is not None or len(calls) != 1 or calls[0].name != TOOL_NAME:
                            raise ValueError("Live expert must make exactly one allowed proposal tool call.")
                        call = calls[0]
                        proposal = _validate_proposal(call.args)
                        await session.send_tool_response(function_responses=[types.FunctionResponse(
                            id=call.id, name=call.name, response={
                                "accepted": True, "status": "candidate_only", "executed": False,
                                "message": "Candidate received. Independent testing and promotion remain required.",
                            })])
                if proposal is None:
                    raise ValueError("Live expert completed without a reusable-skill proposal.")
        return {"steps": proposal, "model_calls": 1, "tokens": tokens, "model": model}
    finally:
        await asyncio.wait_for(client.aio.aclose(), timeout=CLOSE_TIMEOUT_SECONDS)
