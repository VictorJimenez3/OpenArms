# Working in OpenArms

- Before planning, assigning or implementing, read [the architecture](docs/ARCHITECTURE.md). Joseph's latest explicit decisions govern product intent; verified code/evidence governs what works; current specifications supersede older plans. Report conflicts instead of changing requirements to match code.
- The physical goal is a student-directed, first-minute **two-vessel A→C pour**, donor return and HOME. Preferred Smartivity magic-tea/citric-acid chemistry and fallback fizz remain physically unverified. [Project](docs/PROJECT.md) owns the demo definition; [wet-lab](docs/WET_LAB.md) owns supervised bench readiness. Prediction/reflection and simulation previews are optional.
- MuJoCo is the active simulator for independent software development; Isaac is parked. Keep simulation provenance distinct from physical qualification. Read [simulation guidance](simulation/README.md) before scene work.
- Read [interfaces](docs/INTERFACES.md) before connecting components, [R1–R6 delivery](docs/FULL_SYSTEM_DELIVERY.md) before assigning work, and [the integration ledger](docs/MAIN_INTEGRATION.md) before merging. Preserve one application task loop, registry and deterministic executor.
- Preserve working Gemini Live speech. Expert inference is separate and selected through shared Codex/Claude profiles; report requested and actual identity without silent substitution. Fable needs an explicit supported provider/model binding. Authentication stays local.
- Each substantial assignment names D1–D4/R1–R6, issue, owned files/worktree, producer/consumer dependency, baseline and acceptance evidence. Coordinate with active owners before editing their files. Use [the team plan](docs/TEAM_WORK_PLAN.md) and [current TODO](research/joseph/TODO.md); avoid competing writers or runtimes. Root/subsystem ignored local TODOs are historical lane notes, not the canonical status; preserve teammate content and resolve conflicts with the coordinator.
- Work in isolated branches/worktrees. Victor retains team integration ownership; Joseph has explicitly authorized the existing reconciliation coordinator to review, integrate and push this reconciliation. Coordinate shared changes and preserve Victor's active work. Preserve dirty teammate files. Refresh from current main before creating a new lane; archive only completed, safely preserved worktrees.
- Keep OpenArms GitHub issue and PR conversations read-only across both Codex accounts and all delegated workers. Do not post or edit comments/replies, submit reviews, request reviewers, tag people or message anyone through GitHub. A new explicit instruction from Joseph authorizing a specific message is required. Keep coordination, handoffs and pre-push receipts in the task chat or local notes; this overrides older posting workflows.
- Before every authorized push, review the actual diff against requirements and record evidence, gaps and reviewer in a local receipt. Substantial work requires independent review. Software tests, simulator results and physical acceptance are separate statuses.
- Preserve operator authorization, deterministic limits and STOP/cancellation. Late tools, reconnect and stale observations cannot restart cancelled work. No unattended motor motion, calibration edits or physical candidate promotion through documentation/software work.
- Before research or repeated trials, check [existing evidence](research/README.md). Preserve recordings, failed attempts, calibration and working fallback behavior. Only Joseph authorizes material product-scope changes.

Codex and Claude use this source; `CLAUDE.md` imports it. Local lane tooling may help execute one bounded ticket, but does not supersede current ownership or shared requirements.

## Ownership

| Owner / active lane | Responsibility |
| --- | --- |
| Victor | Existing `agentic/` owner and `main` integrator; coordinate runtime changes with his student-loop work and physical bring-up. |
| Duc | Firmware controls, calibration and physical bring-up; preserve the existing supervised executor and taught trajectories. |
| Joe (Joseph) | Current focus: MuJoCo, camera-aware agent integration, architecture/docs and coordination; retains browser/iPhone ownership. |
| Stefanie | Existing simulation work and assets remain hers; coordinate file ownership rather than assigning competing scene work. |
| Model two-vessel base plate | Active fixture/measured-vessel lane: `firmware/fixtures/cup_dock/` and its agreed vessel assets. Other lanes consume its handoff. |
| Build Smartivity volcano simulation | Active simulation implementation lane; additional vessels are optional simulation scope, not extra physical demo vessels. |
| Improve harness self-improvement | Existing evaluator/improvement lane; independent trials do not establish D4 until comparable evidence is reviewed. |

The [team plan](docs/TEAM_WORK_PLAN.md) records handoffs. Changes to session, UI, scene or executor seams require agreed examples in [INTERFACES.md](docs/INTERFACES.md) and coordination with the affected owner. Existing hardware work continues while software uses explicitly provisional inputs.

## Harness benchmark

- From this isolated lane, run `PYTHONPATH=agentic:. /Users/victor/OpenArms/device-expert-smoke/.venv-lab/bin/python agentic/scripts/harness_benchmark.py run --out outputs/harness-run-unique`. The existing environment contains the simulator and test dependencies. A fresh output directory is mandatory; retained runs are never overwritten.
- Defaults: real demo-bench simulator with an explicitly deterministic test expert, two repetitions, proposal-only/end-to-end, cold/warm. Proposal-only stops before presentation/consent; late-fault rows cover only their proposal prefix in that mode. STOP controls run end-to-end only.
- Development inputs/expected behavior are in `agentic/benchmarks/cases.jsonl`; machine scoring is in `agentic/benchmarks/harness_grader.py`. Coordinator-owned held-out cases are `.devin/harness-loop/heldout.jsonl`; optimizer workers must not read them. Keep grader, expectations and held-out inputs outside optimizer ownership.
- Cold rows get fresh registries. Warm rows copy one frozen seed admitted by the existing setup-scoped evaluator, separately from timed requests. This common deterministic seed is not a claim that each live cold-authored skill was admitted. Changing source/policy scope requires separate admission.
- `--expert live --expert-profile sol --reasoning-effort medium --executable /Users/victor/.local/bin/codex` uses the existing local Codex account without fallback. Requested/actual identity and token usage stay distinct; null actual identity is unverified. The command can consume the account's allowance.
- Candidate code runs through `--target /absolute/worktree --revision FULL_COMMIT`. `--guarded` enables only the explicit default-off demo checkpoint API and uses a distinct policy scope. Do not edit tested source, runner, cases or grader during a run.
- Compare identical matrices with `harness_benchmark.py compare BASELINE_DIR CANDIDATE_DIR --variable effort --out outputs/comparison-unique.json` or `--variable checkpoint`. Per-case traces, failures, source/protocol hashes and paired-passing speed remain separate. Comparison never adopts a runtime change or promotes a skill.
- Fast verification: `PYTHONPATH=agentic:. /Users/victor/OpenArms/device-expert-smoke/.venv-lab/bin/python -m pytest agentic/tests/test_harness_benchmark.py --import-mode=importlib -o asyncio_mode=auto -q`. The pinned runtime baseline passed `agentic/tests simulation/tests` using the same pytest options. Existing pytest-asyncio and helper-class collection warnings are not hidden.
- Timing uses monotonic wall intervals; scripted approval wait, controller wall duration and simulated motion seconds are reported separately. These are text/simulator checks, not human approval latency, audible speech, physical motion or chemistry qualification.

## Demo app on the current simulation

- This branch includes main's updated `simulation/` (recorded-pour offset correction, `reach.py`, tilted edge grasp, demo `poses.json`). The agentic demo-bench adapter reads `setups/demo` directly, so the new poses are used automatically.
- Seed the base pour once per data directory, and again after any simulator or lab source change (admission is bound to the content-derived execution scope): `PYTHONPATH=agentic:simulation:. .venv-lab/bin/python agentic/scripts/seed_demo_skill.py --data "$PWD/outputs/sim-main-demo-app"`. It uses the app's own Lab, one scripted exactly confirmed SIMULATED execution, a fresh observation and the existing setup-scoped evaluator; no model is called.
- Run the app on that data directory: `OPENARMS_HOST=127.0.0.1 OPENARMS_BENCH=0 OPENARMS_EXECUTION=mujoco OPENARMS_SCENE=demo_bench OPENARMS_DATA_DIR="$PWD/outputs/sim-main-demo-app" OPENARMS_CODEX_EXECUTABLE=/Users/victor/.local/bin/codex PORT=8011 PYTHONPATH=agentic:simulation:. .venv-lab/bin/python -m agentic.openarms_lab`. Phrases matching the seeded skill (for example "pour A into C", "pour the beaker from A into C") route to it with no expert planning call; other supported wording uses the live expert.

## Demo app on the current simulation

- This branch includes main's updated `simulation/` (recorded-pour offset correction, `reach.py`, tilted edge grasp, demo `poses.json`). The agentic demo-bench adapter reads `setups/demo` directly, so the new poses are used automatically.
- Seed the base pour once per data directory, and again after any simulator or lab source change (admission is bound to the content-derived execution scope): `PYTHONPATH=agentic:simulation:. .venv-lab/bin/python agentic/scripts/seed_demo_skill.py --data "$PWD/outputs/sim-main-demo-app"`. It uses the app's own Lab, one scripted exactly confirmed SIMULATED execution, a fresh observation and the existing setup-scoped evaluator; no model is called.
- Run the app on that data directory: `OPENARMS_HOST=127.0.0.1 OPENARMS_BENCH=0 OPENARMS_EXECUTION=mujoco OPENARMS_SCENE=demo_bench OPENARMS_DATA_DIR="$PWD/outputs/sim-main-demo-app" OPENARMS_CODEX_EXECUTABLE=/Users/victor/.local/bin/codex PORT=8011 PYTHONPATH=agentic:simulation:. .venv-lab/bin/python -m agentic.openarms_lab`. Phrases matching the seeded skill (for example "pour A into C", "pour the beaker from A into C") route to it with no expert planning call; other supported wording uses the live expert.
