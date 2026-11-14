# OpenArms

The product gives students control of accessible lab work through responsive conversation, camera-aware expert tools and fast, improving reusable skills. Start with [the runbook](docs/LAB_RUNBOOK.md) to run the app. Read [the architecture](docs/ARCHITECTURE.md) before assigning work and [the consolidation ledger](docs/MAIN_INTEGRATION.md) before merging branches.

**The physical demo is a student-directed two-vessel A→C pour, donor return and HOME.** Preferred Smartivity magic-tea/citric-acid chemistry and fallback fizz still need actual preparation and outcome verification. Use water for calibration. [Project](docs/PROJECT.md) owns the current definition and [wet-lab](docs/WET_LAB.md) the physical checks. First-minute physical action is an unmet target. Prediction and reflection are optional.

The [student app](docs/LAB_RUNBOOK.md) uses one Mac/iPhone session, an image-aware Codex expert, and a persistent notebook. It includes a synthetic regression fixture. MuJoCo is the active development simulator; Isaac is parked. The merged fixed-dispenser regression scene does not yet implement the selected carried-donor kit workflow. Separate two-vessel/camera work is tracked in [the integration ledger](docs/MAIN_INTEGRATION.md). The simplified student view centers on camera, Talk and Stop; `/developer` adds agent evidence and diagnostics, plus simulation frames when that backend is selected. Hardware execution is disabled. Gemini Live provides speech when configured; expert inference is independently selectable. Actual-device acceptance remains open. Observed simulation colors are not physical measurements. The [full delivery contract](docs/FULL_SYSTEM_DELIVERY.md) tracks perception, feedback to both agents, skill admission, reuse and evaluated improvement, including remaining device acceptance. The [session contract](docs/INTERFACES.md) describes their shared transport.

Mandarin transfer is historical hardware evidence, not a student experiment. A supervised C→B transfer succeeded once; its [poses, logs and camera evidence](research/joseph/mandarin-transfer-2026-11-14/README.md) remain preserved. Actual kit/bench qualification is separate in the [wet-lab guide](docs/WET_LAB.md).

## Where to start

Start in your own Git worktree and task branch. Check the [ownership table](AGENTS.md#ownership) before editing and use the [team work plan](docs/TEAM_WORK_PLAN.md) for current handoffs. Victor handles changes to `main`.

Save findings and evidence using the [research guide](research/README.md). Use [GitHub Issues](https://github.com/VictorJimenez3/OpenArms/issues) for shared blockers or decisions.

- [Agent instructions](AGENTS.md) cover edit scope, working in parallel, and handoffs.
- [Project](docs/PROJECT.md) has the demo goal and open decisions.
- [Architecture](docs/ARCHITECTURE.md) covers the command flow; [current TODO](research/joseph/TODO.md) records priorities, owners and evidence.
- [Interfaces](docs/INTERFACES.md) is where we record examples shared between areas.
- [Arm setup and teleoperation](firmware/README.md) covers LeRobot, calibration, and the physical arms.
- [Wet-lab bring-up and training](docs/WET_LAB.md) covers the first water pour, demo scopes, and reuse across recorded takes.
- [Working project outline](voice-lab-arm-outline.md) has the longer concept and background.
