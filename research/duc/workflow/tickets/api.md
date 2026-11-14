# Lane: api (branch duc/api). BLOCKED until core lands and M1's relay and teacher-UI examples are agreed.

Estimate: 4 tickets × 8–12 min = **~40–60 min**. Cap **6**. Attended.
Exact payloads come from the agreed examples in `docs/INTERFACES.md`; master writes them into these tickets before launch.

- [ ] **A1 Relay adapter.** `dialogue_reply(session_id, turn_id, text) -> {"text", "lab_stage"}` for Joseph's `relay/dialogue.py` (see `research/joseph/iphone-voice-bridge/PROTOCOL.md`). Keeps one `Brain` per session.
  - Files you own: `agentic/openarms_agent/relay_adapter.py`
- [ ] **A2 Teacher approval API.** FastAPI: `GET /plans/pending`, `POST /plans/{id}/approve`, `POST /plans/{id}/reject` (with comment), and `POST /stop`, which goes straight to the runner and never through the LLM. Approval runs `runner.run` in the background.
  - Files you own: `agentic/server.py`
- [ ] **A3 Status events.** A server-sent events stream of plan status (`awaiting_teacher` → `executing` → `executed|failed|stopped`) for Victor's UI.
  - Files you own: `agentic/server.py`
- [ ] **A4 Sim preview hook.** Call Stefanie's `preview(plan)` with a 3 s timeout before a plan goes to the teacher; on timeout or error, skip it and attach a warning.
  - Files you own: `agentic/openarms_agent/preview.py`
