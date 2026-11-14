# OpenArms: the judging goal

A student directs a real robot arm one action at a time through a responsive Gemini conversation. One narrow physical pH experiment demonstrates independence; the student chooses the steps. Optional: one short reflection at the end.

The technical contribution is a harness that turns expensive successful reasoning into optimized, parameterized, reusable skills and tools. Prove fast reuse, then one meaningful improvement if feasible. Fixed labeled stations, taught trajectories and a hardcoded physical fallback are acceptable. New-position generalization is optional.

[Architecture](ARCHITECTURE.md) owns D1–D4 and acceptance. [GitHub issues](https://github.com/VictorJimenez3/OpenArms/issues) own work; [interfaces](INTERFACES.md) record actual connections; [wet-lab runbook](WET_LAB.md) owns supervised bench setup. Preserve the baseline. Simulation is for preparation, not the physical judging claim.

Smallest judging sequence: student requests a supported physical action -> Gemini acknowledges while it runs -> independent outcome -> another individual student request -> fast reuse of the tested skill -> visible experiment result. Show the cold/warm receipt and, if established, one baseline/candidate improvement. Never slow the baseline artificially to manufacture a speedup.

## Current software delivery

Red-cabbage indicator pH is the only student demo. Gemini Live, the Codex expert, camera tools, execution feedback and evaluated skill reuse share one session/runtime. Physical actuation is disabled for this software delivery; the selected simulator is the newer MuJoCo metered-dropper apparatus. Its analytical color model and independent rendered-image observation retain SIMULATED provenance. This does not close the physical judging milestone above.

Browser and native iPhone use the same server; prediction/reflection are optional, and no lesson or experiment picker gates requests. The developer view contains simulation diagnostics. New trials preserve history, and normal simulation completion returns home. STOP never authorizes a blind physical reset.

Read [the full software contract](FULL_SYSTEM_DELIVERY.md), [runbook](LAB_RUNBOOK.md), and [main consolidation ledger](MAIN_INTEGRATION.md) for current evidence and remaining gates. [Notion physical demo selection](https://app.notion.com/p/41871c9c107e816fab14f3549f6a8fd6) defines bench scope; [wet-lab procedures](WET_LAB.md) govern supervised hardware work.
