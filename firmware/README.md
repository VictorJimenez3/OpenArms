# Firmware and arm setup

Run the setup and arm commands below from the repository root unless a step changes directories. The shared [calibration files](../calibration/) are loaded by [env.sh](../env.sh).

## Recorded physical result

The November 14 supervised C→B run physically picked up and placed the mandarin on the red card. Its [poses, logs, calibration snapshots and camera evidence](../research/joseph/mandarin-transfer-2026-11-14/README.md) are committed for teammates to inspect. The successful staged run loaded local `outputs/mandarin-bench/bench-a.json` plus pickup/lift corrections, not the default `firmware/openarms_executor/poses.json`. The preserved pose snapshot is historical evidence; keep the current bench configuration explicit when running a new trial.

## Setup (macOS)

You need [conda](https://github.com/conda-forge/miniforge) and git. Run these once, from the root of this repo:

```bash
git clone https://github.com/huggingface/lerobot.git LeRobot/lerobot
cd LeRobot/lerobot
git checkout e0d50211
conda create -y -n lerobot python=3.12
conda activate lerobot
pip install -e ".[feetech]"
cd ../..
```

The `git checkout` line pins everyone to the same LeRobot version (0.6.2).

## Running the arms

### 1. Prepare the terminal

Do this in every new terminal, from the root of this repo:

```bash
conda activate lerobot
source env.sh
```

It should print a line ending in `/calibration`.

### 2. Find the USB ports

Plug in both arms and turn on their power. Then run this once per arm. It asks you to unplug that arm's USB cable and reports which port disappeared:

```bash
lerobot-find-port
```

Ports look like `/dev/tty.usbmodem5A460851921`. They can change between computers and USB sockets, so check again if something stops connecting.

### 3. Teleoperate

Replace the two ports with the ones from step 2:

```bash
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=/dev/tty.usbmodemFOLLOWER \
  --robot.id=my_awesome_follower_arm \
  --teleop.type=so101_leader \
  --teleop.port=/dev/tty.usbmodemLEADER \
  --teleop.id=my_awesome_leader_arm
```

Move the leader arm and the follower copies it. Press `Ctrl+C` to stop.

## Calibration files

LeRobot picks a calibration file from the `id` you pass on the command line, so keep the two ids above exactly as written.

| File | Arm |
|---|---|
| `calibration/robots/so_follower/my_awesome_follower_arm.json` | Follower (the arm that does the work) |
| `calibration/teleoperators/so_leader/my_awesome_leader_arm.json` | Leader (the arm you move by hand) |
| `calibration/robots/so_follower/None.json` | An earlier follower calibration saved without an id. Not used by the commands above. |

These files only fit our two physical arms. If you recalibrate, the new file is written into `calibration/`, so commit it for the rest of the team.

## Troubleshooting

**LeRobot asks me to calibrate.** Stop, don't go through with it. Either `source env.sh` was skipped in this terminal, or an `id` is misspelled. Check with `echo $HF_LEROBOT_CALIBRATION`.

**"Could not connect" or a port error.** Run `lerobot-find-port` again; the port name has probably changed. Also check that the arm's power supply is on, not only the USB cable.

**The leader and follower seem swapped.** The two ports are the wrong way round. Swap `--robot.port` and `--teleop.port`.

**`ImportError: ... libtorch_cpu.dylib` when starting LeRobot.** The PyTorch install is damaged. Repair it with:

```bash
python -m pip install --force-reinstall --no-deps torch
```

## Safety

- Keep hands and faces clear of the follower arm while it is powered.
- Know where the power switch is before you start; cutting power is the emergency stop.
- Water only, in plastic containers, until we have done a safety review.
