# OpenArms — Complete Notion Documentation

Exported 2026-11-14. Full text of 21 accessible OpenArms pages: project home, team brief, design/workstreams 00–10, prompts P0–P6, and project registry entry. Source links and source edit timestamps are preserved. This is a snapshot of the documentation, not independent verification of project claims.

## Contents

- [🧪 OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)](#page-01)
- [🧪 OpenArms — One-Page Team Brief](#page-02)
- [🧭 00 — Orchestration & Collaboration](#page-03)
- [🎯 01 — Product Vision](#page-04)
- [🧠 02 — Reusable Skills & Two-Speed Agents](#page-05)
- [🦾 03 — Runtime & Shared Interfaces](#page-06)
- [📋 04 — Evaluation & Demo Evidence](#page-07)
- [🧬 05 — Isaac Sim / SO-101 Virtual Robotics](#page-08)
- [🔭 06 — Virtual Experiments & Scientific Models](#page-09)
- [🧪 07 — Physical Lab Experiments & Demo Selection](#page-10)
- [🤖 08 — Agent Prompts & Execution Playbook](#page-11)
- [09 — Master TODO & Workstreams](#page-12)
- [10 — Experimental Research](#page-13)
- [🧭 P0 — Master Orchestrator Prompt](#page-14)
- [🧠 P1 — Agentic Reasoning & Skill Harness Prompt](#page-15)
- [🦾 P2 — Physical SO-101 Robotics Prompt](#page-16)
- [🎙️ P3 — Voice, UI & Learning Experience Prompt](#page-17)
- [🧬 P4 — Isaac Sim & Virtual Robotics Prompt](#page-18)
- [🔬 P5 — Experiments, Vision & Evidence Prompt](#page-19)
- [✅ P6 — Integration, Testing & Reliability Prompt](#page-20)
- [OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)](#page-21)

---

<a id="page-01"></a>

# 🧪 OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)

Source: [🧪 OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)](https://app.notion.com/p/41771c9c107e81ab8026cdafa6245063?pvs=204)  
Last edited in Notion: 2026-11-14T09:55:37.599Z

**Last updated:** 2026-11-14 04:54 America/New\_York · **Status:** ACTIVE BUILD. This is the current team documentation home, not a chronological research dump. Each page owns one subject. Old contradictory instructions have been removed rather than stacked as "superseded" sections.

**Project:** OpenArms — student-directed accessible lab assistant · **Repository:** [VictorJimenez3/OpenArms](https://github.com/VictorJimenez3/OpenArms) · **Team:** Joseph, Victor, Duc, Stefanie. Actual code/test evidence determines implementation status.

## Start here

**Vision:** A student makes a science prediction, commands a robot by voice/text, observes a real or clearly modeled outcome, and learns from the evidence. The central technical differentiator is slow/expert reasoning compiled into reusable skills that faster agents can later invoke for the **same tested movements** with less reasoning. The physical SO-101 and an Isaac Sim virtual lab are complementary workstreams.

**How we build:** Agents have freedom to choose reasonable designs and parallelize through as many worktrees as productive. Share a compact interface, avoid conflicting writers, keep a single reviewed main-branch integration owner, and measure genuine results. No rigid agent count or mandatory provider/framework. Physical STOP and truthful observation provenance remain firm.

**Current evidence:** Repo has working starting points for iPhone voice, Mac relay, mock tools/validator, calibration, pose playback and physical runner code. Complete voice-to-real-arm transfer, published speedup benchmark, working Isaac scene and physical chemistry remain unverified in the connected evidence; mark them done only when tested.

## Team quick brief

[OpenArms — One-Page Team Brief](https://app.notion.com/p/41771c9c107e8141bba0d7beb491601b)

## Design & architecture

- Every page has a visible **Last updated** timestamp in America/New\_York and Notion's native Last edited time; modify this field when updating the page.

[00 — Orchestration & Collaboration](https://app.notion.com/p/41871c9c107e819d8a48fbbbd591488a)

- When architecture stabilizes, export concise canonical Markdown to repo `docs/` and keep links aligned; repo implementation evidence supersedes stale prose.

[08 — Agent Prompts & Execution Playbook](https://app.notion.com/p/41871c9c107e8167a373c72a3bb3ab8e)

[01 — Product Vision](https://app.notion.com/p/41871c9c107e8133aa70cf1588e620e4)

## Documentation ownership rules

[09 — Master TODO & Workstreams](https://app.notion.com/p/41871c9c107e81d5b6fdfcb4ab71fdd5)

[02 — Reusable Skills & Two-Speed Agents](https://app.notion.com/p/41871c9c107e811d875beeab9dd78d26)

## Research that is not required for initial delivery

[03 — Runtime & Shared Interfaces](https://app.notion.com/p/41871c9c107e810aad00c2bd7d99014e)

- Update the owning page in place when the current design changes; do not append conflicting iterations to the same document.

[10 — Experimental Research](https://app.notion.com/p/41871c9c107e8185977ce8c72365fcff)

[04 — Evaluation & Demo Evidence](https://app.notion.com/p/41871c9c107e8169ae3fe243a42ce570)

## Physical and virtual laboratory builds

- The **Master TODO** owns task state and blockers; the **Runtime** page owns interface semantics; the **Isaac** page owns simulation decisions; the **Prompt hub** owns copyable agent instructions. Avoid repeating entire sections in multiple places.

[05 — Isaac Sim / SO-101 Virtual Robotics](https://app.notion.com/p/41871c9c107e8155b53ff64d49069434)

**Isaac child doc:** [06 — Virtual Experiments & Scientific Models](https://app.notion.com/p/41871c9c107e811a8392c59985243573) (nested under Isaac, including buoyancy, vial sorting, pH modeling, torque and effervescence).

- Put source findings and speculative follow-ups into **Experimental Research** or the [repo research index](https://github.com/VictorJimenez3/OpenArms/blob/main/research/README.md); do not treat unverified research as active runtime.

[07 — Physical Lab Experiments & Demo Selection](https://app.notion.com/p/41871c9c107e816fab14f3549f6a8fd6)

## Execution — give these to agents

**Team-only source of truth:** This OpenArms project and its child pages are self-contained. Agents should use the documents linked on this page and the OpenArms GitHub repository. Do not require or reference external personal Notion documentation to execute team tasks.


---

<a id="page-02"></a>

# 🧪 OpenArms — One-Page Team Brief

Source: [🧪 OpenArms — One-Page Team Brief](https://app.notion.com/p/41771c9c107e8141bba0d7beb491601b?pvs=204)  
Last edited in Notion: 2026-11-14T09:59:39.151Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)

**Last updated:** 2026-11-14 04:20:05 America/New\_York · **Status:** Active hackathon build. **Canonical home:** [OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)](https://app.notion.com/p/41771c9c107e81ab8026cdafa6245063).

## The pitch

OpenArms lets students with limited hand/arm mobility **direct their own hands-on science experiments** by voice or text, then learn from actual evidence. The student decides, the robot acts, and the AI helps them reason.

## Technical distinction

An expert agent can assemble and validate **reusable robot skills**; a faster agent retrieves and executes the **same tested skills** with less reasoning on subsequent requests. Measure planning calls/tokens, latency and routing correctness. Physical motion doesn't automatically become faster. ACT learned control is experimental.

## Three connected demonstrations

- **Physical SO-101:** actual calibrated leader/follower, real object transfer and a safe lab experiment chosen based on material availability. Live voice-to-arm success not yet verified in connected evidence. [07 — Physical Lab Experiments & Demo Selection](https://app.notion.com/p/41871c9c107e816fab14f3549f6a8fd6).
- **Isaac Sim:** parallel full virtual SO-101 and scenario-based science experiments, including buoyancy, vial sorting and other modeled physics/chemistry. [05 — Isaac Sim / SO-101 Virtual Robotics](https://app.notion.com/p/41871c9c107e8155b53ff64d49069434) · [06 — Virtual Experiments & Scientific Models](https://app.notion.com/p/41871c9c107e811a8392c59985243573).
- **Student learning:** prediction → supported command → clear confirmation → verified execution status → independently observed/model-labeled outcome → follow-up question.

## Working team structure

Joseph: physical arm/motion/bench. Duc: reasoning and skill harness. Victor: UI/voice/approval. Stefanie: camera/data/vision; simulation work may be assigned to any suitable independent agent. These are ownership starting points, not hard limits on parallel agents or worktrees. The integrator owns shared merge decisions and remote main pushes.

## Current demonstrated assets / gaps

**Existing:** iPhone voice prototype and Mac Whisper relay, MCP planning mock tests, agentic catalog/validator, LeRobot servo calibration, pose files and a physical transfer runner implementation.
**To verify:** phone→real robot, stop latency, real experiment, skill-distillation benchmark, Isaac Sim host/scene, actual learner usability.

## Where to work

[09 — Master TODO & Workstreams](https://app.notion.com/p/41871c9c107e81d5b6fdfcb4ab71fdd5) · [08 — Agent Prompts & Execution Playbook](https://app.notion.com/p/41871c9c107e8167a373c72a3bb3ab8e) · [02 — Reusable Skills & Two-Speed Agents](https://app.notion.com/p/41871c9c107e811d875beeab9dd78d26) · [GitHub repo](https://github.com/VictorJimenez3/OpenArms).

**Guiding principle:** ambitious product and technical research, but keep demonstrated outcomes, model-generated predictions and proposed features separate.


---

<a id="page-03"></a>

# 🧭 00 — Orchestration & Collaboration

Source: [🧭 00 — Orchestration & Collaboration](https://app.notion.com/p/41871c9c107e819d8a48fbbbd591488a?pvs=204)  
Last edited in Notion: 2026-11-14T09:55:39.170Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)

**Last updated:** 2026-11-14 04:54 America/New\_York · **Status:** Current design; implementation evidence is explicitly identified. **Project:** [OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)](https://app.notion.com/p/41771c9c107e81ab8026cdafa6245063).

## Purpose

Give an orchestration agent enough context to build OpenArms coherently without micromanaging every implementation. Use the [08 — Agent Prompts & Execution Playbook](https://app.notion.com/p/41871c9c107e8167a373c72a3bb3ab8e) for agent tasking; this page owns shared collaboration and integration conventions.

## Mission

Build a voice/text-accessible science lab where the student makes a prediction, chooses a physical or simulated robot operation, observes the outcome and explains it. The central technical contribution is a **two-speed reusable skill harness**: expert reasoning authors/updates a tested reusable skill; a faster dispatcher uses that same skill repeatedly with less reasoning. A distinct Isaac Sim track expands the range of virtual science experiments. The physical SO-101 remains its own supervised path.

## Current starting evidence

The **actual repo** contains a SwiftUI/iPhone ↔ Mac Whisper relay with MCP `submit_plan`, an agentic catalog/validator/mock runner, SO-101 LeRobot pose playback and a physical transfer runner. They are not yet proven end-to-end on the real arm. The phone/relay and agentic harness currently encode plans differently; resolve that seam before assuming complete integration. The team now reports a Hiwonder SO-ARM101 kit; actual controller/motor IDs, specific kit variant, calibration validity and physical motion need to be verified against the hardware. Older Feetech descriptions may not match the real robot.

## Architectural commitments

- Student scientific decisions, separate planning/tool calls, validated physical skills, observation evidence and reflection form the product loop.
- Physical motion is controlled by a bounded local executor with human supervision and independently testable STOP, not an LLM token stream.
- Skill registry and dispatch are implementation-neutral. Reuse of a skill must be measured against repeated high-reasoning calls, using equivalent tasks and the same motor operation.
- Isaac Sim owns **full virtual laboratory scenes**, running independently. Mock, simulated and real outcomes are labeled honestly.
- One canonical external contract is shared between components; choose appropriate language/types internally. See [03 — Runtime & Shared Interfaces](https://app.notion.com/p/41871c9c107e810aad00c2bd7d99014e).

## Collaboration and autonomy

The orchestrator may create **any number of independent worktrees and subagents** justified by parallel tasks and available compute. Do not assume two. Divide by file ownership and handoff interfaces rather than arbitrary personnel caps. Agents may explore, refactor or rewrite owned subsystems when they can show a better solution, keep compatibility/rollback where required and report test evidence. No rigid predefined agent topology, mandatory model vendor or algorithm choice.

**Current user-approved integration policy:** worktree agents commit locally; one integration owner reviews and merges onto local `main`, and only the integration owner pushes remote `main`. No force push. Shared contracts and calibration are coordinated rather than simultaneously rewritten by separate workers.

## Execution priority with limited hackathon time

Build and test on the physical robot first, while agentic/UI runs against a mock. Isaac Sim is an independently staffed virtual-lab workstream only if compatible compute and agent capacity are available; the physical critical path must not wait for a full simulation. Before object pickup at new locations, verify joint control and taught fixed-station movement. One-shot camera images can be used if objects and fixtures remain stationary; a freely handheld photo is not a calibrated XY map unless the image contains measured planar reference points and the transform is validated. Do not require a camera mounted to the moving arm.

## Project documentation boundary

These team pages and the linked OpenArms repository contain all required context and authority for work on OpenArms. Keep agent prompts, tasks and source-of-truth definitions inside this project. Do not reference or assume access to personal Notion pages. Share the team project tree only with collaborators who need it.

## What agents should optimize

Working systems, scientific credibility, a compelling accessibility demo, small understandable interfaces, measurable skill-reuse improvement, and high parallel throughput with frequent integration. Avoid speculative architecture, long duplicated docs and feature bloat.

## Primary linked documents

- [01 — Product Vision](https://app.notion.com/p/41871c9c107e8133aa70cf1588e620e4)
- [02 — Reusable Skills & Two-Speed Agents](https://app.notion.com/p/41871c9c107e811d875beeab9dd78d26)
- [03 — Runtime & Shared Interfaces](https://app.notion.com/p/41871c9c107e810aad00c2bd7d99014e)
- [04 — Evaluation & Demo Evidence](https://app.notion.com/p/41871c9c107e8169ae3fe243a42ce570)
- [05 — Isaac Sim / SO-101 Virtual Robotics](https://app.notion.com/p/41871c9c107e8155b53ff64d49069434)
- [09 — Master TODO & Workstreams](https://app.notion.com/p/41871c9c107e81d5b6fdfcb4ab71fdd5)
- [08 — Agent Prompts & Execution Playbook](https://app.notion.com/p/41871c9c107e8167a373c72a3bb3ab8e)

**Repository:** [VictorJimenez3/OpenArms](https://github.com/VictorJimenez3/OpenArms). Use repository code and actual tests as implementation evidence; update this document when the team's real design changes instead of appending obsolete versions.


---

<a id="page-04"></a>

# 🎯 01 — Product Vision

Source: [🎯 01 — Product Vision](https://app.notion.com/p/41871c9c107e8133aa70cf1588e620e4?pvs=204)  
Last edited in Notion: 2026-11-14T09:19:15.164Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)

**Last updated:** 2026-11-14 04:17:19 America/New\_York · **Status:** Current design; implementation evidence is explicitly identified. **Project:** [OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)](https://app.notion.com/p/41771c9c107e81ab8026cdafa6245063).

## The product

**OpenArms provides the hands; the student does the science.** A learner with limited hand/arm mobility chooses an experiment, predicts an outcome, directs a supervised SO-101 (real or virtual), observes evidence, and interprets what happened with help from an AI learning companion. Voice is primary; text input remains possible. The student retains scientific agency; the AI assists rather than deciding the hypothesis or explanation on their behalf.

## Technical differentiator

The team wants to reduce repeated high-cost planning. A slow/expert agent can compose or author a **versioned reusable skill** from tested robot actions, parameters and guard conditions. Later, a fast/cheap agent can retrieve and invoke the same approved movement with less reasoning. Success requires actual comparison of planning effort and correct behavior; it is not automatic trajectory optimization. [02 — Reusable Skills & Two-Speed Agents](https://app.notion.com/p/41871c9c107e811d875beeab9dd78d26).

## Three experiences

1. **Physical lab:** student controls a real LeRobot SO-101; start from taught grasp/transfer and a scientifically honest experiment chosen from available materials. [07 — Physical Lab Experiments & Demo Selection](https://app.notion.com/p/41871c9c107e816fab14f3549f6a8fd6).
2. **Virtual lab:** Isaac Sim operates an SO-101 digital scene with science models beyond current lab materials, e.g., buoyancy, density, torque, virtual vial sorting and modeled chemistry. [06 — Virtual Experiments & Scientific Models](https://app.notion.com/p/41871c9c107e811a8392c59985243573).
3. **Learning companion:** shared student-facing interface records prediction, choice, action status, real/simulated outcome and follow-up questions. It distinguishes observable fact from model prediction or unknown result.

## User flow

Student predicts → chooses and requests → system resolves a supported skill → student confirms → operator authorizes if real hardware → skill executes → actual outcome observed or marked UNKNOWN → student explains result → optionally selects next trial. A two-speed cold/warm skill benchmark can be demonstrated as a developer view.

## What is genuinely new or compelling

- Students direct rather than merely watch their experiments.
- Physical and virtual labs share a vocabulary of skills and questions without pretending all simulations are real chemistry.
- Expert-generated skills can persist as compact, tested tools for cheaper/faster agents.
- Lab evidence and failure cases remain inspectable.

## Current reality / open design space

Repo includes useful physical/voice/agent scaffolds but no independently verified complete live phone-to-arm experiment. A trained ACT policy and benchmarked distilled skill are not yet established. Don't claim real student accessibility validation. Model providers, exact orchestrator runtime, skill manifest storage and experiment ordering can evolve through tests.

## Judge story

One student decision → one real or clearly simulated robot action → one scientific observation → one explanatory question; show how the slow skill-authoring path permits fast repeated invocations when the benchmark is ready. Better to prove one thoughtful experiment than show many unvalidated features.


---

<a id="page-05"></a>

# 🧠 02 — Reusable Skills & Two-Speed Agents

Source: [🧠 02 — Reusable Skills & Two-Speed Agents](https://app.notion.com/p/41871c9c107e811d875beeab9dd78d26?pvs=204)  
Last edited in Notion: 2026-11-14T09:19:16.058Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)

**Last updated:** 2026-11-14 04:17:19 America/New\_York · **Status:** Current design; implementation evidence is explicitly identified. **Project:** [OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)](https://app.notion.com/p/41771c9c107e81ab8026cdafa6245063).

## Primary research/engineering goal

Use expert reasoning **once when needed**, then make the resulting supported behavior repeatable by a smaller/faster dispatcher through a compact, versioned skill. "Self-improving" refers mainly to the library and agent's use of it: descriptions, retrieval, parameterization, composition, error handling, evidence and promotion. It does **not** require discovering a shorter servo trajectory.

## Conceptual architecture

**Cold path:** student goal → inspect available state and skills → expert selects/composes a validated workflow → propose a versioned skill artifact → test and review → register.

**Warm path:** new phrasing of equivalent goal → fast skill matching/slot filling → validate context/parameters → approval → same physical or simulated backend → log result and measured reasoning cost.

**Learning loop:** collect usage, wrong-routing examples, failures, and success evidence → propose revised skill descriptions, retrieval features, composition, or new bounded capabilities → evaluate candidates against unchanged baseline → promote versions that are actually better.

## Minimum skill semantics

Each supported skill needs: identity/version; human-readable intent; accepted parameter types and bounds; preconditions; reference to known controller/macro; expected final state; how to observe its outcome; limitations; test/evidence status. Internal representation (YAML, Pydantic, JSON, Python wrapper) may be chosen by implementation agents with integrator agreement. One live skill must not execute unreviewed motor code.

## Meaningful comparisons

- High-effort plan per request vs fast invocation of already compiled skill on equivalent requests.
- Fast dispatcher before vs after skill catalog improvement.
- Where helpful, skill composition vs a long multi-tool plan each time.

Track valid routing/parameterization, no-motion safety rejects, model calls/tokens, planning latency, human interventions and physical/simulated execution outcome. Separate one-time expert skill construction cost from repeated dispatch. Distinguish planner speedup from unchanged servo travel time.

## Current priority

Make one versioned mandarin transfer skill usable through the current voice relay and physical runner; show warm-path paraphrase robustness and a credible benchmark. Next add a lab skill based on real materials and/or Isaac Sim. Generalizing to arbitrary cups or positions is research, not implied by reuse.

## Optional experiments

ACT for shifted-object grasp, SmolVLA/LabVLA compatibility, calibrated motion transforms, learned routing, failure-based motor revisions, multi-iteration skill refinement. These live under [10 — Experimental Research](https://app.notion.com/p/41871c9c107e8185977ce8c72365fcff), not core runtime contracts.

## Guardrails only where they matter

The model can propose a new candidate skill but cannot silently activate novel physical motions. A physical motor controller remains deterministic or independently tested, supervised, bounded, stoppable and separately verified. Agents are free to choose orchestration algorithms and data structures. No forced framework or model provider.

## Related

[03 — Runtime & Shared Interfaces](https://app.notion.com/p/41871c9c107e810aad00c2bd7d99014e) · [04 — Evaluation & Demo Evidence](https://app.notion.com/p/41871c9c107e8169ae3fe243a42ce570) · [08 — Agent Prompts & Execution Playbook](https://app.notion.com/p/41871c9c107e8167a373c72a3bb3ab8e)


---

<a id="page-06"></a>

# 🦾 03 — Runtime & Shared Interfaces

Source: [🦾 03 — Runtime & Shared Interfaces](https://app.notion.com/p/41871c9c107e810aad00c2bd7d99014e?pvs=204)  
Last edited in Notion: 2026-11-14T09:19:16.892Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)

**Last updated:** 2026-11-14 04:17:19 America/New\_York · **Status:** Current design; implementation evidence is explicitly identified. **Project:** [OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)](https://app.notion.com/p/41771c9c107e81ab8026cdafa6245063).

## Runtime mental model

**Input/UI** → conversation/learning → **fast skill router or expert author/reasoner** → structured plan → independent validation and explicit approvals → **one executor per backend** → execution telemetry and separate outcome evidence → learning companion.

Physical backend = supervised SO-101 via LeRobot; virtual backend = Isaac Sim. Mock backend remains for testing. Agents may implement provider-specific adapters; the external semantics should remain coherent.

## Contract concepts (freeze semantics; let implementers choose practical types)

| Concept | Minimum meaning |
| --- | --- |
| **ExperimentCommand** | Who requested what, session/request ID, student instruction, selected experiment and normalized intent/parameters |
| **SkillDefinition** | ID/version, scope, allowed args, preconditions, controller reference, expected state, observable success, evidence and lifecycle |
| **SkillRequest** | Unique plan/request, skill ID/version, bounded args, current backend/state and approval binding |
| **ExecutionResult** | Same ID, backend (mock/physical/sim), lifecycle status, actual controller trace/timing, failure/STOP if any |
| **ExperimentOutcome** | Independently observed result (camera/sensor/participant/model), uncertainty, units/conditions, provenance including SIMULATED / REAL / UNKNOWN |
| **SkillEvaluation** | Model/version, reasoning path, latency, calls/tokens, dispatch correctness, tested task outcome and interventions |

## Lifecycle and invariants

PROPOSED → VALIDATED → STUDENT\_CONFIRMED → OPERATOR\_AUTHORIZED (physical) → EXECUTING → COMPLETED / FAILED / STOPPED / UNKNOWN. Observation is a separate record, never inferred from the command status. Revised instructions revoke stale proposals. Each authorization binds a specific request and can be consumed once. Unknown/unavailable state means clarify or pause rather than guessed execution.

## Service ownership

- Voice/UI owns speech, transcription, text alternatives, display, confirmation and user-visible state.
- Reasoning/skill service owns dialogue context, skill retrieval/authoring, plans and tutoring; never raw uncontrolled servo actuation.
- Validator/approval service owns supported arguments, station constraints, identity, approval and operator conditions.
- Robot runner owns serial connection, taught actions, motion phases, STOP behavior, faults and telemetry; no LLM on each control tick.
- Simulation runner owns Isaac scene and modeled outcomes with explicit virtual provenance, not physical serial.
- Evidence service owns images, timestamps and actual observation status.

## Existing implementation seams

[Voice bridge](https://github.com/VictorJimenez3/OpenArms/tree/main/research/joseph/iphone-voice-bridge) currently has `submit_plan` and a `TransferRunner` interface; `agentic/openarms_agent/` has a separate `Plan`/`ArmPort` interface. Choose and document one external request/response contract and consolidate or adapt. Do not leave competing command authorities. Working code can be rewritten if tests show the replacement is better; the goal is coherence, not a permanent adapter hierarchy.

## Motion representation

Recorded joint vector sequences are valid for known station geometry. A simple additive joint offset is **not** generally a Cartesian XYZ offset; test frame transforms and IK before claiming spatial generalization. One executor should own motors; use bounded motion, verified start pose, active stop checks inside motion segments and a physical operator stop. The sim may implement distinct control details.

## Vision and observations

Two Logitech cameras are team-reported. A fixed camera can produce before/after physical evidence. A wrist view is optional. Vision may provide uncertainty-aware observations but not uncalibrated 6-DoF grasp targets or assumed chemical identity. Record whether an observation is real camera, human, calibrated sensor, or simulated/model-derived.

## Implementation freedom

Agent topology, transport (WebSocket/HTTP/MCP), model vendors, schema library and exact modules are flexible. Freeze interoperable examples early and update them when real code forces a justified change. Never let backend simulation masquerade as physical execution.

## Related

[Current repo interface](https://github.com/VictorJimenez3/OpenArms/blob/main/docs/INTERFACES.md) · [05 — Isaac Sim / SO-101 Virtual Robotics](https://app.notion.com/p/41871c9c107e8155b53ff64d49069434) · [02 — Reusable Skills & Two-Speed Agents](https://app.notion.com/p/41871c9c107e811d875beeab9dd78d26)


---

<a id="page-07"></a>

# 📋 04 — Evaluation & Demo Evidence

Source: [📋 04 — Evaluation & Demo Evidence](https://app.notion.com/p/41871c9c107e8169ae3fe243a42ce570?pvs=204)  
Last edited in Notion: 2026-11-14T09:51:35.822Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)

**Last updated:** 2026-11-14 04:17:19 America/New\_York · **Status:** Current design; implementation evidence is explicitly identified. **Project:** [OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)](https://app.notion.com/p/41771c9c107e81ab8026cdafa6245063).

## Goal and success evidence

A student can predict, command, approve, observe and explain a real lab action through an accessible interface. A two-speed skill system demonstrates reusing a tested operation with less model reasoning. Isaac Sim runs a distinct virtual SO-101 experiment when a compatible host is available. These are **parallel outcomes**, not a single rigid sequential pipeline.

## Live build tracks

| Track | Outcome / evidence | Current evidence state |
| --- | --- | --- |
| Voice + conversation | Natural utterance, proposed action, confirmation, spoken/text response | Local/mock relay parts exist; full physical connection not proven |
| Physical SO-101 | Approved real object transfer and eventually science experiment, stop tested | Calibrated poses and runner code exist; supervised complete trials not documented |
| Skill harness | Expert authors skill; fast path reuses it; latency/call/routing benchmark | Design current; implementation and measured gains not verified |
| Science / education | Student choice, prediction, actual effect, evidence-based question | Experiment candidates researched; hardware choices pending bench tests |
| Isaac Sim | Reproducible virtual SO-101 scene plus virtual scientific comparison | Selected direction; environment not verified |
| Evidence / UI | Labeled real/sim/unknown result, notebook and camera evidence | Concept and partial scaffolding |

## What to measure

- **Physical:** completed safe repetitions and independently observed placement, stop response, intervention/failure counts and action duration.
- **AI:** correct skill routing under paraphrases/changed station parameters, clarification/rejection correctness, planner latency, calls/tokens, expert authoring cost separated from repeated invocation.
- **Science:** physical or modeled variable values, explicit controls, observation provenance and student explanation.
- **Simulation:** actual boot on compatible host, task success by scene state, reset/replay stability and clear boundary between PhysX outcomes and scientific model outputs.
- **Accessibility:** user can issue/correct/cancel instruction via more than one input method. Avoid unsupported claims of clinical/usability validation.

## Demonstration hierarchy

1. Working real voice-to-object transfer with trustworthy action status.
2. Genuine physical experiment with one student-chosen variable and observed result.
3. Fast-skill reuse compared with slow planning on equivalent tasks.
4. A virtual Isaac experiment that extends the scientific range (potentially built in parallel).
5. Extra visual polish, ACT or other research only where it improves observed quality.

An agent can reorder compatible work when test results or compute make a better path obvious. Do not present aspirational features as implemented.

## Operational quality bar

- Commands cannot cause uncontrolled physical movement; stale/duplicate approval does not repeat action; stop works within movement rather than only between steps.
- The measured scientific outcome is not substituted by a guessed LLM answer.
- Actual test receipts and run mode accompany all success claims.
- Real hardware, mock, Isaac simulation and analytical science model are visibly distinguishable.
- A complete 2-minute judge sequence and backup video should be rehearsed against the actual implementation, not storyboard assumptions.

## Work plan

Tasks, owners, dependencies and status live in [09 — Master TODO & Workstreams](https://app.notion.com/p/41871c9c107e81d5b6fdfcb4ab71fdd5), not duplicated on this page. Research hypotheses and optional learned policies live in [10 — Experimental Research](https://app.notion.com/p/41871c9c107e8185977ce8c72365fcff). Prompt docs live in [08 — Agent Prompts & Execution Playbook](https://app.notion.com/p/41871c9c107e8167a373c72a3bb3ab8e).

## Event and submission

Verify the live HackPrinceton submission requirements and track eligibility from official event sources. Current safest team planning assumes a **Sunday November 15 morning submission**; do not infer judge presentation time or accepted hardware restrictions without checking. Reserve sufficient time for end-to-end recording, documentation and integration tests.


---

<a id="page-08"></a>

# 🧬 05 — Isaac Sim / SO-101 Virtual Robotics

Source: [🧬 05 — Isaac Sim / SO-101 Virtual Robotics](https://app.notion.com/p/41871c9c107e8155b53ff64d49069434?pvs=204)  
Last edited in Notion: 2026-11-14T09:55:40.528Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)

**Last updated:** 2026-11-14 04:54 America/New\_York
**Status:** Selected full-simulation direction; implementation and compute access not yet verified. **Scope:** independent parallel simulation workstream, NOT a prerequisite for the physical demo. Limited-time priority: physical hardware and mock agent/UI first; pursue Isaac only with spare independent agent/compute capacity.

## Why this exists

OpenArms will use **Isaac Sim** for a full virtual SO-101 laboratory, not just pre-motion preview. The simulation can support virtual manipulation, experiments with materials unavailable at the venue, visual presentation and eventual policy/data experiments. It does not replace the supervised physical lab. MuJoCo is not the team's target for full simulation; keep it only if a lightweight local test proves useful.

## Architecture

- **SO-101 scene:** robot articulation, gripper, cameras, vials, racks, fixtures, rigid bodies and environment reset.
- **Simulation controller:** executes scene actions with the simulator's joint names/units; may expose the same high-level skills as the physical runner.
- **Science model:** separate explicitly labeled analytic/data-driven layer for buoyancy, pH response, reactions, and other phenomena that Isaac rigid-body physics does not automatically solve.
- **Lesson adapter:** student prediction → chosen skill/variable → simulated observation → grounded explanation; attach source, units and sim-mode provenance.
- **Adapter boundary:** shared intent/skill/event semantics are desirable, not a reason to force identical low-level physical/simulation code. Never connect sim to real robot serial ports.

## Bootstrap strategy (agent chooses practical details)

1. Check accessible RTX hardware, driver, OS, memory and remote GUI; log actual machine capabilities.
2. Reuse NVIDIA's SO-101 vial-to-rack workshop scene and model where compatible; choose pinned versions independently of the physical LeRobot setup.
3. Demonstrate one virtual SO-101 grasp/place with recorded scene/video and state.
4. Make tasks resettable and reproducible with clear success checks.
5. Add lab scenes from **06 — Virtual Laboratory Experiments**; begin with simple science+robot interaction, then expand if worthwhile.
6. Integrate with UI/agent via a small backend interface only once there is a working scene.

## Material constraints and honest trade-offs

- Official Isaac Sim 5.1 spec cites an RTX 4080-class / 16 GB VRAM minimum and 32 GB system RAM. An RTX 3060 12 GB is below that published floor; perhaps a tiny task works, but treat it as an experiment, not a guaranteed host. MacBooks are not full native Isaac Sim hosts.
- NVIDIA's referenced workshop uses Isaac Sim 5.1.0, Isaac Lab 2.3.0, LeRobot 0.4.3 and a tested Ada/Blackwell GPU. The physical repo pins LeRobot 0.6.2: isolate environments and explicitly map joint/action conventions.
- A100/H100 have no RTX RT cores and are not supported as Isaac Sim hosts; they could be useful for separate model training.
- Full simulated fluid dynamics or chemical reaction is **not** implicit in Isaac Sim. Domain models must be identified as models.

## Useful initial acceptance evidence

- [ ] Compatible machine/runtime actually tested
- [ ] SO-101 workshop launched with screenshot and run configuration
- [ ] One repeatable grasp/place or vial-to-rack outcome logged
- [ ] Sim-only action/result events with stable identifiers
- [ ] No connection to physical hardware in sim mode
- [ ] A science question drives at least one changeable virtual experiment
- [ ] Results openly labeled SIMULATED / MODELED

## References

[NVIDIA SO-101 workshop](https://github.com/isaac-sim/Sim-to-Real-SO-101-Workshop) · [NVIDIA course environment](https://docs.nvidia.com/learning/physical-ai/sim-to-real-so-101/latest/06-get-the-code.html) · [Isaac Sim requirements](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/requirements.html)

[06 — Virtual Experiments & Scientific Models](https://app.notion.com/p/41871c9c107e811a8392c59985243573)


---

<a id="page-09"></a>

# 🔭 06 — Virtual Experiments & Scientific Models

Source: [🔭 06 — Virtual Experiments & Scientific Models](https://app.notion.com/p/41871c9c107e811a8392c59985243573?pvs=204)  
Last edited in Notion: 2026-11-14T09:14:13.935Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026) / 05 — Isaac Sim / SO-101 Virtual Robotics

**Last updated:** 2026-11-14 04:14:12 America/New\_York
**Status:** Active design options, not yet verified simulation scenes. **Execution:** Isaac Sim SO-101 plus a clearly separate scientific model when needed.

## Product value

Give the student a meaningful scientific decision that the available physical apparatus cannot currently support. A virtual manipulation must be connected to a falsifiable prediction and a visible/measured outcome. Avoid treating a scripted color change as computed fluid chemistry.

## Experiments to explore

| Idea | LeRobot-style virtual arm action | What student learns / what must be modeled | Difficulty estimate |
| --- | --- | --- | --- |
| **Vials to rack** | Pick, align, transport, place vials | Spatial planning, sorting, lab procedure; grounded in NVIDIA SO-101 workshop | Low bootstrap risk |
| **Buoyancy and density** | Release labeled sealed samples into container | Average object density vs fluid density; float/sink or modeled submerged fraction. Isaac needs buoyancy implementation or analytic coupling | Strong science first choice |
| **Lever and torque** | Place weights on lever slots | Torque balance and moment arms; predominantly rigid-body mechanics | Relatively accessible |
| **pH indicator** | Move test vial, dip sample tool or transfer virtual dose | Acid/base category, indicator reference/chemistry model; visuals are not PhysX chemical proof | Good narrative |
| **Effervescence** | Deposit virtual tablet into fixed cup | Temperature/area effects on observed fizz duration; model or measured curve, visuals decorative | Medium |
| **Density column** | Place vessels/dispense prepared portions | Compare stratification and mixing; high-fidelity fluids expensive | Medium/high |
| **Osmosis / diffusion** | Assemble samples and set conditions | Diffusion curve and membrane constraints, analytically modeled | Science-rich; little arm novelty |
| **Color mixing / dilution** | Move or combine known portions | Concentration ratios or qualitatively mixed colors | Accessible fallback |

## Scenario format (flexible example)

Each scene should record: scientific question; variables student may change; fixed controls; supported robot actions; predicted mathematical/empirical result; observable outputs; evidence/model assumptions; reset procedure; and pass/fail criteria. Agents may use YAML, Python, JSON, USD metadata or another maintainable format. We require semantic compatibility, not a mandated file extension.

## Candidate sequences

**Buoyancy:** student predicts which of two similarly sized sealed samples floats; arm picks and releases one sample into a fixed vessel; the modeled/simulated result is shown alongside mass and volume; the student chooses a follow-up where mass or fluid density is changed. Validate whether the physics engine actually applies fluid forces or whether an analytic model drives the outcome.

**Vial comparison:** student labels/sorts samples, arm performs rack manipulation, and the simulated lab notebook asks what classification criterion was used.

**Rate question:** student changes water temperature while holding other factors fixed; the arm releases a tablet, and the independent chemistry model reports a simulated response curve. Label animations as illustrative if not directly computed.

## Tasks and proof

- [ ] Choose initial scenario using host capability and demo clarity
- [ ] Define control variables, outcome and science assumptions
- [ ] Connect one robot action to that scenario
- [ ] Build resettable scene and camera/viewer
- [ ] Create two genuinely different student choices and outcomes
- [ ] Save run metadata with seed, version, backend and condition
- [ ] Show virtual result beside an explanation/prediction in UI
- [ ] Attempt a second experiment only after first is reproducible

## Research basis

[Victor's lab-feasibility report](https://github.com/VictorJimenez3/OpenArms/blob/main/research/victor/laboratory-experiments-and-feasibility.md) · [Victor's educational-simulation research](https://github.com/VictorJimenez3/OpenArms/blob/main/research/victor/educational-simulation.md) · [NVIDIA SO-101 workshop](https://github.com/isaac-sim/Sim-to-Real-SO-101-Workshop) · [NVIDIA course environment](https://docs.nvidia.com/learning/physical-ai/sim-to-real-so-101/latest/06-get-the-code.html) · [Isaac Sim requirements](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/requirements.html)


---

<a id="page-10"></a>

# 🧪 07 — Physical Lab Experiments & Demo Selection

Source: [🧪 07 — Physical Lab Experiments & Demo Selection](https://app.notion.com/p/41871c9c107e816fab14f3549f6a8fd6?pvs=204)  
Last edited in Notion: 2026-11-14T10:32:09.514Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)

**Last updated:** 2026-11-14 05:00 America/New\_York
**Status:** Active experiment selection; physical scientific results not verified in current connected evidence.

## Goal

Choose one compelling student-directed science experiment that works **with the actual arm, actual materials and visible evidence**. The orange A→B transfer is now reported by Joseph as working physically (Nov 14 \~05:00 ET; run/video evidence not independently inspected here). It is the existing integration baseline, not automatically a science demo. The urgent next demonstration is reuse/adaptation to pickup from C and placement at B, preserving the A→B implementation.

## Candidate experiments

| Candidate | Manipulation needed | Advantage | Physical gate |
| --- | --- | --- | --- |
| **Red-cabbage pH** | Pre-portioned deposit, controlled tipping fixture, or mounted pH strip dip | Immediate visible chemistry and strong educational question | Obtain safe materials; verify real indicator color, spill control, dose/dip operation |
| **Buoyancy** | Pick/release sealed sample into fixed water vessel | Real physical outcome, fewer moving liquid containers | Verify sample mass/volume contrast, release location, splash and grasp stability |
| **Effervescence** | Release identical tablet into stationary cup | Physical reaction + measurement of fizz duration; can vary conditions | Obtain approved materials; verify clear timing contrast and repeatable release |
| **Dry lever/torque** | Place masses into lever fixture | No open liquids; physics phenomenon | Accurate mass positions and visible equilibrium |
| **Color mixing** | Prepared portion transfer | Visual and easy to explain | Proven liquid-transfer mechanism and meaningful measured variable |

## Practical selection

Use the most impressive setup that reliably supports a genuine student choice and a truthful observed effect. **Default exploration priority:** manual bench-test pH (if materials arrive) and a buoyancy setup (because a grasp/release skill may be simpler). Select using measured reliability, not paper difficulty rankings.

## Minimum experiment loop

1. Student selects condition/sample and predicts effect.
2. App presents interpreted action and requests confirmation.
3. Operator checks fixtures and authorizes physical motion.
4. SO-101 performs the taught/validated physical skill.
5. Camera, sensor or explicitly attributed observer records the real effect or UNKNOWN.
6. Student interprets evidence; companion asks a follow-up.

## Immediate critical path and camera workaround

1. **Physical first:** validate supervised taught fixed-station empty-gripper motion, then dry grasp/placement, before building a full simulation or novel-position grasping system.
2. **One-shot image is acceptable:** Hold or position the camera to capture source and target at the start, then remove it. The robot and objects must remain fixed afterward. A handheld photo is visual context, not automatically an XY calibration; use four measured planar markers in-frame and validate a homography if computing new tabletop coordinates. Otherwise use taught station poses.
3. **After movement:** verify outcome with human observation or a new image. Distinguish motor execution from actual physical transfer. Supervised STOP must remain available.
4. Keep Isaac Sim as an independent virtual lesson track, not a blocker for real hardware testing.

## Bench preparation and tests

- [ ] Verify permissions and low-risk supplies, protect electronics from spills
- [ ] Prepare fixed work surface and labeled stations
- [ ] Manually test expected physical/scientific effect before robot involvement
- [ ] Choose simplest repeatable robotic interface with apparatus
- [ ] Teach/verify poses with real container geometry
- [ ] Log dry and loaded trials with complete observed success/failure
- [ ] Test cancellation and restart with safe test items
- [ ] Check actual outcome visibility from fixed camera
- [ ] Record backup video of complete real learning loop

## Source documents

[Victor's full physical experiment feasibility research](https://github.com/VictorJimenez3/OpenArms/blob/main/research/victor/laboratory-experiments-and-feasibility.md) · [NVIDIA workshop as reference for vial manipulation](https://github.com/isaac-sim/Sim-to-Real-SO-101-Workshop)


---

<a id="page-11"></a>

# 🤖 08 — Agent Prompts & Execution Playbook

Source: [🤖 08 — Agent Prompts & Execution Playbook](https://app.notion.com/p/41871c9c107e8167a373c72a3bb3ab8e?pvs=204)  
Last edited in Notion: 2026-11-14T09:14:13.935Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)

**Last updated:** 2026-11-14 04:14:12 America/New\_York
**Status:** Current agent instruction hub, intended for copy/paste and later repo export.

## Principle

Use **strong context and outcomes, not a giant prescriptive implementation script**. The agents should understand product vision, existing code, scientific integrity, constraints and integration seams. They can propose better architecture or substitute libraries when they justify the change and preserve evidence of working behavior. Do not cap number of subagents/worktrees: allocate as many independent lanes as useful, with one integration authority and no conflicting writers.

## Shared context every coding agent should load

- [OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)](https://app.notion.com/p/41771c9c107e81ab8026cdafa6245063)
- [01 — Product Vision](https://app.notion.com/p/41871c9c107e8133aa70cf1588e620e4)
- [02 — Reusable Skills & Two-Speed Agents](https://app.notion.com/p/41871c9c107e811d875beeab9dd78d26)
- [03 — Runtime & Shared Interfaces](https://app.notion.com/p/41871c9c107e810aad00c2bd7d99014e)
- [Repo AGENTS.md](https://github.com/VictorJimenez3/OpenArms/blob/main/AGENTS.md), [current docs/INTERFACES.md](https://github.com/VictorJimenez3/OpenArms/blob/main/docs/INTERFACES.md) and relevant owned code. Repo facts are more current than any stale text; make contradictions explicit.

## Orchestration conventions

Choose independent tasks and create isolated worktrees as needed; parallelize agentic, physical, Isaac Sim, virtual experiments, vision/data and tests when useful. The orchestrator alone integrates onto remote `main` after checking conflicts and tests; no force push. A worker owns its files for the duration of a task, not forever. Avoid redefining shared contracts without communicating them. Reporting actual tests and known blockers is required. Detailed agent prompts are child pages below.

## Prompts

See child prompt docs: orchestrator, agent/harness, SO-101 robot, UI/voice, Isaac simulation, science/evidence. Each gives the mission, current context, success evidence and broad autonomy. Add role-specific prompts only when they create meaningful independent work.

## Output standard

Each agent should leave a runnable code path (or a specific blocked reason), a concise integration handoff, actual executed tests with results, and a clear distinction between simulated and physical evidence. No imaginary success metrics or uncontrolled physical commands.

[P0 — Master Orchestrator Prompt](https://app.notion.com/p/41871c9c107e81eeb496e7e44f98d450)

[P1 — Agentic Reasoning & Skill Harness Prompt](https://app.notion.com/p/41871c9c107e81bf8598e4f84fd29798)

[P2 — Physical SO-101 Robotics Prompt](https://app.notion.com/p/41871c9c107e81d3b516f9f759926517)

[P3 — Voice, UI & Learning Experience Prompt](https://app.notion.com/p/41871c9c107e8188919ec930d3e362c4)

[P4 — Isaac Sim & Virtual Robotics Prompt](https://app.notion.com/p/41871c9c107e81faaa35d22c3320fd53)

[P5 — Experiments, Vision & Evidence Prompt](https://app.notion.com/p/41871c9c107e81efa96fe798a21c7f0c)

[P6 — Integration, Testing & Reliability Prompt](https://app.notion.com/p/41871c9c107e813c810be9747d688f73)


---

<a id="page-12"></a>

# 09 — Master TODO & Workstreams

Source: [09 — Master TODO & Workstreams](https://app.notion.com/p/41871c9c107e81d5b6fdfcb4ab71fdd5?pvs=204)  
Last edited in Notion: 2026-11-14T10:03:25.661Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)

**Last updated:** 2026-11-14 05:00 America/New\_York
**Status:** LIVE MASTER TODO. The checkboxes below are **open candidates until evidence marks them done**; some may already be partly implemented. Choose the subset that advances the next demonstrable outcome. This is not a mandated order or a fixed worktree schedule.

## How to use

- The orchestrator assigns tasks to as many independent agents/worktrees as justified. Tasks can be split, combined, reprioritized, retired or reassigned as testing reveals better approaches.
- Each completed task records a commit, actual test/run, physical observer if applicable, or a decision/result link. Do not check off unverified work.
- Labels A–K are workstreams, **not permanent team assignments**. Several may run in parallel. Keep actual blockers visible.
- Main objectives: real student-controlled lab; two-speed reusable skills; independent Isaac Sim science lab; honest outcomes. Detailed design [00 — Orchestration & Collaboration](https://app.notion.com/p/41871c9c107e819d8a48fbbbd591488a) · [05 — Isaac Sim / SO-101 Virtual Robotics](https://app.notion.com/p/41871c9c107e8155b53ff64d49069434) · [08 — Agent Prompts & Execution Playbook](https://app.notion.com/p/41871c9c107e8167a373c72a3bb3ab8e).

## Snapshot — what is documented to exist

SwiftUI/Whisper relay, mock MCP planning, separate agentic harness, LeRobot calibration and physical runner code. Current evidence does **not** verify a complete physical voice-to-experiment or skill-reuse speedup. Isaac Sim is now a selected direction, not yet booted in observed team evidence.

## A — Project orchestration & current state

- [ ] **A01** Read latest repository state, relevant Notion pages and existing code before assigning implementation work
- [ ] **A02** Record current HEAD commit, environments, available machines, known verified vs team-reported capabilities
- [ ] **A03** Confirm demo scope and identify the one physical science experiment most plausible with current materials
- [ ] **A04** Identify active code owners, shared-file collision risks and immediate blockers
- [ ] **A05** Choose an appropriate number of parallel worktrees; do not cap arbitrarily
- [ ] **A06** Create isolated tasks for voice, planning, hardware, cameras, Isaac, science and testing where useful
- [ ] **A07** Define how integrator receives commits, evidence and review receipts from each lane
- [ ] **A08** Agree on main-only remote push protocol and recovery for upstream changes
- [ ] **A09** Establish concise daily/current status in hub without duplicating the task board
- [ ] **A10** Review which research docs are relevant before new research and avoid repeated surveys
- [ ] **A11** Resolve teammate's access blocker: grant the four OpenArms collaborators appropriate permissions on this project root; verify each can directly open child pages (Master TODO, architecture, prompts, Isaac) and check for any separate child restrictions. Keep the project self-contained and independent of unrelated Notion pages.

## B — Shared contracts & runtime integration

- [ ] **B01** Inventory conflicting Plan/SkillRequest/ExecutionResult definitions in existing voice, agentic and firmware
- [ ] **B02** Choose the smallest shared command/skill/result representation that all backends can adapt to
- [ ] **B03** Write one concrete spoken request → proposed skill → permission → result example
- [ ] **B04** Define event IDs/session IDs, plan staleness rules and replay/duplicate handling
- [ ] **B05** Agree physical, simulated, mock and unknown provenance fields
- [ ] **B06** Determine skill registry version and activation semantics
- [ ] **B07** Define the required approval and operator state in a physical execution request
- [ ] **B08** Define backend selection so simulation cannot accidentally access robot serial hardware
- [ ] **B09** Build a testable mock adapter at the shared seam
- [ ] **B10** Connect first real runner through chosen contract
- [ ] **B11** Exercise contract against agentic mock, voice relay and physical fake runner
- [ ] **B12** Document actual API after implementation rather than forcing unused types

## Immediate milestone selection

**Physical first, mocked services in parallel.** Joseph supervises the SO-101 fixed-pose transfer, STOP, and evidence recording. Agentic/UI should proceed against mock contracts in parallel. Do NOT wait for Isaac Sim to launch before collecting real hardware results. A one-shot image is fine for known stations; arbitrary novel XY targets require calibrated reference points and validated IK before executing. The virtual lab remains an independent optional workstream and must not block the physical demo.

## Hardware milestone update — 05:00 ET

**Joseph reports the orange A→B transfer has already worked on the physical arm.** Treat it as a working baseline, not the next feature to build; review saved code/poses and request a run receipt if needed. Some earlier checklist items additionally require camera recording or repeated trials and should remain unchecked until their full acceptance conditions are met. **Immediate objective:** preserve A→B, adapt same transfer skill to source C and destination B, verify actual physical result and A→B regression. Known C station reuse is distinct from a never-taught XY pickup.

## C — Physical SO-101 baseline

- [ ] **C01** Confirm Hiwonder SO-ARM101 kit variant (user-reported Hiwonder; Standard/Advanced/Starter not yet identified), actual HX/STS motor labels, connected leader/follower ports, calibration profiles and LeRobot environment. Older Feetech STS3215 documentation is unverified for this hardware.
- [ ] **C02** Inspect current pose script, movement interpolation, fault handling and executor implementation
- [ ] **C03** Verify pose units, bounds and initial HOME tolerance on actual hardware
- [ ] **C04** Review within-waypoint stop responsiveness and correct issues found
- [ ] **C05** Check independent physical power stop and operator supervision setup
- [ ] **C06** Test stop during a safe unloaded move, log response and failure behavior
- [ ] **C07** Check one-arm hardware access lock and reconnection behavior
- [ ] **C08** Verify the current station A/B geometry and fixture stability
- [ ] **C09** Record or revalidate grasp, lift, transit, placement and retreat poses with leader arm
- [ ] **C10** Run an unloaded approach/retreat before object grasp
- [ ] **C11** Run one supervised object pickup and release
- [ ] **C12** Run complete Mandarin A→B with physical observer and recording
- [ ] **C13** Document grip failures, alignment and recoverability; adjust fixture or pose accordingly
- [ ] **C14** Repeat full transfer trials and log observed success/failure and intervention
- [ ] **C15** Test stale approval, disconnected session and canceled command while hardware stays safe
- [ ] **C16** Publish runnable, operator-readable physical demo instructions
- [ ] **C17** Prepare a low-risk physical fallback skill for judging
- [ ] **C18** Capture actual working A→B implementation: robot model/driver, recorded poses/trajectory, command used, outcome evidence and known limits; preserve as regression baseline
- [ ] **C19** Inspect transfer representation and choose a minimal source parameterization for C→B without duplicating the complete executor
- [ ] **C20** Define station C physically or estimate new XY through calibrated geometry; explicitly record which of those two cases is tested
- [ ] **C21** Test empty-gripper approach to C and validate reachability, wrist orientation, clearance, STOP and operator control
- [ ] **C22** Perform supervised orange C→B, log observed success/failure, intervention, trace and actual destination
- [ ] **C23** Re-run A→B after changes and check no regression; keep a stable rollback
- [ ] **C24** Expose one transfer skill with source and destination parameters; document supported known stations versus untaught localization and handoff to agentic/UI lane

## D — Voice, app and educational conversation

- [ ] **D01** Run current SwiftUI device app, Mac relay and speech recognition baseline tests
- [ ] **D02** Confirm physical phone can connect on the venue's permitted local network
- [ ] **D03** Check live phone transcript quality, speaking and playback acknowledgements
- [ ] **D04** Trace spoken command through MCP/agent to the mock runner
- [ ] **D05** Show interpreted action in UI before execution
- [ ] **D06** Support correction/confirmation/rejection and fresh proposal identity
- [ ] **D07** Make status updates visible during long reasoning and motor execution
- [ ] **D08** Give fast acknowledgment without claiming action completion
- [ ] **D09** Display physical / simulated / mock / predicted / unknown status unmistakably
- [ ] **D10** Provide text input or control path for users who cannot speak
- [ ] **D11** Provide emergency stop UI wired outside language-model reasoning
- [ ] **D12** Test mute, reconnect, cancellation, duplicate confirmation and interruption behavior
- [ ] **D13** Capture student prediction before outcome is revealed
- [ ] **D14** Display experiment notebook with inputs, observation and evidence source
- [ ] **D15** Ask one question about the actual outcome and permit student explanation
- [ ] **D16** Run one fully mocked student learning session and record demo video
- [ ] **D17** Run same conversation with actual physically observed result when ready

## E — Two-speed skill harness

- [ ] **E01** Inspect existing agentic catalog, validator, brain and tools; choose which to reuse or consolidate
- [ ] **E02** Define compact reusable skill artifact with bounded parameters and controller references
- [ ] **E03** Implement skill discovery/retrieval on existing active skills
- [ ] **E04** Implement fast dispatch or lightweight matching for registered skills
- [ ] **E05** Implement expert path that can compose a candidate from known working primitives
- [ ] **E06** Add skill candidate lifecycle with versioning and review evidence
- [ ] **E07** Register first actual A→B skill only after verifying corresponding behavior
- [ ] **E08** Connect a fast invocation to exactly the approved known motion, not a regenerated trajectory
- [ ] **E09** Test several varied phrasing examples for the same accepted request
- [ ] **E10** Test unsupported object, shifted destination and missing station rejection
- [ ] **E11** Measure expert cold planning model usage and latency
- [ ] **E12** Measure fast warm skill routing model usage and latency on equivalent tasks
- [ ] **E13** Report routing correctness and safety rejects, not only token speed
- [ ] **E14** Refine skill description/aliases/arguments using failed examples
- [ ] **E15** Measure whether improved catalog changes performance against baseline
- [ ] **E16** Demonstrate second supported skill or multi-step composition if useful
- [ ] **E17** Keep prospective skill changes out of live hardware until verified

## F — Cameras, telemetry and evidence

- [ ] **F01** Inventory actual cameras and included Hiwonder accessories, then enumerate/test available video feeds. Hiwonder Standard and Advanced typically include a 480p wrist camera plus mounting bracket; Advanced adds a 1080p external camera. User also reports two Logitech webcams. Confirm actual kit and parts rather than assuming every camera is Logitech.
- [ ] **F02** Check for the manufacturer wrist-camera bracket and screws before improvising tape. If present, mount the small included wrist camera rigidly and restrain its USB cable; use a stable fixed external/Logitech camera to observe the whole tray. If no rigid wrist mount is available, start with a fixed angled camera instead. Confirm clearance with power off before supervised motion.
- [ ] **F03** Test camera frame capture and still images with timestamp
- [ ] **F04** Add capture around a skill execution with stable request/plan IDs
- [ ] **F05** Record controller action and observed state timestamps for the same episode
- [ ] **F06** Record operator or observer's actual placement success separately from motor status
- [ ] **F07** Implement evidence path usable by notebook and UI
- [ ] **F08** Show before/after images with unknown outcome fallback
- [ ] **F09** Check lighting/occlusion and effect readability for chosen experiment
- [ ] **F10** Decide if second wrist/side view materially improves result verification
- [ ] **F13** Try a temporary one-shot webcam photo before the robot moves: include at least four measured tabletop reference points in the same image if pixel-to-XY localization is needed; remove camera after capturing without moving the robot/fixtures/objects. Run fixed taught poses as a fallback if geometry is not calibrated; obtain independent human verification after movement.
- [ ] **F11** Save one reproducible failed episode for analysis without claiming automatic fix
- [ ] **F12** Optionally export synchronized episodes in ACT-compatible form

## G — Real science experiment selection

- [ ] **G01** List available materials and event rules for water, cups, household reagents and powered electronics
- [ ] **G02** Physically test cabbage-indicator reaction with actual prepared samples before arm involvement
- [ ] **G03** Prototype one fixed source/receiver geometry for pre-portioned reaction
- [ ] **G04** Evaluate solid dose, tipping cradle or strip dip by real reliability
- [ ] **G05** Bench-test one buoyancy comparison with known mass and external volume
- [ ] **G06** Check whether a repeatable object-release into water is easier than pH dispensing
- [ ] **G07** Consider effervescence sample release if clear physical result and materials are available
- [ ] **G08** Select a physical experiment based on actual manipulation/visibility success
- [ ] **G09** Secure lightweight holders, catch tray and marked stations
- [ ] **G10** Teach the specific physical experiment skill on actual apparatus
- [ ] **G11** Validate robot transfer with empty/dry substitute first
- [ ] **G12** Verify real effect on at least one supervised full experiment
- [ ] **G13** Record before/after evidence and honest physical outcome
- [ ] **G14** Prepare student prediction and one follow-up question from genuine measurement
- [ ] **G15** Set a robust backup demo if chosen experiment fails

## H — Isaac Sim full robotics workstream (independent parallel lane)

- [ ] **H01** Identify accessible supported RTX GPU host (local or remote) and check specs
- [ ] **H02** Check NVIDIA official Isaac Sim compatibility checker, driver and environment
- [ ] **H03** Choose workshop and Isaac Sim / Isaac Lab version pairing that can actually run
- [ ] **H04** Set up isolated simulator environment without modifying physical LeRobot deployment
- [ ] **H05** Clone/review NVIDIA SO-101 sim-to-real vial-to-rack workshop and its task definitions
- [ ] **H06** Launch base virtual SO-101 scene and save screenshot/launch metadata
- [ ] **H07** Confirm joint and gripper conventions and scene reset behavior
- [ ] **H08** Run or teach one successful virtual pick-and-place or vial-to-rack attempt
- [ ] **H09** Add camera and an objective state-based virtual success condition
- [ ] **H10** Record run seed, sim version, action trace and result
- [ ] **H11** Define virtual execution adapter at shared skill/event boundary
- [ ] **H12** Ensure sim mode makes no physical servo/serial calls
- [ ] **H13** Build experiment props/containers using simple USD/rigid bodies where useful
- [ ] **H14** Add an on-screen experiment view or a recorded scene viewer
- [ ] **H15** Evaluate viability of sim data collection or ACT training separately
- [ ] **H16** Report compute limitations honestly and keep virtual scene work independent of physical integration

## I — Virtual scientific experiments (Isaac + models)

- [ ] **I01** Select first virtual science experiment for visual clarity and meaningful variable choice
- [ ] **I02** Define scientific model inputs, controlled variables, outputs, units and assumptions
- [ ] **I03** Implement virtual vial sorting as reference manipulation scenario if useful
- [ ] **I04** Build buoyancy scene with sealed samples and liquid container geometry
- [ ] **I05** Decide how buoyant forces/outcomes are computed rather than assuming rigid-body PhysX handles liquids
- [ ] **I06** Add at least two mass/volume/fluid-density choices with different justified outcomes
- [ ] **I07** Connect SO-101 robot release action to the virtual buoyancy observation
- [ ] **I08** Consider lever torque experiment using rigid bodies and marked mass positions
- [ ] **I09** Consider modeled pH response with labeled indicator model rather than fake physics
- [ ] **I10** Consider effervescence rate curves with transparent model provenance
- [ ] **I11** Connect virtual chosen condition to prediction and reflection interface
- [ ] **I12** Make virtual scene repeatable with reset/seed and recorded parameters
- [ ] **I13** Render simulated observations and labels in student UI
- [ ] **I14** Check all virtual result reports include SIMULATED/MODELED source
- [ ] **I15** Record short reproducible clip of one full virtual laboratory scenario

## J — Validation, integration and demo readiness

- [ ] **J01** Run current repo test suites and save baseline outputs
- [ ] **J02** Review every lane's actual commit, changed files and tests before integration
- [ ] **J03** Integrate shared contracts first, then workstream outputs as they become ready
- [ ] **J04** Check mock end-to-end session after each relevant merge
- [ ] **J05** Check physical command path for duplicate/stale/unauthorized execution
- [ ] **J06** Check external STOP and power stop are available during physical rehearsal
- [ ] **J07** Check sim backend cannot contact physical robot port
- [ ] **J08** Check scientific observations retain actual source/uncertainty
- [ ] **J09** Check fast/slow benchmark uses comparable requests and measures costs honestly
- [ ] **J10** Rehearse physical student prediction → command → observed result → question
- [ ] **J11** Rehearse virtual SO-101 science scenario independently if available
- [ ] **J12** Write a short judge explanation of why the skill harness is technically interesting
- [ ] **J13** Write project README with setup and truthful verified capabilities
- [ ] **J14** Record high-quality backup video with actual working behavior
- [ ] **J15** Confirm hackathon submission time, track requirements and repository visibility
- [ ] **J16** Push only reviewed integration main and verify remote head
- [ ] **J17** Submit final Devpost artifacts and verify completion

## K — Experimental backlog (not required for demo)

- [ ] **K01** Collect enough aligned SO-101 demonstrations to smoke-test ACT
- [ ] **K02** Evaluate ACT on one narrowly scoped phase with held-out object positions
- [ ] **K03** Test calibrated station-relative motion transforms rather than assuming joint offsets imply Cartesian offsets
- [ ] **K04** Compare deterministic, prompt-heavy and compiled-skill approaches on held-out requests
- [ ] **K05** Investigate alternate VLA and laboratory policy checkpoints for SO-101 compatibility
- [ ] **K06** Explore multi-cycle skill improvement with versioned promotion/rollback
- [ ] **K07** Investigate whether simulated demonstrations help real execution, with transfer gap measured

## Replanning rule

When a task is blocked, record blocker and owner, surface an alternate useful task from another independent track, and revise the plan. Do not invent completed tests, automatically roll unfinished work forward, or let a speculative enhancement displace a functioning demo. For physically consequential operations, get the bench operator's supervision and record actual evidence.

## Current related documents

[OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)](https://app.notion.com/p/41771c9c107e81ab8026cdafa6245063) · [04 — Evaluation & Demo Evidence](https://app.notion.com/p/41871c9c107e8169ae3fe243a42ce570) · [10 — Experimental Research](https://app.notion.com/p/41871c9c107e8185977ce8c72365fcff)


---

<a id="page-13"></a>

# 10 — Experimental Research

Source: [10 — Experimental Research](https://app.notion.com/p/41871c9c107e8185977ce8c72365fcff?pvs=204)  
Last edited in Notion: 2026-11-14T09:26:47.518Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)

**Last updated:** 2026-11-14 04:20:05 America/New\_York · **Status:** Optional and research-oriented. Ideas listed here are **not** automatically needed for the physical or Isaac Sim demonstration. See [09 — Master TODO & Workstreams](https://app.notion.com/p/41871c9c107e81d5b6fdfcb4ab71fdd5) for active assignments.

## Open experimental tracks

### ACT for adaptive grasping

Train a narrow imitation skill on real or simulated SO-101 demonstrations if synchronized observations/actions and compatible policies are available. Compare success vs taught pose playback on held-out placements; do not substitute low training loss for physical outcomes.

### SmolVLA / LabVLA / other policy backends

Investigate embodiment mismatch, action space, cameras, datasets, inference latency and training expense. Keep these as optional executor alternatives. A wet-lab checkpoint is not automatically usable on the SO-101.

### Geometry-aware skill transforms

Explore calibrated frame-relative offsets, IK and interpolation for new station positions. An additive joint-angle vector is not a fixed Cartesian gripper offset. Evaluate with measured contacts and reachability, keeping tested fallback poses.

### Harness improvement beyond the core benchmark

Try learned routing, richer skill summaries, task composition and multiple iterations of expert-generated catalog refinements. Maintain evaluation baseline, versioning and human review for anything activated on real hardware.

### Camera intelligence

Compare marker/geometry tracking, fixed camera verification and VLM scene summaries under lighting and occlusion. Do not claim absolute 3D localization or chemical identity from an uncalibrated frame.

### Isaac Sim research extensions

The **full virtual lab** is an active workstream under [05 — Isaac Sim / SO-101 Virtual Robotics](https://app.notion.com/p/41871c9c107e8155b53ff64d49069434) and [06 — Virtual Experiments & Scientific Models](https://app.notion.com/p/41871c9c107e811a8392c59985243573). Experimental extensions here include sim-to-real transfer, domain randomization, learned manipulation policies, synthetic data and more advanced fluid/chemistry models. MuJoCo is merely a possible lightweight technical fallback, not the selected full-sim framework.

## Experiment report quality

For every claim: hypothesis, baseline, tested backend (mock/sim/real), model/configuration, run count, observed successes/failures, uncertainty, measurements, versioned artifact and decision. Never rewrite live physical safety controls through automatic AI experiments.

## Research sources

[NVIDIA Astranomy](https://research.nvidia.com/labs/srl/projects/astranomy/) · [RoboHarness](https://github.com/BinceQu/RoboHarness) · [LeRobot](https://github.com/huggingface/lerobot) · [SO-101 Isaac workshop](https://github.com/isaac-sim/Sim-to-Real-SO-101-Workshop) · [Victor lab-feasibility research](https://github.com/VictorJimenez3/OpenArms/blob/main/research/victor/laboratory-experiments-and-feasibility.md).

## Nov 14 external-source check: AVA adaptation for XY grasping

**Evidence status:** Source code reviewed; no OpenArms hardware results measured. This is a candidate adaptation, not an accepted release decision.

- [AVA repo, MIT licensed](https://github.com/Pretlei/AVA) implements static-camera colored-object detection, pixel-to-tabletop homography, XY IK and Arduino servo drive on its custom 5-DOF arm.
- [calibrate\_camera\_3a.py](https://github.com/Pretlei/AVA/blob/main/software/calibrate_camera_3a.py) uses known marked tabletop coordinates and clicked pixels to fit a homography, with held-out calibration checking.
- [transform\_coordinates\_3.py](https://github.com/Pretlei/AVA/blob/main/software/transform_coordinates_3.py) maps image pixels to XY in millimeters; most directly reusable with a newly measured OpenArms calibration.
- [object\_detection\_4.py](https://github.com/Pretlei/AVA/blob/main/software/object_detection_4.py) detects selected colors by HSV and centroid; adapt thresholds and camera backend for the actual Logitech camera and chosen tags/objects.
- [arm\_calibration\_3b.py](https://github.com/Pretlei/AVA/blob/main/software/arm_calibration_3b.py) collects gripper positioning errors over a grid and interpolates XY correction offsets; promising for the measured improvement harness after baseline works.
- **Do not copy AVA's custom **[**IK/Arduino/PWM controller**](https://github.com/Pretlei/AVA/blob/main/software/ik_solver_2.py)** unchanged.** Its link lengths, joint calibration and controller are for a different robot.
- [SO-101 Keyboard Typer](https://github.com/ardacinardemirtas/so101-keyboard-typer) (Apache-2.0) supplies SO-101 URDF-based Cartesian control, QP differential IK and measured hand-eye workflow. [Official LeRobot action representations](https://huggingface.co/docs/lerobot/action_representations) describe the SO-101-compatible FK/IK processor path. Verify API compatibility with the team's pinned version.
- A gripper trajectory should be shifted in **Cartesian XYZ** then resolved via IK per approved waypoint; adding the same offset to original servo joint angles does not produce constant XYZ translation.
- **Camera strategy:** fixed overhead is simplest. If hardware mount impossible, rigidly mount one camera on the robot and return to a single calibrated inspection pose for each scan (one view/one plane); full multi-angle moving-camera scan needs per-pose geometry/hand-eye calibration and is deferred. Keep second camera for independent evidence. Homography only localizes points on the calibrated table plane; tall object grasping requires known height/geometry or further sensing.

**Suggested two-hour spike, not guaranteed delivery:** fit one webcam's pixel-to-tabletop mapping with held-out markers → manual image-click XY (no object model) → test supervised gripper hovering above five approved reachable points with independent STOP → evaluate whether geometry is adequate for a dry novel-position grasp. Test colored marker detection only after geometry passes. Fallback remains pre-taught poses and the fixed-location physical demonstration. Preserve original MIT/Apache licenses/notices when copying source code.


---

<a id="page-14"></a>

# 🧭 P0 — Master Orchestrator Prompt

Source: [🧭 P0 — Master Orchestrator Prompt](https://app.notion.com/p/41871c9c107e81eeb496e7e44f98d450?pvs=204)  
Last edited in Notion: 2026-11-14T09:15:24.548Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026) / 08 — Agent Prompts & Execution Playbook

**Last updated:** 2026-11-14 04:15:22 America/New\_York
**Status:** CURRENT COPYABLE AGENT PROMPT. Adapt execution details to observed repository state.

## Assignment

You are the integration orchestrator for OpenArms. Understand OpenArms as a student-directed accessible laboratory assistant: student predicts, commands a robot, observes real or clearly labeled simulated evidence, and reflects. Central contribution: an expensive expert agent compiles/revises versioned reusable robot skills; a faster agent later invokes the same tested capabilities with fewer reasoning calls. ACT is an optional learned controller. Physical SO-101 control must be supervised and independently stoppable. Current repository has voice relay, MCP submit\_plan, LeRobot pose replay, a separate agentic harness, and tests, but full live physical integration is not verified. Full virtual simulation is now Isaac Sim; physical execution and simulation may proceed in parallel.

Read the project Notion hub, numbered architecture/skill/runtime/simulation pages, current fine-grained TODO, and repo [AGENTS.md](http://AGENTS.md) and [INTERFACES.md](http://INTERFACES.md). Inspect the actual git tree and tests before making design assumptions. The user allows clean rewrites of owned subsystems when they simplify integration; keep an evidence-backed rollback and don't discard working behavior blindly.

## Outcomes

- Reconcile the two existing voice/agent/robot interfaces into one coherent external contract.
- Bring up the real student-directed physical workflow and the two-speed skill-reuse comparison.
- Support an independent Isaac Sim virtual-lab lane with common high-level skill/event semantics where practical.
- Deliver one scientific learning experience across physical and/or virtual modes, honestly labeled, while protecting physical safety.
- Keep a current, granular task board with owners, dependencies, blockers and verification links.

## How to organize

Launch as many isolated worktrees/subagents as improve throughput. Split by independent files or components (voice, planning, skill registry, robot, cameras, Isaac, experiments, UI, tests, integration); these are examples, not a mandatory number or decomposition. Avoid simultaneous edits to shared contracts. Assign tasks by deliverable and interfaces, not fixed procedures. Let subagents investigate and choose strong implementations. Prefer a bounded API and small mergeable artifacts over speculative frameworks.

Only the integrator pushes reviewed changes to remote main under the team's current policy. Integrate frequently with actual tests; refuse blind force pushes. If a plan fails in reality, update the architecture and task board instead of continuing from fictional progress.

## Report

State what works in hardware, mock and sim separately; list changed files, tests executed, independent physical sign-offs, open risks and next highest-value tasks. Do not confuse a mock pass with a real result.


---

<a id="page-15"></a>

# 🧠 P1 — Agentic Reasoning & Skill Harness Prompt

Source: [🧠 P1 — Agentic Reasoning & Skill Harness Prompt](https://app.notion.com/p/41871c9c107e81bf8598e4f84fd29798?pvs=204)  
Last edited in Notion: 2026-11-14T09:15:24.548Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026) / 08 — Agent Prompts & Execution Playbook

**Last updated:** 2026-11-14 04:15:22 America/New\_York
**Status:** CURRENT COPYABLE AGENT PROMPT. Adapt execution details to observed repository state.

## Assignment

Build the OpenArms intelligent skill system. Understand OpenArms as a student-directed accessible laboratory assistant: student predicts, commands a robot, observes real or clearly labeled simulated evidence, and reflects. Central contribution: an expensive expert agent compiles/revises versioned reusable robot skills; a faster agent later invokes the same tested capabilities with fewer reasoning calls. ACT is an optional learned controller. Physical SO-101 control must be supervised and independently stoppable. Current repository has voice relay, MCP submit\_plan, LeRobot pose replay, a separate agentic harness, and tests, but full live physical integration is not verified. Full virtual simulation is now Isaac Sim; physical execution and simulation may proceed in parallel.

Study current `agentic/openarms_agent/`, Joseph's voice relay and the skill architecture page. There are currently two partly incompatible plan representations. Choose one maintainable shared contract with the integrator; a clean consolidation is allowed. Preserve the deliberate student decision-making loop.

## Target behavior

- A student instruction is interpreted with lab context and mapped to registered valid skills.
- A high-reasoning path can compose/author a novel supported skill candidate from existing validated building blocks; it saves a concise versioned reusable artifact, not a huge reasoning transcript.
- A fast path retrieves and invokes the approved skill for equivalent later requests. It escalates when uncertain rather than inventing an unsafe motor action.
- Independent validation/approval happens regardless of model confidence or provider.
- Execution and real observation are distinct event streams; tutoring uses evidence and students' own predictions.

## Engineering freedom

Use Deep Agents, other tool frameworks, deterministic routing, typed manifests, and data stores when they actually simplify or improve the system. Don't impose exact agent counts, model providers, programming libraries or file structures prematurely. Expose interfaces that can be tested with fake robot, actual arm and Isaac simulation. Treat ACT as a swappable low-level experiment rather than a reasoner substitute.

## Evidence of success

Show one expensive skill authoring/registration → multiple equivalent fast invocations comparison. Record correctness, planning latency, model calls/tokens, failures and model/configuration. No claimed speedup without numbers. Include negative/ambiguous/stale request tests. Physical activation needs operator sign-off.


---

<a id="page-16"></a>

# 🦾 P2 — Physical SO-101 Robotics Prompt

Source: [🦾 P2 — Physical SO-101 Robotics Prompt](https://app.notion.com/p/41871c9c107e81d3b516f9f759926517?pvs=204)  
Last edited in Notion: 2026-11-14T10:03:20.806Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026) / 08 — Agent Prompts & Execution Playbook

**Last updated:** 2026-11-14 05:00 America/New\_York
**Status:** CURRENT COPYABLE AGENT PROMPT. Adapt execution details to observed repository state.

## Assignment

Make OpenArms physically useful on the calibrated leader/follower SO-101. Understand OpenArms as a student-directed accessible laboratory assistant: student predicts, commands a robot, observes real or clearly labeled simulated evidence, and reflects. Central contribution: an expensive expert agent compiles/revises versioned reusable robot skills; a faster agent later invokes the same tested capabilities with fewer reasoning calls. ACT is an optional learned controller. Physical SO-101 control must be supervised and independently stoppable. Current repository has voice relay, MCP submit\_plan, LeRobot pose replay, a separate agentic harness, and tests, but full live physical integration is not verified. Full virtual simulation is now Isaac Sim; physical execution and simulation may proceed in parallel.

**Immediate update from Joseph, Nov 14 \~05:00 ET:** The real orange A→B transfer has ALREADY WORKED on the physical robot (user-reported verified). DO NOT spend the first block reimplementing or reteaching A→B. First inspect the latest working code, saved trajectory and exact success conditions; preserve that implementation as a regression baseline. The next task is to modify/parameterize the working transfer skill so the orange can start at a different position C and still be placed at B. Start by inspecting LeRobot pin, `firmware/openarms_executor/`, calibration, pose JSON, transfer runner, and actual recorded poses. Choose the simplest robust hardware architecture; rewriting the executor is acceptable if it improves control and is validated with tests.

## Urgent C→B adaptation milestone

Success means the same high-level `transfer(source, destination)` capability accepts source C and destination B without breaking the already working A→B. First decide whether C is a known/taught station or a previously untaught XY coordinate: these are different demonstrations. A known station can reuse shared grasp/placement phases with C-specific validated pickup geometry; genuine novel-position transfer requires a measured tabletop frame and safe reachability/IK or equivalent calibrated controller. A constant offset to every servo joint angle is NOT generally a constant XY translation. If considering shifting a taught path, transform appropriate Cartesian waypoints, solve/validate joints and retain gripper/fixture behavior, never execute untested offsets blindly.

Candidate fast experiments: inspect how the existing trajectory stores phases and q(t); preserve a clean A→B copy; derive the smallest parameterization for pickup at C; test empty-gripper approach to C first while Joseph supervises; then attempt C→B; record outcome and failures; rerun A→B as regression check. If the geometry is not already available, try a manually taught C pickup and shared B placement first (skill composition), explicitly labeling that as known-station reuse rather than novel-location generalization. A one-shot camera image can support known station selection but does not yield calibrated millimeter coordinates on its own. No Isaac Sim prerequisite.

**Acceptance:** A→B still works; at least one supervised real C→B transfer with actual object-placement observation; unchanged safe STOP/operator control; one reusable skill interface and a concise diff/test receipt; clear statement of whether C was taught or inferred. Do not claim a physical generalization benchmark from a software-only mock.

## Target behavior

- A user-approved named skill calls a deterministic, instrumented SO-101 executor.
- Leader-taught demonstrations define reusable, versioned motions or named phases; allow carefully tested compositional transformations if warranted.
- Physical state, stop path, retry policy, gripper state, reachability, robot lock and operator approval are handled independently of language-model prompting.
- A single connected scene can demonstrate one repeatable real transfer and eventually a science experiment selected based on available materials.

## Explore rather than assume

Investigate the existing pose and action conventions, motor units, interpolation and camera use. In particular evaluate the existing per-waypoint rather than within-waypoint stop checks, unknown HOME tolerance, and overshoot/nudge behavior under real constraints. Test with fake robot and supervised low-risk physical motions. Do not fabricate station coordinates, successful attempts or delivered volumes.

## Deliver

A runnable adapter to the common skill request/execute/result interface; meaningful status and real trial receipts; demonstrated safe stop; a minimal physical trial checklist; clear limitations and next tests. No need to build a general IK system unless the fixed bench setup warrants it.

<p />


---

<a id="page-17"></a>

# 🎙️ P3 — Voice, UI & Learning Experience Prompt

Source: [🎙️ P3 — Voice, UI & Learning Experience Prompt](https://app.notion.com/p/41871c9c107e8188919ec930d3e362c4?pvs=204)  
Last edited in Notion: 2026-11-14T09:15:24.548Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026) / 08 — Agent Prompts & Execution Playbook

**Last updated:** 2026-11-14 04:15:22 America/New\_York
**Status:** CURRENT COPYABLE AGENT PROMPT. Adapt execution details to observed repository state.

## Assignment

Make OpenArms feel like an actual student-controlled lab. Understand OpenArms as a student-directed accessible laboratory assistant: student predicts, commands a robot, observes real or clearly labeled simulated evidence, and reflects. Central contribution: an expensive expert agent compiles/revises versioned reusable robot skills; a faster agent later invokes the same tested capabilities with fewer reasoning calls. ACT is an optional learned controller. Physical SO-101 control must be supervised and independently stoppable. Current repository has voice relay, MCP submit\_plan, LeRobot pose replay, a separate agentic harness, and tests, but full live physical integration is not verified. Full virtual simulation is now Isaac Sim; physical execution and simulation may proceed in parallel.

Read the working SwiftUI/iPhone and Mac relay implementation under `research/joseph/iphone-voice-bridge/`, the current contract and Victor's accessibility/educational simulation research. Preserve working speech behavior or replace it only after verifying the alternative.

## Target experience

A student chooses a question, makes a prediction, directs a physical or simulated experiment, sees the proposed action clearly, corrects/approves it, observes the actual result with provenance, and receives an intelligent follow-up question. Provide voice and text paths, clear progress/status, a visible lab notebook, and separate labels for PHYSICAL / SIMULATED / MODEL-PREDICTED / UNKNOWN.

## Implementation autonomy

Choose native phone UI, web UI, streaming voice, local STT/TTS, ElevenLabs, Gemini Live or adapters based on actual compatibility and latency. Do not force a provider switch for novelty. Speak/respond quickly while long planning/robot tasks continue asynchronously when feasible. The UI should not rely on a long LLM call for an immediate STOP, and it must never describe a proposed action as completed.

## Deliver

One runnable student journey including a negative/failed/unknown outcome case, credible accessibility affordances, thoughtful visual presentation and integration screenshots or recordings. Keep the component seams clear enough to swap between mock, real and Isaac backends.


---

<a id="page-18"></a>

# 🧬 P4 — Isaac Sim & Virtual Robotics Prompt

Source: [🧬 P4 — Isaac Sim & Virtual Robotics Prompt](https://app.notion.com/p/41871c9c107e81faaa35d22c3320fd53?pvs=204)  
Last edited in Notion: 2026-11-14T09:15:24.548Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026) / 08 — Agent Prompts & Execution Playbook

**Last updated:** 2026-11-14 04:15:22 America/New\_York
**Status:** CURRENT COPYABLE AGENT PROMPT. Adapt execution details to observed repository state.

## Assignment

Build the full virtual OpenArms SO-101 science laboratory in Isaac Sim as an independent parallel workstream. Understand OpenArms as a student-directed accessible laboratory assistant: student predicts, commands a robot, observes real or clearly labeled simulated evidence, and reflects. Central contribution: an expensive expert agent compiles/revises versioned reusable robot skills; a faster agent later invokes the same tested capabilities with fewer reasoning calls. ACT is an optional learned controller. Physical SO-101 control must be supervised and independently stoppable. Current repository has voice relay, MCP submit\_plan, LeRobot pose replay, a separate agentic harness, and tests, but full live physical integration is not verified. Full virtual simulation is now Isaac Sim; physical execution and simulation may proceed in parallel.

Read the Isaac page and virtual science experiments page, NVIDIA's official SO-101 vial-to-rack workshop, and official hardware requirements. Do not assume Macs, A100/H100 or the known RTX 3060 12 GB will run a full Isaac Sim stack. Verify a suitable host first; report a compute blocker if one exists, then continue scene/spec preparation that is host-independent.

## Goal

Show a rendered virtual SO-101 performing useful lab manipulation, with resettable scenes and science experiments that can exceed what the physical kit supports. Begin with an existing workshop scene if that gets a working arm fastest. Build at least one compelling virtual science experiment such as buoyancy, torque, pH model comparison or effervescence, matching actual compute and time availability.

## Engineering freedom

Choose Isaac Sim/Isaac Lab modules, Python, USD assets, ROS bridges or standalone scripts based on demonstrated simplicity. Use simulated robotics physics for motion, and add a separate honest scientific model for quantities Isaac does not physically solve. Share high-level intent/skills/events when it reduces duplication; do not couple scene startup to live robot approval or serial communications.

## Deliver

A reproducible environment bootstrap, pinned dependencies, SO-101 scene with camera, basic manipulation result, one changeable virtual science variable and observable outcome, plus short evidence clips. Report simulation assumptions, objective task success and actual machine compatibility. Do not call a rendered pH color physically simulated chemistry unless modeled accordingly.


---

<a id="page-19"></a>

# 🔬 P5 — Experiments, Vision & Evidence Prompt

Source: [🔬 P5 — Experiments, Vision & Evidence Prompt](https://app.notion.com/p/41871c9c107e81efa96fe798a21c7f0c?pvs=204)  
Last edited in Notion: 2026-11-14T09:15:24.548Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026) / 08 — Agent Prompts & Execution Playbook

**Last updated:** 2026-11-14 04:15:22 America/New\_York
**Status:** CURRENT COPYABLE AGENT PROMPT. Adapt execution details to observed repository state.

## Assignment

Design the actual and virtual science demonstrations so OpenArms is more than a moving robotic arm. Understand OpenArms as a student-directed accessible laboratory assistant: student predicts, commands a robot, observes real or clearly labeled simulated evidence, and reflects. Central contribution: an expensive expert agent compiles/revises versioned reusable robot skills; a faster agent later invokes the same tested capabilities with fewer reasoning calls. ACT is an optional learned controller. Physical SO-101 control must be supervised and independently stoppable. Current repository has voice relay, MCP submit\_plan, LeRobot pose replay, a separate agentic harness, and tests, but full live physical integration is not verified. Full virtual simulation is now Isaac Sim; physical execution and simulation may proceed in parallel.

Review Victor's full research under `research/victor/`, current physical/virtual experiment pages, and the camera/data interfaces. Investigate the physical materials/arm constraints before selecting an experiment.

## Desired outcomes

- Select a robust real science demo using student choice, visible result and meaningful follow-up. Candidates: cabbage-indicator pH, buoyancy, effervescence, torque.
- For virtual scenes, build stronger variable-controlled comparisons even where physical materials are absent. Separate domain model from rendered manipulation.
- Record timestamped camera/telemetry and independently observed physical or simulated outcome. Preserve unknown/missing observations rather than hallucinating success.
- Create a concise science explanation and expected measurement/inference limitations for each candidate.

## Freedom and tradeoffs

Test alternatives quickly and adapt to available materials, positioning, lighting, fixtures and compute. Prioritize visible scientific effect over implausible dexterity. Use one fixed Logitech view first if that is enough; add wrist camera or vision model only when there is a measured need. Your job is to discover which experiment works, not execute a predetermined pH recipe at all costs.

## Deliver

Candidate comparison with actual bench evidence, at least one executable scenario definition, lesson variables and objective observations, a capture workflow, and clear simulated-vs-real provenance that the UI can display.


---

<a id="page-20"></a>

# ✅ P6 — Integration, Testing & Reliability Prompt

Source: [✅ P6 — Integration, Testing & Reliability Prompt](https://app.notion.com/p/41871c9c107e813c810be9747d688f73?pvs=204)  
Last edited in Notion: 2026-11-14T09:15:24.548Z

Notion path: OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026) / 08 — Agent Prompts & Execution Playbook

**Last updated:** 2026-11-14 04:15:22 America/New\_York
**Status:** CURRENT COPYABLE AGENT PROMPT. Adapt execution details to observed repository state.

## Assignment

Independently challenge OpenArms and help the orchestrator integrate safely without stalling legitimate parallel engineering. Understand OpenArms as a student-directed accessible laboratory assistant: student predicts, commands a robot, observes real or clearly labeled simulated evidence, and reflects. Central contribution: an expensive expert agent compiles/revises versioned reusable robot skills; a faster agent later invokes the same tested capabilities with fewer reasoning calls. ACT is an optional learned controller. Physical SO-101 control must be supervised and independently stoppable. Current repository has voice relay, MCP submit\_plan, LeRobot pose replay, a separate agentic harness, and tests, but full live physical integration is not verified. Full virtual simulation is now Isaac Sim; physical execution and simulation may proceed in parallel.

Read current runtime contracts, repo tests, existing voice and robot adapters, and the master task board. Execute tests in a safe mock or simulation environment unless a human physical operator explicitly authorizes and supervises motion.

## Cover

Plan identity and duplicate execution; stale confirmation; unauthorized movement; disconnect/stop behavior; model and speech timeouts; unverified observation claims; simulator/physical backend leakage; inconsistent skill versions; shared component integration and rollback. Include positive end-to-end demo checks: spoken request, prediction, authorized skill, actual execution outcome, grounded feedback.

## Style

Automate checks where valuable, keep failures reproducible, and propose focused fixes. Avoid adding heavyweight frameworks or rigid test gates for speculative features. Physical tests are a distinct supervised sign-off. Keep reporting factual: tests actually executed, failures observed, artifacts/commits produced and what remains unknown.

## Deliver

A small runnable acceptance suite, integration results, top failure modes, and an actionable go/no-go note for the demonstration.


---

<a id="page-21"></a>

# OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)

Source: [OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)](https://app.notion.com/p/41871c9c107e814ea932ed2a8ab31b28?pvs=204)  
Last edited in Notion: 2026-11-14T09:21:27.201Z

Notion path: College OS / Projects

## Registry properties

```json
{"Area":["Robotics","ML","Hardware"],"Created":"2026-11-14T02:57:08.602Z","Evidence Link":"https://app.notion.com/p/41771c9c107e81ab8026cdafa6245063","Goal":"Student-directed accessible physical + Isaac Sim virtual science lab; expert-authored reusable robot skills executed by faster agents with less reasoning; evidence-grounded learning.","Next Action":"Open current OpenArms team workspace and 09 Master TODO. Parallelize physical SO-101, voice/UI, skill harness, cameras/evidence, and Isaac Sim as practical; validate shared interfaces, real transfers, simulations and benchmark. Orchestrator reviews main-only merges.","Outcome":"","Priority":"High","Project":"OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)","Status":"Active","Type":"Competition","Updated":"2026-11-14T09:21:27.201Z","date:Review Date:is_datetime":0,"url":"https://app.notion.com/p/41871c9c107e814ea932ed2a8ab31b28"}
```

**Last updated:** 2026-11-14 04:21:24 America/New\_York · **Status:** Active hackathon build. This registry entry is an index, not a second architecture document.

**Canonical shared technical workspace:** [OpenArms — Voice-Accessible Robotic Lab Assistant (HackPrinceton 2026)](https://app.notion.com/p/41771c9c107e81ab8026cdafa6245063)

**Live task owner:** [09 — Master TODO & Workstreams](https://app.notion.com/p/41871c9c107e81d5b6fdfcb4ab71fdd5)

**Current product:** Students choose science questions and direct either a supervised physical SO-101 or an Isaac Sim SO-101 virtual lab; AI helps plan supported skills and reflect on observed/model results. Expert reasoning compiles reusable skills so faster agents can invoke the same tested operation without recurring high-cost planning.

**Current state:** Calibrated physical arms (team-reported) and voice/agentic/runner code exist. Complete physical science demo, measured two-speed improvement and working Isaac lab remain to be independently verified.

**Working approach:** Arbitrary useful independent worktrees/agents; coordination around shared interfaces; integration owner alone pushes remote main. ACT and advanced policies are optional research. Full Isaac lab development is a separate parallel track, not a prerequisite for physical movement.
