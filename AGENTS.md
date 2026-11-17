# Working in OpenArms

Read [HANDOFF.md](HANDOFF.md) before doing anything. It is the current source of truth: what works, how to run and test, which code is live, and which documents are out of date.

The HackPrinceton hackathon is over. Victor Jimenez is the sole developer and makes every product decision. Older documents that name team lanes, owners, D1–D4 or R1–R6 requirements, receipts or ledgers describe a process that no longer applies.

## Product rules

- OpenArms lets a student direct a robot lab partner (Ollie). Every action follows one loop: the student asks, a planner proposes one bounded action, the exact plan is shown, the student confirms that exact version, a deterministic executor runs it once, and an independent observer reports what a fresh image shows.
- Preserve exact consent, the deterministic executor, the independent observation and Stop. A cancelled or stale plan must never run. Late tool results, reconnects and old observations cannot restart cancelled work.
- Label every result as simulated, mock, real or unknown. A controller finishing is not a result. Software tests, simulator runs and physical runs are separate kinds of evidence.
- Keep one task loop, one skill registry and one executor. Do not add a second dispatcher.
- Gemini Live provides speech. The planner is a separate model chosen by profile; report the requested and the actual model and never substitute silently.

## Safety

- Never move the real arm without a person at the bench. Never edit `calibration/`. Never send simulator joint targets to the real arm. Never set `OPENARMS_BENCH_CONFIRM=page` with a real arm.
- Never commit `.env`, API keys, `outputs/` or `LeRobot/`.

## Working practice

- The live product is the student app in `ui/student`, the session runtime in `agentic/openarms_lab`, the demo bench (`demo_bench.py`, `demo_bench_worker.py`), the simulator core in `simulation/openarms_sim`, and the real-bench lane (`bench_lane.py`, `firmware/`). HANDOFF.md section 5 lists what to ignore.
- When a document and the code disagree, trust the code and say so.
- Verify before stating. Run it, or say it was not run.
- Follow the existing style of the file you edit. Do not add or remove comments unless asked.
- Run the test command in HANDOFF.md section 3 before any push. Commit when asked; push only when Victor asks.
- Do not post, comment or review on GitHub unless Victor asks for that specific message.
- Small changes can go straight to `main`. Use a branch for anything risky or large.

## Ownership

Victor owns the whole repository. Former teammates' areas, for history only: Joseph wrote `ui/lab`, the Smartivity world and most of `docs/`; Stefanie wrote the real-bench lane and much of the simulator; Duc wrote the firmware controls and calibration.

Codex and Claude Code both use this file; `CLAUDE.md` imports it.
