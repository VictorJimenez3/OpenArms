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
