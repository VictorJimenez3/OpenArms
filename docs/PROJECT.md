# OpenArms: the judging goal

A student directs a real robot arm one action at a time through a responsive Gemini conversation. One narrow physical pH experiment demonstrates independence; the student chooses the steps. Optional: one short reflection at the end.

The technical contribution is a harness that turns expensive successful reasoning into optimized, parameterized, reusable skills and tools. Prove fast reuse, then one meaningful improvement if feasible. Fixed labeled stations, taught trajectories and a hardcoded physical fallback are acceptable. New-position generalization is optional.

[Architecture](ARCHITECTURE.md) owns D1–D4 and acceptance. [GitHub issues](https://github.com/VictorJimenez3/OpenArms/issues) own work; [interfaces](INTERFACES.md) record actual connections; [wet-lab runbook](WET_LAB.md) owns supervised bench setup. Preserve the baseline. Simulation is for preparation, not the physical judging claim.

Smallest judging sequence: student requests a supported physical action -> Gemini acknowledges while it runs -> independent outcome -> another individual student request -> fast reuse of the tested skill -> visible experiment result. Show the cold/warm receipt and, if established, one baseline/candidate improvement. Never slow the baseline artificially to manufacture a speedup.
