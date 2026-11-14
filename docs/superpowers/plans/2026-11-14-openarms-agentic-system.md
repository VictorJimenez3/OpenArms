# OpenArms agentic runtime and simulator implementation plan

**Goal.** Finish the shared agentic runtime so a student's typed or spoken request reaches an expert that uses scene evidence to decide a supported robot action, checks the outcome, and can revise its decision. The student directs each action and decides what to do next.

**Architecture.** One path through `agentic.openarms_lab`: completed student turn → session → active skill or expert → validated proposal → student confirmation → bounded executor → independent observer → expert and student. Keep one action per confirmation. The expert can change a proposal or ask for clarification. The student must approve a changed proposal before it can run.

**Scope.** Victor's branch, `victor/agentic-student-loop`. Work in `agentic/openarms_lab/`, `agentic/scripts/`, `agentic/tests/`, and the associated agentic docs. Track #10 and #19 under D2–D4 / R1–R6. Preserve the app's hardware guard. Prove the runtime on the existing synthetic bench and indicator MuJoCo fixture first. Then exercise the teammate's published simulator through the existing app contract where it exposes bounded execution and independently checkable evidence. The supervised Smartivity activity requires a qualified bench.

**Spec and starting point.** [Project objective](../../../PROJECT_OBJECTIVE.md), [Victor's handoff](../../../research/victor/student-and-agent-flow.md), [repo ownership](../../../AGENTS.md), and [delivery contract](../../FULL_SYSTEM_DELIVERY.md). Start from Victor's branch plus the reviewed conversation changes on `main` at `4f9c3ec` ([PR #25](https://github.com/VictorJimenez3/OpenArms/pull/25)). Gemini Live handles speech. Expert selection stays separate. The PR records generated-audio evidence, including an actual Gemini/Codex correction run, and leaves device audibility and physical qualification open.

## Checkpoint for the next implementer

Start with the [Devin or teammate handoff](../../../research/victor/devin-handoff.md). It records the branch state, evidence, and reproduction commands. Victor's priorities carry forward regardless of who implements the remaining work.

| Work | State at handoff | Resume here |
| --- | --- | --- |
| Text and student control | Shared feature path implemented. The exact-proposal, correction and STOP checks pass on the current branch. | For new actions, extend the existing session regression tests. |
| Robot decisions | A real Codex run changed its observation plan after an unreadable checkpoint and recovered via a second view with one motion dispatch. | Bring the same decision and safety tests to the next runnable setup. Keep current request guards bounded to demonstrated behavior. |
| Skill admission and improvement | Cold/warm runs passed in scoped mock and indicator MuJoCo sessions. The synthetic improvement experiment also ran. | Repeat the improvement command using the new mock-scoped baseline before relying on a revised version for the next demo. |
| Speech | Existing Gemini Live bridge retained. Transport, consent and playback fixtures passed. | Run the generated-audio rehearsal when a local key is present, then a separate actual-device speech check. This can proceed independently of the simulator. |
| Teammate simulator | The published kit preview ran with placeholder poses and a predicted result. | Integrate one runnable action once the teammate provides independent evidence and STOP support. |

## 1. Establish one baseline and consolidate conversation

- [x] Reconcile Victor's draft with the merged conversation implementation. `runtime.py` retains the whole action request through a sample correction. `test_conversation_integration.py` checks that the old proposal expires or is revoked and the replacement needs presentation and fresh consent.
- [x] Exercise the shared session through authenticated HTTP. `test_student_simulator_trace.py` checks `request`, `present`, `confirm`, artifact delivery and `stop` using actual MuJoCo. The conversation tests cover follow-ups, clarification and optional learning steps. The result and next decision stay in the same session.
- [x] Identify the application and supporting scripts in [the agentic README](../../../agentic/README.md). Keep historical tools available to existing callers.

## 2. Make the robot decision path explicit in the existing harness

- [ ] Reuse `PlanDraft`, `SkillDefinition`, `SkillRegistry`, and the task-pinned `ConfiguredExpert` adapters. In `contracts.py`, `skills.py`, and `task_loop.py`, consolidate the existing operation allowlist, argument schema and proposal description so the expert tool context, validator, and executor agree on what the active setup supports. Keep the current operation IDs and persisted skill format. Use the existing backend's `capabilities`, `check_step`, `execute_step`, and `stop`, plus the observer's `inspect_scene`, `localize_objects`, and `observe`. Keep final readiness and state checks with the backend. Keep indicator sample, wording, and science rules at the fixture boundary where the shared path currently depends on them.
- [x] Bind the frozen proposal to the current execution scope at confirmation and dispatch. The scoped registry and passive-history checks keep older admissions and pending work out of the new setup. `test_runtime_review_repairs.py` and `test_simulation_admission.py` exercise the scope boundary.
- [x] Give the expert the full student request, any correction, fresh images, observer features and verified labels. Existing fixture checks cover explicit sample substitution, a negated action, and common requests with a second action or unsupported measurement. Arbitrary phrasings and novel operation coverage remain open. Add cases from the new scene and keep ambiguous requests in clarification.
- [x] Preserve separate controller and observer receipts at each checkpoint. Regression tests prove failed host preflight blocks dispatch even if the expert returns `continue: true`. After dispatch, an observation-only revision keeps the approved checks and uses fresh consent. Failed or unreadable outcomes cannot qualify for admission.

## 3. Demonstrate decisions, learning and fast reuse

- [x] Run `student_decision_rehearsal.py` with the configured expert. In the changed case, both views were obscured for the first post-action observation, then the secondary view recovered. The expert saw the unreadable receipt, inspected the secondary frame, and proposed a new observation. The both-obscured control remained unreadable.
- [ ] Use the existing evaluation path to admit a successful expert-authored skill for that setup. Run an equivalent supported request with the active version and verify zero expert calls on a clean run. Save a small fixed set of supported, ambiguous, negated and unsupported mixed requests, with the expected routes. Keep the baseline unchanged for an improvement run. Use `improvement_rehearsal.py` and the frozen synthetic cases to compare a substantive revision from a recorded failure, such as recovering a secondary view, including a held-out case. Keep the recorded promotion or rejection and its reasons.
- [ ] Save the run index with commit and setup revision, student inputs, tool and image IDs, final proposal version, controller and observation receipts, model calls and tokens, and failures. Record the requested model and actual identity if the provider emits it. Record acknowledgment, plan ready, human approval wait, dispatch, controller finish and first useful result separately. Report the cold/warm comparison on equivalent requests. A single run describes that run's latency.

## 4. Verify speech on the same path

- [ ] Use PR #25's `app.py`, `live.py`, `voice_controls.py`, and `conversation_rehearsal.py` for Gemini Live. Once the text path passes, replay the same request, status question, correction, confirmation and result through the voice adapter. Check that the exact audio preview must finish playback before spoken approval can bind, that one completed turn can dispatch at most once, and that interruption or provider loss leaves text and direct STOP usable. Check a separate STOP run with a delayed expert reply. Record generated audio and actual-device audibility as distinct checks. Text and agentic verification can finish when voice credentials or a device are unavailable.

## 5. Integrate and evaluate the teammate's simulator

- [ ] Pin the teammate's published revision and identify its prepared setup, selected robot action, station and unit bindings, reset, stop and observable outcome. Trace the simulator's normal entrypoint and run its hardware-free smoke check. Treat generated motion previews as previews. If the published revision only renders a preview or lacks a supported action and outcome, record which interface is missing and use the current MuJoCo fixture to finish app integration checks while the teammate's revision is pending.
- [ ] Connect the runnable setup at the existing backend, scene and evaluator boundary. Keep the runtime, proposal protocol, tools and skill lifecycle shared. Preserve the simulator team's files. Check the incoming setup's revision and ports against the scope used to admit skills before enabling an active route there.
- [ ] Use the same student trace and compare clear, ambiguous, failed, cancelled and equivalent warm cases. Record the confirmed action, real simulator diagnostics, independent observation, recovery, and time from input to acknowledgment, plan, dispatch and outcome. Record the scene revision and exact commands. Distinguish model reasoning time from scene startup, motion and consent wait.
- [ ] Use the first measured failure or bottleneck to choose one bounded change and rerun the same cases. Keep the original results for comparison. Report a measured limitation when the candidate provides no benefit or the teammate's supplied interface cannot yet produce the required evidence.

The first integration should supply a revision, operation schema and valid amount or targets, reset/ready signal, executor progress and terminal receipt, stop completion, and an observer result with evidence ID and capture time. Add the app-side registration in `contracts.py` and `app.py` once the setup is verified. Model `check_step`, `execute_step`, and `observe` after the current `MujocoBackend` and `MujocoSceneService`. Keep the existing hardware guard and scope admission to the new setup. Run the basic deterministic API test first, then the real expert, then the same cold/warm case. With a preview-only revision, preserve its canary receipt and leave the connected evaluation pending.

## Definition of done

- [ ] Python integration suite passes with the existing simulation dev dependencies. Run focused tests in `test_conversation_integration.py`, `test_task_loop.py`, `test_task_evidence_review.py`, `test_registry_routing_admission.py`, `test_evaluation_replay.py`, and `test_simulation_admission.py`, then run the full suite from the [lab runbook](../../LAB_RUNBOOK.md). Use the runbook's browser and audio checks for voice-facing changes.
- [ ] A real text run proves the expert used scene evidence and made a different decision when feedback changed. The trace also proves one dispatch after exact confirmation, no dispatch for stale consent, an independent result delivered to the student, and a late expert result discarded after STOP. A separate receipt proves admitted warm reuse, and a scope-change test blocks old admission.
- [ ] Deliver the reviewed branch diff and run index to Victor. Include the simulator revision tested, the exact input, expected event order, example controller/observer receipts, one failure to replay, and the specific gap for any acceptance case still open.
