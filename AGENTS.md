# Working in OpenArms

- Before planning, assigning, implementing, reviewing or pushing, read [the demo architecture](docs/ARCHITECTURE.md). Read [the software delivery contract](docs/FULL_SYSTEM_DELIVERY.md) for R1–R6 and the [integration ledger](docs/MAIN_INTEGRATION.md) when merging branches. The architecture defines D1–D4: fast physical student control and responsive conversation first, optimized reusable skills and measured improvement next. The Smartivity kit is the demo target; its activity is undecided. The retained simulation is optional Devpost/presentation material, outside the core architecture and acceptance requirements.
- Read [current interfaces](docs/INTERFACES.md) before connecting components. Distinguish target behavior, implemented behavior and demonstrated behavior. Preserve the working physical fallback; no unsupported claims.
- Every substantial task names D1–D4, its GitHub issue, owned files, producer/consumer dependency, baseline and acceptance evidence. Keep assignments short. No general framework or research expansion without a demonstrated demo need.
- Only Victor works on and pushes or merges into `main`. Everyone else works on their own branch/worktree and hands changes to Victor. Keep one application runtime and coordinate shared changes as described below.
- Before creating a worktree, pull `main` with `git pull --ff-only origin main` in the main checkout; preserve uncommitted user changes.
- Before research or rerunning an experiment, check [the research index](research/README.md) and search existing evidence. Reuse tools and measurements before adding dependencies.
- Before every push, inspect the diff against D1–D4 and record requirement, evidence, remaining gaps and reviewer in an issue/PR or local receipt. Substantial changes get independent review. First-push receipts can be local; draft/partial work is explicitly labeled. Do not equate unit tests with physical or conversational proof.
- Only Joseph can authorize a material change to the agreed vision. Missing hardware, model access or time is a reported blocker, not permission to replace the product with a scripted mock.
- Preserve physical authorization, deterministic limits and STOP. Simulation is development evidence; do not activate hardware or candidate motions through a documentation task.

Codex and Claude use this same instruction source; `CLAUDE.md` imports it. Select expert providers/models through the shared profile configuration, never by forking the task loop, tool contracts or skills. Provider-specific authentication stays local. Report requested and actual model identity, and never substitute a model silently.

Where local `TODO.md` and `.openarms/` lane tooling are installed, pick one folder ticket and use that runner. Review and land or close each lane before opening another for the folder. Shared requirements and current work remain in the architecture and GitHub issues.

## Ownership

| Owner | Area |
| --- | --- |
| Victor | [`agentic/`](agentic/), including the AI harness, expert routing, skills and student-loop behavior. Active branch is `victor/agentic-student-loop`. |
| Joe (Joseph) | [`ui/`](ui/), including the browser UI, and the [native iPhone UI](research/joseph/iphone-voice-bridge/ios/), plus lab scans and [fixture CAD](firmware/fixtures/). Joe can take AI tasks after coordinating the specific files with Victor. |
| Stefanie | [Simulation](simulation/) scenes, robot and lab assets, and simulated motion. |
| Duc | [Firmware controls](firmware/openarms_executor/), [calibration](calibration/) and simulation feedback tests. |

Use the [team work plan](docs/TEAM_WORK_PLAN.md) for current deliverables and handoffs. Coordinate shared session, UI and executor interface changes with the affected owners and record agreed examples in [INTERFACES.md](docs/INTERFACES.md). Before editing files another person is actively working on, agree on who will make the change.

## Assignment format

Issue + D1–D4; concrete outcome; owned files/worktree; dependency and consumer; baseline to preserve; acceptance trace and measured evidence; explicit exclusions. Return commit, checks, evidence and remaining gaps. Victor reviews changes before they land on `main`. Keep runtime and documentation synchronized.
