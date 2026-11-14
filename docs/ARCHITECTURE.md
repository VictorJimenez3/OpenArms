# OpenArms demo architecture

Vision revision: **demo-speed-v2**, reconciled to Joseph's November 14, 2026 two-vessel Smartivity direction. [PROJECT](PROJECT.md) owns the experiment definition.
This is the required direction, not a claim that the implementation is complete.
Provider correction, November 14: Joseph retained Gemini Live for speech and withdrew only Gemini thinking. Keep speech separate from expert inference: Sol, Astra, Opus or an explicitly configured Fable binding use the shared expert boundary. Live quota and actual-device evidence remain separate checks.
[Notion product vision](https://app.notion.com/p/41871c9c107e8133aa70cf1588e620e4) owns product intent; this document translates it into the lean build contract. If they diverge, surface the conflict before changing scope.

## The demo we are building

OpenArms gives a student physical independence at a lab bench. The student speaks individual actions: “pick up cup A”, “put it down”, or a supported pour into the receiver. The student chooses the sequence. The voice agent stays responsive while the arm works and reports what actually happened. Clarify ambiguous references; gently reject inappropriate actions and suggest an alternative. No experiment wizard or mandatory prediction/quiz gates. One brief optional reflection at the end is enough.

The judging proof targets the selected two-vessel Smartivity activity: donor A → receiver C → donor A → HOME. Preferred indicator chemistry and fallback fizz still require bench verification. A visible physical action in the first minute is the target, not a demonstrated result. Labeled fixed stations, calibrated geometry, taught trajectories, a few specialized skills and a hardcoded physical fallback are valid choices. Simulation is backstage testing, not a replacement for the physical student experience. New-position generalization is optional if it threatens reliability.

## Kit scope and bench handoff

The Smartivity **My First Science Kit** packaging lists the inventory below. Its manual has been reviewed in the [shared physical experiment page](https://app.notion.com/p/41871c9c107e816fab14f3549f6a8fd6). Actual inventory, preparation and two-vessel adaptation remain unverified. Do not infer a validated dose, powder composition or robot capability from packaging or manual review.

| Listed equipment | Listed chemicals and liquids |
| --- | --- |
| 2 cups, beaker, flask, spoon, stirring stick, tray, foam parts, mould, balloons, magic tea bag | Citric acid powder, snow powder, baking soda powder, cornstarch powder, food colours, liquid soap |

Exactly two physical vessels are active: a moving donor at A and stationary wider receiver at C. Use water for nearly all calibration; reserve reagents for verification and rehearsals. The preferred magic-tea/citric-acid change and fallback contained fizz are selected candidates, not physically qualified results. Food-color mixing is a motion/visibility test. MuJoCo is active for software development; Isaac is parked. Optional simulation experiments may use additional vessels. Kit support requires validated material bindings, supported motion and independent observations; relabeling the old simulator does not establish it.

Victor's November 14 physical-lab handoff is incorporated as the following remaining work. The raw email stays private; [the wet-lab guide](WET_LAB.md) owns the supervised procedure.

- [ ] **Physical team + existing fixture lane, D1:** verify actual donor/receiver dimensions, fixture fit, calibration and saved-pose versions. The photo-derived vessel models are estimates. Consume the existing two-vessel base-plate lane; no competing fixture writer.
- [ ] **Bench owner, D1:** verify empty-cup routes before supervised water trials; record grip, clearance, delivery, spills, return and HOME. Controller completion alone is not successful delivery.
- [ ] **Physical team, D1:** verify actual packets, preparation, two-vessel recipe and visible outcome for the preferred chemistry or fallback. Manual review is not a chemistry result; fruit-transfer evidence is not liquid qualification.
- [ ] **Joseph + coordinated runtime/perception lanes, R3–R6 / D3–D4:** connect fresh camera evidence and the two-vessel MuJoCo slice through the existing task loop and registry. Reuse the unmerged prototype after review; retain unchanged baselines, failures and independent observations. The separate improvement lane must establish its own measured result.
- [ ] **Voice/client owners, R1/R4 / D2:** retain Gemini Live and rehearse actual Mac and unplugged-iPhone conversation. Software merge is authorized without these rehearsals; acceptance remains open.

Successful routine HOME can be automatic. Replenishing materials and recovery after a fault require separate readiness checks; a STOP does not authorize a blind reset. Existing software covers exact proposal/confirmation, separate execution and observations, skill versions and evaluation. It has not qualified the physical kit or bench.

## Priorities and acceptance

| ID | Priority | Required behavior | Evidence of delivery |
| --- | --- | --- | --- |
| D1 | P0 | Student-directed physical actions on the actual fixture | Spoken individual commands produce the requested real actions; repeat/reset and failed attempts recorded |
| D2 | P0 | Responsive voice conversation during work | Actual-device audio with acknowledgment, progress, clarification, cancellation and observed result; no blocking expert call in the conversation path |
| D3 | P1 | Expensive successful work becomes a reusable capability | Real expert task -> parameterized tested skill/tool -> equivalent warm request uses it without repeating unnecessary reasoning |
| D4 | P1 | One substantive measured harness improvement | Same task/setup, unchanged baseline, candidate, timings and success/failure evidence; retain or reject based on results |

Every substantial change must advance D1–D4. All other work must justify its human-time cost. D3/D4 must not destabilize the D1/D2 baseline. Their incompleteness must remain visible, not be called “everything implemented”.

## Minimum connected system

```mermaid
flowchart LR
  S[Student] <--> G[Continuous voice agent]
  G --> R[Task and current scene]
  R --> K[Known skill fast path]
  R --> E[Expert when needed]
  C[Camera and localization tools] --> R
  E -->|Progress and results| G
  E --> V[Candidate validation and testing]
  V --> K
  K --> X[One supervised executor]
  X --> O[Telemetry and independent observation]
  C --> O
  O --> G
  O --> E
  O --> I[Inspect bottleneck and propose improvement]
  I --> V
```

The voice agent owns the conversation. The background expert gets the relevant instruction/context, timestamped scene evidence and available capabilities; it reports progress and results back. Use one configured expert per task through the shared Codex/Claude adapter boundary; an operator may switch the profile for new tasks. Do not fork the runtime for each model. Familiar operations use valid skills directly. Camera tools may be simple markers, calibrated transforms or fresh known-station checks; all-frame remote visual reasoning is not required.

The expert may request current camera frames on demand. Capture FPS, expert inference cadence and motor execution are independent. Evidence binds capture time, frame ID, camera/configuration identity, coordinate frame and provenance; stale or invalid scene assumptions require refresh or rejection. Fixed camera regions or colored synthetic markers are not measured fiducial localization. Fixture coordinates become robot coordinates only through independently validated registration.

The executor owns motion, bounded parameters and STOP. Existing approval/bench supervision remains in force; changing consent semantics requires an explicit interface decision. Removing educational gates does not remove physical authorization. Reject stale scene/cache assumptions and unsupported actions; controller completion alone does not prove success. The harness can propose and test new algorithms/tools offline, but that does not automatically authorize novel physical motion.

## What self-improvement means

Improve the available tools and skills, not merely names, descriptions or routing. Successful expensive work becomes compact reusable behavior. A candidate can replace repeated visual reasoning with measured geometry, improve perception, use IK, streamline calls, cache valid scene state, or optimize an execution phase. Choose the simplest change that addresses the largest measured bottleneck. Training a VLA, arbitrary manipulation and a general autonomous learning platform are not requirements.

Keep baseline -> recorded limitation -> candidate -> comparison -> retain/reject. Compare equivalent tasks and report failures/interventions, not just latency. A renamed/re-registered skill is not an improvement. Cold-to-warm savings and a subsequent implementation improvement are separate claims. Retain the physical fallback throughout.

## Speed receipt

For the same request record: completed student input, first acknowledgment, dispatch decision ready, authorization complete, first actual motion, controller finish, independent outcome available, spoken completion. Report request-to-acknowledgment, request-to-motion, planning/perception, motor duration and recovery separately. Include human approval wait rather than hiding it; also report it separately. Use repeated comparable attempts and report sample count and failures. No motor-speed increase simply to improve a latency number.

## Current implementation and evidence boundary

The product's physical target above remains open. Joseph authorized software development with physical actuation disabled. The main architecture is the shared conversation, expert, perception, skills and supervised executor. MuJoCo is the active development backend; Isaac remains parked. A mandatory simulation preview or model round trip is not part of the familiar physical motor path. [FULL_SYSTEM_DELIVERY](FULL_SYSTEM_DELIVERY.md) maps R1–R6; [MAIN_INTEGRATION](MAIN_INTEGRATION.md) tracks branches, evidence and release gates. Software and simulation evidence do not establish D1 physical completion.

- `agentic/openarms_lab` is the sole application task/session/registry runtime. Gemini Live owns responsive conversation; the configured expert performs image-aware planning and tool decisions, with Codex gpt-6.1-sol medium as the default. See [model profiles](EXPERT_MODELS.md) for Claude qualification gaps and task-pinned switching. Known skills reuse their validated versions.
- `ui/lab` and the native SwiftUI client share authenticated sessions, exact proposals, playback acknowledgments, STOP and provenance. Prediction/reflection are optional. `/developer` shows authenticated evidence and diagnostics.
- PR #25 records real Gemini Live generated-speech cold/warm, correction, mock STOP and barge-in evidence on main. Mac human audibility, unplugged iPhone, real-camera integration and selected-kit physical acceptance remain open; see the evidence ledger rather than inferring completion from test counts.
- `bench_vision` supplies reusable evidence/localization tooling. `firmware/openarms_executor` preserves supervised taught actions and the successful historical mandarin trace; neither is activated implicitly by the software demo.
- `simulation/` supplies active MuJoCo development and retained reproducible alternatives. Main currently runs the older fixed-dispenser pH apparatus; the carried-donor two-vessel prototype is separate unmerged work. Rendered liquid and rule-based chemistry are models, not validated fluids or measurements. The old `openarms_agent` research harness is not the current app entrypoint.

[Historical speed measurements and next bounded work](DEMO_SPEED.md).

## Work and review

Use [GitHub issues](https://github.com/VictorJimenez3/OpenArms/issues), existing ownership and isolated worktrees. One integrator owns shared contracts/merges; no competing runtime. Put requirement ID, owned files, dependency/consumer, baseline, acceptance evidence and exclusions in each assignment. Deliver one working connection early, not disconnected completed modules.

Before **every push**, inspect the actual diff against D1–D4 and record requirement, evidence, remaining gap and reviewer in the issue/PR or review receipt. A local receipt can precede the first branch push. A reviewer other than the implementer checks substantial changes. Tests alone cannot certify the vision; the integrator owns end-to-end proof. Do not silently reduce scope or rewrite requirements to match code. Scope changes need Joseph's explicit decision. Partial work may be pushed as a draft with gaps; it may not claim completion.
