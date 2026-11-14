# OpenArms team work plan

The student chooses each action, reviews what the AI proposes, and decides what to do next based on the result. Victor owns that loop in the app. Joe supplies measured bench assets. Stefanie builds the simulation scene, and Duc tests the feedback it sends through Victor’s loop.

## What we have

- Duc laid the foundation for callable skills so the agent can invoke a validated task without planning it from scratch. The merged app already has a shared expert loop and skill registry. [Current architecture](ARCHITECTURE.md)
- Joe built the Google Live transcription path. Gemini was later withdrawn, and replacement voice and actual-device checks are open. Start the loop rehearsal with text. [Lab runbook](LAB_RUNBOOK.md)
- Stefanie and Duc have been testing pieces of the simulation. Existing scenes give them a starting point. The Smartivity kit is the physical demo target, and Joe still needs to choose its activity. The simulation is for development feedback and optional presentation use. [Kit and bench handoff](ARCHITECTURE.md#kit-scope-and-bench-handoff)

## Ownership

Follow the [root ownership rules](../AGENTS.md#ownership). Use a task branch per owner and hand changes to Victor for integration on `main`.

| Owner | Work and files | Deliverable and handoff |
| --- | --- | --- |
| **Victor** · D1–D3 / R2, R4, R5 · [#10](https://github.com/VictorJimenez3/OpenArms/issues/10), [#19](https://github.com/VictorJimenez3/OpenArms/issues/19) | Own the AI harness and student interaction loop on `agentic-student-loop`. Start with the existing `agentic/openarms_lab/task_loop.py` and focused task-loop tests. Rework the harness as needed within the shared application runtime. Reuse validated skills, clarify ambiguity, surface progress and observations, and let the student confirm, correct or stop. Coordinate UI or executor interface changes with the affected owners. | Save one text-to-result trace and a correction/STOP trace with simulated or synthetic provenance. Give Duc the request, expected event order and sample observation. |
| **Joe (Joseph)** · D1 bench prep · [#12](https://github.com/VictorJimenez3/OpenArms/issues/12) | Scan the lab set and CAD-model the measured base. Own scans and measurements under `research/joseph/` and any base CAD under `firmware/fixtures/`. Check the base and station dimensions against the actual setup. | Hand Stefanie a versioned scan/CAD export with units, scale reference, origin/axes, station labels, measured dimensions and any gaps. Record which parts were measured and which were estimated. |
| **Stefanie** · D1 development support · [#19](https://github.com/VictorJimenez3/OpenArms/issues/19) | Own the simulation scene in `simulation/models/`, `simulation/config/` and the selected simulator’s scene files. Place the SO-101, base and lab components using Joe’s assets. Check scale, alignment and clearance when running one supported action. | Give Duc the scene revision, run/reset instructions, and a sample run with frames and execution status. Record any temporary geometry or unverified fit. |
| **Duc** · D1 firmware / D2–D3 feedback testing · [#12](https://github.com/VictorJimenez3/OpenArms/issues/12), [#10](https://github.com/VictorJimenez3/OpenArms/issues/10) | Own robot controls and calibration. Keep simulation feedback cases and replay inputs under `simulation/tests/`. Exercise the scene through the existing app interface after Victor’s trace is ready. Send runtime issues to Victor and geometry issues to Stefanie. | Return a passing run and an unreadable-observation or cancelled case, with task IDs and frames. Check that the controller receipt and independent observation reach the right task and that an unreadable result is reported as `UNKNOWN`. |

**UI if time.** Joe owns the student-facing clients. Victor can help with scoped UI changes after agreeing on the files with Joe. Joe can pick up AI work the same way with Victor.

## Order of work

1. Work in parallel. Victor uses the current synthetic fixture to rehearse the loop. Joe scans and measures the bench. Stefanie can use existing scene geometry until Joe’s assets arrive. Duc prepares the expected feedback cases using the [session contract](INTERFACES.md).
2. Run the same test from the student side and the simulator side. Use an action the scene supports. The existing indicator fixture takes “Please test the prepared vinegar sample and check the indicator color.” Follow the request through acknowledgment/progress → exact proposal → fresh confirmation → one dispatch → controller receipt → independent observation → student-facing result. Check that the session can take a follow-up while the expert works. A changed proposal needs fresh confirmation. STOP must cancel pending work and prevent a delayed result from reviving it. If the new scene cannot yet run an action, use the existing regression scene and record which scene ran.
3. Duc saves the integrated trace and reports failures to the owner of the affected component. If the event contract needs a change, agree on one example with Victor and the affected owners in [#9](https://github.com/VictorJimenez3/OpenArms/issues/9). Record the app commit, scene revision and result so someone else can replay it. Track spoken-device and supervised physical checks separately in [#4](https://github.com/VictorJimenez3/OpenArms/issues/4) and [#12](https://github.com/VictorJimenez3/OpenArms/issues/12).
