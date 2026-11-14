# OpenArms: the judging goal

A student directs a real robot arm one supported action at a time through responsive conversation. The student chooses the sequence; prediction and reflection are optional. The technical contribution is an image-aware expert that turns expensive successful work into tested, parameterized skills and demonstrates a measured improvement.

The new target is the **Smartivity My First Science Kit**, with the activity to be chosen later. [Architecture](ARCHITECTURE.md#kit-scope-and-bench-handoff) owns the materials inventory, Victor's bench handoff, D1–D4 priorities and outstanding work. Fixed stations and taught trajectories are acceptable; physical delivery must be independently observed.

## Current software

Main contains one authenticated browser/iPhone session service, a configurable Codex/Claude expert, perception tools, exact proposals, deterministic execution, independent observations and evaluated skill reuse. The default expert is Codex gpt-6.1-sol medium. Gemini Live remains the speech provider; expert inference is independently selectable. Physical actuation is disabled.

The main architecture is conversation → expert/perception → supported skills → supervised execution → independent observations. Simulation is an optional Devpost/presentation extra, outside core acceptance. The retained simulator and synthetic fixture do not implement the new kit. `/developer` shows evidence and diagnostics; STOP never authorizes a blind physical reset.

Start with the [runbook](LAB_RUNBOOK.md). Use the [delivery contract](FULL_SYSTEM_DELIVERY.md), [interfaces](INTERFACES.md), [main ledger](MAIN_INTEGRATION.md) and [GitHub issues](https://github.com/VictorJimenez3/OpenArms/issues) for coordinated work. Earlier Notion/demo selections are historical where they conflict with Joseph's kit decision.
