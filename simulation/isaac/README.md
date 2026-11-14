# Isaac 5.1 runtime and mass experiment

**Actual grasp-and-place and both science conditions passed on Rutgers RTX A6000
Slurm job 1273420**, using Isaac 5.1.0.0, driver 580.178.04, and source commit
`002e9a7cbd7f60f7cbd763369881dd0c34922d29`. Each trial recorded 720 frames / 24 seconds
at 960×720, satisfied live contact/lift/release/settling checks, and exited zero.
The white SO-101 uses NVIDIA's original NO-CAMERA articulation. An external camera
records evidence; the robot has no onboard camera. See [evidence](evidence/README.md).

A temporary RTX 3060 passthrough VM also ran the same simulation. This separate
dedicated-host route must not be confused with a Slurm allocation. The host's
installed 595 driver was retained; only the guest used 580. Host restoration is
tracked in the execution receipt. Native host 595 attempts failed and are preserved.

## Student experiment

Question: **How does increasing mass change the force on a support at fixed gravity?**
Students select a 10 g or 40 g block. Geometry, robot motion, friction, gravity
9.81 m/s², receiver, and acceptance checks remain fixed. The robot grasps the block,
transfers it, releases it into the tray, and retreats. The measured quantity is the
tray's signed vertical normal force on the block during the final one-second
settled window (121 raw samples at 120 Hz). Expected weights `m*g` are separately
labelled analytic predictions. No chemical, liquid, or physical-robot outcome is claimed.

`experiment_report.py` checks completed processes, hashes, continuous raw samples,
settling, finite measurements, and matching controls before comparing conditions.
It refuses failed, incomplete, tampered, or unmatched recordings. One pair alone
does not establish statistical significance or broad reliability.

## Reproduce on Rutgers

Use approved Slurm allocations, storage, and network access. Never launch GPU work
on a login node. Inspect current `sinfo`, `squeue`, and `scontrol` before requesting
an RTX GPU. The verified environment lives on **rlab7 node-local storage**:
`/freespace/local/jdr317/openarms-isaac-5.1.0`. It contains Python 3.11 and an isolated
Isaac 5.1 pip environment; no root or Docker is required. On a fresh environment,
run `bootstrap.sh` and `prepare_assets.sh` inside an approved installation job.
Allow at least 50 GB free and accept NVIDIA's EULA before installation/use.
Workshop pin: `ce807d99724cb65671abec01f908a2fcb4a6eab7`. Fetch actual Git LFS assets.

From a clean checkout at the desired execution commit:

```bash
export OPENARMS_ISAAC_ROOT=/freespace/local/jdr317/openarms-isaac-5.1.0
export OPENARMS_EVIDENCE_ROOT=/common/users/jdr317/openarms-isaac/evidence
sbatch --partition=unlimited --nodelist=rlab7 -G a6000:1 \
  --mem=32G --time=00:15:00 --job-name=openarms-mass-light \
  --output="$OPENARMS_EVIDENCE_ROOT/slurm-%j.log" --export=ALL \
  simulation/isaac/skill_job.sh light
# Repeat with heavy after light completes; use the same source and configuration.
```

Inside an existing allocation, use `srun --jobid=JOB --overlap --ntasks=1 bash
simulation/isaac/skill_job.sh light`. All GPU identity/version evidence comes from
the allocated step. The script creates a unique request and evidence directory.
First shader compilation may take several minutes. Streaming is not required.

After both complete:

```bash
python3 -m simulation.isaac.experiment_report \
  --light /absolute/light-run/recording \
  --heavy /absolute/heavy-run/recording \
  --output /absolute/comparison
```

Every new invocation creates a fresh stage, resets robot positions and velocities
before simulation, and rejects reused output directories. Scene construction and
reset were exercised by separate successful light/heavy runs. Preserve startup
and Slurm logs, preflight, `request.json`, `result.json`, `experiment.json`, and all
`recording/` artifacts: receipt, external process result, flattened stage, raw
states, events, first frame, configuration, and actual MP4. Flattened stages retain
Isaac MDL dependencies; reproduce with the pinned runtime and workshop resolver.

## Simulation-only application interface

`skill.py` is a process integration entry point; it is not registered automatically
as an application backend. The application retains student confirmation and request
deduplication. These science requests use the existing canonical Parameters shape:

```json
{"request_id":"trial-001","session_id":"student-session-001",
 "skill_id":"isaac.mass_weight.light.v1",
 "parameters":{"object":"sample","source":"A","destination":"B"}}
```

Choose `isaac.mass_weight.heavy.v1` for 40 g. `known_station_transfer.v1` performs
the bounded 10 g transfer with the same parameters. `isaac.articulation.v1` with
empty parameters is a standalone diagnostic, not the application's Parameters shape.

```bash
"$OPENARMS_ISAAC_ROOT/venv/bin/python" simulation/isaac/skill.py \
  --request request.json --workshop "$OPENARMS_ISAAC_ROOT/workshop" \
  --output "$OPENARMS_EVIDENCE_ROOT/skill-trial-001"
```

`recording/events.jsonl` streams request ID, SIMULATED provenance, phases and completion.
`result.json` and stdout use the application's ExecutionResult shape. Science results
include mass, measured support force, separately labelled analytic prediction, and
an audited `experiment.json`. `physical_success` is always null. This module never
imports firmware, serial, LeRobot teleoperation, or MuJoCo.

Use a common evidence-root directory so the process lock prevents concurrent
simulators. Send SIGTERM to the skill process for STOP: it forwards interruption,
then terminates the child process group after 30 seconds if necessary. A real
experimental run was stopped through this interface; it returned `stopped` and
preserved its failed/interrupted recording. No physical robot STOP is implied.

The default `--cleanup sensors` explicitly releases camera subscriptions and
viewports before normal application close. It completed on the Rutgers trials.
Native crashes remain captured by `run_recording.py`; successful observations alone
cannot produce overall success if process exit or explicit cleanup failed.

## Contact model and limits

Only joint drive targets change after reset. The cube is dynamic: no pose writes,
parenting, welds, or attachments make the grasp succeed. Acceptance requires two
finger-body contacts, at least 40 mm lift held for 0.25 s, no sustained contact loss
before release, placement within the receiver, release, over 50 mm retreat, upright
support and one continuous second below 0.01 m/s and 0.1 rad/s. Actual contact
points, normals, forces and separations are logged. Normal-force telemetry is not
a complete tangential-friction force balance.

All active colliders use 0.5 mm contact offset, zero rest offset and zero added
torsional-patch radius. Earlier successful footage used oversized library defaults;
retain it as historical evidence, not the qualified contact configuration.
`vial_scene.py` remains an unqualified offline candidate and is not a student skill.
The kinematic solver's synthetic tests are preparation, not execution proof.

## Checks and sources

```bash
python3 -m unittest simulation.isaac.test_experiment_report \
  simulation.isaac.test_interface simulation.isaac.test_manipulation_checks
python3 -m py_compile simulation/isaac/*.py
bash -n simulation/isaac/skill_job.sh
```

- [Rutgers GPU scheduling](https://resources.cs.rutgers.edu/docs/scheduler-for-gpu-jobs/)
- [Rutgers storage](https://resources.cs.rutgers.edu/docs/file-storage/storage-technology-options/)
- [Isaac 5.1 installation](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/install_python.html)
- [Pinned NVIDIA SO-101 workshop](https://github.com/isaac-sim/Sim-to-Real-SO-101-Workshop/tree/ce807d99724cb65671abec01f908a2fcb4a6eab7)

Original upstream licenses/notices are retained. This implementation uses the
workshop articulation with Isaac Core API; it does not require the workshop's
Docker/Isaac Lab/training stack.
