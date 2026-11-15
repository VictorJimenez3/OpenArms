# Simulation

The [Smartivity replay guide](smartivity/README.md) includes the Volcano, Magic Potions and Lava Lamp videos and render commands.

A MuJoCo model of the SO-101 arm and the bench. Given a plan, it plays the arm's motion, reports what would go wrong, and says whether the plan is safe to run on the real arm.

There are two bench setups:

- **`block`** (the default): one block, moved between three marked points A, B and C.
- **`liquid`**: mini-cups at A and B poured into receivers at C and D, with a predicted colour change.

**Status:** both setups run end to end, but neither has been matched to the real arm yet. The poses and the bench positions are placeholders, and the joint mapping is unmeasured. Every result says so in its `warnings` until that is done. See [Matching the real arm](#matching-the-real-arm).

## Setup

From the repo root, in the same conda environment as LeRobot:

```bash
conda activate lerobot
pip install -e simulation
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

## From the simulation to the real arm

This path needs no ruler. You show the arm two spots once; after that the simulation plans moves between them and the real arm runs them. Run these from the repo root.

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

### Bench check for the joint map

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

## Open questions for the team

- **Block or liquid for the demo** is still undecided in `docs/PROJECT.md`. Both work here; block is the default because it is simpler to get reliable on the real arm.
- **Action names.** `move_block(from, to)` follows the name suggested in `research/duc/harness.md`; the agent's catalog needs the same one.
- **Who tracks where the block is.** The simulation takes the block's position as an input each time. The firmware's `state()` is the natural owner.
- **Serving the video.** `video_url` is a `file://` link, which only works on the bench laptop. The UI needs it served over HTTP.
- **Liquid only: showing the predicted result.** The preview shows the predicted colour, while the agent prompt currently says not to tell the student the expected result before testing.
- **Liquid only: `portions` greater than 1.** `add_sample` expands to several `pour` steps with the same cup, which is empty after the first. The simulation reports this as a note.

## Robot appearance

Render the OpenArms SO-101 with white structural plastic in every simulation, including policy cameras, student views, stills, and videos. The base, links, wrist, and printed gripper parts are white. Motor housings, fasteners, and grip pads may stay dark. Carry the same treatment into MuJoCo and Isaac. Use material edits that preserve the geometry and controller.

Use the current white materials for new exports and re-renders. Retain historical observations and their original appearance in evidence records.

## Credits

The arm model in `models/so101/` is from [TheRobotStudio/SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100) (`Simulation/SO101`, commit `a758567`), Apache 2.0. OpenArms applies a white printed-plastic finish in the shared model. See `models/so101/LICENSE`.
