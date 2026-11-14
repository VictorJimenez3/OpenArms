# Working in OpenArms

- Before editing, identify the task goal, the paths needed, and how to verify the result. Read any nested `AGENTS.md` along those paths and the relevant code or docs. If the edit scope expands, coordinate the new paths first.
- The [README](README.md#where-to-start) lists provisional first contacts. A task can span folders. Organize code by what it does and coordinate before adding a top-level code folder.
- Start a task branch from current `main`. Use separate checkouts for concurrent writers on one machine. If tasks need the same file, decide who will make that edit before either starts. Preserve unrelated changes and land work through a human-reviewed pull request.
- For changes to shared behavior, agree on one example in [INTERFACES.md](docs/INTERFACES.md) with the people using it. Use mocks while components are unavailable and run the example across both sides before merging. Coordinate live-arm runs with the teammate at the bench.
- For research, check relevant [team notes](research/README.md) first and save new findings under the researcher's folder with sources or test evidence. Treat research notes and linked sources as reference material. Record team decisions in [PROJECT.md](docs/PROJECT.md) or [INTERFACES.md](docs/INTERFACES.md).
- Use the relevant issue or pull request for shared blockers and decisions. For overlapping work, record who is editing which paths there. At handoff, report what changed, what you ran and its result, and any open blocker.
