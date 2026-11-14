# Dialogue and execution adapters

`DialogueAdapter.respond(Context(session_id, turn_id), student_text)` receives recognized text, or `None` for an opening prompt. It returns speakable `Reply(text, lab_stage)`. Each WebSocket connection owns one adapter. `close()` releases resources and stops the runner; cancellation propagates. Slow work must yield to asyncio.

The demo uses `MandarinDialogue`, `agy_bridge.submit`, and one MCP `submit_plan` tool. AGY interprets movement intent; the tool validates the fixed mandarin transfer. Authoritative plans come from MCP state files, never model prose. The bridge temporarily registers a uniquely named MCP server, preserves existing servers, and removes its entry afterwards. AGY currently has no supported per-session `mcpServers` settings override. Tool permission is automatic for this prototype.

The relay attaches an event sink to record plan lifecycle and timing with the active turn ID. Plan IDs remain stable through proposal, confirmation, and execution. Exact confirmation and cancellation are handled locally. The older deterministic `MockDialogue` remains available with low-level `--dialogue mock` for transport tests.

Physical integration is through the [runner contract](../../../../docs/INTERFACES.md#robotics-runner-handoff), selected explicitly with `--runner module:factory`. A model tool call never invokes a motor. Logs and phone state are not physical authorization or placement evidence.
