# Which tools does the arm expose, to whom, and why these?

Duc's tool brief for OpenArms, Fri Nov 13, 2026. The design is in [harness.md](harness.md) and the plan in [agentic-plan.md](agentic-plan.md). None of this code exists yet. Paths under `agentic/` are Duc's; paths under `firmware/` are proposals to Joseph.

## Finding

"Tools" come in four layers. Each layer can only reach the one below it through a check:

```
1. Brain tools (Claude calls these)        agentic/openarms_agent/tools.py
        │ submit_plan
2. Plan actions (what a plan may contain)  agentic/openarms_agent/catalog.py
        │ validator → teacher Approve → runner
3. Arm steps (ArmPort, what moves)         firmware/ (Joseph); agentic/openarms_agent/mock_arm.py for dev
        │ named poses + gripper
4. Motor primitives (never seen by the LLM) firmware/ on LeRobot 0.6.2
```

STOP sits outside all four layers. It goes from the UI, voice or keyboard straight to `ArmPort.stop()` and never through the LLM.

### 1. Brain tools: what Claude can call

File: `agentic/openarms_agent/tools.py` (brain lane, ticket B2). None of these moves the arm.

| Tool | What it does | Design choice | Alternative |
|---|---|---|---|
| `submit_plan(plan)` | Runs the validator. Returns the rejection reason so the brain can fix the plan, or `awaiting_teacher`. | This is the only route to motion, and it ends at a human. The rejection goes back in the same turn, so the brain fixes its own mistakes without bothering the student. | The brain calls arm steps directly: puts the LLM in the motor loop. Asking for JSON in the reply text: breaks easily. |
| `look(station)` | Returns a camera still of a station. No motion. | Lets the brain take "before" and "after" pictures as evidence. Without motion it needs no approval. | Streaming video into the model: slow and costly. No vision at all: the brain would have to trust what the student says. |
| `record_prediction(text)` | Writes the student's prediction to the notebook | The point of the lab is predict, then test, then observe. The prediction has to be saved *before* the run so it can't be revised afterwards. | Rebuilding it from the chat history later: easy to lose or change. |
| `record_observation(text, source)` | Writes what was seen; `source` is `student`, `teacher` or `unknown` | Keeps evidence apart from what the arm reports. "Executed" never means "it turned pink". | Infer the outcome from the run result: claims a chemistry result the arm can't see. |
| `get_notebook()` | Returns the session so far as short text | The brain can refer back to earlier predictions without a long history | Put the whole notebook in every system prompt: wastes tokens on every turn. |
| `request_help(reason)` | Alerts the teacher and stops submitting plans | For spills, a dropped cup or a worried student: things the LLM shouldn't handle alone | Let the brain keep trying: unsafe around liquids. |

Also from Astranomy: no shell or code tools, since the optional tools didn't clearly help.

### 2. Plan actions: what a plan can contain

File: `agentic/openarms_agent/catalog.py` (core lane, C1). A plan has 1–6 of these for one student instruction.

| Action | What it does | Design choice | Alternative |
|---|---|---|---|
| `add_sample(source, into, portions=1)` | Expands to `pick(source)`, `pour(into)` × portions, `return_cup()`, `home()`. The teacher sees every expanded step. | One macro for the only experiment we run. The brain can't forget to return the cup or go home. Astranomy's biggest planning failure (20.2%) was the wrong target or plan, so fewer choices means fewer of those. | Give the brain `pick`, `pour`, `return_cup` and `home` separately (harness Part B): more flexible, more ways to leave a cup in the gripper. The validator would still catch that, but each rejection costs another round. |
| `wait(seconds)` | The arm holds still for 1–30 s, for example to let a color develop | It goes in the plan, not the conversation, so the teacher approves the whole timing | The brain waits by not replying: no record of it, and the UI can't show a countdown. |
| `present(station)` *(optional)* | Moves the arm out of the camera's view of a station | Add it only if the arm blocks the camera at HOME. Find out at the bench. | Pick a HOME pose that never blocks the camera: better, if one exists. |

`look` is a brain tool (layer 1), not a plan action, because it doesn't move anything. The earlier decision listed it with the actions. This brief proposes moving it.

**Never available to the brain:** joint angles, XYZ targets, speed, torque, gripper force, free-form motion, arming or disarming, retries after a failure. Claude Opus 5.5 driving an arm directly succeeded only 25.3% of the time in Astranomy.

### 3. Arm steps: the `ArmPort` interface that actually moves

The real version is in `firmware/` (Joseph; proposed `firmware/openarms_executor/arm.py`). The mock for development is `agentic/openarms_agent/mock_arm.py` (core lane, C3). The runner (`agentic/openarms_agent/runner.py`, C4) calls these one at a time.

| Step | What the arm does | Precondition (checked by the validator) | Design choice |
|---|---|---|---|
| `pick(station)` | Opens the gripper, moves above the cup, lowers, grips, lifts to a safe height | Gripper empty; the station is a source that still has a cup | Each step is one taught sequence. A failure points to one physical motion, so Joseph knows what to re-teach. |
| `pour(into)` | Moves above the receiver and tips out one pre-filled mini-cup completely | Holding a cup; the cup has a portion left; the receiver has room | A portion is a whole mini-cup, not a timed tilt, so the amount is the same every time. Joseph picks the method after dry runs: drop the cup in, a tipping cradle, or a real tilt pour (the stretch option). |
| `return_cup()` | Puts the cup back at its own station and lets go | Holding a cup | The bench looks the same after every experiment, which keeps the validator's state accurate. |
| `home()` | Rest pose, gripper open | Gripper empty | Every plan ends here, so the next plan always starts from a known pose. |
| `wait(seconds)` | Holds still | 1–30 s | — |
| `stop()` | Halts after the current motion, holds a safe pose, and skips the remaining steps | — (always allowed) | It halts between steps instead of cutting torque, so a held cup isn't dropped. The teacher's physical e-stop is still the hard stop. |
| `state()` | Returns `{at, holding, portions_left, receiver_load, armed}` | — | The validator and runner both read this, so the plan is checked against the real bench rather than the brain's memory of it. |

Failures raise `ArmError(step, reason)`. The runner stops at the first one and **never retries**, because a blind retry around liquid risks a spill. The student is told which step failed and decides what to do next.

### 4. Motor primitives: firmware only

Joseph's, in `firmware/`, on LeRobot 0.6.2 and the SO-101 calibration in `calibration/`.

| Primitive | What it does | Design choice | Alternative |
|---|---|---|---|
| `go_to(pose_name)` | Moves to a named, taught joint pose (`ABOVE_A`, `GRASP_A`, `POUR_C` and so on) with a speed limit and timeout | Poses are taught by hand on the real arm, which is fastest to get reliable with no leader arm | IK from grid coordinates (LeRobot `RobotKinematics`): easier to add stations, but the 5 positioning joints may not reach. ACT policies: need ~50 demos per skill. |
| `gripper(open\|close)` | Opens or closes the gripper | — | — |
| `teach_pose` script | Torque off, move the arm by hand, save the joint readings to a poses file | Fastest way to get poses without a leader arm | Keyboard teleop: the fallback if the servos can't be moved by hand safely. |

An arm step is marked `verified` only after 9 successes in 10 dry runs (`test_action.py`).

### Checks and gates (not tools, but they decide what runs)

| Gate | File | Role |
|---|---|---|
| Validator | `agentic/openarms_agent/validator.py` | Runs the plan step by step against `state()` with fixed rules, and returns one readable sentence on a rejection |
| Sim preview *(optional)* | `agentic/openarms_agent/preview.py` → Stefanie's `preview(plan)` | Shows the teacher a video, with a 3 s timeout. The demo carries on without it. |
| Teacher approval | `agentic/server.py` + Victor's UI | Approve, or Reject with a comment. Nothing moves without it. |
| Stop words | `agentic/openarms_agent/brain.py` | "stop", "wait" and "cancel" are matched before any LLM call |

## Evidence

- [harness.md](harness.md): Part B is the full action catalog and validator rules. Part C covers taught poses. Part D lists the brain's tools.
- Astranomy (Yang, Khetan, Zhang, CoRL 2026 LBR): 25.3% for Claude as a direct policy, 20.2% of failures were the wrong target or plan, and optional tools didn't help.
- `firmware/` on `main` holds only a README as of Nov 13, so every firmware path above is a proposal.

## Open question

- **Liquid or a block?** If it's a block, layer 2 becomes something like `move_block(from, to)`, and `pour` becomes `place`. Layers 1 and 4 stay the same.
- **Should `look` move out of the plan actions and become a brain tool only?** This brief says yes.
- **Is `present` needed?** It depends on whether the arm at HOME blocks the camera.
- **Joseph:** how `pour` works mechanically, and where `ArmPort` lives in `firmware/`.
