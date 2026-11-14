# OpenArms full-system delivery contract
Architecture correction · November 14, 2026 · supersedes the narrow pH-runtime assignment

## Product and evidence boundary
The Smartivity kit is the new demonstration target; Joseph deferred activity selection. Simulation is optional Devpost/presentation material, not the main architecture or a required demonstration. The product is a continuous conversational agent connected to a background expert, scene evidence and perception tools, deterministic execution, independent observations, and an evaluated reusable-skill library. Physical actuation is disabled for this delivery. That does not exclude reasoning, image inspection, perception integration, skill authoring, or improvement.

The reviewed software baseline is merged on main through PR #22 (`0ab5819`). Preserve it while implementing the selected kit activity. Use isolated worktrees for new concurrent tasks; archive completed lanes after integration. No second runtime or registry. No further push until the integrator reviews changes against R1–R6. Component tests alone do not meet completion.

Sources: [01 — current product vision](https://app.notion.com/p/41871c9c107e8133aa70cf1588e620e4), [02 — skills](https://app.notion.com/p/41871c9c107e811d875beeab9dd78d26), [03 — interfaces](https://app.notion.com/p/41871c9c107e810aad00c2bd7d99014e), [10 — perception/improvement](https://app.notion.com/p/41871c9c107e8185977ce8c72365fcff), [P1 — agent harness](https://app.notion.com/p/41871c9c107e81bf8598e4f84fd29798).

## Requirement IDs
R1: A continuous voice agent remains responsive to the student. Joseph withdrew Gemini on November 14; its default connection is disabled while the replacement is built and qualified. This changes the provider, not the required two-agent behavior.
R2: The selected Codex or Claude expert (default OpenAI gpt-6.1-sol at medium reasoning through Codex) performs image-aware planning and makes tool-level decisions during execution; familiar tasks reuse skills and unfamiliar supported tasks escalate.
R3: Timestamped raw images and recognition/localization tools inform planning.
R4: Execution and independent observation feedback reach both agents; progress, clarification, failure, cancellation and bounded replanning work.
R5: Expert-authored, validated, versioned skills become conversationally callable.
R6: A real recorded limitation causes a substantive expert revision, unchanged-baseline comparison, and evidence-based promotion or rejection.

The current `demo-speed-v2` product correction also applies: D1 reliable direct actions; D2 responsive voice; D3 one expensive expert pass produces a tested parameterized skill with fast subsequent reuse; D4 measured improvement. Students can issue individual supported actions immediately. Prediction and reflection are optional. A successful familiar skill must not wait for another expert call at each checkpoint; independent validation and observation continue, with uncertainty/failure escalating to the expert.

November 14 provider compatibility correction: Joseph requested shared Codex/Claude agents and hot model selection. [Expert profiles](EXPERT_MODELS.md) own configuration and qualification details; a task retains its selection through confirmation/checkpoints. This does not alter the shared tools, registry, consent or supported hardware-disabled execution.

## Responsibility map
| Accountable owner / isolated lane | Requirements and owned connection | Dependencies | Required evidence / remaining gap |
| --- | --- | --- | --- |
| Integrator, shared service and contracts | R1/R4 and architecture acceptance; HTTP/WS authentication, session lease, voice bridge, asynchronous task/event delivery to both agents, shared docs and full-loop test | Runtime task API; perception/evaluation artifacts; both clients | Real provider conversation remains usable during expert work; progress and delayed observations are spoken/displayed; no fake student turns; final cross-lane evidence. Shared session repairs are integrated; replacement voice remains open. |
| Runtime owner (agentic) | R2/R4/R5; sole task orchestrator, skill matching/authoring/registry, validation, candidate promotion and mock execution; integrator owns the Codex provider adapter | Shared evidence tool API; integrator gateway; provider qualification | One real cold planning trace using conversation + images + tools, one parameterized skill artifact, equivalent warm reuse, recorded cost/latency and negative routing. The current image-aware expert and task loop are integrated; a kit activity needs new validated bindings. |
| Perception/evaluation owner, existing runtime | R3/R6; image/episode ingestion, bench_vision adapters, independent observer, frozen scenario suite, candidate-vs-baseline evaluation | Runtime expert/tool/candidate APIs; existing bench_vision schemas | Raw timestamped images with hashes, tool invocations and detections, uncertainty/coordinate semantics, outcome derived independently of executor status, actual limitation/revision/evaluation receipts. Never another dispatcher or registry. |
| Browser owner (ui/lab) | R1/R3/R4/R5 presentation; supported activity flow, audio lifecycle, scene/evidence view, task progress/clarification, exact proposal, reusable-skill status | Stable session/task snapshot and event contract | Desktop/mobile end-to-end interaction, keyboard use, interruptions, reconnect, text alternative, useful scene/result display. No inference or promotion authority in the client. |
| Native client owner (SwiftUI) | Same session and observation/progress behavior as browser; streaming audio, actual playback acknowledgment, lifecycle recovery | Same gateway; real-device reachable endpoint | Compiling native app, portable tests, simulator checks, physical device rehearsal explicitly separated. No parallel voice/runtime backend. |
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

The expert is the robot agent: it uses fresh images and tool receipts DURING a task to choose the next supported action, revise a failing skill, and check the outcome. The voice agent is separate from the expert. Preserve the observed camera-assisted C→B behavior in the November 14 bench log: the agent inspected successive webcam frames, adjusted pickup alignment, added lift/carry clearance, and verified placement. This was a supervised staged physical run using LeRobot-backed tools, not a trained ACT policy demonstration. The product must encode that feedback loop; it must not reduce the expert to one initial recipe-selection call. [Committed physical evidence](https://github.com/VictorJimenez3/OpenArms/tree/8f6344faee38bc35f84861bf634bb753b082d5c5/research/joseph/mandarin-transfer-2026-11-14).

1. The voice agent submits a natural task through start_task and receives its task ID promptly. The background expert must not block microphone handling, conversation, cancel or STOP.
2. The router checks active skills and parameter/context coverage. A supported unfamiliar request, uncertain match or failed precondition reaches the expert; an unsupported capability produces a clear limitation, not fabricated execution.
3. The expert receives the TaskContext and can call inspect_scene, localize_objects, list/get_skill, validate_plan, propose_skill and evaluate_candidate. It can inspect raw images as well as tool results. Tool adapters carry source/model/version and uncertainty.
4. Expert output is a structured candidate/plan, clarification or rejection. Validation is independent of model confidence. Only registered bounded mock/simulation primitives can execute; no generated Python or arbitrary motor code.
5. The server presents the exact validated plan. Consent binds the exact plan/version and presented scene/context. Late tool results after cancellation or context changes cannot restore it.
6. One selected supported executor emits per-step progress and receipts. At observation checkpoints, a separate observer reads fresh resulting frames/episode; a cold or uncertain task sends them to the expert before continuation or correction. A validated familiar skill uses deterministic checkpoint checks without blocking on repeated model calls; feedback remains in its task record for expert escalation and improvement. UNKNOWN remains possible after successful controller completion. Changed executable proposals require a new version and confirmation; STOP invalidates outstanding tools.
7. Execution and observation events are persisted and delivered to BOTH the voice agent and the expert. Use supported asynchronous tool/task outcomes and correlated completion messages, not fabricated student turns. Replanning may request another observation or produce a revised plan; it never reuses old consent.
8. A task-validated candidate may be invoked once under that task's explicit consent. Reusable activation requires its evaluation/observation evidence and a promotion decision. Equivalent subsequent requests use the exact active skill version without reauthoring it.
9. STOP/cancel invalidate task generations, pending approvals and scheduled expert actions. No automatic resumption of execution on reconnect. History is passive and preserves backend/provenance.

### Supported capabilities and optional simulation
The selected kit activity will determine material bindings, supported primitives and independently observable outcomes. Until those are specified and implemented, report that capability gap explicitly. Preserve one task loop, registry and executor interface. Recorded or synthetic inputs may verify software contracts with their provenance intact.

MuJoCo and other retained simulations are optional Devpost/presentation material. Their supported operations and limitations belong in [their own guide](../simulation/lab_demos/ph/README.md); they are not requirements or the architecture of the main product. No simulation result qualifies physical actuation or the new kit.

## One improvement cycle to demonstrate
Freeze clear-view, occluded-view, distractor, missing-object and stale-frame cases before revision. Retain the unchanged baseline skill. Run it and record an actual limitation such as UNKNOWN when the receiver is occluded. Give the expert that failure receipt and permitted tools. It proposes a substantive revision, for example a bounded secondary-view observation and an explicit ambiguity/freshness check. Compare baseline and candidate on the same frozen cases, including held-out cases not shown during revision. Promote only with improved recovery and no new false-success/consent/STOP regressions; otherwise record rejection. Preserve both artifacts and replay the decision. This is skill/workflow improvement, not an unproven motor-policy claim.

## Acceptance checklist
- [ ] A natural spoken supported request starts a real background expert task; the voice agent remains responsive to a follow-up while it runs.
- [ ] The expert receives relevant conversation, task, registry and scene; receipts show actual image inspection and at least one recognition/localization tool invocation. Fresh checkpoint images must influence the next tool action or bounded skill revision during execution, not only an initial plan.
- [ ] Ambiguous, absent or stale scene evidence produces clarification/UNKNOWN/rejection with provenance intact.
- [ ] The expert authors a nontrivial structured supported plan/skill; independent validation rejects unsupported operations and malformed bindings.
- [ ] The exact validated proposal is presented; fresh explicit consent executes it once. Negation, assistant speech, stale/duplicate input, changed scene/plan and reconnect replay cannot execute it.
- [ ] Supported execution emits progress and a separate observer reads resulting images. Successful controller completion plus an unreadable image remains UNKNOWN.
- [ ] Both expert and the voice agent receive execution and observation results. The voice agent describes their actual provenance and limitation.
- [ ] Clarification, provider timeout, failure, cancellation, STOP and at most two replans are exercised. Each materially changed execution plan needs fresh consent.
- [ ] Evaluation-backed registration makes the expert-created skill callable through conversation.
- [ ] Equivalent natural requests reuse the same version with measured cold/warm calls, tokens and planning latency; motor/mock travel time is reported separately.
- [ ] A real saved failure/limitation yields a substantive expert revision, same-suite baseline comparison, and justified promotion/rejection with rollback.
- [ ] Browser and iPhone show task progress, scene evidence, proposals, results and recovery without exposing developer controls or credentials.
- [ ] Actual Mac and unplugged iPhone audible checks are reported separately from generated speech, headless browsers and simulator checks.
- [ ] A final run index links commit/build, provider/model, input hashes, artifacts, all failures, tests and architectural coverage. No architectural-completion claim from component counts.

## Provider qualification and current gaps
Current decision: Gemini is withdrawn. The application must not start it even when legacy Google credentials are present. The common session, text, direct STOP, expert and simulator remain usable. Replacement voice is not yet implemented or qualified, and no OpenAI API key is configured for a replacement voice service. Do not reuse Codex authentication as a voice API credential or infer replacement acceptance from old Gemini tests.

The default image-aware expert is **OpenAI gpt-6.1-sol, medium reasoning, through Codex**. [Expert profiles](EXPERT_MODELS.md) describe the shared Codex/Claude boundary, independent authentication and remaining live qualifications. Fresh tool images and execution feedback belong to the same task loop regardless of model. Retain requested/actual model identity and evidence receipts.

The merged implementation and historical measured results are in [the main ledger](MAIN_INTEGRATION.md) and [evidence index](../research/joseph/software-consolidation-2026-11-14/README.md). Historical provider probes, quotas and simulation outcomes do not qualify the replacement voice or selected kit.

## Remaining delivery work
1. Keep the shared session and expert working while replacing the voice provider; qualify responsive progress, results, cancellation and actual-device audio.
2. Once Joseph chooses the kit activity, inspect its instructions and map actual supported actions, materials and independent observations through the existing runtime.
3. Verify the complete cold loop, skill admission, equivalent warm reuse and one substantive improvement on that supported task. Preserve an unchanged baseline and failures.
4. Complete the supervised bench and real-device checks in the architecture checklist. Review all requirement connections before claiming completion.

Every assignment and PR includes requirement IDs, owned connections, integration dependencies, produced evidence, remaining gaps and baseline/rollback impact. Optional presentation simulations are not on this critical path.
