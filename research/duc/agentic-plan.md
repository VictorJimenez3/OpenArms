# How does the agent harness fit with the rest of OpenArms?

Duc's working plan for `agentic/`, as of Fri Nov 13, 2026, ~23:30. The design behind it is [harness.md](harness.md).

## Finding

**Decisions for `agentic/`** (Duc, Nov 13):
- The brain sees three actions only: `add_sample(source, into, portions)`, `wait(seconds)` and `look(station)`. Pick, pour, return-the-cup and home happen inside `add_sample`, on the executor's side.
- A "portion" is one pre-filled mini-cup, tipped all the way out. Portion size comes from the cup, not from timing. This is a proposal to Joseph; the executor is his.
- The brain is Claude Sonnet 5.5, with one model call per student turn. It never drives the motors.
- The agent server runs on the laptop plugged into the arm and calls the executor as ordinary Python. During development, everyone uses a mock arm.
- Teacher approval is one Approve / Reject (+ comment) button in Victor's UI, synchronous only.
- The sim preview is optional. The agent calls Stefanie's `preview(plan)` with a few-second timeout and continues without it.
- A STOP request goes straight to the arm runner and never through the LLM.
- No tests yet; the team decides later.

**How it connects to everyone else** (to be agreed as examples in [INTERFACES.md](../../docs/INTERFACES.md)):

| Handoff | Draft shape |
|---|---|
| Voice relay → agent (Joseph, [PROTOCOL.md](../joseph/iphone-voice-bridge/PROTOCOL.md)) | `dialogue_reply(session_id, turn_id, text) -> {text, lab_stage}` |
| Agent → teacher UI (Victor) | `GET /plans/pending`, `POST /plans/{id}/approve\|reject`, `POST /stop`, a status event stream |
| Agent → executor (Joseph) | `run_step(action, args)`, `stop()`, `state()` |
| Agent → sim (Stefanie) | `preview(plan) -> {ok, video_url?, warnings[]}` |

**How Duc's agents work in parallel:**
- `duc` is Duc's integration branch.
- Each agent lane gets its own worktree and branch, `duc/<lane>`, and owns a separate set of files inside `agentic/`.
- Lanes merge into `duc` after a review; `duc` reaches `main` by PR.
- This follows the per-agent worktree rule in open PRs #1 and #6.

## Evidence

- The team docs and branches as of Nov 13, ~23:00: PRs #1, #5 and #6, and issues #2–#4.
- Joseph's relay mock (PR #5) already says a spoken confirmation is only conversational and that "the team agent owns plan identity and any preview, approval, or execution boundary". That matches this plan.

## Open question

- **What is the demo action: pouring liquid or moving a block?** Joseph's relay mock asks the student to "predict where the block will land". The catalog names depend on this. See open decisions in [PROJECT.md](../../docs/PROJECT.md).
- **Watch out:** the root `.gitignore` ignores any file named `prompt.md`, `PRD.md`, `progress.txt`, `ralph` or `skills`, in every folder. A file with one of those names won't be committed.
