# Lab Arm: Agent Instruction Prompt & Arm Action Catalog (v3)

**Status:** Proposal, Fri Nov 13, 2026, ~23:45. Nothing in `agentic/` is written yet, and nothing is verified on the real arm. Station names, poses and steps are placeholders until Joseph records and tests them. The team plan is [agentic-plan.md](agentic-plan.md).

**What changed since v2**
- The brain now sees three plan actions: `add_sample`, `wait` and `look`. Pick, pour, return-the-cup and home are arm steps it never names (Part B).
- A portion is one pre-filled mini-cup, tipped all the way out.
- Teacher approval is synchronous only. A sim preview is optional.
- Hardware is confirmed: SO-101 with Feetech servos on LeRobot 0.6.2. **There is a leader arm**, used once to record the poses the scripts replay (Part C). No model is trained.
- Part C now maps each piece to a file and an owner.

**Setup**
- **One SO-101 follower arm, on the teacher's side.** It's the only arm in the demo. The leader arm is used to record poses, not by the student.
- **The teacher is on-site.** They set up the bench, approve plans and hold the physical stop.
- **The student is remote or has a motor disability.** They speak (through Joseph's iPhone voice bridge) or type, and watch the camera feed.
- **The LLM is the "brain"**: Claude Sonnet 5.5 (`claude-sonnet-5-5`), one model call per student turn. It turns the student's words into a short plan. Local code checks the plan, the teacher approves it, then the arm runs it without the LLM in the loop.

**Contents**
- **Part A:** design rules from NVIDIA's Astranomy study
- **Part B:** tool layers and the action catalog
- **Part C:** how it's built, and who builds what
- **Part D:** paste-ready instruction prompt for the brain
- **Part E:** open items

---

## Part A: Design rules (from Astranomy)

Source: J. X. Yang, A. Khetan, S. Zhang, *Astranomy*, NVIDIA Seattle Robotics Lab, CoRL 2026 (LBR), Oct 14, 2026. <https://research.nvidia.com/labs/srl/projects/astranomy/>. This is the original idea we build on. They test whether a general model (GPT-6 Astra) can act as a pick-and-place policy for a DROID Franka arm. All results are **simulation (RoboLab) with the sim paused during every model call**; no real robot was tested. Their conclusion: "there is a significant gap between capability and real-time control and deployment." This project closes that gap by keeping the model out of the motor loop.

- **The LLM is never in the motor loop.** Its calls took ~13–19 s each and made up 95–98% of episode time; a 5 s pick took ~4 min. The brain plans; local code moves the arm.
- **The arm waits at HOME while the brain thinks.** A real bench doesn't pause the way the sim did.
- **One brain call per student turn**, not per motion. Cost was ~$2 per successful episode for Direct calls and ~$36 for a persistent agent session.
- **Stations, not coordinates.** Geometry in the prompt was crucial for direct control (19% → 73%). We avoid the problem: the brain names stations, and the executor owns calibrated, absolute poses.
- **Give the brain the session notebook.** Keeping full history helped most.
- **No shell or code tools.** Optional tools didn't clearly help.
- **Ambiguous request → clarify, no motion.** Vague instructions hurt one-shot calls (72.7% → 64.0%); a persistent agent barely noticed (86.0% → 85.3%). We keep the full conversation history across turns to get closer to the persistent case, and still ask before planning.
- **Separate "the move finished" from "the experiment worked."** When the model reviewed a fast policy's moves, it stepped in for: failed grasps 64.4%, wrong target or plan 20.2%, placement failures 11.4%.
- **Don't force a "plan first" instruction for reasoning.** Explicit planning prompts didn't help (86.0% with vs 90.0% without). Our plan is a structured output for the validator, not a reasoning step.
- **Model ranking doesn't transfer.** As a direct policy, Astra scored 72.7% and Claude Opus 5.5 25.3%. That measures low-level control, which we never ask the brain to do. Pick our brain model by latency and tool-use reliability.
- **Fewer choices, fewer wrong plans.** Wrong target or plan was the biggest planning failure (20.2%). So the brain gets one macro for the one experiment, not the separate arm steps.

---

## Part B: Tool layers and the action catalog

Each layer can only reach the one below it through a check:

```
1. Brain tools (Claude calls these)          agentic/openarms_agent/tools.py
        │ submit_plan
2. Plan actions (what a plan may contain)    agentic/openarms_agent/catalog.py
        │ validator → [sim preview] → teacher Approve → runner
3. Arm steps (ArmPort, what moves)           firmware/ (Joseph); mock_arm.py for development
        │ named poses + gripper
4. Motor primitives (never seen by the LLM)  firmware/ on LeRobot 0.6.2
```

**STOP sits outside all four layers.** It goes from the UI, voice or keyboard straight to the runner and `ArmPort.stop()`. Stop words ("stop", "wait", "cancel") are matched before any LLM call.

### Bench map (example; set per lab)

| Station | Holds | Kind |
|---|---|---|
| `A` | pre-filled mini-cups of sample A (teacher-labeled) | source |
| `B` | pre-filled mini-cups of sample B (teacher-labeled) | source |
| `C` | receiver with purple indicator | receiver (fixed) |
| `D` | receiver with purple indicator | receiver (fixed) |
| `HOME` | arm rest pose, gripper open | — |

### Arm state

```json
{ "at": "HOME", "holding": null, "portions_left": { "A": 2, "B": 2 }, "receiver_load": { "C": 0, "D": 0 }, "armed": true }
```

- `holding` is the station the held cup came from (`"A"`), or `null`.
- Capacity is counted in **portions**, not mL. A portion is one pre-filled mini-cup tipped all the way out, so its size comes from the cup, not from timing.

### Layer 1: brain tools (none of these moves the arm)

| Tool | What it does | Why |
|---|---|---|
| `submit_plan(plan)` | Runs the validator. Returns the rejection reason, or `awaiting_teacher`. | The only route to motion, and it ends at a human. A rejection comes back in the same turn, so the brain fixes its own plan without bothering the student. |
| `look(station)` | Camera still of a station | "Before" and "after" pictures as evidence |
| `record_prediction(text)` | Saves the student's prediction | Saved *before* the run, so it can't be revised afterwards |
| `record_observation(text, source)` | Saves what was seen; `source` ∈ `student`, `teacher`, `unknown` | Keeps evidence apart from what the arm reports |
| `get_notebook()` | The session so far, as short text | Refers back without a long prompt |
| `request_help(reason)` | Alerts the teacher; the brain stops submitting plans | Spills, a dropped cup, a worried student |

### Layer 2: plan actions (the only things a plan may contain)

| Action | What happens | Validator checks |
|---|---|---|
| `add_sample(source, into, portions=1)` | Expands to (`pick(source)`, `pour(into)`, `return_cup(source)`) × portions, then `home()`: one mini-cup per portion, so `portions=2` is 7 steps. The teacher sees every expanded step. | source is a source with enough portions left; `into` is a receiver with room |
| `wait(seconds)` | The arm holds still, e.g. to let a color develop. In the plan so the teacher approves the timing and the UI can show a countdown. | `1 ≤ seconds ≤ 30` |
| `look(station)` | Camera still, no motion | station exists |

`look` is both a tool and a plan action for now; see Part E. **Never available to the brain:** pick/pour/return/home on their own, joint angles, XYZ targets, speed, torque, gripper force, free-form motion, the physical stop, arming/disarming, retries after a failure.

### Layer 3: arm steps (`ArmPort`)

| Step | What the arm does | Precondition |
|---|---|---|
| `pick(station)` | Opens the gripper, moves above a mini-cup, lowers, grips, lifts to a safe height | gripper empty; the station has a cup |
| `pour(into)` | Moves above the receiver and tips the mini-cup out completely | holding a cup; the receiver has room |
| `return_cup()` | Puts the cup back at its own station and lets go | holding a cup |
| `home()` | Rest pose, gripper open | gripper empty |
| `wait(seconds)` | Holds still | 1–30 s |
| `stop()` | Halts after the current motion, holds a safe pose, skips the remaining steps. It doesn't cut torque, so a held cup isn't dropped. The teacher's physical e-stop is still the hard stop. | always allowed |
| `state()` | Returns the arm state above | — |

`ArmPort` is `run_step(action, args)`, `stop()`, `state()`. Failures raise `ArmError(step, reason)`. The runner stops at the first one and **never retries**: a blind retry around liquid risks a spill.

**`pour` mechanism** (Joseph picks after dry runs; the name stays the same): drop the mini-cup in → a tipping cradle → a real tilt pour (stretch).

### Plan format (brain → validator → teacher → runner)

The brain submits 1–6 plan actions for **one** student instruction:

```json
{
  "plan_id": "p-0007",
  "student_instruction": "add some of A to C",
  "steps": [
    { "action": "add_sample", "args": { "source": "A", "into": "C", "portions": 1 } }
  ]
}
```

**Validator** (local code, no LLM): expands the plan and walks it step by step against `state()`. It rejects an unknown action, a bad argument, more than 6 plan actions, an empty source, a receiver over capacity, or a plan that doesn't end at `HOME` with an empty gripper. A rejection means no motion and one readable sentence back to the brain. On success it returns the predicted end state.

**Sim preview (optional):** the agent calls Stefanie's `preview(plan) -> {ok, video_url?, warnings[]}` with a 3 s timeout and carries on without it.

**Teacher approval:** the expanded steps appear in Victor's UI with **Approve / Reject + comment**, synchronously. Nothing moves without approval.

**Runner:** runs the approved steps one at a time on `ArmPort`, stops at the first error or STOP, and reports which step failed. The brain then tells the student in one line (`notify`) and asks what they see.

```json
// ExecutionResult
{ "plan_id": "p-0007", "status": "executed", "steps_done": ["pick", "pour", "return_cup", "home"], "failed_step": null, "reason": null }
// status ∈ rejected | awaiting_teacher | teacher_rejected | executing | executed | failed | stopped

// ExperimentOutcome  (evidence only; never inferred from ExecutionResult)
{ "plan_id": "p-0007", "station": "C", "before_image": "C_before.jpg", "after_image": "C_after.jpg",
  "observation": "Student: it went pinkish", "evidence_source": "student" }
// evidence_source ∈ student | teacher | unknown
```

---

## Part C: How it's built, and who builds what

### Layer 4: preprogrammed scripts (Joseph, `firmware/`)

Each arm step is a fixed script that replays named poses plus gripper commands. No model is trained; a pose is just saved joint readings:

```
pick(A)  = gripper(open) → go_to(ABOVE_A) → go_to(GRASP_A) → gripper(close) → go_to(LIFT_A)
pour(C)  = go_to(ABOVE_C) → go_to(TIP_C) → go_to(ABOVE_C)
```

| Method | How | Status |
|---|---|---|
| **Record with the leader arm** | Teleoperate (`lerobot-teleoperate`, see [firmware/README.md](../../firmware/README.md)), move the follower to a pose, save its joint readings as a named pose | First choice: both arms are already calibrated in `calibration/` |
| **Hand-guiding** | Torque off, move the follower by hand, save the pose | Fallback |
| **IK from grid coordinates** | LeRobot `RobotKinematics` from measured station cells | For adding stations later; the arm has only 5 positioning joints, so check reach |

`go_to` has a speed limit and a timeout. A step is marked `verified` only after 9 successes in 10 dry runs. **Learned policies (ACT) stay deprioritized**: the leader arm makes demos possible, but ~50 demos per skill doesn't fit 36 h, and scripted poses are easier to debug.

### `agentic/openarms_agent/` (Duc, built in Ralph lanes)

| Lane | File | What it does |
|---|---|---|
| foundation | `types.py`, `contracts/*.example.json` | Shared dataclasses and the `ArmPort` protocol; example JSON the team agrees on in `docs/INTERFACES.md` |
| core | `catalog.py` | The three plan actions and `expand()` |
| core | `validator.py` | `validate(plan, state) -> ValidationResult` |
| core | `mock_arm.py` | Fake `ArmPort`: ~0.5 s per step, can fail at a named step |
| core | `runner.py` | `run(plan, arm, should_stop) -> ExecutionResult`, never retries |
| core | `notebook.py` | Session log to `outputs/sessions/<id>.json`, `as_text()` for the brain |
| brain | `prompts/brain_system.md`, `prompting.py` | Part D, filled by `render_system_prompt(stations, arm_state, objective)` |
| brain | `tools.py` | Layer 1 tool schemas and `dispatch()` |
| brain | `brain.py` | `Brain(session_id).handle_turn(turn_id, text) -> TurnReply`, stop words, `notify(result)` |
| brain | `scripts/brain_repl.py` | Terminal demo: type as the student, approve y/n as the teacher, run on `MockArm` |
| api | `relay_adapter.py` | `dialogue_reply(session_id, turn_id, text) -> {text, lab_stage}` for Joseph's `relay/dialogue.py` |
| api | `agentic/server.py` | FastAPI: `GET /plans/pending`, `POST /plans/{id}/approve\|reject`, `POST /stop`, a status stream |
| api | `preview.py` | Stefanie's `preview(plan)` with a 3 s timeout |

The agent server runs on the laptop plugged into the arm and calls the executor as ordinary Python. Everyone develops against `MockArm`.

### Built by teammates
- The real `ArmPort` and layer 4 on the SO-101: Joseph.
- Speech-to-text, text-to-speech and the iPhone bridge (PR #5): Joseph.
- The teacher approval UI: Victor.
- The 3D sim and `preview()`: Stefanie.

---

## Part D: Instruction prompt for the brain (paste-ready)

Fill `{{...}}` at session start.

```text
You are the Lab Companion, the "brain" of an accessible remote science lab. A student who cannot easily
use their hands runs a real experiment with ONE robot arm located at their teacher's bench. The student
is remote and watches through a camera. The teacher is next to the arm and approves every plan before
the arm moves.

The student does the science. The robot provides the hands. You turn the student's words into safe arm
plans and help them learn.

## Who decides what
- Student: chooses predictions, which samples, where, how many portions, what order, and the conclusion.
- You: translate one student instruction into a short plan using ONLY the plan actions below, ask
  clarifying questions, keep the notebook, and ask learning questions.
- Teacher: approves or rejects each plan, handles the physical stop, and may confirm what the camera shows.
- Never make a scientific choice for the student or tell them the expected result before they test it.

## Lab
Objective: {{objective}}

One arm, one action at a time. It works only with these stations:
{{stations_table}}

Current arm state:
{{arm_state}}        (where it is, what it holds, portions left, receiver load)

### Plan actions
- add_sample(source, into, portions=1): the arm picks up a cup from a source (A or B), tips one portion
  into a receiver (C or D) per portion, puts the cup back and returns home. A portion is one small
  pre-filled cup, not a measured volume.
- wait(seconds): the arm holds still for 1–30 seconds, e.g., to let a change develop.
- look(station): take a camera picture of a station. No motion.

### Plan rules
- One student instruction → one plan of 1–6 plan actions.
- Never add a scientific step the student didn't ask for: no extra samples, receivers or portions.
- You cannot control angles, positions, speed, force, or any motion not listed above. If the student
  asks for something outside the list, say it isn't possible on this arm and list what is.
- Never retry a failed plan on your own.

### Your tools
- record_prediction(text)
- submit_plan(plan) → a rejection reason you can fix, or awaiting_teacher
- look(station) → image reference
- record_observation(text, source)   source ∈ student | teacher | unknown
- get_notebook()
- request_help(reason) → alerts the teacher

## Session flow
1. PRE-LAB
   - State the objective in one or two sentences.
   - Ask the student for a prediction in their own words. If they're stuck, ask a guiding question;
     don't give the answer.
   - Save it with record_prediction.
2. EXPERIMENT (for each student instruction)
   a. If anything is missing or unclear (which sample, which receiver, how many portions), ask ONE
      short question. No plan yet.
   b. Read the plan back in plain words:
      "I'll add one portion of A to C. Send it to your teacher?"
   c. Only after a clear yes: look(into) for a "before" picture, then submit_plan.
      If it's rejected, fix the plan if you can; otherwise tell the student why and offer what is possible.
   d. Then say: "Waiting for your teacher to approve."
   e. When you're told the result, say what happened in one short line:
      - teacher_rejected: share the teacher's comment.
      - executed: "The arm finished the steps."
      - failed or stopped: "The arm stopped at <step>." Ask the student what they want to do next.
   f. Take look(into) for an "after" picture. Ask what the student sees. Save it with
      record_observation. If they can't tell, ask the teacher or record "unknown".
3. POST-LAB
   - Using the notebook, ask what actually changed and how it compares with the prediction.
   - Ask why it may have happened, what stayed the same, and what they'd test next.
   - If a choice or conclusion is off but safe, let it stand and ask a question that helps them notice.
     Safe mistakes are part of learning.

## Hard rules
- Never invent what happened. Colors, amounts and results come only from the student, the teacher, or
  "unknown". "The arm finished" never means "the sample was added".
- No plan is sent without the student's yes. No motion happens without the teacher's approval.
- If something seems wrong (spill, dropped cup, the student is worried), call request_help and stop
  submitting plans.
- Say "portions", never milliliters or exact pH.

## Tone and accessibility
- Your replies may be spoken aloud. Short sentences, one question at a time, plain words, no lists or
  symbols. Define a science term the first time.
- The student may speak or type. Accept short or partial phrases and confirm them rather than correcting.
- Be warm and patient. Praise good questions and careful thinking, not only right answers.

## Examples
Student: "do the vinegar one"
You: "Into which receiver, C or D?"

Student: "C"
You: "I'll add one portion of A to C. Send it to your teacher?"
Student: "yes"
→ look("C"); submit_plan({steps:[add_sample(source="A", into="C", portions=1)]})
You: "Waiting for your teacher to approve." … "The arm finished the steps."
→ look("C")
You: "Take a look at C. What do you notice?"

Student: "make it pour faster and tilt more"
You: "I can't change speed or tilt on this arm. I can add a portion, wait, or show you a station
up close. What would you like to do?"
```

Stop words never reach this prompt: `brain.py` answers "stop", "wait" and "cancel" itself and calls the runner's stop.

---

## Part E: Open items

- [ ] **Liquid or a block?** Joseph's relay mock says "predict where the block will land". If it's a block, `add_sample` becomes something like `move_block(from, to)`, `pour` becomes `place`, and the capacity rule changes. Layers 1 and 4 stay the same.
- [ ] **Joseph:** the `pour` mechanism, and where `ArmPort` lives in `firmware/`.
- [ ] Record the poses with the leader arm and dry-run each step 10 times.
- [ ] Should `look` be a brain tool only, not a plan action? It doesn't move anything, so it needs no approval.
- [ ] Is `present(station)` needed? Only if the arm at HOME blocks the camera. Check at the bench.
- [ ] **Victor:** status stream as Server-Sent Events or WebSocket.
- [ ] `types.py`: dataclasses for now; revisit pydantic when the api lane starts.
- [ ] Stream the camera to the student; check latency on venue Wi-Fi.
- [ ] Test `stop()` with a held cup over the spill tray.
- [ ] Get organizer approval for liquids. Keep electronics out of the pour zone.
