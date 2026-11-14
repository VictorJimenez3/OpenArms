# Demo interfaces

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

The relay does not retry motion. A completion report is not proof of placement; return `placement=None` unless independently observed. Keep serial configuration, motor limits, taught poses, and operator approval in the robotics module. The LLM never gets joint targets or motor access. No physical adapter ships in this change because the teammate's robotics code is pending.

Voice is half-duplex: speech is not captured while processing or playing a reply. Spoken `stop` is therefore not a hard real-time emergency stop. The physical operator must retain the bench stop; phone End/disconnect cancels the task and calls the runner's stop hook.

## Acceptance checks

The [rehearsal](../research/joseph/mandarin-verification/voice_rehearsal.py) covers generated speech through actual Whisper, AGY MCP invocation, proposal, confirm or cancel, and mock result. Tests also cover changed destinations, stale IDs, duplicate confirmation, subprocess cleanup, operator rejection, and wrong result identity. Physical success remains unverified until the real runner is connected and bench-tested.
