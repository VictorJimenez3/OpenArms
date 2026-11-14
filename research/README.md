# OpenArms research

Check the questions below before starting new research or repeating a test. Use the source links to confirm what was tried and which setup the result applies to. Search from the repo root for other questions or alternate terms.

```sh
rg -ni -g '*.md' 'follower|teach.*pose|waypoint|teleop' research/
```

| Question | Current answer | Evidence |
| --- | --- | --- |
| Can the SO-101 run in Isaac 5.1 on Rutgers RTX? | Isolated installation and headless recorder prepared; GPU allocation, actual launch and manipulation remain unverified. | [Runtime bring-up evidence](stefanie/isaac-runtime-bringup.md) |
| How do two cameras and a teaching trace become an inspectable skill? | Offline capture/replay, checkpoint evidence, versioned candidates, guarded geometry and measured GPU comparisons are runnable; actual-cup qualification remains pending. | [Bench tooling and measured handoff](../bench_vision/START_HERE.md) |
| What is the current demo, and what is verified? | Mandarin A-to-B transfer. Phone installed; intent-based AGY/MCP and mock confirm/cancel rehearsed. Physical runner integration pending; simulator deferred. | [Runbook, next steps, and human to-do](joseph/mandarin-transfer-handoff.md) |
| How do we teach poses or record waypoints on the follower? | Two-arm teleoperation is documented. Harness v3 proposes teaching poses with the leader and running the demo on the follower. The demo motion still needs bench trials. | [Firmware setup](../firmware/README.md#3-teleoperate) · [Pose teaching](duc/harness.md#layer-4-preprogrammed-scripts-joseph-firmware) |
| Can the arm run if simulation preview times out? | Open. The project brief puts preview before physical execution. Duc's draft proposes continuing without a preview after three seconds. Try the timeout against a mock executor and agree on the behavior in the shared interface. | [Project brief](../docs/PROJECT.md#first-integration) · [Preview proposal](duc/harness.md#plan-format-brain--validator--teacher--runner) · [Mock experiment](joseph/TODO.md#first-pass) |
| Why keep model calls out of the motor loop? | Astranomy's simulated direct-control trials motivate keeping motion local. OpenArms still needs its own command-to-preview timing. | [Paper takeaway and limits](duc/harness.md#part-a-design-rules-from-astranomy) · [Latency experiment](joseph/TODO.md#follow-up) |
| What can the model ask the arm to do? | Duc's proposal gives the model a small action catalog and puts the executor behind validation and teacher approval. The final catalog depends on the demo action. | [Action catalog](duc/harness.md#part-b-tool-layers-and-the-action-catalog) · [Arm tool brief](duc/arm-tools.md) · [Draft team handoffs](duc/agentic-plan.md#finding) |
| How does Duc split agentic work into lanes? | The foundation defines shared types and examples, then the core, brain, and API lanes build against them. | [Build plan](duc/harness.md#agenticopenarms_agent-duc-built-in-ralph-lanes) · [Workflow snapshot](#ducs-agent-workflow) |
| How could OpenArms fit the Best Physical AI Hack track? | The note covers the sponsor's hardware and AI criteria, prior winners, and how they apply to OpenArms. | [Track guidance and OpenArms assessment](victor/tracks/best-physical-ai-hack-track-openarms.md) |
| How could OpenArms fit Best Hardware Hack? | The note covers the award criteria and how OpenArms could demonstrate creative hardware integration. | [Hardware track notes](victor/tracks/hackprinceton-best-hardware-hack-openarms.md) |
| How could OpenArms fit the Education track? | The note assesses how OpenArms could make hands-on lab learning more accessible and interactive. | [Education track notes](victor/tracks/hackprinceton-education-track-openarms.md) |
| How could OpenArms fit Amazon’s Best Practical AI Innovation track? | The note assesses how a voice-guided lab assistant could make hands-on experiments more accessible in everyday use. | [Amazon track notes](victor/tracks/hackprinceton-amazon-practical-ai-openarms.md) |
| What should the OpenArms simulation help students learn? | Research recommends pairing one student-chosen physical observation with a modeled result and one additional virtual trial. Dilution is conditional on a comparable measurement. | [Educational simulation and competitor research](victor/educational-simulation.md) |
| Which lab barriers remain after existing accommodations, and where might OpenArms help? | Published cases document barriers to manipulation and participation. The report compares student-directed assistance, adaptive equipment, remote labs and simulations, and identifies what needs validation with students and institutions. | [Accessibility and market validation](victor/accessibility-market-validation.md) |
| Can a captured transfer be adapted? | A supervised +5° pickup correction and higher carry placed the mandarin on the red card. Two webcams confirmed the result. | [Wet-lab plan and transfer evidence](../docs/WET_LAB.md#recovery-and-evidence) |
| Which laboratory experiments can OpenArms support with the SO-101? | Test controlled buoyancy first. Effervescence can reuse the same release. Qualitative pH depends on a validated dip or dose and a readable result. Bench trials are pending. | [Laboratory experiments and feasibility report](victor/laboratory-experiments-and-feasibility.md) |

## Research to-do

See [Joseph's experiment checklist](joseph/TODO.md) for simulation, bench runs, and teammate walkthroughs. Save a short result in the owner's research folder and link it from the checklist and the relevant index row.

Use the research question as the note title. Write the finding and what it changes for OpenArms. Include the commit, setup, trial counts, failures, and evidence links for experiments. For papers, link the source and explain where its results apply and what needs a local check. Label the evidence as paper, sim, mock, physical bench, or teammate walkthrough. Keep open team decisions in [PROJECT.md](../docs/PROJECT.md) and agreed handoff examples in [INTERFACES.md](../docs/INTERFACES.md).

## Duc's agent workflow

The [workflow snapshot](duc/workflow/) is from Duc's `duc` branch at `85a7914`. The [foundation](duc/workflow/tickets/master.md), [core](duc/workflow/tickets/core.md), [brain](duc/workflow/tickets/brain.md), and [API](duc/workflow/tickets/api.md) tickets describe the planned sequence and checks.

The original [Ralph scripts](duc/workflow/ralph/) expect Duc's local `tmp/` layout, a `duc` branch, and Claude Code. Use the snapshot as reference. Follow the root [worktree rule](../AGENTS.md) before creating a lane worktree.
