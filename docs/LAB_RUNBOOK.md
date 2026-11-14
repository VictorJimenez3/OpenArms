# Run the conversational lab

[Architecture](ARCHITECTURE.md) defines D1–D4 product targets; [FULL_SYSTEM_DELIVERY](FULL_SYSTEM_DELIVERY.md) defines the R1–R6 software scope. Prediction and reflection are optional. Software/simulation evidence does not complete the supervised physical milestone.

The student app targets continuous voice on Mac and iPhone. Red-cabbage indicator pH is the student demonstration. **Voice is currently disabled:** Joseph withdrew Gemini, and its replacement is not qualified yet. Text, the shared session, STOP and simulation remain available. OpenAI `gpt-6.1-sol`, medium reasoning through the authenticated Codex CLI, inspects images and plans supported tasks. Physical execution is disabled in this application lane.

## Start

From the repository root, use Python 3.12 and the project virtual environment:

```sh
uv venv --python 3.12 .venv  # only if it does not exist
uv pip install --python .venv/bin/python -r agentic/requirements-lab.txt -e 'simulation[dev]'
OPENARMS_EXECUTION=mujoco PORT=8010 .venv/bin/python -m agentic.openarms_lab
```

Authenticate the chosen expert independently; see [model profiles and switching](EXPERT_MODELS.md). The default needs the `codex` CLI on PATH. Legacy Google keys do not enable voice in the application. Never copy credentials into evidence or Git.

Open `http://127.0.0.1:8010/` for the student view and `/developer` for the same session with the simulator, actual expert/tool trace, observations and skill evaluations. Both views use the same bearer grant and voice connection. A phone needs a reachable configured HTTPS endpoint; localhost refers to the phone itself. Browser microphone access requires localhost or HTTPS.

`OPENARMS_EXECUTION=mock` runs the explicitly labeled synthetic camera fixture for software regression. `mujoco` runs the updated lab apparatus, selected explicitly; failure never falls back to mock. The older `openarms_sim.Player` preview is historical and is not the current student simulator. The four source lab demonstrations remain reproducible research examples under `simulation/lab_demos`; they are not additional student experiment choices.

## Real bench lane (optional): camera, simulated preview, then the real arm

`OPENARMS_BENCH=1` adds a **Real bench** panel above the pH investigation. It is separate from the pH task loop and does not change it. Press **Look now** first (fixed webcam, OpenCV); a typed command plans from the most recent look and takes no new picture, and is refused if there has been no look yet. Then: plan (fixed patterns, then Claude), MuJoCo preview of the exact joint targets, **execute** (plus the bench operator's `y` in the server terminal for the real arm), then a camera check of the result. Code: `agentic/openarms_lab/bench_lane.py`, `free_plan.py`, `sim_preview.py`, `firmware/openarms_camera/`.

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
- **Pours are simulation only.** A command with pour, tip, empty, add or mix in it ("pour this into that") takes the overhead picture (`OPENARMS_OVERHEAD_CAMERA=N`, or `OPENARMS_OVERHEAD_PHOTO=path` to use a saved photo), finds the two red rulers and the containers (`firmware/openarms_camera/bench.py`), lets Claude decide what is poured into what and say why, rebuilds the simulation's demo bench at the positions the picture shows (a working copy, `simulation/config/setups/demo_live/`, not the committed layout) and plays the pour. The panel shows the flattened picture with its centimetre grid beside the preview. Execute stays disabled: no poses have been taught on the real arm for the beaker and container. When the rulers or a container are not found, the last known position is used and the panel says so.
- The routes under `/api/bench` answer only to the computer the server runs on. The page's Stop button also stops the arm. A stop or failed run disarms the lane until the server restarts.
- The Claude profiles call the `claude` CLI with `ANTHROPIC_API_KEY`; that spending is not counted by `agentic/openarms_agent/budget.py`.

## Which processes to run

| Process | Start / inspect | Ownership |
| --- | --- | --- |
| Application server | The single Python command above; keep its terminal open. `GET /api/health` reports the selected backend/provider and voice availability. | Owns sessions, task orchestration, approvals, notebook and skill registry. |
| Desktop website | Open `http://127.0.0.1:8010/`; `/developer` adds execution frames/video and diagnostic evidence. | Served by Python. No separate Node/web development server. |
| Expert | Launched automatically for unfamiliar tasks or feedback requiring reasoning. Select it using [expert profiles](EXPERT_MODELS.md). | A bounded Codex or Claude subprocess; host tools execute its decisions. No second agent server. |
| MuJoCo | Started by the application when the confirmed supported action runs. Inspect `/developer`. | One subprocess per simulated operation. Do not launch the old preview/gallery as the application simulator. |
| Native iPhone | Open `research/joseph/iphone-voice-bridge/ios/OpenArmsVoice.xcodeproj` in Xcode, select the scheme and device, then Run. Enter the reachable server origin in app Settings. | Same Python session service. No legacy Mac relay. See the [native guide](../research/joseph/iphone-voice-bridge/ios/README.md) for signing/network details. |
| Physical arm / standalone research | Separate supervised [firmware setup](../firmware/README.md), [wet-lab runbook](WET_LAB.md), or [research index](../research/README.md). | Preserved tools; not started or activated by this software demo. |

For another device, serve the app through a trusted HTTPS endpoint reaching the Mac, set `OPENARMS_DEMO_TOKEN` and explicitly allow that hostname with `OPENARMS_ALLOWED_HOSTS`. Use `OPENARMS_HOST=0.0.0.0` only when the gateway must accept external connections. Put the origin and pairing code in the phone’s Settings. USB installation does not create a network route; phone localhost refers to the phone. Keep tokens in the environment or untracked `.env`, never URLs.

Stop the application with Ctrl-C. The server cancels active work; reopening a session restores history but never replays execution or consent. Use a fresh `OPENARMS_DATA_DIR` for an isolated rehearsal rather than deleting someone else’s notebook.

## Demonstrate

1. Open **Type instead** and request, “Please test the prepared vinegar sample and check the cabbage indicator color.” Talk reports the pending voice replacement.
2. Follow progress while the expert examines the scene. The session remains connected while planning runs; continuous spoken follow-up remains an unmet acceptance check.
3. Review the exact server proposal and use its confirmation button. Bare typed confirmation does not authorize execution.
4. Watch the new apparatus execute in `/developer`. The observer reads a fresh rendered image, and the session displays the observed simulated color.
5. Inspect the versioned candidate and its evaluation. Only a promoted skill becomes reusable. Prepare a new trial and use an equivalent supported request to exercise that version without a new planning call.
6. Use **Stop** at any time. After cancellation, failure or server restart, prepare a fresh trial before new execution. Returning home after a normal successful simulated run is automatic.

Prediction and reflection are optional. The expert can clarify or reject unsupported requests. The current MuJoCo pH primitive doses prepared solution through the fixed apparatus; standalone cup pickup, pouring and arbitrary robot motion are outside its capabilities. Geometric paddle engagement and qualitative color rules are declared simulation assumptions, not calibrated contact physics or measured pH.

## Evidence and controls

Exact proposal presentation precedes fresh confirmation. Corrections, changed plans, expiry, STOP and reconnect invalidate old consent. The server owns validation and execution; a model claim that an action started is not an execution receipt. Stopping voice or losing the session cancels outstanding work. Direct Stop bypasses speech recognition.

Images have timestamps, immutable hashes and session-scoped URLs. The developer view identifies the scene, source revision and controller. Its MP4 is generated by the confirmed execution. The observer processes pixels separately from executor completion; unreadable evidence remains UNKNOWN. SIMULATED, SYNTHETIC, recorded physical evidence and analytical predictions are distinct.

Skill admission combines the frozen synthetic robustness suite with actual MuJoCo runs for every declared parameter combination. The demonstrated occlusion improvement is measured in the synthetic suite; clear-view MuJoCo admission is separate evidence. A new simulator version requires fresh admission. This does not qualify a skill for the physical arm.

## Configuration

| Variable | Purpose |
| --- | --- |
| `OPENARMS_EXECUTION` | `mock` default; `mujoco` selects the actual simulator |
| `OPENARMS_DATA_DIR` | Persistent notebook, scene artifacts, evaluations and scoped registry |
| `OPENARMS_ENV_FILE` | Optional explicit local environment file |
| Legacy `GEMINI_LIVE_MODEL` / Google keys | Ignored by the current default application voice path |
| `OPENARMS_EXPERT_CONFIG` | Host-owned selection file for model changes between tasks |
| `OPENARMS_EXPERT_PROFILE`, `OPENARMS_EXPERT_EFFORT` | Defaults without a config file: `sol`, `medium` |
| `OPENARMS_CODEX_EXECUTABLE`, `OPENARMS_CLAUDE_EXECUTABLE` | Independent CLI paths; default `codex`, `claude` |
| `OPENARMS_DEMO_TOKEN` | Creation credential for a remote deployment |
| `OPENARMS_ALLOWED_HOSTS` | Explicit additional hostnames; same-origin controls still apply |
| `OPENARMS_HOST`, `PORT` | Default `127.0.0.1`, `8000` |

## Verify

```sh
PYTHONPATH=agentic:simulation:. .venv/bin/python -m pytest agentic/tests simulation/tests --import-mode=importlib -o asyncio_mode=auto -q
PYTHONPATH=agentic:simulation:. .venv/bin/python agentic/scripts/full_loop_rehearsal.py --execution mujoco --out /absolute/new-evidence-directory
cd ui/lab/tests
npm ci
OPENARMS_FIXTURE_PORT=8774 npm test
npm run test:unit
```

The full-loop script makes real expert calls and uses an automated test student for explicit presentation/confirmation. It is not a spoken or physical-device rehearsal. The old `agentic/scripts/ph_voice_rehearsal.py` is a historical Gemini harness; do not run it under the current provider instruction. Retain previous results and failed/interrupted attempts. Generated speech, Mac playback, browser tests and a signed iOS simulator build do not establish human audibility or unplugged iPhone connectivity. Replacement voice and actual-device checks remain separate release acceptance items in [the delivery contract](FULL_SYSTEM_DELIVERY.md).
