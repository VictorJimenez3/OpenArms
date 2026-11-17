# OpenArms handoff for Devin or a teammate

> **Historical (HackPrinceton, November 2026).** This document is no longer maintained and may describe plans, scenes, owners or rules that no longer apply. [HANDOFF.md](../../HANDOFF.md) is current. Where they differ, trust the code.

For Duc’s current simulator integration, start with the [Duc handoff and Claude prompt](duc-simulator-handoff.md). The water run below is the earlier baseline.

Work in `OpenArms-student-loop` on `victor/agentic-student-loop`. Victor owns the shared AI harness and student loop in `agentic/`. On November 14 he asked to implement the agentic system first using text, keep speech lower priority, then integrate and rapidly evaluate the teammate's runnable simulator when available. His project direction is one supervised live SO-101 activity and several simulation examples. Use Victor's handoff, current branch code and verified runs to resolve stale information. Joseph's issue comments and mentions are outside this assignment. The old standalone 20 mL dilution video is historical and supplies no requirement for the next setup.

Read in this order: [AGENTS](../../AGENTS.md), [project objective](../../PROJECT_OBJECTIVE.md), [Victor's student/agent flow](student-and-agent-flow.md), [implementation plan](../../docs/superpowers/plans/2026-11-14-openarms-agentic-system.md), and [interfaces](../../docs/INTERFACES.md). Treat the flow document's baseline table as historical. The newer implementation and this receipt describe the current branch. Use the existing app, expert adapters, registry, observer and executor. Keep the student in charge of one action at a time. Questions, corrections, observable results and the student's next choice belong to the same session. Prediction and reflection are optional.

## What is implemented

- PR #25 at `4f9c3ec` is included in Victor's branch. It supplies shared conversation handling and Gemini Live speech when a key is configured. The local text draft was reconciled with that implementation. A sample correction now preserves the original task intent and the validated replacement sample. Scope changes revoke earlier approval. The approved proposal remains a prerequisite for execution.
- `task_loop.py` validates the current setup, typed arguments, and known cases of negated, unsupported or compound requests. For the two-vessel scene it also blocks explicit out-of-scope sources, receivers, donor return targets, amounts and known chemistry requests before a proposal can be presented. The executor checks readiness and the independent observer checks the outcome. If motion has already run, the expert can request another observation under fresh consent while preserving the original controller receipt and approved checks. The task allows a single motion dispatch. General natural-language request coverage remains open.
- `contracts.py` exposes the executor and observer interfaces. The app supports the synthetic bench, indicator regression scene (`metered_dropper`), and upstream `two_vessel` scene from `main` at `72c5ea0`, reconciled at `8682661`. Enable the water scene with `OPENARMS_EXECUTION=mujoco OPENARMS_SCENE=two_vessel`. It supports one premeasured portion of water A→C, donor return to A, and HOME. The shared app gets a fresh frame before dispatch, then captures a separate result image. The scene uses both assessment replays and its own skill admission scope. [Upstream simulator evidence and limitations](../joseph/reconciliation-2026-11-14/README.md)
- Synthetic replay now scores a case as recovered only when the task completes, the controller reports completion, and independent outcome checks pass. Create a fresh data directory for new qualification. Historical receipts retain the scoring rules under which they were generated.

## Recorded evidence

The earlier fixture rehearsals requested Codex `gpt-6.1-sol` at medium effort. This branch's water runs requested high effort. CLI telemetry left the actual model identity empty.

| Run | Observed result | Local receipt |
| --- | --- | --- |
| Real expert, synthetic images, clear versus obscured checkpoint | Clear run completed. The obscured run returned `UNKNOWN`, then the expert requested the secondary view and proposed an observation-only revision. Fresh confirmation produced a readable result. Both runs dispatched one action. A both-obscured control remained `UNKNOWN`. Total time was 72.8 s clear and 108.4 s obscured for this pair. | `/tmp/openarms-evidence.BCbvlG/results/summary.json`, plus `clear/state.json` and `adaptive/state.json` in that directory |
| Real expert, current indicator MuJoCo cold and warm | On scope `mujoco-2f834c3ed2930865`, the same skill version and bindings ran with 7 cold and 0 warm expert calls. Time to proposal was 47.67 s cold and 0.62 s warm. Controller time was about 2.17 s on both runs. Both outcomes came from rendered pixels. | `/tmp/openarms-scoped-mujoco.40mtS8/results/summary.json`, `cold.json`, `warm.json` |
| Real expert, mock baseline and skill revision | A fresh mock session admitted a skill and reused it with 7 cold and 0 warm expert calls. The expert subsequently added secondary-view recovery to that mock-admitted skill after a recorded failure. | `/tmp/openarms-mock-baseline.aIZIk5/results/summary.json`, `/tmp/openarms-429bd20-mock-improvement.m72uUL/results/summary.json` |
| Replay under tightened scoring and a held-out condition | The exact mock definitions recovered 9/24 and 12/24. Combining a shifted source with an obscured primary view, outside the frozen matrix, gave 0/3 and 3/3. This rechecked the definitions in the synthetic fixture. | `$TMPDIR/openarms-mock-improvement-v2.pm_druir/summary.json` |
| Two-vessel request validation, same pinned expert and real scene | On `8682661`, six explicitly unsupported requests all received the nominal A→C proposal. Independent review exposed three more variants involving quantity wording, a named donor at the wrong station and return of the sample cup. All nine now yield no pending proposal and zero dispatches. The supported request with explicit cup return still completes after exact consent. | `agentic/tests/test_two_vessel_runtime.py`, `outputs/handoff/two-vessel-final/verification/` |
| Real expert, two-vessel MuJoCo cold and warm | The expert authored `water_portion_a_to_c`, the host admitted that version after replay, and an equivalent student request reused the admitted version. Both trials completed one simulated pour, returned the donor to A and reached HOME. A separate frame showed water appearance and the donor at A. | `outputs/handoff/two-vessel-final/summary.json`, `cold.json`, `warm.json`, `student-follow-ups.json` and `evaluations/ed06ee747b9c4af8a128e1a296bae66d/receipt.json` |

### Two-vessel run index

Live provider source `6eeda17`, scene `two_vessel_docks` version `1`, camera `two_vessel_overview.v1`, execution scope `two-vessel-b3a2f1880663afe4`. Cold input was “Please pour one premeasured portion of water from A into C, return the donor to A and go HOME, then check the result.” The student asked “What are you doing?” and “What happened?” in the same session. The result answer matched the independent observation. “Prepare a new trial” reset the scene before the student made the equivalent request “Transfer the prepared water portion from A to C and verify the receiver after returning the donor and going HOME.” The rehearsal harness presented and confirmed each plan, versions `1` and `2`, respectively.

| Event | Cold, new skill | Warm, admitted skill |
| --- | ---: | ---: |
| Request acknowledgment by the server | 2 ms | 6 ms |
| Request to exact proposal | 88.08 s | 1.08 s |
| Proposal to scripted confirmation | 31 ms | 17 ms |
| Confirmation to first controller progress | 21.48 s | 3.15 s |
| Controller wall time | 6.14 s | 6.08 s |
| Request to independent observation | 115.80 s | 10.45 s |
| Total expert model calls | 8 | 0 |

The cold planning run used five calls and reported 136,367 input-plus-output tokens. The cold student-facing completion message arrived at 129.0 s including post-observation expert review. The warm request completed through the admitted skill. Both 594-frame recordings encode 19.8 s of simulated motion. The replay gate checked negative routes, outcomes, consent and STOP. The initial attempt started from merge `8682661` and completed the cold simulated move. Editing a scope-hashed source during that attempt caused evaluation to reject the stale source scope. The completed runs used fresh directories. These timings reflect this machine, scripted confirmation and these runs.

The authenticated water HTTP smoke used the same scene with a deterministic test expert. It rejected confirmation before presentation and after STOP, served the real video and independent observation, and let the student reset for a second trial in the same session. It dispatched once across the completed and cancelled trials. Local receipt `outputs/handoff/two-vessel-final/http-smoke.json`.

After independent review tightened quantity and station wording, the scope changed to `two-vessel-138ce41cb1105132`. A fresh replay took the saved Codex draft, bound current scene evidence, and passed admission and warm reuse in the new scope with two controller dispatches and zero model calls. The new scope therefore has replay evidence while the live-model timings above come from `6eeda17`. Local receipt `outputs/handoff/two-vessel-reviewed-replay/summary.json`.

The combined Python suite passed 588 tests. All 38 desktop and mobile browser checks and five browser audio unit tests passed. The iPhone sources parsed and the portable protocol source typechecked. The Swift tests stopped at `No such module XCTest` with Command Line Tools. Project and plist validation passed separately. No Gemini key was available in this session. Browser speech transport, consent, interruption and playback were exercised with fixtures. Upstream already ran generated Gemini Live student audio through this water scene. Mac and iPhone audibility remain open. Physical operation is disabled in this app. Local artifacts may expire or need to be transferred separately. [Upstream voice receipt](../joseph/reconciliation-2026-11-14/gemini-water-receipt.json)

## Where to resume

1. For the demo, run the existing app with `OPENARMS_EXECUTION=mujoco OPENARMS_SCENE=two_vessel` and a fresh data directory. Rehearse the exact water request below and prequalify the active skill on that installation. Use `metered_dropper` as the second prepared simulation example. The server command and access-grant procedure are in the [lab runbook](../../docs/LAB_RUNBOOK.md).
2. For a new simulated action, require typed parameters, setup identity and revision, readiness/reset, STOP, and a separately specified observable. Re-evaluate in the destination scope. An observation-only rescue can finish the student's task under fresh consent. Admitting a reusable recovery requires authoring and evaluating that recovery in the skill itself. General request coverage remains bounded. A read-only proposal can still omit part of a mixed request. For water skill improvement beyond reuse, use a frozen independent scoring rule and held-out variation on a scene that can execute from that variation. The current water scene uses one overview camera, reconstructed nominal geometry, and visually modeled water appearance. Pose adaptation, measured volume, chemistry, and a water-specific D4 gain remain open. [Water-scene evaluation limits](../joseph/reconciliation-2026-11-14/README.md#review-and-limits)
3. With Gemini credentials, repeat the speech rehearsal using the same app and consent path, then verify human audibility on the actual judging device. Physical operation requires the approved bench and supervised qualification. A separate machine needs the branch contents and its own provider credentials.

## Reproduce from the repo root

```bash
export PYTHONPATH=agentic:simulation:.
uv venv --python 3.12 .venv-lab
uv pip install --python .venv-lab/bin/python -r agentic/requirements-lab-dev.txt -e 'simulation[dev]'
.venv-lab/bin/python -m pytest agentic/tests simulation/tests --import-mode=importlib -o asyncio_mode=auto -q
.venv-lab/bin/python agentic/scripts/student_decision_rehearsal.py --out outputs/decision-rehearsal
.venv-lab/bin/python agentic/scripts/full_loop_rehearsal.py --execution mujoco --out outputs/mujoco-cold-warm
.venv-lab/bin/python agentic/scripts/full_loop_rehearsal.py --execution mujoco --scene two_vessel --expert-profile sol --reasoning-effort high --out outputs/two-vessel-cold-warm
.venv-lab/bin/python agentic/scripts/full_loop_rehearsal.py --execution mock --out outputs/mock-cold-warm
.venv-lab/bin/python agentic/scripts/improvement_rehearsal.py --baseline outputs/mock-cold-warm --out outputs/mock-improvement
```

Reuse an existing `.venv-lab` if present. Each rehearsal needs a fresh output directory. Run the provider-free checks first to conserve account usage. The real-expert scripts use the local authenticated CLI and accept `--expert-profile` and `--expert-config`. Each provider uses its own local credentials.

Suggested prompt for Devin or Codex:

> Continue Victor's OpenArms work on `victor/agentic-student-loop`. Read `research/victor/devin-handoff.md`, the linked plan, and the project objective. Reproduce the existing scene before changing it, then start at the first remaining step whose prerequisites are available. Keep the existing session, expert, and skill registry. Preserve exact student consent and direct STOP. State which simulator revision you tested and report the evidence gaps.
