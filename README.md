# OpenArms

A conversational, camera-aware lab assistant that learns reusable skills. **Red-cabbage indicator pH is the demonstration scenario.** Choose vinegar, mild baking-soda solution, or water; predict, review and confirm a trial; examine clearly labeled evidence; then explain the result.

The [student app](docs/LAB_RUNBOOK.md) uses one Mac/iPhone session, Gemini Live voice, an image-aware Codex expert, and a persistent notebook. It supports an explicitly selected MuJoCo lab simulator and a separate synthetic regression fixture. The simplified student view centers on camera, Talk and Stop; `/developer` adds actual simulator frames, recording and agent evidence. Hardware execution is disabled. Observed simulation colors are not physical measurements. The [full delivery contract](docs/FULL_SYSTEM_DELIVERY.md) tracks perception, feedback to both agents, skill admission, reuse and evaluated improvement, including remaining device acceptance. The [session contract](docs/INTERFACES.md) describes their shared transport.

Mandarin transfer is historical hardware evidence, not a student experiment. A supervised C→B transfer succeeded once; its [poses, logs and camera evidence](research/joseph/mandarin-transfer-2026-11-14/README.md) remain preserved. Actual pH bench qualification is separate in the [wet-lab guide](docs/WET_LAB.md).

## Where to start

Start in your own Git worktree and task branch. The table lists provisional contacts. Agree on the specific paths when a task spans areas.

| Code | First contact | Research |
| --- | --- | --- |
| [`firmware/`](firmware/) | Joseph | [`research/joseph/`](research/joseph/) |
| [`simulation/`](simulation/) | Stefanie | [`research/stefanie/`](research/stefanie/) |
| [`agentic/`](agentic/) | Duc | [`research/duc/`](research/duc/) |
| [`ui/`](ui/) | Victor | [`research/victor/`](research/victor/) |

Save findings and evidence using the [research guide](research/README.md). Use [GitHub Issues](https://github.com/VictorJimenez3/OpenArms/issues) for shared blockers or decisions.

- [Agent instructions](AGENTS.md) cover edit scope, working in parallel, and handoffs.
- [Project](docs/PROJECT.md) has the demo goal and open decisions.
- [Architecture and team to-do](docs/ARCHITECTURE.md) covers component ownership, the command flow, and issues you can claim.
- [Interfaces](docs/INTERFACES.md) is where we record examples shared between areas.
- [Arm setup and teleoperation](firmware/README.md) covers LeRobot, calibration, and the physical arms.
- [Wet-lab bring-up and training](docs/WET_LAB.md) covers the first water pour, demo scopes, and reuse across recorded takes.
- [Working project outline](voice-lab-arm-outline.md) has the longer concept and background.
