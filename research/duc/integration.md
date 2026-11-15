# How does the integration code connect Victor's harness to the openarms_sim demo bench?

**Duc · November 14, 2026 · branch `integration` at `8ffef59`** · Evidence label: **sim** (code walkthrough). Results and timings are in [the demo bench evidence note](demo-bench-integration.md).

## Finding

The harness was not rewritten. Victor's app, task loop, skill registry and consent code run unchanged in shape. A thin adapter of two files plugs openarms_sim in behind the same three seams the two-vessel scene already used:

- a **scene service** that takes pictures and reads them;
- a **backend** that moves the simulated arm;
- an **evaluator** that tests a skill before it is saved.

The simulator owns the motion. The harness owns consent, STOP and the verdict. A separate pixel reader decides whether the pour happened, from a fresh picture.

## The parts

| Part | File | Job |
| --- | --- | --- |
| App wiring | `agentic/openarms_lab/app.py:142` | `OPENARMS_SCENE` defaults to `demo_bench`. It builds the demo scene, backend, evaluator and setup scope. `two_vessel` and `metered_dropper` stay selectable. |
| Typed action | `agentic/openarms_lab/contracts.py:79`, `:163` | `add_sample` joins the action operations. `AddSampleArguments` admits only `source=A`, `into=C`, `portions=1`, so no other route fits the schema. |
| Task loop guard | `agentic/openarms_lab/task_loop.py:551` (`_check_context`), `:627` (`_check_water_request`) | Rejects requests the fixed action cannot honour: other routes, amounts, liquids and return stations. Requires every action plan to carry the setup's required outcome check (`:608`). |
| Scene service | `agentic/openarms_lab/demo_bench.py:124` | Captures frames through the worker, finds the two vessels, and reads the outcome from pixels. |
| Pixel reader | `agentic/openarms_lab/demo_bench.py:79` (`anchors`), `:88` (`read_pixels`) | Pure function from an image to features. It never sees the plan or the simulator's report. |
| Backend | `agentic/openarms_lab/demo_bench.py:198` | Declares capabilities, checks the step, and turns an approved request into a worker command. |
| Evaluator | `agentic/openarms_lab/demo_bench.py:240` | Replays a candidate skill on the nominal case and fault cases before admission. |
| Worker | `agentic/openarms_lab/demo_bench_worker.py:32` | Child process that imports openarms_sim. It renders frames (`capture`) or plays the pour (`execute`). |
| Expert | `agentic/openarms_lab/claude_expert.py:49` | Claude CLI planner. It uses `--bare` with an API key, and otherwise the person's logged-in CLI. In both modes it runs with no tools, MCP, settings sources or hooks. |

No file under `simulation/` changed. The worker imports `openarms_sim`'s own `expand_plan` and `build_segments` (`demo_bench_worker.py:38`, `:104`).

## One request, start to finish

```
student text
  -> Lab.start_task (runtime.py:219)
  -> TaskLoop: known skill? registry.match (task_loop.py:747)
       yes -> reuse admitted skill, no model call
       no  -> expert plans from a fresh frame (inspect_scene, localize_objects tools)
  -> _check_context: schema, route/amount guard, fresh frame, required outcome check
  -> exact proposal shown -> Lab.present (runtime.py:502) -> student confirms -> Lab.confirm (runtime.py:536)
  -> backend.execute_step (task_loop.py:876) -> worker 'execute' -> openarms_sim plays add_sample
  -> scene.observe: new frame -> read_pixels -> donor_appearance
  -> outcome checks compared to observed features -> task completed / failed
```

1. **Prepare.** `Lab.prepare` (`runtime.py:638`) resets the bench. The worker renders a home frame, and the scene keeps it as the reference for that generation. Each reset bumps the generation, so older frames stop counting.
2. **Plan.** On a first request the expert gets a fresh picture. It may call `inspect_scene` and `localize_objects` (`task_loop.py:323`, `:327`), and it returns a skill definition: `inspect_scene → add_sample(A, C) → observe`, with outcome checks. On later requests `registry.match` finds the admitted skill, and no model runs.
3. **Check.** `_check_context` runs before any proposal exists:
   - the operation must be supported, and `check_step` must accept the arguments;
   - the frame must be fresh, and the vessels must sit at their docks (`_fixture_state`, `task_loop.py:512`);
   - the request text must pass the route, amount and liquid guard;
   - the plan must include `donor_appearance = empty`.
   Any failure ends the task with no proposal and zero dispatches.
4. **Consent.** The student sees the exact plan. `confirm` works only after `present`, only for the matching request ID and version, and only once.
5. **Move.** The backend sends `{'kind': 'execute', 'source': 'A', 'into': 'C', 'portions': 1}` to a worker process. The worker plays pick, pour, return_cup and home in MuJoCo, records an MP4, and streams progress frames. It returns `dose_count`, `returned_to_dock`, `home_reached` and its own final state.
6. **Observe.** `scene.observe` renders a new frame from that state, and `read_pixels` reads it. The controller receipt only says "the run finished". The features come from pixels alone.
7. **Verdict.** The plan's outcome checks are compared with the observed features. If the run failed, or the frame reads `unknown`, the task does not complete.

## How the pixel reader decides

The demo receiver at C is pre-coloured red by its chemistry, so its colour cannot show a transfer. The reader looks at the **donor beaker at A** instead (`demo_bench.py:88`):

- **Registration.** It finds the blue marker disc under A and the orange disc under C. If either drifts more than 6 px from the reference, the camera has moved, and everything reads `unknown`.
- **Receiver check.** There must be red at C (at least 60% of the reference amount) and no red at A. Swapped vessels fail this check.
- **Donor fill.** It samples the rows just above A's marker. Liquid-coloured pixels read `liquid_visible`, and clear glass reads `empty`. If the beaker's wall is missing, the beaker is gone or hidden.
- **Freshness.** The frame must come from the demo camera and the current generation, and be under 180 s old (`demo_bench.py:145`).

Anything the reader cannot confirm becomes `unknown`, which can never satisfy an outcome check.

## How the adapter reuses Victor's code

The demo classes subclass the two-vessel ones and override only small hooks:

- `worker`, on the scene and the backend, chooses which worker module renders. The two-vessel classes resolve `run_worker` at call time (`two_vessel_scene.py:34`, `two_vessel_backend.py:20`), so tests can still patch it.
- `_command` (`two_vessel_backend.py:65`) builds the setup's execute command.
- The evaluator class attributes `scene_class`, `backend_class`, `suite` and `scope` (`two_vessel_evaluation.py:74`), plus the `_check_definition` hook, set what is replayed and what a valid skill looks like.

Process control is inherited. `run_worker` starts each worker in its own process group (`two_vessel_worker.py:20`), and STOP kills that whole group (`:38`). A cancelled pour therefore cannot keep running in the background. Single-use request IDs, generations and receipts come from `runtime.py` unchanged.

## How a skill gets saved

After a successful first run, the evaluator (`two_vessel_evaluation.py:199`) replays the new skill against:

- the nominal case;
- fault views: camera shifted, beaker missing, vessels swapped, view occluded, stale frame, broken reference;
- a consent control, where nothing moves without a confirmation;
- a STOP control.

The skill is promoted only if the nominal case passes, every fault fails closed and both controls hold. Admission is tied to `execution_scope()` (`demo_bench.py:47`), a hash of the demo `bench.yaml`, `poses.json`, `joint_map.yaml`, `chemistry.yaml`, the `openarms_sim` sources and the adapter files. If any of those changes, the scope changes, and old skills stop matching.

## Running it

```sh
OPENARMS_EXECUTION=mujoco PORT=8010 .venv-lab/bin/python -m agentic.openarms_lab
PYTHONPATH=agentic .venv-lab/bin/python -m pytest agentic/tests/test_demo_bench_runtime.py --import-mode=importlib -o asyncio_mode=auto -q
```

## Limits

- Only one action exists: one premeasured portion from A into C, then return the beaker and go HOME.
- The pixel reader cannot tell "empty and back on its mark" from "empty and slightly displaced". It also does not check whether the beaker is still held. That comes from the simulator's run result, not from pixels.
- openarms_sim has no persistent clock, so the simulation does not advance while the expert thinks.
- Without an API key, the logged-in Claude CLI may still load CLAUDE.md files into the planner's context. This is unverified, and tools, MCP and hooks stay blocked.
- Sim only. The poses are solved, not taught. Nothing here qualifies physical motion.
