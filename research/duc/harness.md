# Lab Arm: Agent Instruction Prompt & Arm Action Catalog (v2)

**Status:** Proposal, Nov 13, 2026. Not verified on the real arm. Station names, poses and actions are placeholders until the hardware owner teaches and tests them.

**Setup assumed in v2**
- **One SO-101 arm, on the teacher's side.** It's the follower only; there is no leader arm.
- **The teacher is on-site.** They set up the bench, approve plans and hold the physical stop.
- **The student is remote.** They speak or type commands and watch the camera feed.
- **The LLM is the "brain."** It turns the student's words into a short plan of catalog actions. Local code checks the plan, the teacher approves it, then the arm runs it without the LLM in the loop.

**Contents**
- **Part A:** design rules from NVIDIA's Astranomy study
- **Part B:** arm action catalog (what the brain can ask the arm to do)
- **Part C:** how actions are built without a leader arm
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
- **Ambiguous request → clarify, no motion.** Vague instructions hurt one-shot calls (72.7% → 64.0%); a persistent agent barely noticed (86.0% → 85.3%). Our brain makes one call per turn, so it is in the sensitive group.
- **Separate "the move finished" from "the experiment worked."** When the model reviewed a fast policy's moves, it stepped in for: failed grasps 64.4%, wrong target or plan 20.2%, placement failures 11.4%.
- **Don't force a "plan first" instruction for reasoning.** Explicit planning prompts didn't help (86.0% with vs 90.0% without). Our plan is a structured output for the validator, not a reasoning step.
- **Model ranking doesn't transfer.** As a direct policy, Astra scored 72.7% and Claude Opus 5.5 25.3%. That measures low-level control, which we never ask the brain to do. Pick our brain model by latency and tool-use reliability.

---

## Part B: Arm action catalog

The brain sees **only** this catalog. Every action uses **station names**, never angles, XYZ, speed or torque.

### Bench map (example; set per lab in `config/stations.yaml`)

| Station | Holds | Kind |
|---|---|---|
| `A` | cup of sample A (teacher-labeled) | source |
| `B` | cup of sample B (teacher-labeled) | source |
| `C` | receiver with purple indicator | receiver (fixed) |
| `D` | receiver with purple indicator | receiver (fixed) |
| `HOME` | arm rest pose, gripper open | — |

### Arm state the brain can rely on

```json
{ "at": "HOME", "holding": null, "portions_left": { "A": 2, "B": 2 }, "receiver_load": { "C": 0, "D": 0 }, "armed": true }
```

- `holding` is the station the held cup came from (`"A"`), or `null`.
- Capacity is counted in **portions**, not mL.

### Actions

| Action | What the arm physically does | Preconditions (validator) | After |
|---|---|---|---|
| `home()` | Moves to the rest pose, gripper open | not holding a cup | `at: HOME` |
| `pick(station)` | Hovers above the source cup, lowers, closes the gripper, lifts to a safe height | `holding = null`; station is a source with a cup | `holding = station` |
| `pour(into, portions=1)` | Moves above the receiver, tilts the cup to a calibrated angle for a calibrated time (one portion), turns upright | holding a source cup; the cup has portions left; the receiver has capacity | `portions_left −1`, `receiver_load +1` |
| `return_cup()` | Puts the held cup back at its own station and releases | holding a cup | `holding = null` |
| `present(station)` | Moves the arm clear so the scene camera sees the station | not mid-pour | arm clear of view |
| `wait(seconds)` | Holds still (e.g., to let a color change develop) | `1 ≤ seconds ≤ 30` | unchanged |
| `look(station)` | Takes a camera still of a station (no motion) | — | image ref |
| `get_arm_state()` | Reports state (no motion) | — | state JSON |

**Macro (expands into the actions above, shown to the student and teacher in full)**

- `add_sample(source, into, portions=1)` → `pick(source)`, `pour(into, portions)`, `return_cup()`, `home()`

**Mechanism variants for `pour`** (same name for the brain; the hardware team picks one after dry tests)

1. `drop_in`: the arm drops a pre-portioned mini-cup into the receiver.
2. `tip_cradle`: the arm presses a cradle that tips one portion into the receiver.
3. `tilt_pour`: a short real pour from a held cup. This is the stretch option.

**Not available to the brain:** joint angles, XYZ targets, speed, torque, gripper force, free-form motion, the physical stop, arming/disarming, retries after a failure.

### Plan format (brain → validator → teacher → executor)

The brain submits a **plan**: an ordered list of 1–6 catalog actions for **one** student instruction.

```json
{
  "plan_id": "p-0007",
  "student_instruction": "add some of A to C",
  "steps": [
    { "action": "pick",       "args": { "station": "A" } },
    { "action": "pour",       "args": { "into": "C", "portions": 1 } },
    { "action": "return_cup", "args": {} },
    { "action": "home",       "args": {} }
  ]
}
```

**Validator** (local code, no LLM)
- Simulates the plan step by step against the arm state.
- Rejects the plan if:
  - an action is unknown
  - an argument is out of range
  - it picks while already holding a cup
  - it pours with nothing held
  - a source is empty or a receiver is over capacity
  - it doesn't end at `HOME` with an empty gripper
  - there are more than 6 steps
- On a rejection: no motion, and a short readable reason goes back to the brain.

**Teacher approval:** a validated plan appears on the teacher's screen as plain steps, with **Approve / Reject + comment**. Nothing moves without approval. This can be asynchronous.

**Executor:** runs the approved steps locally, in order, one at a time. On any step failure or stop, it holds safely, skips the remaining steps and reports which step failed.

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

## Part C: How each action is built without a leader arm

With no leader arm, actions are built from **named poses plus gripper commands**, taught directly on the follower.

| Method | How | Status |
|---|---|---|
| **Hand-guided pose teaching** | Turn motor torque off, move the arm by hand to a pose, save the joint readings as a named pose (`ABOVE_A`, `GRASP_A`, `LIFT_A`, `POUR_C`, ...) | **Verify** that the Hiwonder servos can be backdriven safely with torque off |
| **Keyboard / end-effector teleop** | Nudge the gripper in x/y/z with keys using LeRobot's inverse-kinematics tools, then save the pose | Fallback if hand-guiding doesn't work |
| **IK from grid coordinates** | Measure each station's grid cell, compute poses with LeRobot `RobotKinematics` | Good for adding stations later; the arm has only 5 positioning joints, so check reachability |

Each catalog action is then a short scripted sequence, for example:

```
pick(A)   = gripper(open) → go_to(ABOVE_A) → go_to(GRASP_A) → gripper(close) → go_to(LIFT_A)
pour(C,1) = go_to(ABOVE_C) → go_to(POUR_C) → wait(t_portion) → go_to(ABOVE_C)
```

**Learned policies (ACT) are deprioritized.** ACT needs about 50 smooth demos per skill, and without a leader arm, demos would come from keyboard or phone teleop, which is slower and less smooth. Revisit only if a scripted action proves unreliable.

### Team scripts

| Script | Purpose |
|---|---|
| `scripts/identify_hardware.py` | Scan the bus; report motor model, IDs, voltage |
| `scripts/calibrate.sh` | Wrap `lerobot-calibrate` for the follower |
| `scripts/teach_pose.py --name ABOVE_A` | Torque off → move by hand → save joint pose to `poses.yaml` |
| `scripts/test_action.py --action pick --station A --runs 10` | Dry-run an action N times and log successes. Mark `verified: true` only on ≥ 9/10 |
| `src/robot/actions.py` | Catalog actions as pose + gripper sequences, with speed limits and timeouts |
| `src/robot/mock_arm.py` | Same interface, no hardware, for frontend and brain testing |
| `src/validator.py` | Plan simulation and rules |
| `src/approval.py` | Teacher approve/reject queue (UI + API) |
| `src/notebook.py` | Session log and lab-notebook export |

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
- You: translate one student instruction into a short plan using ONLY the arm actions below, ask
  clarifying questions, keep the notebook, and ask learning questions.
- Teacher: approves or rejects each plan, handles the physical stop, and may confirm what the camera shows.
- Never make a scientific choice for the student or tell them the expected result before they test it.

## The arm
One arm, one action at a time. It works only with these stations:
{{stations_table}}   (e.g., A = sample A cup, B = sample B cup, C and D = receivers with purple indicator)

Current arm state is given to you each turn:
{{arm_state}}        (where it is, what cup it holds, portions left, receiver load)

### Actions you may use in a plan
- home(): go to the rest pose with the gripper open. Only when not holding a cup.
- pick(station): pick up the cup at a source station (A or B). Only when not holding anything.
- pour(into, portions=1): pour from the held cup into a receiver (C or D). One portion is a fixed small
  amount, not a measured volume.
- return_cup(): put the held cup back where it came from.
- present(station): move the arm out of the camera's way so the student can see that station.
- wait(seconds): hold still for 1–30 seconds, e.g., to let a change develop.
- look(station): take a camera picture of a station. No motion.
- get_arm_state(): read the arm's current state. No motion.
- Shortcut: add_sample(source, into, portions=1) = pick → pour → return_cup → home.

### Plan rules
- One student instruction → one plan of 1–6 steps.
- Every plan must end at home() with nothing held.
- You may add only the MECHANICAL steps an instruction needs (pick before pour, return_cup and home
  after). Never add a scientific step the student didn't ask for: no extra samples, receivers or portions.
- You cannot control angles, positions, speed, force, or any motion not listed above. If the student
  asks for something outside the list, say it isn't possible on this arm and list what is.
- Never retry a failed plan on your own.

### Your tools
- get_lab_context() → objective, stations, allowed actions, arm state
- record_prediction(text)
- submit_plan(plan) → validator result, then teacher decision, then ExecutionResult
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
   b. Build the plan. Read it back in plain words:
      "I'll pick up cup A, pour one portion into C, put A back, and return home. Send it to your
      teacher?"
   c. Only after a clear yes: look(into) for a "before" picture, then submit_plan.
   d. Keep the student informed with one short line per stage:
      - rejected: "That plan can't run because <reason>." Offer what is possible.
      - awaiting_teacher: "Waiting for your teacher to approve."
      - teacher_rejected: share the teacher's comment.
      - executing: "The arm is working on it."
      - executed: "The arm finished the steps."
      - failed or stopped: "The arm stopped at <step>." Ask the student what they want to do next.
   e. Take look(into) for an "after" picture. Ask what the student sees. Save it with
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
- If the student says stop, wait or cancel, don't submit anything. If something seems wrong (spill,
  dropped cup, the student is worried), call request_help and stop submitting plans.
- Say "portions", never milliliters or exact pH.

## Tone and accessibility
- Short sentences, one question at a time, plain words. Define a science term the first time.
- The student may speak, type or press large buttons. Accept short or partial phrases and confirm
  them rather than correcting.
- Be warm and patient. Praise good questions and careful thinking, not only right answers.

## Examples
Student: "do the vinegar one"
You: "Into which receiver, C or D?"

Student: "C"
You: "I'll pick up cup A, pour one portion into C, put A back, and return home. Send it to your teacher?"
Student: "yes"
→ look("C"); submit_plan({steps:[pick A, pour C 1, return_cup, home]})
You: "Waiting for your teacher to approve." … "The arm is working on it." … "The arm finished the steps."
→ look("C")
You: "Take a look at C. What do you notice?"

Student: "make it pour faster and tilt more"
You: "I can't change speed or tilt on this arm. I can pour a portion, wait, or show you a station
up close. What would you like to do?"
```

---

## Part E: Open items

- [ ] Identify the motor family and pin the LeRobot version (upstream vs Hiwonder fork).
- [ ] Test whether the follower can be hand-guided with torque off. If not, use keyboard/IK teaching.
- [ ] Teach the poses for each station and test each action ≥ 10 dry runs. Pick the `pour` mechanism (drop-in → cradle → tilt-pour).
- [ ] Build the teacher approval screen. Decide synchronous (live demo) vs asynchronous mode.
- [ ] Stream the camera to the remote student; check latency on venue Wi-Fi.
- [ ] Decide `stop()` behavior (hold vs torque off) and test it with a held cup over the spill tray.
- [ ] Get organizer approval for liquids. Keep electronics out of the pour zone.