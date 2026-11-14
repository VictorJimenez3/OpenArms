# Working in OpenArms

- Before planning, assigning, implementing, reviewing or pushing, read [the demo architecture](docs/ARCHITECTURE.md). Read [the software delivery contract](docs/FULL_SYSTEM_DELIVERY.md) for R1–R6 and the [integration ledger](docs/MAIN_INTEGRATION.md) when merging branches. The architecture defines D1–D4: fast physical student control and responsive conversation first, optimized reusable skills and measured improvement next. pH is the demo context, not a forced lesson sequence.
- Read [current interfaces](docs/INTERFACES.md) before connecting components. Distinguish target behavior, implemented behavior and demonstrated behavior. Preserve the working physical fallback; no unsupported claims.
- Every substantial task names D1–D4, its GitHub issue, owned files, producer/consumer dependency, baseline and acceptance evidence. Keep assignments short. No general framework or research expansion without a demonstrated demo need.
- Keep parallel agents in isolated branches/worktrees. Use the [ownership table](README.md#where-to-start); the integrator owns shared contracts and merges. Reuse existing GitHub issues for decisions/blockers. Do not edit another active lane's files or create a competing runtime.
- Before creating a worktree, pull `main` with `git pull --ff-only origin main` in the main checkout; preserve uncommitted user changes.
- Before research or rerunning an experiment, check [the research index](research/README.md) and search existing evidence. Reuse tools and measurements before adding dependencies.
- Before every push, inspect the diff against D1–D4 and record requirement, evidence, remaining gaps and reviewer in an issue/PR or local receipt. Substantial changes get independent review. First-push receipts can be local; draft/partial work is explicitly labeled. Do not equate unit tests with physical or conversational proof.
- Only Joseph can authorize a material change to the agreed vision. Missing hardware, model access or time is a reported blocker, not permission to replace the product with a scripted mock.
- Preserve physical authorization, deterministic limits and STOP. Simulation is development evidence; do not activate hardware or candidate motions through a documentation task.

Codex and Claude use this same instruction source; `CLAUDE.md` imports it. Select expert providers/models through the shared profile configuration, never by forking the task loop, tool contracts or skills. Provider-specific authentication stays local. Report requested and actual model identity, and never substitute a model silently.

## Assignment format

Issue + D1–D4; concrete outcome; owned files/worktree; dependency and consumer; baseline to preserve; acceptance trace and measured evidence; explicit exclusions. Return commit, checks, evidence and remaining gaps. Integrator reviews before push/merge; keep runtime and documentation synchronized.
