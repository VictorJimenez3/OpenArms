# Is Victor's agent connected to the openarms_sim demo bench?

**Duc's integration · November 14, 2026 · branch `integration`** · Evidence label: **sim** (MuJoCo, kinematic). No physical operation.

## Finding

Yes, as a text baseline. The lab app now runs the openarms_sim `demo` setup by default under `OPENARMS_EXECUTION=mujoco`. A student request becomes an exact proposal. The student sees and confirms it, the simulator runs it once, and a fresh rendered frame is read independently. STOP revokes a presented proposal. Unsupported routes, amounts and return stations end with no proposal and zero dispatches. The old two-vessel water scene stays selectable for regression (`OPENARMS_SCENE=two_vessel`).

A live run with a real expert passed end to end. The expert was Claude `opus`, resolved to `claude-opus-5-5`, at high effort, using the local logged-in Claude CLI. Codex was not usable on this machine because Duc's ChatGPT account rejects `gpt-6.1-sol` and `gpt-6-astra` (`model_not_found`). By Victor's decision, the Claude adapter now falls back to the person's own logged-in CLI when no `ANTHROPIC_API_KEY` is set. It keeps the same isolation: no tools, no MCP, no settings sources, no hooks. With a key it still runs `--bare`. A Codex/ChatGPT CLI path for team devices is a follow-up.

## Source revisions

| Part | Revision |
| --- | --- |
| Victor's harness | `origin/victor/agentic-student-loop` at `5b0fe9f` (tested agent baseline named in his handoff: `7722e8d`) |
| Simulator | `openarms_sim` with the `demo` setup on `duc` at `58722b8` (`db1da78`: demo matched to a recorded real pour) |
| Integration | `duc` + Victor's branch merged clean as `5abe535`, then the adapter commit |

## Design

- **Typed action.** `add_sample(source=A, into=C, portions=1)` is the simulator's own plan action (`simulation/openarms_sim/motion.py`: pick, pour, return_cup, home). It is now a contract operation (`contracts.AddSampleArguments`, `ACTION_OPERATIONS`). Its schema admits only A→C and one portion, so another route cannot be coerced into it.
- **Adapter.** `agentic/openarms_lab/demo_bench.py` and `demo_bench_worker.py`. They subclass the two-vessel scene, backend and evaluator through small seams (`worker`, `_command`, evaluator class attributes). The existing consent, single-consumption, STOP (process-group kill), reset-generation and receipt code is reused, not copied. No `simulation/` file changed.
- **Independent outcome.** The demo receiver is pre-coloured red by its mix (`chemistry.yaml`), so receiver colour cannot show a transfer. The observer reads the **beaker at A** in a fresh frame at pixel anchors registered from the reset reference: it shows liquid before the pour and reads empty after. It also checks both station markers (camera registration) and that red liquid is at C, not A. Missing, swapped, occluded, shifted and stale frames all read `unknown`. The observer never sees the receipt, plan or prediction.
- **Setup-scoped admission.** `demo_bench.execution_scope()` hashes the demo `bench.yaml`, `poses.json`, `joint_map.yaml`, `chemistry.yaml`, `openarms_sim` sources and the lab seam files, giving `demo-bench-<hash>`. The evaluator replays a skill on the nominal case, six fault cases, the consent control and the STOP control.
- **Timing choice.** `openarms_sim` is an on-demand runner with no persistent simulation clock, so nothing runs while the expert thinks. The arm stays idle until confirmation anyway. Each run starts a worker process, which costs about 1.8 s before first motion. The kinematic player computes 23.7 s of motion in about 7.5 s wall time, and the MP4 plays it at 1×. Adding an idle stepping clock would mean a custom player inside `simulation/`, which is Stefanie's.

## Evidence

Entry command: `OPENARMS_EXECUTION=mujoco PORT=8010 .venv-lab/bin/python -m agentic.openarms_lab` (the scene defaults to `demo_bench`).

Rehearsal: `PYTHONPATH=agentic:. .venv-lab/bin/python agentic/scripts/full_loop_rehearsal.py --execution mujoco --scene demo_bench --expert-profile <profile> --out <fresh dir>`. It runs cold, admission, warm, then the STOP and unsupported checks.

### Live expert run

Local receipts are in `outputs/handoff/demo-bench-live/` (`summary.json`, `cold.json`, `warm.json`, `final-state.json`, `evaluations/`). Scope `demo-bench-5d51eaaadd4642e0`, this MacBook, scripted student confirmation.

- **Cold request:** "Please pour the beaker from A into C, return the beaker to A and go HOME, then check the result."
- **Cold planning:** the expert authored `demo_bench.pour_a_to_c` in 4 planning calls and 6,181 tokens. Including the execution checkpoint, the cold run made 6 model calls.
- **Admission:** the evaluator admitted the skill in the demo-bench scope (`promoted`).
- **Warm request:** "add the prepared sample from A to C and check the result", after "Prepare a new trial". It reused the admitted skill with 0 model calls.

| Event | Cold (expert plans) | Warm (admitted skill) |
| --- | ---: | ---: |
| Request to exact proposal | 58.81 s | 0.41 s |
| Confirmation to first controller progress | 9.52 s | 1.32 s |
| Controller wall time | 5.53 s | 5.08 s |
| Simulated motion (separate clock) | 23.7 s | 23.7 s |
| Controller receipt to observation | 0.43 s | 0.41 s |
| Request to independent observation | 73.78 s | 6.75 s |

The cold run's 9.5 s from confirmation to motion is not the simulator. The harness takes a fresh frame and asks the expert at its execution checkpoint before the first action, and that call took 7.9 s. The warm skill route skips it. Each run dispatched once. The observation read the beaker at A as empty, and its text matched the student's "What happened?" answer.

Live negative checks (same session):

- **STOP:** a presented warm proposal was revoked. A later confirm was rejected ("Stale or consumed proposal"), with 0 dispatches.
- **Unsupported route:** "Pour the beaker from C into A." The expert asked for clarification and said only A→C is supported. There was no pending proposal and 0 dispatches, from 1 model call in 11.1 s.

### Deterministic run

Local `outputs/handoff/demo-bench-deterministic/summary.json`, scope `demo-bench-4dfe792c7852eedd`, test planner with no model:

| Event | Wall time |
| --- | ---: |
| Request to exact proposal (no model) | 0.52 s |
| Confirmation to first controller progress | 1.76 s |
| Controller wall time | 7.47 s |
| Simulated motion (separate clock) | 23.7 s, 710 frames |
| Controller receipt to observation | 0.54 s |
| Request to independent observation | 9.65 s |

Observed features: `donor_appearance=empty`, `receiver_appearance=red_liquid`, `sample_cup_station=A`, `sample_cup_held=false`. One dispatch. The beaker returned to A and the arm reached HOME.

Tests (`agentic/tests/test_demo_bench_runtime.py`, 25 cases):
- full consent with a single dispatch and an independent outcome, including confirm-before-present rejection and second-confirm rejection;
- STOP revoking a presented proposal;
- fifteen unsupported requests ending with zero dispatches: B→C, A→B, two portions, 5 mL, return to C, vinegar, baking soda, "twice", "all of", left/right routes, "C onto A", "Pour B into C", "three times", "100 g" and "leave it at C". The host guard rejects other liquids and unbound amounts even if a planner would propose the pour;
- a plan whose outcome checks skip the donor reading is refused. Every action plan must include the setup's required check (`donor_appearance = empty`), so success cannot rest on features the pour never changes;
- the fault views failing closed;
- admission passing in its own scope;
- the app defaulting to the demo bench;
- the scope changing when the setup or adapter changes.

## Missing interfaces and limits

- **Codex/ChatGPT CLI on team devices.** Duc's account cannot serve the Sol/Astra profiles. The Claude logged-in path is in place, and the Codex equivalent is a follow-up for Victor or Joseph.
- **Demo bench camera.** `setups/demo/bench.yaml` has no `camera:` block, so `render.camera(shifted=True)` is a no-op there. The worker turns the default view itself for the camera-shift fault.
- **Simulation clock.** `openarms_sim` exposes no persistent clock or step API, so the simulation cannot keep running during inference.
- **Physical meaning.** The poses are solved, not taught, and `joint_map.yaml` is unmeasured. Liquid is drawn from `chemistry.yaml`. Nothing here qualifies grasp, delivery, spill or chemistry. Physical dispatch stays disabled.
- **Observer limit.** The donor reading cannot tell "empty and back on its mark" from "empty and slightly displaced". Mark-level displacement fails registration only if it hides the marker.
