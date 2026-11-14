# OpenArms agents

The application entrypoint is `python -m agentic.openarms_lab`. Follow the [runbook](../docs/LAB_RUNBOOK.md) for installation and configuration. `openarms_lab` owns the one authenticated session, task loop, registry, deterministic validation and shared client gateway. The default expert is Codex gpt-6.1-sol medium; the [expert profiles](../docs/EXPERT_MODELS.md) keep model selection separate from task/execution authority. Gemini has been withdrawn and voice is disabled pending replacement.

The Smartivity activity is undecided. An optional Devpost/presentation simulation supports indicator pH using explicit mock or newer MuJoCo execution and independently observed images. Physical execution remains disabled in this app. See [architecture](../docs/ARCHITECTURE.md), [interfaces](../docs/INTERFACES.md), and the [R1–R6 acceptance contract](../docs/FULL_SYSTEM_DELIVERY.md). Optional prediction/reflection never gate control.

`openarms_agent`, its original Claude prompts and older `scripts` are preserved research/fallback components, not an alternate application entrypoint. Do not start a second dispatcher or registry when integrating new capabilities. Firmware and recorded physical evidence retain their separate supervision and authorization requirements.

Victor is the [agentic owner](../AGENTS.md#ownership). His [student and agent flow handoff](../research/victor/student-and-agent-flow.md) covers the current gaps, lab setup changes and first tests. Coordinate shared interfaces with the affected owners. Each substantial assignment names its GitHub issue, requirement, owned files, producer/consumer dependency, baseline, evidence and gaps. [Consolidation status](../docs/MAIN_INTEGRATION.md)
