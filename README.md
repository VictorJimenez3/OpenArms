# OpenArms

A conversational, camera-aware lab assistant that learns reusable skills. **Red-cabbage indicator pH is the demonstration scenario.** Choose vinegar, mild baking-soda solution, or water; predict, review and confirm a trial; examine clearly labeled evidence; then explain the result.

The [student app](docs/LAB_RUNBOOK.md) uses a shared Mac/iPhone session, Gemini Live voice, text controls, and a persistent notebook. This release runs **mock trials only**; reference colors are MODEL-PREDICTED, not physical measurements. Hardware execution is disabled. The [full delivery contract](docs/FULL_SYSTEM_DELIVERY.md) requires background expert planning, perception, execution feedback to both agents, skill registration and measured improvement. Current local components are not yet a completed architecture. The [session contract](docs/INTERFACES.md) records compatible transport repairs.

Mandarin transfer is historical hardware evidence, not a student experiment. A supervised C→B transfer succeeded once; its [poses, logs and camera evidence](research/joseph/mandarin-transfer-2026-11-14/README.md) remain preserved. Actual pH bench qualification is separate in the [wet-lab guide](docs/WET_LAB.md).

## Where to start

Pull `main`, create a branch for your work, and start in your area. Ownership is provisional.

| Code | Owner | Research |
| --- | --- | --- |
| [`firmware/`](firmware/) | Joseph | [`research/joseph/`](research/joseph/) |
| [`simulation/`](simulation/) | Stefanie | [`research/stefanie/`](research/stefanie/) |
| [`agentic/`](agentic/) | Duc | [`research/duc/`](research/duc/) |
| [`ui/`](ui/) | Victor | [`research/victor/`](research/victor/) |

Put research notes and source links in your folder. Use [GitHub Issues](https://github.com/VictorJimenez3/OpenArms/issues) for shared blockers or decisions.

- [Project](docs/PROJECT.md) has the demo goal and open decisions.
- [Architecture and team to-do](docs/ARCHITECTURE.md) covers component ownership, the command flow, and issues you can claim.
- [Interfaces](docs/INTERFACES.md) is where we record examples shared between areas.
- [Arm setup and teleoperation](firmware/README.md) covers LeRobot, calibration, and the physical arms.
- [Wet-lab bring-up and training](docs/WET_LAB.md) covers the first water pour, demo scopes, and reuse across recorded takes.
- [Working project outline](voice-lab-arm-outline.md) has the longer concept and background.
