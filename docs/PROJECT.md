# Project

OpenArms is a HackPrinceton prototype for accessible lab work. The current demo lets a student speak a natural command to transfer a mandarin from station A to B, review the interpreted plan, and confirm it. The bench operator authorizes physical execution.

The phone client is installed on Joseph's iPhone. The Mac relay transcribes speech, uses headless AGY Gemini Flash High to call `submit_plan`, and saves transcripts, timings, and audio. The included runner is mocked; physical robotics integration is pending.

Simulation is deferred for this demo. A simulator does not require a 3D scan, but building one is outside the current command-to-robot test. Named stations and a readable plan are sufficient for this rehearsal; measured coordinates and local motor limits belong to the physical runner.

See the [demo runbook, next steps, and human to-do](../research/joseph/mandarin-transfer-handoff.md), [interfaces](INTERFACES.md), and [arm setup](../firmware/README.md).
