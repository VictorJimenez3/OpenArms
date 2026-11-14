# Simulation

A MuJoCo model of the SO-101 arm and bench. It previews modeled motion and reports configured checks; it does not establish that a real trajectory is safe or physically qualified. **MuJoCo is active. Isaac is parked**, with its source and completed evidence preserved.

Current setups:

- **`liquid`**: exactly two active vessels, donor A and fixed receiver C. One premeasured water portion, donor return, HOME. This is the physical rehearsal baseline.
- **`block`** (the standalone CLI default): retained block-transfer diagnostic, outside the selected physical chemistry demo.
- **`liquid_legacy`**: retained four-station example under `config/setups/liquid/legacy/`, outside current physical scope.

**Status:** the two-vessel scene, renderer, image checks and return sequence are implemented. The poses, dock/robot placement and joint mapping remain provisional. The active liquid scene still uses provisional 70 mm donor / 60 mm receiver heights; it has not yet consumed the newer [photo-derived vessel meshes](models/vessels/measured_2026_11_14/README.md) or [two-seat CAD](../firmware/fixtures/cup_dock/README.md). Those inputs must be reconciled without silently resizing docks or claiming measured registration. See [Matching the real arm](#matching-the-real-arm).

The student application selects this carried-donor apparatus with `OPENARMS_EXECUTION=mujoco OPENARMS_SCENE=two_vessel`; follow [the runbook](../docs/LAB_RUNBOOK.md). The earlier fixed-dispenser `metered_dropper` apparatus remains a distinct regression backend. No preview or simulator enables physical dispatch.

`openarms_sim.two_vessel` captures fresh overview images and detects colored reference patches and vessel rims from pixels. These simulated color patches are **not ArUco/AprilTag markers**. Actual printable marker patterns and machine-readable fixture coordinates belong to the CAD directory. Both application view names currently use the same overview; there is no independent side-camera corroboration. Camera shifts, missing/swapped vessels, occlusion, stale timestamps and reset generations are rejection cases. Ground-truth state remains separate from image detections; receiver water appearance is not a measured transferred volume.

Smartivity volcano and broader virtual experiments are an independently owned extension in development. Their apparatus may differ from the two-vessel physical demo. Modeled chemistry and attached-object grasp must remain explicit, and the hardware pour need not wait for simulation polish.

## Setup

From the repo root, use a separate application/simulation environment and preserve the working hardware environment:

```bash
python3 -m venv .venv-lab
.venv-lab/bin/python -m pip install -e simulation -r agentic/requirements-lab.txt
```

## Try it

```bash
# Preview "move the block from A to B": prints the result and writes an MP4.
python -m openarms_sim --from A --to B

# Watch it in an interactive 3D window (macOS needs mjpython, not python).
mjpython -m openarms_sim.view --from A --to B

# Start with the block somewhere else.
python -m openarms_sim --from C --to A --objects '{"block": "C"}'

# Render every one-step plan ahead of time (see "Speed").
python -m openarms_sim.prerender

# Tests. No arm or display needed.
cd simulation && pytest
```

The liquid setup uses the same commands with `--setup liquid`:

```bash
python -m openarms_sim --setup liquid --from A --to C
mjpython -m openarms_sim.view --setup liquid --from A --to C

# A mix that is only allowed in simulation: shown, then blocked.
python -m openarms_sim --setup liquid --from A --to C --contents '{"A": {"bleach": 1}, "C": {"ammonia": 1}}'
```

To make liquid the default for a terminal session, run `export OPENARMS_SETUP=liquid`.

## Historical taught-block integration procedure

The retained procedure below is separate from the current two-vessel application. It is not executed by software reconciliation. Physical operators own calibration and qualification; use the current [wet-lab runbook](../docs/WET_LAB.md) for A→C dry/water bring-up. A successful simulated preview alone cannot authorize this real-arm path.

1. **Record one move with the leader arm**: pick the object up at A, put it down at B, and bring the arm back to rest before the time runs out.

   ```bash
   source env.sh
   lerobot-record --robot.type=so101_follower --robot.port=<follower port> --robot.id=my_awesome_follower_arm \
     --teleop.type=so101_leader --teleop.port=<leader port> --teleop.id=my_awesome_leader_arm \
     --dataset.repo_id=local/block_A_B --dataset.root=recordings/block_A_B \
     --dataset.single_task="Move the block from A to B" --dataset.num_episodes=1 \
     --dataset.episode_time_s=40 --dataset.reset_time_s=0 --dataset.push_to_hub=false
   ```

2. **Check the take in the simulation.** It finds the moments the gripper closed and opened, and draws A and B there.

   ```bash
   mjpython -m openarms_sim.recording recordings/block_A_B --view
   ```

3. **Teach.** This writes `config/setups/taught/`: points A and B, the real grasp poses, and the lifted poses the simulation works out.

   ```bash
   python -m openarms_sim.teach recordings/block_A_B --block-size <width cm> <height cm>
   ```

4. **Plan a move you never recorded, and preview it.**

   ```bash
   mjpython -m openarms_sim.view --setup taught --from B --to A --objects '{"block": "B"}'
   ```

5. **Send it to the real arm.** Try `--dry-run` first to see the commands without connecting.

   ```bash
   python -m openarms_sim.real --port <follower port> --setup taught --from B --to A --objects '{"block": "B"}'
   ```

   It refuses to run a plan the preview blocks, checks that the arm is resting near `HOME`, waits for ENTER, runs at half speed by default (`--speed`), and ends back at rest before the motors switch off. Ctrl+C stops the motion and holds the arm until you press ENTER.

Why this works with an unmeasured joint map: the same map turns the real joint readings into simulated positions and the simulation's joint angles back into real commands, so the error cancels at the taught spots. It does not cancel in between: the lift height and the path across are the simulation's own, and can be off by a centimetre or two until `joint_map.yaml` is measured.

Things `teach` decides for you:

- `HOME` is where the arm came to rest at the end of the take.
- If the simulation shows the object being let go above the table, `GRASP_B` is lowered to the pick's height, so that picking up at B grips the object at the same place as at A.
- Whatever overlaps in the simulation at a taught pose (the folded arm at rest, for example) is not reported as a collision near that pose.

## Using it from code

```python
from openarms_sim import preview

result = preview({
    "plan_id": "p-0007",
    "steps": [{"action": "move_block", "args": {"from": "A", "to": "B"}}],
})
```

```json
{
  "plan_id": "p-0007",
  "setup": "block",
  "ok": true,
  "video_url": "file:///.../simulation/outputs/previews/a5ed9d97466cf5c7.mp4",
  "warnings": ["Poses are placeholders, not recorded on the real arm, so this preview is illustrative."],
  "issues": [{"severity": "note", "code": "placeholder_poses", "message": "...", "step": null}],
  "objects": [{"name": "block", "at": "B", "started_at": "A", "moved": true}],
  "predicted": [],
  "motion_seconds": 11.6,
  "cached": false
}
```

- `ok` is `false` when any issue has severity `block`. A blocked plan is still simulated and still gets a video, so the student can see what would happen; it must not be sent to the real arm.
- `warnings` lists the reasons for a block first, then the notes.
- `objects` says where each loose object ended up. `at` is `null` if it was dropped off a mark.
- `predicted` is filled in the liquid setup: one entry per receiver with its contents and predicted colour.

Options:

- `preview(plan, objects={"block": "C"})` says where the block starts. Without it, the block starts where `bench.yaml` puts it (A). The simulation does not remember earlier plans, so the caller passes the current position each time.
- `preview(plan, contents={...})` overrides what each container holds at the start (liquid setup).
- `preview(plan, setup="liquid")` picks the setup.

### Plan actions

| Action | Expands to | Setup |
|---|---|---|
| `move_block(from, to)` | `pick(from)`, `place(to)`, `home()` | block |
| `add_sample(source, into, portions=1)` | `pick(source)`, `pour(into)` × portions, `return_cup()`, `home()` | liquid |
| `wait(seconds)` | The arm holds still for 1 to 30 seconds | both |
| `look(station)` | Ignored; nothing moves | both |

A plan may also contain the arm steps `pick`, `place`, `pour`, `return_cup` and `home` directly.

### What gets blocked

| Code | Meaning |
|---|---|
| `missed_grasp` | The gripper closes with nothing between the jaws, for example picking from an empty point |
| `nothing_held` | A place or pour with an empty gripper |
| `bad_release` | The object is let go away from a mark, or tilted |
| `occupied` | Something is already on the point |
| `still_holding` | The plan ends with something in the gripper |
| `hits_table`, `hits_object`, `held_hits_table`, `held_hits_object`, `self_collision` | The arm, or the thing it holds, runs into something |
| `joint_limit` | A pose is outside the model's joint range |
| `bad_plan` | Unknown action, unknown station, or a missing argument |
| `unsafe_mix`, `overflow`, `spill`, `no_pour` | Liquid setup: a disallowed mixture, a full receiver, a pour that misses, a cup not tipped far enough |

### Speed

Rendering a block move takes about 1.5 seconds on an M2 MacBook, and a pour about 3 seconds, which is at the agent's timeout. Videos are cached by plan, starting state and config, so a repeat request returns instantly. Run `python -m openarms_sim.prerender` before a demo, and again after changing anything in `config/`.

## Science kit setup

`--setup kit` puts the Smartivity "My First Science Experiment Kit" on the bench: the kit's two cups (A and B) are poured by the arm into its beaker (C) and flask (D).

```bash
python -m openarms_sim --setup kit --from A --into C     # erupting volcano
python -m openarms_sim --setup kit --from B --into D     # instant snow
python -m openarms_sim --setup kit --from B --into D --contents '{"D": {"cornstarch": 2}}'    # oobleck
python -m openarms_sim --setup kit --from A --into C \
  --contents '{"A": {"yellow_colour": 1}, "C": {"water": 1, "blue_colour": 1}}'              # colour mixing: green
```

| Experiment | In the cup | In the beaker or flask | Predicted |
| --- | --- | --- | --- |
| Erupting volcano | citric acid solution | baking soda, liquid soap, red colour | red with fizzing and foam rising like a volcano |
| Instant snow | water | snow powder | white, swelling into fluffy instant snow |
| Oobleck | water | cornstarch | white, thickening into oobleck |
| Colour mixing | one food colour | water and another colour | orange, green or purple |

The kit's substances, the colour-mixing rule and these reactions are in `config/chemistry.yaml`. The predictions come from that rule table: the simulation draws the liquid and names what the student should see, it does not simulate foam, swelling or thickening. All of the kit's substances are on the `real_bench` list.

Two things are placeholders in `config/setups/kit/bench.yaml`: the sizes of the cups, beaker and flask (the listing gives none, so they are estimates) and their positions (chosen so the simulated arm reaches them). The poses in `poses.json` are solved by the simulation, not recorded on the arm. Measure the pieces and record real poses once the kit is on the bench.

## Demo bench with the rulers as axes

`--setup demo` is the live demo bench: a small beaker (about 50 mL) that the arm pours into a wide round container marked 100 mL. Two 30 cm rulers taped in an L are the bench's axes, and `config/setups/demo/bench.yaml` gives every position in **ruler centimetres**, so a layout change is an edit of two numbers:

```yaml
ruler_frame:
  arm_cm: [16.0, 33.0]      # where the arm's base axis sits, read off the rulers
  arm_heading_deg: -90      # which way the arm points: 0 along +X, 90 along +Y, -90 along -Y
stations:
  A: {kind: source,   ruler: [4.6, 4.2], ...}    # centre of the beaker's base
  C: {kind: receiver, ruler: [4.8, 13.6], ...}   # centre of the container's base
```

The origin is the inner corner of the L. Standing at the open side of the L, X runs to the right along one ruler and Y toward you along the other. After editing, run `python -m openarms_sim.ik --setup demo` to re-solve the arm poses, then `python -m openarms_sim --setup demo --from A --into C`.

What is measured and what is not:

- **Container sizes** come from `outputs/camera/live_demo.jpg`, scaled by the rulers' millimetre marks: beaker rim 4.5 cm, base 3.2 cm, about 4.7 cm tall; container rim 8.4 cm, base 6.0 cm, about 3.0 cm tall. The photo is tilted, so widths are good to about 0.5 cm and heights to about 1 cm. Check them against the real pieces.
- **Container positions** are read from the same photo.
- **The arm's position and heading** were first read from `outputs/camera/live_demo_2.jpg`, then corrected from a pour recorded on the real arm (2026-11-14, beaker at (22.3, 7.6), container at (5.8, 7.6)): swivel axis at about ruler (17, 36), base facing the X ruler almost squarely (heading -88). With that, the recorded grasp lands 0.6 cm from the photographed beaker. The earlier heading of -100 was the direction the gripper pointed in the photo, not the base's forward direction.
- **The grip and the pour** (`grasp:` in `bench.yaml`) also follow that recording: which way up the gripper holds the beaker (`wrist_roll_deg`), a quarter-turn tip (`tip_angle_deg`), and pouring about 3 cm from the container's centre (`pour_offset`). The solved grasp pose is within 8 degrees of the recorded one on every joint; the pouring pose is within 17 degrees and 4 cm. One recording is not a calibration: `joint_map.yaml` is still unmeasured and the solved poses are not sent to the real arm.
- The poses are solved by the simulation, not recorded on the arm.

### Rebuilding the bench from a picture

```bash
python -m firmware.openarms_camera locate --photo outputs/camera/your_photo.jpg          # look only
python -m firmware.openarms_camera locate --photo outputs/camera/your_photo.jpg --apply  # update the bench and run the pour
python -m firmware.openarms_camera locate --camera 0 --apply --beaker 4,7                # webcam; beaker position typed in
```

It finds the two red rulers, saves a flattened top-down picture with a 5 cm grid (`outputs/camera/bench_flat.jpg`), looks for the container and the beaker, and with `--apply` writes their positions into `bench.yaml`, re-solves the poses and runs the pour preview. The ruler mapping is good to about 0.5 cm near the rulers. Finding the clear containers is not reliable: on the two bench photos the container was right in one and 1.8 cm out in the other, and the beaker was 1 cm and 3.5 cm out, because its raised rim is easier to see than its base. Open `bench_flat.jpg`, read the true base position off the grid, and pass `--beaker X,Y` or `--dish X,Y` to correct it. The arm's own position is not detected; edit `arm_cm` if the arm moves.

Where the pour works in the simulation: both about 28 to 31 cm from the arm's base, on either side of it. Checked with the arm at (17, 36): beaker (22.3, 7.6) with container (5.8, 7.6), the mirror layout beaker (4, 7) with container (22, 4), and beaker (12, 6) with container (24, 8). Closer than about 25 cm the grasp is out of reach. As first photographed (beaker (4.8, 4.1), container (5.6, 12.8)) the container is between the arm and the beaker and the pour is blocked.

## Preview inside the student lab app

With `OPENARMS_PREVIEW=mujoco`, the lab app (`agentic/openarms_lab/`) simulates every
proposed transfer before it can be executed; see `docs/LAB_RUNBOOK.md`. That path uses
`openarms_sim/script.py`, which plays the firmware runner's own waypoint list instead of
a plan built from a setup:

```python
from openarms_sim.script import preview_script
out = preview_script(script, home, marks={"A": grasp_a, "B": grasp_b}, object_at="A", seconds=1.5)
```

`script` is the list of targets the runner sends (five arm joints in degrees, or the
gripper alone). The marks are drawn where those poses put the gripper, so nothing is
measured. A grasp on nothing, or an object that does not end at the destination, blocks.
Contacts with the table or object are notes until `config/joint_map.yaml` is measured.

## Config

Everything the simulation knows about the real world is in `config/`. The firmware should read the same files.

| File | What it holds | State |
|---|---|---|
| `setups/<setup>/bench.yaml` | Station positions, object and container sizes, grasp height | Placeholder: chosen so the simulated arm can reach, not measured |
| `setups/<setup>/poses.json` | Named joint poses (`HOME`, `ABOVE_A`, `GRASP_A`, ...) in LeRobot degrees | Placeholder: solved from `bench.yaml` by `python -m openarms_sim.ik --setup <setup>` |
| `joint_map.yaml` | Sign and offset per joint between the real arm and the model; gripper values; `go_to` speed | Unmeasured: sign +1, offset 0 |
| `chemistry.yaml` | Substances, the indicator colour scale, the real-bench allowlist, hazards (liquid setup) | First draft |

The arm steps are scripts over those poses (`openarms_sim/motion.py`):

```
pick(A)      = gripper(open) → ABOVE_A → GRASP_A → gripper(close) → LIFT_A
place(B)     = ABOVE_B → GRASP_B → gripper(open) → ABOVE_B
pour(C)      = ABOVE_C → TIP_C → hold → ABOVE_C
return_cup() = ABOVE_A → GRASP_A → gripper(open) → ABOVE_A
home()       = HOME
```

The block is 3.6 cm wide and 7 cm tall, standing upright, and the gripper holds it from the side at 4 cm above the table. A side grasp at that height only reaches marks about 28 cm or more from the arm's shoulder, which is why the points sit on an arc.

## Matching the real arm

The real arm replays poses that were recorded on the real arm, so reality is the reference and the simulation is fitted to it. Four things have to be true for the preview to match:

1. **Same poses.** Record the poses with the leader arm and write them to the setup's `poses.json` in the same format, with `"source": "recorded"`. The simulation and the firmware must both read that one file.
2. **Same motion between poses.** `go_to_duration()` and `blend()` in `motion.py` define how a move is timed. The firmware should import them, not reimplement them.
3. **Measured joint map.** Run the bench check below and fill in `joint_map.yaml`, then set `measured: true`.
4. **Measured bench.** Measure each mark's position from the arm's base with a ruler and put it in `bench.yaml`.

### Measuring the joint map without a ruler

```bash
source env.sh
python -m openarms_sim.calibrate collect --port /dev/tty.usbmodemXXXX   # motors off, arm moved by hand
python -m openarms_sim.calibrate fit            # look at the result
python -m openarms_sim.calibrate fit --write    # save it to config/joint_map.yaml
```

The table is flat, so every time the gripper's tip touches it the model must put the gripper's lowest point at table height. `collect` records about fourteen touches in different places and postures; `fit` finds the direction and offset of shoulder lift, elbow and wrist flex (and the height of the base above the table) that put all of them on one plane. On synthetic touches with 0.3 degrees of reading noise it recovers the offsets to within about 1 to 2 degrees, and it refuses to save when the touches are too alike or do not fit a plane. Shoulder pan and wrist roll are not measured: they do not change any height.

Once `measured: true` is saved, table and object contacts in the app's preview block a plan; until then they are notes. Re-run after any LeRobot recalibration, which moves every joint's zero.

### Bench check by eye (older method)

Not yet run on the real arm.

```bash
source env.sh
mjpython -m openarms_sim.mirror --port /dev/tty.usbmodemXXXX
```

The simulated arm follows the real one, and the terminal prints the real joint readings and where the simulation thinks the grasp point is, in centimetres from the arm's base.

1. Move one joint at a time on the real arm. If the simulated joint turns the opposite way, set that joint's `sign` to `-1`.
2. Put the arm in a pose that is easy to judge by eye, such as the forearm level or the gripper pointing straight down. Adjust `offset_deg` for each joint until the simulated arm looks the same.
3. Touch the gripper to a few marked points on the table and compare the printed position with a ruler. Aim for under 1 cm.

A starting point worth knowing: both LeRobot and this model put each joint's zero at the middle of its range, which is why sign +1 and offset 0 is the first guess. Our follower's calibrated ranges are 5 to 30 degrees wider than the model's, so expect offsets of a few degrees.

### What the simulation cannot show

- It moves the arm to exactly the commanded angles. The real arm sags a little under load and can lag behind.
- Collisions use simplified hulls around each part, so near misses can be reported as hits.
- A held object is attached to the gripper while the jaws are closed. A slipping or crooked grasp is not modelled.
- In the liquid setup, liquid is drawn, not simulated. The colour comes from `chemistry.yaml`.

## Chemistry (liquid setup)

The colour prediction is swappable. `RuleTableChemistry` in `chemistry.py` looks the colour up from acid portions minus base portions. To replace it, write a class with a `predict(contents) -> Outcome` method, add it to `MODELS`, and name it under `model:` in `chemistry.yaml`. A pH-based model would need real volumes and concentrations per portion in `bench.yaml`.

Safety is separate from the prediction and stays a list: only substances under `real_bench` may reach the real arm, and combinations under `hazards` are blocked. Anything not listed is simulation-only.

## Current handoff and retained diagnostic questions

- **Decided physical demo:** two vessels with preferred Smartivity indicator/citric-acid adaptation, pending actual packet, bench adaptation and outcome verification; contained fizz is fallback. Water qualifies motion. Block and four-station scenes are historical diagnostics.
- **Action names.** `move_block(from, to)` follows the name suggested in `research/duc/harness.md`; the agent's catalog needs the same one.
- **Who tracks where the block is.** The simulation takes the block's position as an input each time. The firmware's `state()` is the natural owner.
- **Serving the video.** `video_url` is a `file://` link, which only works on the bench laptop. The UI needs it served over HTTP.
- **Science evidence:** distinguish a model prediction from independently observed results. Prediction/reflection is optional; the current water rehearsal makes no chemical claim.
- **Liquid only: `portions` greater than 1.** `add_sample` expands to several `pour` steps with the same cup, which is empty after the first. The simulation reports this as a note.

## Credits

The arm model in `models/so101/` is from [TheRobotStudio/SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100) (`Simulation/SO101`, commit `a758567`), Apache 2.0. See `models/so101/LICENSE`.
