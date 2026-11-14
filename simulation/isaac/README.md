# Isaac 5.1 runtime lane

Status: preparation and installation in progress; **no verified Isaac execution,
manipulation, experiment, or simulation video yet**. Track the compute blocker in
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

Next use one workshop vial and one rack, with deterministic initial poses and
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
