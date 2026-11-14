# What are we building in `agentic/`, and why this way?

Duc's build brief for the agent harness, Fri Nov 13, 2026. The design is in [harness.md](harness.md) and the plan is in [agentic-plan.md](agentic-plan.md). Nothing below has been written yet.

## Finding

The harness is a set of small Python modules in `agentic/openarms_agent/`, built by three lanes plus one shared foundation. The LLM only writes plans. Plain code checks each plan, the teacher approves it, and only then does the arm move.

```
student (voice or text) → brain (Claude) → submit_plan → validator → [sim preview] → teacher approves → runner → arm
                                ↑                                                                              │
                                └──────────────────────────── notify(result) ←─────────────────────────────────┘
STOP → runner.stop(), never through the LLM
```

### Foundation (master, M0): built first, every lane imports it

| What | File | What it does | Why this way | Alternative |
|---|---|---|---|---|
| Shared types | `types.py` | `Plan`, `Step`, `ArmState`, `ValidationResult`, `ExecutionResult`, `TurnReply`, `ArmError`, and the `ArmPort` protocol (`run_step`, `stop`, `state`) | One place where every lane gets its signatures, so lanes can build in parallel without editing each other's files. Plain dataclasses keep core free of dependencies. | Pydantic models. FastAPI already installs pydantic, and it would validate JSON for free. Worth switching to when the api lane starts if the conversions get tedious. |
| Example JSON | `contracts/*.example.json` | A sample of each plan, arm state, execution result and turn | Teammates read JSON, not Python, so these are what we agree on in `docs/INTERFACES.md` | JSON Schema: stricter, but slower to write and agree on in 36 h |
| Stubs | each lane file | Functions that return canned values (`validate` → ok, `MockArm` does nothing) | Brain can run its Checks before core lands | Lanes wait for each other in sequence: slower |

### Core lane: pure Python, no network, no hardware

| What | File | What it does | Why this way | Alternative |
|---|---|---|---|---|
| Action catalog | `catalog.py` | The three brain actions (`add_sample(source, into, portions)`, `wait(seconds)`, `look(station)`) and `expand()`, which turns `add_sample` into `pick`, `pour` × portions, `return_cup`, `home` | A small menu leaves the LLM fewer ways to go wrong. In Astranomy, 20.2% of failures were the wrong target or plan, and Claude driving the arm directly succeeded only 25.3% of the time. Motion stays in Joseph's executor. | Show the brain `pick`/`pour`/`return` directly: more flexible, more ways to fail. Or let it command joints: ruled out by the 25.3% result. |
| Validator | `validator.py` | Checks a plan against the arm state: unknown action, bad argument, more than 6 steps, empty source, receiver over capacity, not ending at HOME with an empty gripper. Returns the predicted end state. | Fixed rules, the same answer every time, and a one-sentence reason the brain can fix on its own | Ask the LLM to check itself: not reliable. Rely on the sim preview: slower and optional. |
| Mock arm | `mock_arm.py` | A fake `ArmPort` that sleeps ~0.5 s per step, updates state, and can be told to fail at a named step | Everyone develops without the real arm, and failures can be tested on purpose | Use Stefanie's sim as the arm: ties our schedule to hers |
| Plan runner | `runner.py` | Runs the expanded steps in order and stops at the first error or STOP. Reports which step failed. Never retries. | Safety: a failed pour with liquid shouldn't be repeated blindly. The student hears what happened and decides. | Automatic retry: risks a spill. Let the LLM call one step at a time: puts the LLM inside the motor loop and adds a delay before every step. |
| Session notebook | `notebook.py` | Records predictions, plans, results, observations and help requests. Saves to `outputs/sessions/<id>.json`, and `as_text()` feeds them to the brain. | A JSON file is enough for one session and survives a crash | Keep it in memory only: lost on crash. SQLite: more than we need. |
| Demo scripts | `scripts/check_validator.py`, `scripts/check_runner.py` | Print accepted and rejected example plans, and clean, failed and stopped runs | Each ticket needs a Check you can run, and we agreed no tests yet | pytest: later, once the team decides on tests |

### Brain lane: the LLM loop

| What | File | What it does | Why this way | Alternative |
|---|---|---|---|---|
| System prompt | `prompts/brain_system.md`, `prompting.py` | Part D of harness.md, cut down to the three actions. `render_system_prompt(stations, arm_state, objective)` fills in placeholders. | The prompt lives in a Markdown file, so anyone can edit it without touching code. Filling it uses plain string replacement, so no extra dependency. | Jinja2 templates: an extra dependency for a handful of placeholders |
| Claude tools | `tools.py` | `submit_plan`, `record_prediction`, `record_observation`, `look`, `request_help`, `get_notebook`, plus `dispatch()`. `submit_plan` runs the validator and returns the rejection reason or `awaiting_teacher`. It never moves the arm. | Tool calls give us structured plans, and a rejection goes straight back to the model so it can fix the plan in the same turn | Ask for JSON inside the reply text and parse it: breaks easily. A separate planner model: more calls and more delay. |
| Turn loop | `brain.py` | `Brain(session_id).handle_turn(turn_id, text) -> TurnReply`. Each student turn is one model call that loops only through tool calls, on `claude-sonnet-5-5`, keeping the full history. | Fast enough for a live conversation and good at tool use. Keeping the history matches Astranomy's persistent agent: vague-instruction success held at 86.0%→85.3%, while single calls fell from 72.7% to 64.0%. | Opus: smarter, but slower and costlier per turn. The Claude Agent SDK: more machinery than one loop needs. Forcing the model to plan first: Astranomy found no gain (86.0% vs 90.0%). |
| Stop words | `brain.py` | Checks for "stop", "wait" and "cancel" *before* any model call and returns `stop_requested` | STOP can't wait on the network or depend on the model understanding it | Let the LLM decide what counts as stop: slower, and it could miss one |
| Result feedback | `brain.py` (`notify`) | Tells the student in one line what the arm did (or which step failed) and asks what they see | Keeps the student observing and predicting, which is the point of the lab | The UI shows raw status: less accessible for a voice-only student |
| Terminal REPL | `scripts/brain_repl.py` | Type as the student, approve y/n as the teacher, run on `MockArm` | A complete demo before the UI or voice exists | Wait for Victor's UI: blocks testing the brain |
| Brain smoke test | `scripts/brain_smoke.py` | Two paid calls: a vague instruction should get a clarifying question, and a clear one should get a plan awaiting the teacher | The cheapest check that the loop works for real | Mock the model: proves less |

### API lane: links to teammates. Starts after core lands and the handoffs are agreed.

| What | File | What it does | Why this way | Alternative |
|---|---|---|---|---|
| Voice relay adapter | `relay_adapter.py` | `dialogue_reply(session_id, turn_id, text) -> {text, lab_stage}` for Joseph's `relay/dialogue.py` | Joseph's relay already has this plug-in point. Calling it directly in Python saves a network hop. | An HTTP endpoint the relay calls: one more process and one more failure point |
| Teacher server | `agentic/server.py` | FastAPI: `GET /plans/pending`, `POST /plans/{id}/approve\|reject`, `POST /stop` | Victor's UI needs HTTP, and FastAPI is small and typed | Flask: about the same. WebSocket only: harder for the UI to call. |
| Status stream | `agentic/server.py` | Pushes plan and run status to the UI | Proposing Server-Sent Events: one-way, built into browsers, and simple | WebSocket: two-way, which we don't need. Polling: laggy. **Victor decides.** |
| Sim preview | `preview.py` | Calls Stefanie's `preview(plan)` with a 3 s timeout and carries on without it | The demo can't depend on the sim being up | Require a preview before approval: one sim failure stops the demo |

### Built by teammates, not here
- The real `ArmPort` (executor) on the SO-101: Joseph.
- Speech-to-text, text-to-speech and the iPhone bridge: Joseph.
- The teacher approval UI: Victor.
- The 3D sim and `preview()`: Stefanie.

## Evidence

- [harness.md](harness.md), Part A: the Astranomy results cited above (Yang, Khetan, Zhang, CoRL 2026 LBR).
- Joseph's draft PR #5: `relay/dialogue.py` is the adapter, and "the team agent owns plan identity and any preview, approval, or execution boundary".
- Duc's decisions of Nov 13, recorded in [agentic-plan.md](agentic-plan.md).

## Open question

- **Pouring liquid or moving a block?** If it's a block, `add_sample` becomes something like `move_block(from, to)`, and the validator's capacity rule changes. Nothing else in this brief changes.
- **Status stream:** Server-Sent Events or WebSocket. Victor decides.
- **Dataclasses or pydantic in `types.py`:** start with dataclasses and revisit when the api lane starts.
