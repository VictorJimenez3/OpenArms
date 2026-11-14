# Isaac 5.1 runtime lane

Status: **real Isaac 5.1 articulation video recorded**, but the first process
crashed during shutdown. No successful grasp/place or science experiment yet.
Job `1273056` on rlab7 used an RTX A6000, driver 580.178.04 and commit
`761a57974fa43af942b5a3b564413de2f7df1a5d`. Its 240-frame, 8-second H264 recording
shows measured joint motion (Rotation span 0.3613 rad). The original observation
receipt says passed; Slurm/process exit 139 is authoritative for the failed
shutdown. Preserve both. Evidence is under
`/common/users/jdr317/openarms-isaac/evidence/job-1273056`.

The updated configuration uses the workshop's NO-CAMERA robot and white plastic.
The external recording camera is separate from the robot. Job `1273070` was
executed with commit `2cb3088` and produced the [actual updated recording](evidence/README.md).
Its articulation observations passed; native cleanup aborted with return -6.
`run_recording.py` now records child-process exits independently in
`execution.json`, so a native shutdown crash cannot leave an overall passed
receipt. Track current runtime state in
[issue 15](https://github.com/VictorJimenez3/OpenArms/issues/15). This directory
never imports firmware, serial, LeRobot teleoperation, or MuJoCo.

## Reproduce the first runtime proof

Use Rutgers Slurm, not a direct GPU process on a login node. Inspect current
availability (`sinfo`, `scontrol show node`, `squeue`) before choosing a GPU.
At the initial attempt the RTX PRO 5000 node was drained for maintenance and the
A6000/A5000 GPUs were fully allocated. A CPU-only installation does not allocate
an RTX GPU or prove rendering works.

1. Check out this branch at the execution receipt's commit. Use Git LFS for
   NVIDIA assets. The upstream pin is `ce807d99724cb65671abec01f908a2fcb4a6eab7`.
2. Set `OPENARMS_ISAAC_ROOT` to approved writable storage with at least 50 GB
   free. This run uses `/freespace/local/jdr317/openarms-isaac-5.1.0` on `rlab7`.
   Node-local environments must be run on the same node. Evidence belongs on
   shared storage and is copied back to the review machine.
3. Inside a Slurm CPU installation job, set `OMNI_KIT_ACCEPT_EULA=YES` after
   accepting NVIDIA's EULA, then run `bash simulation/isaac/bootstrap.sh` and
   `bash simulation/isaac/prepare_assets.sh`. This creates a Python 3.11 venv,
   installs Isaac 5.1.0, and downloads the actual workshop LFS assets. No root,
   Docker privilege, device mounts, or streaming ports are needed.
4. Submit the GPU job below. If installation has not completed, add an
   `--dependency=afterok:INSTALL_JOB_ID` argument. Do not mistake a queued job
   for an allocated GPU.

```bash
export OPENARMS_ISAAC_ROOT=/freespace/local/jdr317/openarms-isaac-5.1.0
export OPENARMS_EVIDENCE_ROOT=/common/users/jdr317/openarms-isaac/evidence
sbatch --job-name=openarms-isaac-smoke --partition=unlimited --nodelist=rlab7 \
  -G a6000:1 --mem=32G --time=00:30:00 \
  --output="$OPENARMS_EVIDENCE_ROOT/slurm-%j.log" \
  --export=ALL simulation/isaac/runtime_job.sh
```

The job captures host/GPU/driver/allocation evidence and runs `smoke.py` in
headless Isaac. The first scene is a neutral ground plane, workshop SO-101,
fixed third-person camera and ordinary lighting. It uses no Blender footage.
The smoke moves the Rotation joint through a small bounded sinusoid using
physics drives. It does not pick up an object and can never report manipulation
success. Inspect the actual first frame and video before accepting visual proof.

Each attempt uses a new output directory. Retain `startup.log`, Slurm logs,
`exit-status.txt`, `receipt.json`, flattened `scene.usda`, `state.jsonl`,
`first-frame.png`, and `camera.mp4`. A failure may have only some of these.
The receipt records source commit, dirty state, upstream commit, asset hash,
Isaac distribution version, GPU identity, simulation timing, measured joints
and artifact hashes. MDL modules still depend on Isaac's resolver even when USD
references are flattened. Reproduce using the pinned runtime and upstream assets.

A fresh invocation constructs a new stage and resets joint positions/velocities
before time integration. Reproducibility must still be demonstrated by rerunning
on the allocated device; reset code alone is not reset evidence.

## Manipulation gate

The unvalidated `vial_scene.py` is retained as a failed offline design candidate:
the nominal TCP can overlap the fixed finger with the tall vial, and the rack's
roughly 1 mm clearance needs tighter acceptance than its current checks. Do not
treat its task flag as a validated skill. A small block and broad receiver are
being evaluated as the first contact-only manipulation proof.

Use deterministic initial poses and
no inherited random/preplaced-vial resets. Drive only robot joints after reset;
never teleport, parent, weld or kinematically attach the object to make a grasp.
Record individual finger-object forces, object pose/velocity, measured joints,
phase transitions and release. Require sustained contact plus lift, placement
inside a specific receiver with lower/upper height bounds, release, retreat and
settling. Reject NaN, missing data and time gaps. The experimental evaluator in
`manipulation_checks.py` currently checks a simple cube-receiver transfer;
its tests are **synthetic evaluator tests**, not a vial task or Isaac proof.
Vial/rack checks must additionally use the actual slot transform and orientation.

Only after a repeatable grasp/place and reset should the lane choose two science
conditions from observed runtime feasibility and expose execution to the student
app. No simulation skill is advertised to the app yet. Preserve request IDs,
student confirmation, STOP/cancellation and SIMULATED/MODELED provenance from
`agentic/openarms_lab/contracts.py`; science quantities beyond rigid-body physics
must identify their separate model. Do not connect this runtime to serial ports.

## Validation and sources

```bash
python3 -m unittest simulation.isaac.test_manipulation_checks -v
python3 -m py_compile simulation/isaac/smoke.py
bash -n simulation/isaac/*.sh
```

These checks do not load Isaac. Independent review fixed camera aperture/focal
length units, physics/render cadence and nonfinite-measurement handling.

- [Rutgers scheduling](https://resources.cs.rutgers.edu/docs/scheduler-for-gpu-jobs/)
- [Rutgers storage](https://resources.cs.rutgers.edu/docs/file-storage/storage-technology-options/)
- [Isaac 5.1 installation](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/install_python.html)
- [Isaac requirements](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/requirements.html)
- [NVIDIA workshop](https://github.com/isaac-sim/Sim-to-Real-SO-101-Workshop/tree/ce807d99724cb65671abec01f908a2fcb4a6eab7)
- [OpenArms architecture](https://app.notion.com/p/41871c9c107e8155b53ff64d49069434)

The workshop is Apache-2.0; assets are fetched without relicensing or replacing
the original notices. The current upstream Dockerfile uses Isaac Lab 2.3.2;
this minimal Core API smoke isolates Isaac 5.1 and does not install that Docker
stack, LeRobot, GR00T or training dependencies.

## Dedicated Linux host and simulation request interface

A separate, explicitly authorized host is supported without fabricating a Slurm
identity. The default remains Slurm. `execution_context.py` requires the exact
configured dedicated hostname and rejects Rutgers managed hosts in that mode.
The verified IGVC machine is `igvc-NUC12DCMi9`, RTX 3060 12 GB, driver 595.99.02.
Its isolated installation passed dependency checks, but actual scene startup
crashes in `librtx.scenedb`. An empty-stage diagnostic reproduces this failure;
keeping the startup stage allows construction but does not make scene setup work.
The official immediate-cleanup option hung in a diagnostic and was terminated.
No RTX 3060 recording has passed. This resembles upstream 5.1/595 Vulkan reports,
including [issue 912](https://github.com/isaac-sim/IsaacSim/issues/912); the exact
root cause is not established. A host-wide driver change requires separate approval.
Its isolated environment is `/home/igvc/openarms-isaac-5.1`; no IGVC code, services,
robot calibration or physical devices are changed. Installation/launch outcomes
must be read from evidence, not inferred from this host inventory.

```bash
export OPENARMS_EXECUTION_CONTEXT=dedicated
export OPENARMS_DEDICATED_HOST=igvc-NUC12DCMi9
export OPENARMS_ISAAC_ROOT=/home/igvc/openarms-isaac-5.1
export OPENARMS_EVIDENCE_ROOT=/home/igvc/openarms-isaac-evidence
bash simulation/isaac/runtime_host.sh                   # articulation
bash simulation/isaac/runtime_host.sh --task cube       # unvalidated contact trial
```

`cube_plan.py` extracts reachable waypoints using the actual USD articulation.
`cube_scene.py` creates a dynamic 20 mm / 10 g block, a fixed broad receiver,
contact sensors and measurements. Its TCP offset is derived from the distal
finger geometry; closing preload is a drive target, not an achieved pose or a
weld. The proposed 24-second trial has not yet passed live physics. The older
vial candidate is retained for failure provenance and should not be promoted.

`skill.py` is an integration entry point, not a registered application backend.
The student application must retain confirmation and request deduplication.
Supported request envelopes carry `request_id`, `session_id`, `skill_id`, and
`parameters`. An articulation probe uses `isaac.articulation.v1` with `{}`.
The bounded transfer example uses the application's existing request shape:

```json
{"request_id":"trial-001","session_id":"student-session-001",
 "skill_id":"known_station_transfer.v1",
 "parameters":{"object":"sample","source":"A","destination":"B"}}
```

```bash
"$OPENARMS_ISAAC_ROOT/venv/bin/python" simulation/isaac/skill.py \
  --request request.json --workshop "$OPENARMS_ISAAC_ROOT/workshop" \
  --output "$OPENARMS_EVIDENCE_ROOT/skill-trial-001" \
  --allow-unvalidated-transfer
```

The experimental opt-in is required until a transfer is runtime-qualified.
There is one simulator lock per evidence root; integration must use the same
root for all student sessions. `recording/events.jsonl` reports request ID,
SIMULATED provenance, phases, observation completion and process completion.
`result.json` follows the application's execution-result fields; physical success
is always null. Send SIGTERM to the skill process for STOP; it requests simulator
interruption and escalates to process-group termination after 30 seconds. Each
new invocation creates a new stage/reset and refuses to reuse an output directory.
The interface, lock and STOP mechanism remain host-side implementation until
verified against an actual running simulator; they are not physical-robot APIs.
