# OpenArms

A HackPrinceton project giving students physical independence: speak individual actions and a real arm performs them while Gemini remains responsive. The technical contribution is an improving harness that turns expensive work into fast reusable skills. **Read [the demo architecture](docs/ARCHITECTURE.md) before assigning or implementing work.**

The [lab runbook](docs/LAB_RUNBOOK.md) starts the existing software baseline, whose mock lessons are not the target student experience. [Simulation](simulation/README.md) is backstage testing. [Wet-lab setup](docs/WET_LAB.md) describes supervised physical work. The [older phone demo](research/joseph/mandarin-transfer-handoff.md) is historical evidence.

**Physical result:** On November 14 the SO-101 picked up a mandarin from C and placed it at B on the red card. The [run evidence, actual poses, logs and camera frames](research/joseph/mandarin-transfer-2026-11-14/README.md) document the successful supervised, camera-assisted transfer using local `bench-a.json` checkpoints and staged corrections. Phone-to-physical integration and the packaged replay have separate verification status.

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
