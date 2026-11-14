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
| Robot decisions | A real Codex run changed its observation plan after an unreadable checkpoint and recovered via a second view with one motion dispatch. The water scene also rejects six tested goal substitutions before presenting a proposal. | Keep request coverage bounded to tested phrasing and explicitly qualify new actions. |
| Skill admission and improvement | Cold/warm runs passed on the synthetic bench and both MuJoCo scenes. The real expert's synthetic-scoped revision passed the stricter replay and a held-out case. | Qualify transferred skills independently in each destination scope. Water-specific improvement needs a scenario the nominal skill cannot already solve. |
| Speech | Existing Gemini Live bridge retained. Transport, consent and playback fixtures passed. Upstream ran generated water-scene dialogue through Gemini Live. | Repeat the generated-audio rehearsal with local credentials, then test speech on the judging device. |
| Teammate simulator | `main` at `72c5ea0` supplied a runnable two-vessel water scene through the shared app. Reconciled at `8682661`. | Coordinate measured geometry, alternate views and qualified variation with the simulator team. |

## 1. Establish one baseline and consolidate conversation

- [x] Reconcile Victor's draft with the merged conversation implementation. `runtime.py` retains the whole action request through a sample correction. `test_conversation_integration.py` checks that the old proposal expires or is revoked and the replacement needs presentation and fresh consent.
- [x] Exercise the shared session through authenticated HTTP. `test_student_simulator_trace.py` checks `request`, `present`, `confirm`, artifact delivery and `stop` using actual MuJoCo. The conversation tests cover follow-ups, clarification and optional learning steps. The result and next decision stay in the same session.
- [x] Identify the application and supporting scripts in [the agentic README](../../../agentic/README.md). Keep historical tools available to existing callers.

## 2. Make the robot decision path explicit in the existing harness

- [x] Reuse `PlanDraft`, `SkillDefinition`, `SkillRegistry`, and the task-pinned `ConfiguredExpert` adapters. `contracts.py` supplies the typed primitive schemas used in the expert context and by the registry. The backend advertises and validates the narrower operation and preparation limits for each scene and provides the exact action description where needed. The same task loop calls each backend's readiness, execution and STOP and the independent scene interface. Existing operation IDs and stored skill definitions stay compatible.
- [x] Bind the frozen proposal to the current execution scope at confirmation and dispatch. The scoped registry and passive-history checks keep older admissions and pending work out of the new setup. `test_runtime_review_repairs.py` and `test_simulation_admission.py` exercise the scope boundary.
- [x] Give the expert the full student request, any correction, fresh images, observer features and verified labels. Regression coverage includes sample substitution, negated and compound requests, unsupported measurements, and unsupported water setup routes, amounts and chemistry. Ambiguous cases can request clarification. Arbitrary phrasings and novel operation coverage remain open.
- [x] Preserve separate controller and observer receipts at each checkpoint. Regression tests prove failed host preflight blocks dispatch even if the expert returns `continue: true`. After dispatch, an observation-only revision keeps the approved checks and uses fresh consent. Failed or unreadable outcomes cannot qualify for admission.

## 3. Demonstrate decisions, learning and fast reuse

- [x] Run `student_decision_rehearsal.py` with the configured expert. In the changed case, both views were obscured for the first post-action observation, then the secondary view recovered. The expert saw the unreadable receipt, inspected the secondary frame, and proposed a new observation. The both-obscured control remained unreadable.
- [x] Admit and reuse an expert-authored skill in the existing fixtures. An equivalent warm request used zero expert calls. In the mock-scoped improvement run, the secondary-view revision recovered 12 of 24 cases versus 9 for the original. With a held-out shift and occlusion combined, it recovered 3 of 3 versus 0 for the original. The route tests cover supported, ambiguous, negated, and unsupported requests for the existing fixture.
- [x] Save the setup scope, student inputs, model-call counts, receipt paths, failure and timing comparison in the [run index](../../../research/victor/devin-handoff.md#two-vessel-run-index). Raw receipts retain tool and image IDs, exact proposal versions, controller and observation receipts, tokens and nullable actual identity. The timing separates scripted confirmation from server and controller work.

## 4. Verify speech on the same path

- [x] Retain PR #25's shared Gemini Live path. Exercise proposal playback acknowledgment, transcript generations, interruption and STOP with fixtures. The merged upstream water receipt covers generated student audio, a status question, repeated preview, fresh approval, simulated outcome and STOP.
- [ ] Repeat with live Gemini credentials on the current checkout and verify human audibility on the actual judging device. Neither prerequisite was available in this run. [Upstream generated-audio receipt](../../../research/joseph/reconciliation-2026-11-14/gemini-water-receipt.json)

## 5. Integrate and evaluate the teammate's simulator

- [x] Pin and merge `72c5ea0` for the water-only setup. Its complete action is one premeasured water portion A→C, donor return to A and HOME. The scene offers bounded dispatch, reset, STOP, SIMULATED pixel evidence and a distinct controller receipt. The older `stefanie/joint-map` canary only exercised preview generation and stays a historical reference.
- [x] Exercise the shared app registration for `OPENARMS_EXECUTION=mujoco OPENARMS_SCENE=two_vessel`. Keep backend, scene and evaluator on the same execution scope. Existing tests cover scope isolation, real execution and independent evidence, pre-dispatch rejection and active STOP. The simulator team's implementation came in through the merge.
- [x] Run the real expert through a cold proposal, independent result, student follow-up and equivalent warm request in the same session. Use authenticated HTTP with the actual water backend to verify consent, STOP and media delivery independently of the provider. Run the scene's replay and existing negative tests for ambiguous routes, wrong results, cancellation and stale evidence. The run index records timings and simulator scope.
- [x] Use the measured default-pour substitution to add a fixture guard. Against `8682661`, six of six unsupported requests produced a pending proposal with the deterministic nominal expert. The same six cases now deny the proposal with zero dispatches. The positive donor-return request remains executable after exact consent.

The water evaluator freezes host-owned expected effects and requires both a completed controller and independent image checks. Existing tests cover an observable wrong result and negative admissions. The water scene has provisional geometry and a single overview. For future water skill improvement, add an executable holdout and a pinned independent outcome judge, then compare the same baseline and candidate. [Simulator and evaluator limits](../../../research/joseph/reconciliation-2026-11-14/README.md#review-and-limits)

## Definition of done

- [x] Run the Python suite (585 passing), browser suite (38 passing), and audio unit suite (five passing). The [lab runbook](../../LAB_RUNBOOK.md) contains the invocation. The handoff records the iOS toolchain and live voice limits.
- [x] A real text run used scene evidence and changed its observation choice after an unreadable checkpoint. Exact confirmation, stale consent, independent results and discarded late expert results after STOP are exercised in the simulator and runtime tests. The water run proves admission and warm reuse. Scope-change tests reject old admission.
- [x] Record the branch, simulator revision, inputs, evidence, red/green regression and remaining scope in the [handoff](../../../research/victor/devin-handoff.md).
