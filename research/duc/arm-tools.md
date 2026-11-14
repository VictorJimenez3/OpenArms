# Which tools does the arm expose, to whom, and why these?

Duc's tool brief for OpenArms, Fri Nov 13, 2026, matching [harness.md](harness.md) v3. None of this code exists yet. Paths under `agentic/` are Duc's; paths under `firmware/` are proposals to Joseph.

## Finding

The arm's tools come in four layers. Each layer reaches the one below only through a check:

```
1. Brain tools (Claude calls these)          agentic/openarms_agent/tools.py
        │ submit_plan
2. Plan actions (what a plan may contain)    agentic/openarms_agent/catalog.py
        │ validator → [sim preview] → teacher Approve → runner
3. Arm steps (ArmPort, what moves)           firmware/ (Joseph); agentic/openarms_agent/mock_arm.py for dev
        │ named poses + gripper
4. Motor primitives (never seen by the LLM)  firmware/ on LeRobot 0.6.2
```

STOP sits outside all four. It goes from the UI, voice or keyboard straight to the runner and `ArmPort.stop()`, never through the LLM.

### 1. Brain tools: what Claude can call

File: `agentic/openarms_agent/tools.py` (brain lane, B2). None of these moves the arm.

| Tool | What it does | Design choice | Alternative |
|---|---|---|---|
| `submit_plan(plan)` | Runs the validator; returns the rejection reason or `awaiting_teacher` | The only route to motion, and it ends at a human. A rejection comes back in the same turn, so the brain fixes its plan without bothering the student. | The brain calls arm steps directly: puts the LLM in the motor loop. JSON in the reply text: breaks easily. |
| `look(station)` | Camera still of a station | "Before" and "after" pictures as evidence; no motion, so no approval needed | Stream video into the model: slow and costly. No vision: the brain only has the student's word. |
| `record_prediction(text)` | Saves the student's prediction | Saved *before* the run, so it can't be revised afterwards | Rebuild it from chat history: easy to lose or change |
| `record_observation(text, source)` | Saves what was seen; `source` ∈ `student`, `teacher`, `unknown` | Keeps evidence apart from what the arm reports. "Executed" never means "it turned pink". | Infer the outcome from the run result: claims a result the arm can't see |
| `get_notebook()` | The session so far, as short text | Refers back to earlier predictions without a long prompt | Put the whole notebook in every system prompt: wastes tokens each turn |
| `request_help(reason)` | Alerts the teacher; the brain stops submitting plans | Spills, a dropped cup or a worried student need a human | Let the brain keep trying: unsafe around liquids |

No shell or code tools: in Astranomy, optional tools didn't clearly help.

### 2. Plan actions: what a plan can contain

File: `agentic/openarms_agent/catalog.py` (core lane, C1). A plan holds 1–6 of these for one student instruction.

| Action | What it does | Design choice | Alternative |
|---|---|---|---|
| `add_sample(source, into, portions=1)` | Expands to `pick`, `pour` × portions, `return_cup`, `home`. The teacher sees every expanded step. | One macro for the one experiment. The brain can't forget to return the cup or go home. Wrong target or plan was Astranomy's biggest planning failure (20.2%), so fewer choices means fewer of those. | Expose `pick`/`pour`/`return_cup`/`home` separately (harness v2): more flexible, more ways to leave a cup in the gripper. The validator would catch it, but each rejection costs a round. |
| `wait(seconds)` | The arm holds still 1–30 s, e.g. for a color to develop | In the plan, so the teacher approves the timing and the UI can show a countdown | The brain waits by not replying: no record, no countdown |
| `look(station)` | Camera still inside a plan | Lets one plan include "add, wait, look" in order | Keep `look` as a brain tool only (it needs no approval). Open question below. |
| `present(station)` *(maybe)* | Moves the arm out of the camera's view | Add only if the arm at HOME blocks the camera | A HOME pose that never blocks the camera: better, if one exists |

**Never available to the brain:** joint angles, XYZ targets, speed, torque, gripper force, free-form motion, arming/disarming, retries. Claude Opus 5.5 driving an arm directly succeeded 25.3% of the time in Astranomy.

### 3. Arm steps: the `ArmPort` interface that moves

Real version: `firmware/` (Joseph; proposed `firmware/openarms_executor/arm.py`). Development mock: `agentic/openarms_agent/mock_arm.py` (core, C3). The runner, `agentic/openarms_agent/runner.py` (core, C4), calls them one at a time through `run_step(action, args)`.

| Step | What the arm does | Precondition (validator) | Design choice | Alternative |
|---|---|---|---|---|
| `pick(station)` | Opens the gripper, moves above a mini-cup, lowers, grips, lifts | Gripper empty; station has a cup | One preprogrammed script per step, so a failure points to one motion Joseph can re-record | One long scripted move per experiment: a failure doesn't say where |
| `pour(into)` | Moves above the receiver, tips the pre-filled mini-cup out completely | Holding a cup; receiver has room | A portion is a whole mini-cup, so the amount is the same every time | Timed tilt pour: amount depends on fill level and angle. Kept as the stretch option; drop-in and a tipping cradle come first. |
| `return_cup()` | Puts the cup back at its own station and lets go | Holding a cup | The bench looks the same after every run, which keeps the validator's state true | Drop used cups in a bin: needs a bin station and more poses |
| `home()` | Rest pose, gripper open | Gripper empty | Every plan ends here, so the next starts from a known pose | Stay at the last pose: the next plan starts somewhere unknown |
| `wait(seconds)` | Holds still | 1–30 s | — | — |
| `stop()` | Halts after the current motion, holds a safe pose, skips the rest | Always allowed | Halting between steps instead of cutting torque doesn't drop a held cup. The teacher's physical e-stop stays the hard stop. | Torque off at once: fastest, but drops the cup |
| `state()` | Returns `{at, holding, portions_left, receiver_load, armed}` | — | Validator and runner both read it, so plans are checked against the bench, not the brain's memory | Let the brain track state: drifts after a failure |

Failures raise `ArmError(step, reason)`. The runner stops at the first one and **never retries**: a blind retry around liquid risks a spill. The student hears which step failed and decides.

### 4. Motor primitives: firmware only

Joseph's, in `firmware/`, on LeRobot 0.6.2 (Feetech servos) with the calibration in `calibration/`.

**These are preprogrammed movement scripts. No model is trained.** Each arm step is a fixed script that replays saved joint positions. Saving a position is a one-time recording: drive the arm there, save the joint readings under a name. Nothing learns anything.

| Primitive | What it does | Design choice | Alternative |
|---|---|---|---|
| `go_to(pose_name)` | Moves to a named joint pose (`ABOVE_A`, `GRASP_A`, `TIP_C`…) with a speed limit and timeout | Replaying saved positions is deterministic and the fastest way to reliable motion in 36 h | IK from grid coordinates (`RobotKinematics`): easier to add stations, but 5 positioning joints may not reach. A trained policy (ACT): needs ~50 demos and training per skill, and can behave differently each run. |
| `gripper(open\|close)` | Opens or closes the gripper | — | — |
| `record_pose` script | Saves the follower's current joint readings under a name (one-time setup, not training) | Drive the follower there with the leader arm (`lerobot-teleoperate`); both arms are already calibrated | Torque off and move the follower by hand: fallback. Keyboard teleop: slowest. |
| `test_action` script | Dry-runs one step N times | A step is `verified` only after 9 of 10 | Trust one good run: hides flaky grasps |

### Gates (not tools, but they decide what runs)

| Gate | File | Role | Alternative |
|---|---|---|---|
| Validator | `agentic/openarms_agent/validator.py` | Walks the expanded plan against `state()` with fixed rules; one readable sentence on rejection | Ask the LLM to check itself: not reliable |
| Sim preview *(optional)* | `agentic/openarms_agent/preview.py` → Stefanie's `preview(plan)` | Shows the teacher a video, 3 s timeout; the demo carries on without it | Require a preview: one sim failure stops the demo |
| Teacher approval | `agentic/server.py` + Victor's UI | Approve, or Reject with a comment, synchronously. Nothing moves without it. | Asynchronous queue: needed for real classrooms, not for a live demo |
| Stop words | `agentic/openarms_agent/brain.py` | "stop", "wait", "cancel" matched before any LLM call | Let the model decide what counts as stop: slower, can miss one |

## Evidence

- [harness.md](harness.md) v3: Part B (layers, catalog, validator rules), Part C (poses, file map), Part D (brain tools).
- Astranomy (Yang, Khetan, Zhang, CoRL 2026 LBR): Claude as a direct policy 25.3%; 20.2% of failures were wrong target or plan; optional tools didn't help.
- [firmware/README.md](../../firmware/README.md): LeRobot pinned at `e0d50211` (0.6.2) with Feetech, leader and follower calibrated. `firmware/` holds no executor yet, so every firmware path above is a proposal.

## Open question

- **Liquid or a block?** If a block, `add_sample` becomes something like `move_block(from, to)` and `pour` becomes `place`. Layers 1 and 4 stay the same.
- **`look`:** brain tool only, or also a plan action?
- **`present`:** needed only if the arm at HOME blocks the camera.
- **Joseph:** the `pour` mechanism, and where `ArmPort` lives in `firmware/`.
