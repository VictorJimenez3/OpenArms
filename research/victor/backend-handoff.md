# Backend Handoff For The UI Merge

Branch: `victor/integration-device-expert` (pushed). Keep it; build any merged branch as a new branch from it.

## What this branch is

The agentic backend: one task loop (request, expert plan, exact proposal, student present+confirm, one dispatch, fresh independent observation, STOP), the demo-bench simulation that Duc/Stefanie align to the real arm, Joseph's Smartivity experiments on that same bench, main's Gemini Live voice fixes, and Stefanie's real-arm bench lane with voice.

## How to run

- Simulation demo (any experiment, any expert CLI):
  `OPENARMS_DEMO_EXPERIMENT=volcano|potions|lava_lamp agentic/scripts/run_demo_app.sh devin-sol-fast medium 8011`
  Experts: `devin-sol-fast` (measured), `devin-astra-fast`, `devin-opus-fast`, `sol`/`astra` (Codex), `opus`/`sonnet` (Claude). Run where that CLI is logged in (Terminal for Devin).
- Real arm lane: add `OPENARMS_BENCH=1` plus Stefanie's camera/arm settings from `docs/LAB_RUNBOOK.md`. It is a separate lane (`/api/bench/*`), not the simulation task loop.
- Gemini Live: `GEMINI_API_KEY` in the repo-root `.env` (gitignored, local only). `/api/health` reports `live_configured`.
- Speed (live, simulated): new wording about 13 s to the answer with one expert call; repeats and "do it again" about 9 s with no model call. Fast path is on for the demo bench; `OPENARMS_DEMO_FAST_PATH=0` turns it off.

## API the UI talks to (agentic/openarms_lab/app.py)

- Session loop: `POST /api/sessions`, `GET /api/sessions/{sid}`, `POST .../request`, `.../present`, `.../confirm`, `.../cancel`, `.../prepare`, `.../stop`, `.../condition`, `.../prediction`, `.../reflection`, `.../disconnect`; evidence/media: `GET .../evidence/{id}`, `GET .../media/{name}`.
- Voice: `WS /api/sessions/{sid}/live` (Gemini Live), `WS /api/bench/voice` (real-arm lane voice).
- Real arm lane: `GET /api/bench`, `POST /api/bench/look|request|execute|answer|cancel|stop`, `GET /api/bench/{kind}/{name}`.
- Joseph's separate Smartivity world (`OPENARMS_SMARTIVITY=1`): `GET/POST /api/sessions/{sid}/smartivity...`. It does **not** go through consent; the consented experiments are the demo-bench variants above.
- Pages: `/` (student) and `/developer`.

Invariants any UI must keep: show the exact proposal, then send `present` and a separate `confirm` with the same `request_id` and `proposal_version`; one Stop button calls `/stop` (it also stops the bench lane and any Smartivity episode); never treat controller completion as success, only the observation.

## UI files on this branch that differ from main

`ui/lab/{api.js, app.js, index.html, live-client.js, bench.js, bench-voice.js, style.css, tests/browser.spec.mjs}` plus Joseph's `ui/lab/smartivity.js` and `smartivity.css`. Main has since removed the Smartivity panel (`smartivity.js/.css` and its `index.html` block); a UI overhaul can drop it too without affecting the backend. Experiment selection is currently a startup setting, not an API; a UI picker needs a small backend endpoint.

## Verified before the UI merge

- Full suite: 900 passed, 1 skipped (`agentic/tests simulation/tests`). Firmware: `test_arm.py` 29 passed; camera `test_bench.py` 9 passed, 3 skipped (need a camera) and `test_stations.py` 14 passed. `test_action.py` is a hardware dry-run script, not a test; `test_transfer_runner.py` has no tests.
- Live Gemini voice through the real `/api/sessions/{sid}/live` socket with synthesized student speech (`.devin/harness-loop/voice_check.py`): request heard, plan proposed, preview read aloud and marked presented, spoken "Yes, I confirm. Go ahead." executed exactly once, independent result spoken. Spoken "Cancel" cancelled with no motion; spoken "Stop!" during motion stopped it about 0.4 s after the word.
- Fix found by that check: compound confirmations such as "Yes, I confirm. Go ahead." were refused (nothing ran). Confirmation is now any short phrase made only of confirmation words with an anchor (yes, confirm, go ahead, run it, do it); questions, negations, extra content and "okay"/"sure" alone still are not consent.
- Real-arm lane on the stand-in arm (`OPENARMS_BENCH=1`, no follower port): look, "move the mandarin from A to B" simulated then executed (MOCK); "pour the beaker into the dish" simulates; replaying a real pour needs `OPENARMS_POUR_POSES` plus its layout file.

## Still open

- No physical run: no arm or camera is connected to this laptop yet. Do the first hand run supervised, with Stop in reach.
- The real-arm lane's free-form planner uses the Claude API (`ANTHROPIC_API_KEY`); without it the lane uses fixed patterns only (the standard move and pour commands work).
- Voice timing: about 14 s of each turn is Gemini reading the exact preview aloud. Gemini occasionally read the preview twice or repeated "The active execution was interrupted."; harmless but slow (prompting in `live.py`).
- Independent review of the latest backend changes is still pending.
