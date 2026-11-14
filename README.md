# OpenArms

A HackPrinceton project for accessible, student-directed lab work. The [student lab runbook](docs/LAB_RUNBOOK.md) is the primary setup: continuous Gemini Live voice, text controls, experiment lessons, confirmed mock actions, quizzes, and a persistent notebook. Start it with `.venv/bin/python -m agentic.openarms_lab`, then open <http://127.0.0.1:8000>.

The [mandarin phone demo](research/joseph/mandarin-transfer-handoff.md) documents the older SwiftUI/Whisper path. Physical bench work and its separate operator approval remain in the [wet-lab guide](docs/WET_LAB.md). Simulation is deferred.

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
