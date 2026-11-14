# How do we record the arm's actions so `add_sample(A, C, 1)` works?

Duc, Sat Nov 14, 2026. Bench how-to for [arm-tools.md](arm-tools.md) layer 4.

## Finding

Each arm step replays saved joint positions. Recording means steering the follower into each position with the leader arm and saving its joint readings under a name. Nothing is trained, and nothing is tuned by the LLM.

**Before you start**
- Tape the cup holders down at A, B, C and D. A saved position is only right while the cups stay where they were.
- Put the whole stack in the team's `lerobot` env (see [firmware/README.md](../../firmware/README.md)), then add ours: `pip install -r agentic/requirements.txt`.
- Run `source env.sh` in every terminal so the calibration files load, and find both ports with `lerobot-find-port`.
- Keep a hand on the follower's power switch: cutting power is the emergency stop.

**1. Record**, with an empty mini-cup in each source holder:

```bash
python -m firmware.openarms_executor.teleop_record \
  --follower-port /dev/tty.usbmodemFOLLOWER --leader-port /dev/tty.usbmodemLEADER \
  --out firmware/openarms_executor/poses.json
```

Move the leader. When the follower is where you want it, hold the leader still and type the name:

| Name | Where the follower should be |
|---|---|
| `HOME` | Rest pose, clear of the cups and the camera |
| `ABOVE_A`, `ABOVE_B` | Gripper open, about 5 cm straight above the source cup |
| `GRASP_A`, `GRASP_B` | Lowered straight down from `ABOVE`, cup between the gripper's fingers |
| `ABOVE_C`, `ABOVE_D` | Holding a cup, about 5 cm above the receiver |
| `TIP_C`, `TIP_D` | The cup tipped all the way out over the receiver |
| `open` | Gripper fully open (saves the gripper value only) |
| `cup` | Gripper closed firmly on a mini-cup (saves the gripper value only) |

Rules for good positions:
- `ABOVE` → `GRASP` must be a straight vertical drop.
- Every move goes through an `ABOVE` position, so record those high enough to clear every cup.
- If a source holds two cups, record `ABOVE_A2`/`GRASP_A2` for the second. Record both or neither.

Typing a name again overwrites that position. Press Enter on an empty line to finish. Torque stays on, so the arm holds where it is.

**2. Check one position comes back**: `python -m firmware.openarms_executor.replay_test --port /dev/tty.usbmodemFOLLOWER`

**3. Dry-run each step 10 times with water, then without:**

```bash
python -m firmware.openarms_executor.test_action --action pick --station A --runs 10 --port /dev/tty.usbmodemFOLLOWER --poses firmware/openarms_executor/poses.json
```

Repeat for `--action pour --into C`, and for B and D. A step is `verified` at 9/10. If a step fails, re-record the position it failed on and run it again.

**4. Run the demo**: `python -m agentic.scripts.brain_repl --real --port /dev/tty.usbmodemFOLLOWER` (needs `ANTHROPIC_API_KEY` in `agentic/.env`).

**Voice demo (Joseph's relay, mandarin A → B).** Record a separate file, `--out firmware/openarms_executor/poses.mandarin.json`, with `HOME`, `ABOVE_A`, `GRASP_A` (fingers around the mandarin), `ABOVE_B`, `GRASP_B` (where it is set down), `open`, and `cup` (closed on the mandarin). Then start the relay from `research/joseph/iphone-voice-bridge/relay/`:

```bash
PYTHONPATH=<repo root> OPENARMS_FOLLOWER_PORT=/dev/tty.usbmodemFOLLOWER \
OPENARMS_POSES=<repo root>/firmware/openarms_executor/poses.mandarin.json \
python relay.py --dialogue agy --runner firmware.openarms_executor.transfer_runner:create_runner
```

The relay's terminal asks the operator `y/n` before every transfer. It won't ask while the arm is moving or while an earlier prompt is still open (answer that one `n` first). The arm must start at `HOME` (within 5 units per joint), or the transfer fails without moving. A fault or a STOP mid-transfer locks the runner until the relay restarts. A STOP lets the current move finish first, which can take up to about 3.5 s. Use `OPENARMS_FAKE_ROBOT=1` instead of the port to rehearse without the arm.

## Evidence

- Updated November 14: guided recording ran on the real arms and produced `bench-a.json` plus a continuous A demonstration trace. A subsequent camera-assisted C→B mandarin transfer succeeded. See the [actual poses, logs and images](../joseph/mandarin-transfer-2026-11-14/README.md). The cup/pour procedure above still needs validation with the actual fixtures.
- LeRobot class names (`SO101Follower`, `SO101Leader`) and `<motor>.pos` keys were checked in LeRobot's source at the pinned commit `e0d50211`.
- Why our own loop and not `lerobot-teleoperate` plus `record_pose`: teleop holds the follower's serial port, and stopping it switches torque off, so the arm sags before it can be read.

## Open question

- Are the joint values degrees, or LeRobot's −100 to 100 scale? It changes what the 10-unit step cap and the 3-unit arrival tolerance mean.
- The relay runs under `uv` with Python 3.13 and LeRobot lives in the conda env: one Python needs both for the voice demo. Untested.
- Does the arm sag more than 3 units holding a full cup? If moves fail with "did not reach target", raise `tol` in `move_to`.
