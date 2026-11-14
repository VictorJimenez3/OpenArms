# Demo interfaces

## Canonical student application

The primary app is `agentic/openarms_lab/` and `ui/lab/`; see the [runbook](LAB_RUNBOOK.md). Browser REST mutations and `/api/sessions/{sid}/events` share one `Lab` lifecycle with `/api/sessions/{sid}/live`. Gemini audio streams continuously after one microphone gesture. Live tools select experiments, record predictions, propose/correct actions, cancel, prepare the next MOCK trial, answer quizzes, read state/instructions, and request STOP. No tool supplies motor targets.

Concrete cross-area example: select `buoyancy_trial`, record a prediction, then `request_action {"text":"test sample at A in B"}` produces a pending `request_id`, `transfer.v1`, and `{"source":"A","destination":"B","object":"sample"}`. Nothing executes until UI confirmation or a fresh explicit input “confirm” bound to that exact current request. `student_confirm {"request_id":"<current-id>"}` is independently gated by the server's input transcription; a model cannot manufacture consent fields. Correction cancels the old proposal and creates a new ID. Replays, expiry, disconnect and STOP revoke old requests. Selection, prediction and preparation never imply confirmation.

The current-checkout `TransferRunnerAdapter` maps `request_id` to legacy `plan_id` and obtains separate `authorize(plan)` approval before execution. It serializes physical ownership, rejects mismatched results, and preserves cancellation/STOP without blind motion retries. Physical setup assumptions and completion without independent placement evidence remain UNKNOWN. Mock execution uses the existing agentic catalog/validator and no hardware import. Dilution binds existing `add_sample` primitives only in mock mode; the physical bench receiver C differs from the lesson receiver B and is not connected here.

Notebook events correlate requests, state, transcripts, model usage, controller receipts, observations and quiz feedback. Observations retain `MOCK`, `MODEL-PREDICTED`, `REAL`, `SIMULATED` or `UNKNOWN` provenance. A generated transfer→observe skill remains a candidate until independent mock testing and explicit promotion. Physical approval is a separate scope. Future simulators implement the backend Protocol without changing this lifecycle.

## Legacy phone demo

The current demo transfers one mandarin from named station A to B. Simulation is deferred. The phone displays the interpreted transfer before confirmation; this is a text proposal, not a motion simulation.

## Voice and planning

The SwiftUI phone sends PCM audio to the Mac WebSocket relay. Local Whisper produces a transcript. Headless AGY (`gemini-3.8-flash-high`) interprets intent and invokes the local MCP tool `submit_plan` with:

```json
{"object":"mandarin","source":"A","destination":"B"}
```

Natural phrasing and synonyms are interpreted by the agent. There is no sentence-matching gate for movement commands. The tool validates the fixed action and returns:

```json
{"plan_id":"plan-<uuid>","object":"mandarin","source":"A","destination":"B","status":"preview_ready","preview":"placeholder","coordinates":null,"execution":"mock_only"}
```

`execution: mock_only` describes the planning tool's capability: it never moves hardware. A separately selected runner owns execution. Each revised instruction clears the pending proposal and requires a new plan ID and confirmation. Exact `confirm` / `I confirm` consumes the current session's pending plan once. `confirm <plan_id>` must match; an old ID never executes the new plan. `cancel` and `stop` bypass the model. Reconnect creates fresh state.

## Robotics runner handoff

Implement `TransferRunner` from [runner.py](../research/joseph/iphone-voice-bridge/relay/runner.py). Expose a zero-argument factory in your robotics module. Start the demo with `--runner your_module:create_runner`; Python must be able to import that module. Without this flag, every execution is mocked.

- Declare `mode = "physical"`.
- `async authorize(plan) -> bool` obtains bench operator approval for this exact plan ID before motion. False means zero calls to `execute`.
- `async execute(plan) -> ExecutionResult` performs the taught A-to-B motion once, checks reachability/current station state locally, and returns the same plan ID, `mode="physical"`, `status` (`completed`, `failed`, `stopped`, or `unknown`), `operator_authorized=True`, and observed `placement` or `None`.
- `async stop()` is idempotent and promptly stops/holds safely. It is called on cancellation, disconnect, shutdown, and execution failure. The runner must propagate cancellation and must not leave an untracked background motion running.

The relay does not retry motion. A completion report is not proof of placement; return `placement=None` unless independently observed. Keep serial configuration, motor limits, taught poses, and operator approval in the robotics module. The LLM never gets joint targets or motor access. The canonical student application now supplies a current-checkout adapter; this historical relay description does not establish bench verification.

Voice is half-duplex: speech is not captured while processing or playing a reply. Spoken `stop` is therefore not a hard real-time emergency stop. The physical operator must retain the bench stop; phone End/disconnect cancels the task and calls the runner's stop hook.

## Acceptance checks

The [rehearsal](../research/joseph/mandarin-verification/voice_rehearsal.py) covers generated speech through actual Whisper, AGY MCP invocation, proposal, confirm or cancel, and mock result. Tests also cover changed destinations, stale IDs, duplicate confirmation, subprocess cleanup, operator rejection, and wrong result identity. Physical success remains unverified until the real runner is connected and bench-tested.

## Local water bench

The supervised CLI uses the existing agentic plan and shares the physical pose executor. With source fixture A and receiver C fixed, the minimum request is:

```json
{
  "plan_id": "bench-pour",
  "steps": [
    {"action": "add_sample", "args": {"source": "A", "into": "C", "portions": 1}}
  ]
}
```

The catalog expands this to `pick → pour → return_cup → home`. The local operator approves the start and confirms visible lift before the pour. Receipts log the controller's result and the separate operator observation. The phone relay still dispatches mandarin transfers. [Bench setup and demo tiers](WET_LAB.md)
