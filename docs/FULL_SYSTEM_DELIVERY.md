# OpenArms full-system delivery contract
Architecture correction · November 14, 2026 · supersedes the narrow pH-runtime assignment

## Product and evidence boundary
pH is the demonstration scenario. The product is a continuous conversational agent connected to a background expert, scene evidence and perception tools, deterministic execution, independent observations, and an evaluated reusable-skill library. Physical actuation is disabled for this delivery. That does not exclude reasoning, image inspection, perception integration, skill authoring, or improvement.

Preserve the working baseline at 8f6344faee38bc35f84861bf634bb753b082d5c5. Retain all current compatible work unmerged in isolated worktrees. No second runtime or registry. No further push until the integrator reviews changes against R1–R6. Component tests alone do not meet completion.

Sources: [01 — current product vision](https://app.notion.com/p/41871c9c107e8133aa70cf1588e620e4), [02 — skills](https://app.notion.com/p/41871c9c107e811d875beeab9dd78d26), [03 — interfaces](https://app.notion.com/p/41871c9c107e810aad00c2bd7d99014e), [10 — perception/improvement](https://app.notion.com/p/41871c9c107e8185977ce8c72365fcff), [P1 — agent harness](https://app.notion.com/p/41871c9c107e81bf8598e4f84fd29798).

## Requirement IDs
R1: Gemini Live remains the responsive student-facing agent.
R2: OpenAI gpt-6.1-sol at medium reasoning through Codex performs image-aware planning and makes tool-level decisions during execution; familiar tasks reuse skills and unfamiliar supported tasks escalate.
R3: Timestamped raw images and recognition/localization tools inform planning.
R4: Execution and independent observation feedback reach both agents; progress, clarification, failure, cancellation and bounded replanning work.
R5: Expert-authored, validated, versioned skills become conversationally callable.
R6: A real recorded limitation causes a substantive expert revision, unchanged-baseline comparison, and evidence-based promotion or rejection.

The current `demo-speed-v2` product correction also applies: D1 reliable direct actions; D2 responsive voice; D3 one expensive expert pass produces a tested parameterized skill with fast subsequent reuse; D4 measured improvement. Students can issue individual supported actions immediately. Prediction and reflection are optional. A successful familiar skill must not wait for another expert call at each checkpoint; independent validation and observation continue, with uncertainty/failure escalating to the expert.

## Responsibility map
| Accountable owner / isolated lane | Requirements and owned connection | Dependencies | Required evidence / remaining gap |
| --- | --- | --- | --- |
| Integrator, current ph-plan-review worktree | R1/R4 and architecture acceptance; HTTP/WS authentication, session lease, Gemini bridge, asynchronous task/event delivery to both agents, shared docs and full-loop test | Runtime task API; perception/evaluation artifacts; both clients | Real provider conversation remains usable during expert work; progress and delayed observations are spoken/displayed; no fake student turns; final cross-lane evidence. Current voice/session repairs are local, not architectural completion. |
| Existing runtime worker, ph-runtime worktree | R2/R4/R5; sole task orchestrator, skill matching/authoring/registry, validation, candidate promotion and mock execution; integrator owns the Codex provider adapter | Shared evidence tool API; integrator gateway; provider qualification | One real cold planning trace using conversation + images + tools, one parameterized skill artifact, equivalent warm reuse, recorded cost/latency and negative routing. Current fixed pH recipe is scaffolding, not the expert. |
| Integrator, ph-plan-review worktree (no competing perception/runtime lane) | R3/R6; image/episode ingestion, bench_vision adapters, independent observer, frozen scenario suite, candidate-vs-baseline evaluation | Runtime expert/tool/candidate APIs; existing bench_vision schemas | Raw timestamped images with hashes, tool invocations and detections, uncertainty/coordinate semantics, outcome derived independently of executor status, actual limitation/revision/evaluation receipts. Never another dispatcher or registry. |
| Existing browser worker, ph-browser worktree | R1/R3/R4/R5 presentation; polished pH flow, audio lifecycle, scene/evidence view, task progress/clarification, exact proposal, reusable-skill status | Stable session/task snapshot and event contract | Desktop/mobile end-to-end interaction, keyboard use, interruptions, reconnect, text alternative, useful scene/result display. No inference or promotion authority in the client. |
| Existing iPhone worker, ph-ios worktree | Same session and observation/progress behavior as browser; streaming audio, actual playback acknowledgment, lifecycle recovery | Same gateway; real-device reachable endpoint | Compiling native app, portable tests, simulator checks, physical device rehearsal explicitly separated. No parallel voice/runtime backend. |
| Integrator and independent review pass | R1–R6; review lane diffs and evidence, integration merges and final acceptance | All lane receipts and test corpus | Requirements/dependencies/evidence/gaps recorded in each assignment and PR; no merge based solely on passing isolated tests. |

[GitHub #19](https://github.com/VictorJimenez3/OpenArms/issues/19) is the shared full-system delivery issue; preserve its current P0/P1 revision and other coordinators’ updates. GitHub #9 remains the shared-interface decision; #10 tracks the complete software loop; #4 tracks actual iPhone connectivity/audio. Preserve their history. Do not create a duplicate architecture issue.

## Shared domain contract
Existing HTTP/WS security, heartbeat, presentation, playback and transcript contracts remain. Extend the canonical session with task, scene, plan, skill and evaluation records; do not fork the service. All writes are server-owned and all records have stable IDs.

Every event carries event_id, session_id, turn_id where applicable, task_id, trial_id, request_id, skill_id/version and evidence_ids where applicable, sequence/revision, timestamp and provenance. Missing associations are explicit null, never guessed.

| Record | Required contents and rules |
| --- | --- |
| ExperimentCommand / TaskContext | Original natural request, relevant conversation and prediction, task goal, backend/capability limits, current scene and evidence references, available tool schemas, registered skills, budget/deadline and cancellation token. |
| SceneEvidence | Frame/episode/camera IDs, capture timestamp and clock, original image bytes via immutable artifact reference + hash, provenance (recorded real, recorded simulation, synthetic), freshness, labels/detections with method/model/version, uncertainty, coordinate frame/units/calibration or explicit unknown. Replay age is measured against the episode clock; recorded footage is never presented as a live camera. |
| ExpertTask | Task ID and status queued/running/needs_clarification/awaiting_confirmation/executing/observing/completed/failed/cancelled; actual provider/model/configuration, tool receipts, concise decision rationale, measured calls/tokens/latency, maximum two replans with bounded tools/time. Never store hidden reasoning as a deliverable. |
| PlanProposal | Immutable plan/version hash, ordered bounded tool/skill operations and parameter bindings, referenced scene/evidence/skill versions, preconditions, expected observation checks, supported backend, student-readable exact preview, expiry and presentation binding. A changed plan requires new presentation and confirmation. |
| SkillDefinition | Content-derived version, intent and retrieval examples, typed/bounded parameters, preconditions, validated primitive/executor references, composition, expected final state, observation checks, limitations, source evidence, evaluation receipts and lifecycle candidate/task-validated/active/rejected/retired. New labels alone do not constitute improvement. |
| ExecutionReceipt | Plan/skill/task IDs, backend, progress, controller lifecycle/status, timestamps, cancellation/failure and trace references. Completion is not an observation. |
| ExperimentOutcome | Independently sourced image/sensor/observer result, linked input evidence, observed features, uncertainty and provenance. Mock/controller success never implies pink, delivery or a physical result. Model reference expectations are a separate record. |
| SkillEvaluation / PromotionDecision | Immutable baseline and candidate hashes, frozen cases/split and artifact hashes, routing/outcome/unknown/STOP regressions, calls/tokens/latency and interventions, semantic diff, pass/fail reasons, promotion or rejection and rollback target. Only the registry's deterministic promotion gate changes the active version. |

### Agent and tool connections

The expert is the robot agent: it uses fresh images and tool receipts DURING a task to choose the next supported action, revise a failing skill, and check the outcome. Gemini Live is the separate conversational agent. Preserve the observed camera-assisted C→B behavior in the November 14 bench log: the agent inspected successive webcam frames, adjusted pickup alignment, added lift/carry clearance, and verified placement. This was a supervised staged physical run using LeRobot-backed tools, not a trained ACT policy demonstration. The product must encode that feedback loop; it must not reduce the expert to one initial recipe-selection call. [Committed physical evidence](https://github.com/VictorJimenez3/OpenArms/tree/8f6344faee38bc35f84861bf634bb753b082d5c5/research/joseph/mandarin-transfer-2026-11-14).

1. Gemini submits a natural task through start_task and receives its task ID promptly. The background expert must not block microphone handling, conversation, cancel or STOP.
2. The router checks active skills and parameter/context coverage. A supported unfamiliar request, uncertain match or failed precondition reaches the expert; an unsupported capability produces a clear limitation, not fabricated execution.
3. The expert receives the TaskContext and can call inspect_scene, localize_objects, list/get_skill, validate_plan, propose_skill and evaluate_candidate. It can inspect raw images as well as tool results. Tool adapters carry source/model/version and uncertainty.
4. Expert output is a structured candidate/plan, clarification or rejection. Validation is independent of model confidence. Only registered bounded mock/simulation primitives can execute; no generated Python or arbitrary motor code.
5. The server presents the exact validated plan. Consent binds the exact plan/version and presented scene/context. Late tool results after cancellation or context changes cannot restore it.
6. One selected mock or MuJoCo executor emits per-step progress and receipts. At observation checkpoints, a separate observer reads fresh resulting frames/episode; a cold or uncertain task sends them to the expert before continuation or correction. A validated familiar skill uses deterministic checkpoint checks without blocking on repeated model calls; feedback remains in its task record for expert escalation and improvement. UNKNOWN remains possible after successful controller completion. Changed executable proposals require a new version and confirmation; STOP invalidates outstanding tools.
7. Execution and observation events are persisted and delivered to BOTH Gemini and the expert. Use supported asynchronous tool/task outcomes and correlated completion messages, not fabricated student turns. Replanning may request another observation or produce a revised plan; it never reuses old consent.
8. A task-validated candidate may be invoked once under that task's explicit consent. Reusable activation requires its evaluation/observation evidence and a promotion decision. Equivalent subsequent requests use the exact active skill version without reauthoring it.
9. STOP/cancel invalidate task generations, pending approvals and scheduled expert actions. No automatic resumption of execution on reconnect. History is passive and preserves backend/provenance.

### Bounded demonstration capabilities
The bounded pH workflow composes scene inspection, object/fixture identification, condition binding, one prepared-sample operation in the selected mock or MuJoCo environment, observation acquisition and qualitative comparison. It may select a second recorded/simulated camera view when the first is ambiguous. It may clarify missing labels or reject unsupported routes. It cannot infer liquid identity from appearance, claim metric geometry from a box center, produce numeric measured pH from a reference color, or actuate physical hardware.

MuJoCo uses the new fixed-dispenser lab apparatus imported from `16a975e`, adapted for qualitative cabbage indicator dosing. It supports a complete prepared dose with actuator feedback and geometric paddle engagement. Standalone pick/put/pour are not supported in this backend. This limitation is explicit in expert capabilities; it does not establish completion of the separate physical P0 direct-action product.

The scene renderer/environment and observer must be separate from the executor's success flag. A simulated outcome is legitimate software evidence when its provenance is retained and the observer actually processes the image. The first loop does not require Isaac, new policy training, remote GPU access or a live camera. Existing bench_vision perception, episode, keyframe, outcome and candidate-verification interfaces should be reused where useful.

## One improvement cycle to demonstrate
Freeze clear-view, occluded-view, distractor, missing-object and stale-frame cases before revision. Retain the unchanged baseline skill. Run it and record an actual limitation such as UNKNOWN when the receiver is occluded. Give the expert that failure receipt and permitted tools. It proposes a substantive revision, for example a bounded secondary-view observation and an explicit ambiguity/freshness check. Compare baseline and candidate on the same frozen cases, including held-out cases not shown during revision. Promote only with improved recovery and no new false-success/consent/STOP regressions; otherwise record rejection. Preserve both artifacts and replay the decision. This is skill/workflow improvement, not an unproven motor-policy claim.

## Acceptance checklist
- [ ] A natural spoken supported request starts a real background expert task; Gemini remains responsive to a follow-up while it runs.
- [ ] The expert receives relevant conversation, task, registry and scene; receipts show actual image inspection and at least one recognition/localization tool invocation. Fresh checkpoint images must influence the next tool action or bounded skill revision during execution, not only an initial plan.
- [ ] Ambiguous, absent or stale scene evidence produces clarification/UNKNOWN/rejection with provenance intact.
- [ ] The expert authors a nontrivial structured supported plan/skill; independent validation rejects unsupported operations and malformed bindings.
- [ ] The exact validated proposal is presented; fresh explicit consent executes it once. Negation, assistant speech, stale/duplicate input, changed scene/plan and reconnect replay cannot execute it.
- [ ] Mock/sim execution emits progress and a separate observer reads resulting images. Successful controller completion plus an unreadable image remains UNKNOWN.
- [ ] Both expert and Gemini receive execution and observation results. Gemini describes their actual provenance and limitation.
- [ ] Clarification, provider timeout, failure, cancellation, STOP and at most two replans are exercised. Each materially changed execution plan needs fresh consent.
- [ ] Evaluation-backed registration makes the expert-created skill callable through conversation.
- [ ] Equivalent natural requests reuse the same version with measured cold/warm calls, tokens and planning latency; motor/mock travel time is reported separately.
- [ ] A real saved failure/limitation yields a substantive expert revision, same-suite baseline comparison, and justified promotion/rejection with rollback.
- [ ] Browser and iPhone show task progress, scene evidence, proposals, results and recovery without exposing developer controls or credentials.
- [ ] Actual Mac and unplugged iPhone audible checks are reported separately from generated speech, headless browsers and simulator checks.
- [ ] A final run index links commit/build, provider/model, input hashes, artifacts, all failures, tests and architectural coverage. No architectural-completion claim from component counts.

## Provider qualification and current gaps
Google Gemini remains the voice provider. A fresh gemini-3.8-live preflight returned the spoken transcript “Ready” and 40,802 PCM audio bytes; this verifies provider speech generation, not physical-device audibility. The extended-thinking Live variant returned API error 1007.

The user explicitly selected **OpenAI gpt-6.1-sol, medium reasoning, through Codex** for the image-aware expert. Account 1 successfully inspected an actual historical bench image and returned a structured request for another scene view. The integrator owns `agentic/openarms_lab/codex_expert.py`; the sole runtime lane consumes its injected async tool-loop contract. The adapter must receive fresh tool images and actual execution feedback and preserve model/effort/usage/evidence receipts. No Gemini expert fallback or fixed recipe substitute.

Provider diagnosis: the app's Google API project is on free tier. Gemini 2.5 Pro is unavailable to new users; Google's recommended gemini-3.1-pro-preview returned 429 with a zero free-tier limit. Gemini 3.8 Flash was below its daily quota and explicitly returned 503 high demand. These were distinct failures, not a general voice outage. Account 2 Codex workers subsequently exhausted their own usage allowance; that is separate from Google quota. Account 1 passed the requested model preflight.

Local implementation now includes the selected Codex adapter, synthetic image producer and pixel observer, task orchestration, registry, and client repairs. A real recorded-image → tool → new-image Codex trace passed in 24,979 ms. A separate actual Gemini Live background-event probe narrated the simulated result with provenance. These are component integration receipts, not full-loop acceptance: connected natural speech → Codex task → execution → observation → registration → warm reuse → evaluated improvement remains under verification. Actual device audibility and unplugged networking also remain unverified.

## Delivery sequence within the approximately 18-hour window
1. Correct assignments/contracts and qualify the expert provider first; keep compatible client repairs progressing locally.
2. Build the narrow complete cold loop with one scene and one supported pH composition before extending breadth.
3. Connect observation feedback, registration and equivalent warm reuse; measure actual calls and timings.
4. Freeze and run the improvement comparison; preserve a working baseline and rollback throughout.
5. Exercise failures and recovery, run computer-use and actual device checks, review all requirement connections, then allow integrator-controlled pushes/merges. Reserve the final hours for evidence, fixes and a reproducible demonstration.

Every assignment and PR must include: requirement IDs; owned files/connections; integration dependencies; evidence actually produced; remaining gaps/blockers; and baseline/rollback impact.

