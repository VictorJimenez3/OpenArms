# Run the conversational lab

[Architecture](ARCHITECTURE.md) defines D1–D4 product targets; [FULL_SYSTEM_DELIVERY](FULL_SYSTEM_DELIVERY.md) defines the R1–R6 software scope. Prediction and reflection are optional. Software/simulation evidence does not complete the supervised physical milestone.

The student app targets continuous voice on Mac and iPhone. The selected physical target is the two-vessel Smartivity pour in [PROJECT](PROJECT.md). MuJoCo is active for development; Isaac is parked. The retained indicator-pH apparatus is a regression implementation, not the carried-donor kit experiment. **Gemini Live provides speech** when configured. Joseph withdrew only Gemini thinking; expert inference remains independently selectable. Text, the shared session and direct STOP remain available if voice is unavailable. OpenAI `gpt-6.1-sol`, medium reasoning through the authenticated Codex CLI, inspects images and plans supported tasks. Physical execution is disabled in this application lane.

## Start

From the repository root, use Python 3.12 and the dedicated application environment (leave an existing bench `.venv` intact):

```sh
uv venv --python 3.12 .venv-lab  # only if it does not exist
uv pip install --python .venv-lab/bin/python -r agentic/requirements-lab.txt -e 'simulation[dev]'
OPENARMS_EXECUTION=mujoco PORT=8010 .venv-lab/bin/python -m agentic.openarms_lab
```

Authenticate the chosen expert independently; see [model profiles and switching](EXPERT_MODELS.md). The default needs the `codex` CLI on PATH. Configure GEMINI_API_KEY or GOOGLE_API_KEY in an untracked local environment file for Gemini Live speech. Never copy credentials into evidence or Git.

Open `http://127.0.0.1:8010/` for the student view and `/developer` for the same session with the simulator, actual expert/tool trace, observations and skill evaluations. Both views use the same bearer grant and voice connection. A phone needs a reachable configured HTTPS endpoint; localhost refers to the phone itself. Browser microphone access requires localhost or HTTPS.

`OPENARMS_EXECUTION=mock` runs the explicitly labeled synthetic camera fixture for software regression. `mujoco` runs the openarms_sim `demo` bench by default (`OPENARMS_SCENE=demo_bench`). Ask for a complete pour from A into C with return and HOME, or say “pick up the beaker,” “pour it into the container,” and “put the beaker back” as separate requests. Each action requires its exact proposal and fresh confirmation. The view reads the outcome from fresh rendered pixels. [Demo bench integration evidence](../research/duc/demo-bench-integration.md)

`OPENARMS_SCENE=two_vessel` keeps the carried-donor water scene and `OPENARMS_SCENE=metered_dropper` the indicator-pH regression. The app reuses `openarms_sim`. The [standalone Smartivity runner](../simulation/smartivity/README.md) reproduces four activities offline. After simulator or command changes, re-run `agentic/scripts/seed_demo_skill.py` for the selected experiment to admit its base pour in the new scope.

## Real bench lane (optional): camera, simulated preview, then the real arm

`OPENARMS_BENCH=1` adds a **Real bench** panel above the pH investigation. It is separate from the pH task loop and does not change it. Press **Look now** first (fixed webcam, OpenCV); a typed command plans from the most recent look and takes no new picture, and is refused if there has been no look yet. Then: plan (fixed patterns, then Claude), MuJoCo preview of the exact joint targets, **execute** (plus the bench operator's Yes in the panel for the real arm), then a camera check of the result. Code: `agentic/openarms_lab/bench_lane.py`, `free_plan.py`, `sim_preview.py`, `firmware/openarms_camera/`.

```sh
# once per camera position: find the camera, then teach where A and B appear in its picture
.venv/bin/python -m firmware.openarms_camera list
.venv/bin/python -m firmware.openarms_camera mark --camera 1

source env.sh
OPENARMS_BENCH=1 OPENARMS_CAMERA=1 OPENARMS_SECONDS=3 \
OPENARMS_FOLLOWER_PORT=/dev/tty.usbmodemXXXX OPENARMS_POSES=$PWD/path/to/poses.json \
OPENARMS_EXECUTION=mujoco OPENARMS_EXPERT_PROFILE=sonnet OPENARMS_ENV_FILE=$PWD/agentic/.env \
PORT=8010 .venv/bin/python -m agentic.openarms_lab
```

- Leave out `OPENARMS_FOLLOWER_PORT` for a stand-in arm (nothing moves, results labelled MOCK); leave out `OPENARMS_CAMERA` to track the object without a camera (real results then stay UNKNOWN).
- The camera decides where the object is before planning and again just before running; if it moved in between, nothing starts. After the run the result is REAL only when the picture agrees with the plan.
- The camera check is a colour-blob detector for an orange object inside taught picture regions. It needs a fixed, raised, angled view in which A and B are clearly apart; it reports a view where they coincide. It was developed on the eight real bench photos in `research/joseph/mandarin-transfer-2026-11-14/images` and has not yet been run on a live webcam.
- **Pours are simulated from the picture; the simulated joint targets are never sent to the real arm.** A command with pour, tip, empty, add or mix in it ("pour this into that") takes the overhead picture (`OPENARMS_OVERHEAD_CAMERA=N`, or `OPENARMS_OVERHEAD_PHOTO=path` to use a saved photo), finds the two red rulers and the containers (`firmware/openarms_camera/bench.py`), lets Claude decide what is poured into what and say why, rebuilds the simulation's demo bench at the positions the picture shows (a working copy, `simulation/config/setups/demo_live/`, not the committed layout) and plays the pour. The panel shows the flattened picture with its centimetre grid beside the preview. Without a recorded pour, Execute stays disabled. When the rulers or a container are not found, the last known position is used and the panel says so.
- **Executing a pour replays a recording.** `OPENARMS_POUR_POSES=path/to/take.json` names a pour recorded on the real arm with `teleop_record --capture`; beside it, `take.layout.json` (`{"beaker": [x, y], "dish": [x, y]}`) says where the two stood, in ruler centimetres, at recording time. Within 0.5 cm the recording is replayed as it is. From 0.5 to 4 cm off, the recorded poses at that container are corrected (`simulation/openarms_sim/shift.py`): the model works out how each joint must change to move the recorded grip by the offset, with the gripper tilted and rolled as recorded, and only that change is added to the recording. An offset over 4 cm, a model miss over 5 mm, a tilt or roll change over 3° or a joint change over 25° is shown as a warning and does not block Execute; the one hard limit is the follower's calibrated joint range, which the correction keeps 3° inside. Moving a container toward the arm is limited by the wrist (about 1 cm with pour-take-1), so beyond that the grasp lands short. It looks again before starting and refuses if a container moved more than 1 cm since the correction was made, brings the arm back to the recording's own HOME first when it is not there (which can differ from the HOME in `poses.json`), asks the operator, and asks again after the lift that the cup is held. A container the camera cannot find is left to the operator, who is told so. The result is labelled UNKNOWN: nothing measures delivery. Receipts go to `<data dir>/bench/pour-receipts`. This path has passed tests on the stand-in arm only.
- **Claude writes the pour file.** With a recorded pour configured, Claude is shown where the (camera-corrected) recording puts the gripper at each step, in ruler centimetres and height, and chooses: `replay` it, or `improve` it by moving single steps up to 3 cm along each axis (up and down too) and/or changing the tip angle (45 to 120°, the recording's is about 90). Its moves go through the same model correction and the calibrated-range check; a change out of bounds is not used and the recording runs instead. Either way, the poses Execute would run are saved with Claude's reasons as `<data dir>/bench/pours/pour-ID.json` plus `pour-ID.layout.json`, so a good one can later be named in `OPENARMS_POUR_POSES`. A file Claude changed is marked `recorded_on_real_arm: false`; the simulation preview still plays its own scripted pour, not Claude's changes.
- **Harness loop results.** By default Claude reads Victor's in-repo `research/victor/harness-loop-progress.md`; `OPENARMS_HARNESS_NOTES=/path/to/file.md` points elsewhere (e.g. a running loop's live copy) and `OPENARMS_HARNESS_NOTES=off` disables it. This gives Claude the harness self-improvement loop's latest results as notes for the pour decision. The file is re-read on every request (a running loop's updates are picked up; a file over 12,000 characters is cut to its beginning and end). They are advice only: the motion limits, the calibrated-range check, the operator's Yes and Stop are unchanged, and the camera's reading wins over them. The chat says when they were read; the plan, the pour file and the receipt record the file's path, hash and age. A missing file is said in the chat and Claude decides without it.
- **Voice (Gemini Live) on the bench panel.** Press **Talk** next to "Plan and simulate" (needs `GEMINI_API_KEY` in `agentic/.env`; model `GEMINI_LIVE_MODEL`, default `gemini-3.8-live`). Gemini only listens and speaks: the student's request goes to the same bench request as typing, so Claude plans, the simulation previews, and the panel shows it. "Stop" heard in speech stops the arm at once, before Gemini answers. Voice can run a simulated plan only when the student says execute or go ahead themselves, and on the real arm only when an operator question follows (`OPENARMS_BENCH_CONFIRM` panel or terminal; not `page`). It never answers the operator's Yes / No. Same computer only (`/api/bench/voice`); separate from the session voice guide in `live.py`, which is unchanged.
- **Small misses and the table.** A pour accepts the arm stopping within 7° of a pose (`GIVE_DEG` in `firmware/openarms_executor/pour_once.py`) instead of failing; nothing is pushed harder. On the way down to the grasp, a joint that stopped short is re-commanded to where it stopped, so it no longer presses on the table, and the poses carried with the cup (and the set-down) are raised by the same joint change. Over 7° the move fails as before, over 12° it is "blocked". The receipt logs every accepted miss as `arrival_accepted`.
- **Claude learns from the real arm.** Each real pour that needed such a miss, or failed, is added to `<data dir>/bench/pour-lessons.jsonl` with where the containers stood. When the beaker stands within 6 cm of an earlier one, Claude is shown what the arm met there (for example "the grasp stopped high, roughly 1.9 cm: it likely met the table") and can raise the grasp with its existing `dz` move.
- **A blocked simulation only warns for a recorded pour.** The preview plays its own solved pour, not the recording the arm replays, so its "Blocked" is shown as a warning and Execute stays possible; mandarin moves (which run the simulated poses) are still blocked.
- **Reading the overhead picture** (`firmware/openarms_camera/bench.py`) tolerates a turned or slanted camera and warm or bright light. The rulers are picked out by the usual red, then a wider red, then red compared with the table around them. Each ruler is found along its own direction, and the X and Y rulers are told apart by where they meet. A fit looser than 2 cm is refused rather than used. When the rulers cannot be read (hidden by a hand or the arm, glare), the grid of the last picture whose rulers were read (`<data dir>/bench/overhead_reference.jpg`/`.json`) is carried over, lined up with the new picture by matching features; the panel says so. The rulers themselves must form a square L: a crooked L cannot be fitted.
- With a top-down view or a recorded pour configured and no `OPENARMS_CAMERA`, the panel is a **ruler bench**: the mandarin is moved by where the camera sees it, not by the taught A/B joint poses. Look now finds the mandarin in ruler centimetres (`bench.find_mandarin`: an orange, roundish thing 3 to 9.5 cm across, inside the L, more than 12 cm from the arm's base). "move the mandarin from A to B" then solves arm poses in the model (`simulation/openarms_sim/reach.py`) for the spot the camera saw and for the other place, simulates the move with those poses, and Execute sends the same poses to the arm. The place the mandarin is nearest to is the one it is "on"; `OPENARMS_PLACES="A=22,8;B=8,8"` sets the places (those are the defaults), and "move the mandarin to 12, 10" names a spot directly. HOME and the two gripper values still come from the pose file. Before starting, the camera looks again and the move is refused if the mandarin is more than 1.5 cm from where the plan was made; afterwards the result is REAL only if the camera sees it within 4 cm of the destination. **The solved poses have never been recorded on the real arm.** They go through `simulation/config/joint_map.yaml`, which is still `measured: false`, so the real gripper may be a couple of centimetres off; a place is refused when the model cannot reach it or a joint would leave the follower's calibrated range. This path has passed tests on the stand-in arm and in the simulation only. `OPENARMS_BENCH_STATIONS=1` goes back to the taught A/B poses.
- **Back to HOME first.** When the arm is more than 5° off HOME on any joint at Execute, the panel asks whether to move it slowly back (at most 20° a second per joint, at least 3 seconds, gripper unchanged); Yes moves it, No leaves it and nothing starts, Stop halts it where it is and disarms. With `OPENARMS_BENCH_CONFIRM=page` it goes back without asking. The move is a straight line in joint angles: nothing may be in the gripper and the way back must be clear.
- After Execute, the real arm asks the bench operator in the panel (a Yes / No box) before it starts and, in a pour, after the lift that the cup is held. Only Yes goes on; No, Stop or five minutes without an answer is No. `OPENARMS_BENCH_CONFIRM=terminal` asks the same with y in the server terminal instead. `OPENARMS_BENCH_CONFIRM=page` asks nothing: Execute on the page (or typing execute) starts the real arm as soon as the HOME and camera checks pass. Use `page` only with a person at the bench and a hand near Stop.
- The routes under `/api/bench` answer only to the computer the server runs on. The page's Stop button also stops the arm. A stop or failed run disarms the lane until the server restarts.
- The Claude profiles call the `claude` CLI: with `ANTHROPIC_API_KEY` in bare mode, otherwise through the local logged-in account. That usage is not counted by `agentic/openarms_agent/budget.py`.

## Which processes to run

| Process | Start / inspect | Ownership |
| --- | --- | --- |
| Application server | The single Python command above; keep its terminal open. `GET /api/health` reports the selected backend/provider and voice availability. | Owns sessions, task orchestration, approvals, notebook and skill registry. |
| Desktop website | Open `http://127.0.0.1:8010/`; `/developer` adds execution frames/video and diagnostic evidence. | Served by Python. No separate Node/web development server. |
| Expert | Launched automatically for unfamiliar tasks or feedback requiring reasoning. Select it using [expert profiles](EXPERT_MODELS.md). | A bounded Codex or Claude subprocess; host tools execute its decisions. No second agent server. |
| MuJoCo | Started by the application for fresh scene capture and confirmed supported execution. Inspect `/developer`. | Bounded capture/execution subprocesses. Do not launch the old preview/gallery as the application simulator. |
| Native iPhone | Open `research/joseph/iphone-voice-bridge/ios/OpenArmsVoice.xcodeproj` in Xcode, select the scheme and device, then Run. Enter the reachable server origin in app Settings. | Same Python session service. No legacy Mac relay. See the [native guide](../research/joseph/iphone-voice-bridge/ios/README.md) for signing/network details. |
| Physical arm / standalone research | Separate supervised [firmware setup](../firmware/README.md), [wet-lab runbook](WET_LAB.md), or [research index](../research/README.md). | Preserved tools; not started or activated by this software demo. |

For another device, serve the app through a trusted HTTPS endpoint reaching the Mac, set `OPENARMS_DEMO_TOKEN` and explicitly allow that hostname with `OPENARMS_ALLOWED_HOSTS`. Use `OPENARMS_HOST=0.0.0.0` only when the gateway must accept external connections. Put the origin and pairing code in the phone’s Settings. USB installation does not create a network route; phone localhost refers to the phone. Keep tokens in the environment or untracked `.env`, never URLs.

Stop the application with Ctrl-C. The server cancels active work; reopening a session restores history but never replays execution or consent. Use a fresh `OPENARMS_DATA_DIR` for an isolated rehearsal rather than deleting someone else’s notebook.

## Two-vessel water run

Use the startup command above and a fresh `OPENARMS_DATA_DIR` for this scene. Ask “Pour the premeasured water from donor A into receiver C, then return the donor and go home.” Review the exact proposal, then give fresh confirmation after presentation. The expert can inspect the current scene; the executor re-captures and validates camera/fixture/object evidence immediately before each action. Changed, missing or swapped objects, stale frames and invalid registration prevent dispatch. Observe the independent result and prepare a fresh trial for equivalent warm reuse of an admitted skill. STOP cancels work; delayed capture results cannot restart it.

Only a complete water pour is supported here. The primary and secondary view names both use one overview camera. Post-action pixels are a fresh render of saved final state; water appearance is not measured volume or proof of physical delivery. Controller HOME is recorded separately. Colored patches are simulation references, not decoded physical fiducials. Vessel heights (70/60 mm) and dock geometry remain provisional and do not yet match the latest vessel/base-plate assets.

`TwoVesselSkillEvaluator` independently replays a supported candidate before reusable admission. Equivalent warm requests may then reuse that version. Admission capability is not D4: a saturated suite cannot prove a substantive improvement. The verified real-Codex cold run used 7 expert calls and the admitted warm run reused the same version with zero calls; a separate simulated image passed all four checks. The actual Gemini Live water dialogue also passed using generated audio and headless acknowledgments. See [reconciliation evidence](../research/joseph/reconciliation-2026-11-14/README.md) for the retained admission failure, contract repair, test timeout/rerun and model-identity limits. This is bounded initial D3 evidence, not D4, physical delivery or real-device audibility.

## Retained MuJoCo indicator regression

Restart with `OPENARMS_EXECUTION=mujoco OPENARMS_SCENE=metered_dropper` and a separate data directory for the fixed-dispenser pH apparatus. Its indicator rules do not implement the selected kit. No physical preview gate is introduced by selecting a development simulator.

1. Use **Talk** or **Type instead** and request, “Please test the prepared vinegar sample and check the indicator color.”
2. Follow progress while the expert examines the scene. Ask a follow-up while planning runs; questions must preserve the task and pending proposal.
3. Review the exact server proposal and use its confirmation button. Bare typed confirmation does not authorize execution.
4. Watch the new apparatus execute in `/developer`. The observer reads a fresh rendered image, and the session displays the observed simulated color.
5. Inspect the versioned candidate and its evaluation. Only a promoted skill becomes reusable. Prepare a new trial and use an equivalent supported request to exercise that version without a new planning call.
6. Use **Stop** at any time. After cancellation, failure or server restart, prepare a fresh trial before new execution. Returning home after a normal successful simulated run is automatic.

Prediction and reflection are optional. The expert can clarify or reject unsupported requests. The current MuJoCo pH primitive doses prepared solution through the fixed apparatus; standalone cup pickup, pouring and arbitrary robot motion are outside its capabilities. Geometric paddle engagement and qualitative color rules are declared simulation assumptions, not calibrated contact physics or measured pH.

## Evidence and controls

Exact proposal presentation precedes fresh confirmation. Corrections, changed plans, expiry, STOP and reconnect invalidate old consent. The server owns validation and execution; a model claim that an action started is not an execution receipt. Stopping voice or losing the session cancels outstanding work. Direct Stop bypasses speech recognition.

Images have timestamps, immutable hashes and session-scoped URLs. The developer view identifies the scene, source revision and controller. Its MP4 is generated by the confirmed execution. The observer processes pixels separately from executor completion; unreadable evidence remains UNKNOWN. SIMULATED, SYNTHETIC, recorded physical evidence and analytical predictions are distinct.

For the retained indicator regression, skill admission combines the frozen synthetic robustness suite with actual MuJoCo runs for every declared parameter combination. The demonstrated occlusion improvement is measured in the synthetic suite; clear-view MuJoCo admission is separate evidence. A new simulator version requires fresh admission. The neutral indicator identifiers in scene version 2 make earlier sessions read-only; retain their original evidence and start a new session/data directory for this baseline. Verified kit chemistry remains unimplemented; the separate two-vessel scope supports water motion only. This does not qualify a skill for the physical arm.

## Configuration

| Variable | Purpose |
| --- | --- |
| `OPENARMS_EXECUTION` | `mock` default; `mujoco` selects the actual simulator |
| `OPENARMS_SCENE` | With MuJoCo: `demo_bench` (default) for the openarms_sim demo bench; `two_vessel` and `metered_dropper` for retained regression scenes |
| `OPENARMS_DEMO_EXPERIMENT` | With `demo_bench`, select `volcano` (default), `potions`, or `lava_lamp`. Start a fresh session after changing the experiment. Each selection has its own simulated skill admission scope. |
| `OPENARMS_DATA_DIR` | Persistent notebook, scene artifacts, evaluations and scoped registry |
| `OPENARMS_ENV_FILE` | Optional explicit local environment file |
| `GEMINI_LIVE_MODEL` | Speech model; default `gemini-3.8-live` |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Local Gemini Live speech credential, independent of expert authentication |
| `OPENARMS_EXPERT_CONFIG` | Host-owned selection file for model changes between tasks |
| `OPENARMS_EXPERT_PROFILE`, `OPENARMS_EXPERT_EFFORT` | Defaults without a config file: `sol`, `medium` |
| `OPENARMS_CODEX_EXECUTABLE`, `OPENARMS_CLAUDE_EXECUTABLE` | Independent CLI paths; default `codex`, `claude` |
| `OPENARMS_DEMO_TOKEN` | Creation credential for a remote deployment |
| `OPENARMS_ALLOWED_HOSTS` | Explicit additional hostnames; same-origin controls still apply |
| `OPENARMS_HOST`, `PORT` | Default `127.0.0.1`, `8000` |

## Verify

```sh
PYTHONPATH=agentic:simulation:. .venv-lab/bin/python -m pytest agentic/tests simulation/tests --import-mode=importlib -o asyncio_mode=auto -q
PYTHONPATH=agentic:simulation:. .venv-lab/bin/python agentic/scripts/full_loop_rehearsal.py --execution mujoco --scene two_vessel --expert-profile sol --reasoning-effort high --out /absolute/new-evidence-directory
cd ui/lab/tests
npm ci
OPENARMS_FIXTURE_PORT=8774 npm test
npm run test:unit
```

The full-loop command selects the integrated two-vessel scene and requests Sol at high reasoning through the real Codex CLI. Use `--scene metered_dropper` for the retained indicator regression. The script makes real expert calls and uses an automated test student for explicit presentation/confirmation. It is not a spoken or physical-device rehearsal. Use `agentic/scripts/conversation_rehearsal.py` for generated-speech back-and-forth through the real Gemini Live gateway. The older `ph_voice_rehearsal.py` remains a historical harness. Retain previous results and failed/interrupted attempts. Generated speech, Mac playback, browser tests and a signed iOS simulator build do not establish human audibility or unplugged iPhone connectivity. Live provider and actual-device checks remain separate release acceptance items in [the delivery contract](FULL_SYSTEM_DELIVERY.md).


### Real Gemini Live conversation rehearsal

With the server running and the local Gemini credential configured, use a fresh evidence directory:

```sh
uv pip install --python .venv-lab/bin/python -r agentic/requirements-lab-dev.txt
PYTHONPATH=agentic:simulation:. .venv-lab/bin/python -m agentic.scripts.conversation_rehearsal --url http://127.0.0.1:8010 --confirm-outcome --output /absolute/new-voice-evidence-directory
```

This macOS helper uses `say` and `ffmpeg` to send generated student audio through the actual gateway. It checks progress during real expert work, a science question that preserves the proposal, a sample correction requiring a new proposal, fresh spoken confirmation, an independent simulated/synthetic observation, STOP, and the follow-up. It saves reply audio and correlated transcripts/events. `--audible` plays audio on the Mac; successful playback alone is not human verification. The default without `--confirm-outcome` cancels before execution. For the integrated two-vessel server, add `--water-only` to avoid unsupported chemistry corrections. This flag selects the rehearsal dialogue; the server still needs `OPENARMS_EXECUTION=mujoco OPENARMS_SCENE=two_vessel`. The verified water dialogue used actual Gemini Live with generated audio and headless playback acknowledgments; its passing receipt does not prove human audibility or an actual phone. See [reconciliation evidence](../research/joseph/reconciliation-2026-11-14/README.md).
