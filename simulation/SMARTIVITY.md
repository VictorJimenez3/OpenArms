# Smartivity experiments in OpenArms

The scenes are **Erupting Volcano** (pp. 26–27) and the **Magic Potion-1 → Magic Potion-2** progression (pp. 30–33), from Smartivity’s *My First Science Kit*. The source PDF and the 18-experiment catalog are attached to [06 — Virtual Experiments & Scientific Models](https://app.notion.com/p/41871c9c107e811a8392c59985243573). The page images were checked against the searchable text. Physical lab selection and calibration are separate.

| Station | Prepared before reset | Robot action |
| --- | --- | --- |
| A · beaker in donor dock | 15 mL water, 4 kit spoons citric acid, 6 drops liquid soap. Mix and stir 32 times. | Pick and lift, tilt over C, return upright to A. |
| C · flask fixed in tray | 30 mL water, 4 kit spoons baking soda, 4 drops red colour. Mix and stir 32 times. | Receive the quick pour. |

The booklet does not specify spoon mass, drop volume, solution concentration, or a timed reaction curve. Water volume anchors transfer bookkeeping. The powder and dye/soap amounts retain their booklet units.

Magic Potions starts with one Magic Tea Bag already steeped in 50 mL water for ten minutes, then removed. Reset captures the divided blue tea in both vessels, the pink flask after adding and stirring in one kit spoon of citric acid, and the green cup after adding and stirring in one kit spoon of baking soda. Both portions start at 25 mL. The policy then pours the green cup into the pink flask. The booklet describes a fizz and colour change. Lavender is an illustrative choice based on the final drawing.

The versioned configurations are [volcano.yaml](config/setups/smartivity/volcano.yaml) and [potions.yaml](config/setups/smartivity/potions.yaml). The volcano seed sweep perturbs vessel positions by up to 1.5 mm per horizontal axis, water fills by ±5%, and camera azimuth and elevation by ±2°. Seed 0 uses the booklet’s quantities and nominal arrangement. The Potions scenario keeps the two booklet portions fixed across seeds.

## Launch

From the repository root with Python 3.12 and an authenticated Codex CLI for the default expert profile:

```sh
uv venv --python 3.12 .venv-smartivity
source .venv-smartivity/bin/activate
uv pip install -r agentic/requirements-lab.txt -e simulation
export PYTHONPATH="$PWD/agentic:$PWD/simulation:$PWD"
python -m agentic.openarms_lab.smartivity --seed 0 --checkpoint --out outputs/smartivity-checkpoint
python -m agentic.openarms_lab.smartivity --scenario volcano --seed 0 --out outputs/smartivity
python -m agentic.openarms_lab.smartivity --scenario potions --seed 0 --out outputs/smartivity
python -m openarms_sim.smartivity_trials --seeds 0 1 7 18
```

The commands create a new episode under the output folder and reset the simulator from the seed. Omit `--checkpoint` for the complete experiment. `--diagnostic` runs the same motion primitives with a scripted driver and labels the receipt and video accordingly. Use the existing `--expert-profile`, `--expert-config`, and `--reasoning-effort` options to change the provider explicitly. Each episode writes its own receipt, decision frames, and optional video. A failed experiment returns exit code 1 and retains its evidence.

To use the student browser, run the existing lab server:

```sh
OPENARMS_SMARTIVITY=1 OPENARMS_EXECUTION=mock python -m agentic.openarms_lab
```

Open [the local student app](http://127.0.0.1:8000/), choose an experiment, then use **Reset scene** to inspect a seeded setup or **Run volcano** / **Run potions** to start a fresh trial. **Stop simulation** cancels the pending expert call and motion. The panel uses the existing session grant. The existing pH conversation and Gemini Live speech stay on the existing routes. Use your established lab environment file via `OPENARMS_ENV_FILE` if Gemini Live credentials live outside this worktree. The dedicated panel controls authorize the Smartivity motion. Simulation-specific spoken commands remain outside the panel integration.

To reset directly through the local server API when it is running without a pairing code:

```sh
session=$(curl -fsS -X POST http://127.0.0.1:8000/api/sessions)
sid=$(printf '%s' "$session" | jq -r .session_id)
access=$(printf '%s' "$session" | jq -r .access_token)
curl -fsS -X POST "http://127.0.0.1:8000/api/sessions/$sid/smartivity/reset" \
  -H "Authorization: Bearer $access" -H 'Content-Type: application/json' \
  -d '{"scenario":"volcano","seed":0}'
unset session sid access
```

## Observation and control

The active OpenArms policy is the configured image-aware expert and local bounded skills. The existing expert transport attaches standard RGB images alongside a JSON host context and receives a typed tool decision. It has no learned tensor checkpoint or preprocessing normalization. The provider gets a declared preparation manifest, upright JPEG images named `overview` and `side`, and named joint readings. It never receives simulator object poses or the mutable contents ledger. Capture IDs, hashes, calibration and coordinate frame, capture clocks, and SIMULATED provenance identify the attached bytes. The spectator display samples the latest camera image on its own cadence.

A start authorizes only fixed simulated skills. Each move is bound to a current observation and phase. A fresh camera render rechecks alignment evidence before dispatch. Cancellation is checked before starting and while waiting for motion; a reset revokes the previous generation. Camera cadence, local simulation steps, expert inference, and spectator samples have separate timings. The viewer exposes tool choices and evidence summaries. Evaluator checks independently require a delivered-volume threshold, placement, and a new simulated pixel signature for pink foam or the lavender colour change. A model statement alone cannot pass the trial.

## Robot and approximation boundaries

The vendored model is the canonical SO-101 XML from [TheRobotStudio/SO-ARM100 at a758567](https://github.com/TheRobotStudio/SO-ARM100/tree/a758567/Simulation/SO101), Apache 2.0. The five arm hinges are shoulder pan, shoulder lift, elbow flex, wrist flex, wrist roll, followed by the gripper. The limits in degrees are ±110, ±100, ±96.83, ±95, −157.21 to 162.79, and −10 to 100. MuJoCo uses radians internally. The pinned [LeRobot follower](https://github.com/huggingface/lerobot/tree/e0d50211/src/lerobot/robots/so_follower) uses arm degrees under this project's configuration and gripper commands normalized from 0 to 100. The Hiwonder [SO-ARM101 manual](https://wiki.hiwonder.com/projects/LeRobot/en/latest/docs/1_SO_ARM101_Open_Source_6_Axis_Robotic_Arm_User_Manual.html) lists HX-30HM follower servos and HX-10HM leader servos. These do not establish the simulator's dynamics on that follower. The working map's positive signs and zero offsets remain guesses. No hardware was operated.

MuJoCo integrates the bounded position actuators and joint/contact dynamics. The executor uses existing motion segments and numerical IK to generate joint goals for a taught fixture layout. The grasp attaches a mocap vessel to the gripper after a position check. Docking accepts an upright release within 8 mm and snaps the vessel home. Collision counts measure new penetrating body pairs from the modeled geometry. Jaw friction, payload dynamics and dynamic drops remain unvalidated. Compound convex wall colliders and a separate base preserve each vessel opening. The volcano donor shape is photo-derived. The flask and potion cup dimensions are illustrative.

The flow model uses water or tea as the carrier. It depletes the source as a function of fill and tilt and draws a vertical stream from the spout or cup lip. The receiving opening captures the stream if the projected lip lies inside its geometric catchment. Capacity bounds separate delivered volume, missed spill and overflow. The ledger proportionally moves tracked recipe constituents in their original units. It does not model consumption kinetics, pressure, fluid forces or dissolved-gas expansion. Pink foam, lavender colour, fizz and tray residue are illustrative and appear only after qualifying transfer into the prepared contents.

## Recorded results

| OpenArms policy run | Result | Delivered / spilled | Active wall time | Policy calls |
| --- | --- | --- | ---: | ---: |
| Volcano seed 0 | Passed, returned to dock | 15.000 / 0.000 mL | 77.43 s | 5 |
| Volcano seed 18 | Passed, returned to dock | 15.705 / 0.000 mL | 72.39 s | 5 |
| Potions seed 0 | Passed, returned to dock | 25.000 / 0.000 mL | 68.16 s | 5 |

Each complete run recorded zero drops, collisions, operator interventions, and extra resets. The policy was the authenticated OpenArms Codex expert transport with Sol medium requested. The CLI did not emit a separately resolved model identifier. The first pick-only own-policy checkpoint passed in two calls and showed the beaker lifted in both cameras. The live student browser passed a separate two-camera reset and STOP check while policy inference was pending.

Volcano seed 18 advanced 0.999 sim seconds per wall second at 249.82 physics steps per second, with 2.57 captures per camera per second and 8.00 recorded spectator samples per second. Policy calls took 7.86–12.46 seconds. Dispatch frames were 25–113 ms old when commands started. Setup time is measured separately and varies with machine load. MJCF compilation and IK run off the app event loop. Running the simulator clock at wall rate does not erase the delay between decisions.

The paired scripted diagnostic reused the same four seeds and motion sequence for baseline mouth-centre targeting and candidate spout targeting. Mouth centre passed 3/4, and spout targeting passed 4/4. On seed 18, mouth centre delivered 11.970 mL and spilled 3.734 mL despite visible foam. Spout targeting delivered 15.705 mL with zero spill. No collisions or drops occurred in the eight trials. The simulator defaults to the spout correction. The diagnostic retains the mouth-centre option. This comparison evaluates targeting and transfer with a scripted driver. The expert-driven results are recorded separately.

## Shortlist after Potions

- **Colourful Rainstorm**, pp. 16–17. A prepared oil and dye mixture can reuse the pour, but the water/oil interface and descending droplets need their own visual model.
- **Lava Lamp**, pp. 38–39. Slow acid addition through oil adds metering and a separate two-phase bubble model. Page 39 does not quantify the acid dose.
- **Magic Milk**, pp. 22–23. Surface swirls and cotton-stick handling belong after controlled tool contact is available.

Smartivity retains credit for the booklet, experiment names and recipe. OpenArms' simulation and rendering are project adaptations.

## Next improvement

The repeated expert calls are the largest measured delay. Prove a warm route through the existing registry for the validated pick, spout-aligned pour and placement sequence. Require fresh fixture and outcome checks between moves and invoke the expert when a check fails. Compare that path with the current five-call baseline on the same seeds before admitting it.
