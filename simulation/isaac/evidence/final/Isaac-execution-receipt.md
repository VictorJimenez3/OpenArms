# OpenArms — verified Isaac 5.1 manipulation and science

**Completed:** authentic white, camera-free SO-101 grasp-and-place on a Rutgers RTX A6000, a two-condition mass-versus-weight experiment, and a tested simulation-only skill interface. Both final trials recorded 720 frames / 24 seconds and exited zero. Each invocation created a fresh scene/reset. No physical robot, calibration, or MuJoCo was used.

## Open the evidence

| Condition | Actual video | Execution receipt | Student result | Raw log |
| --- | --- | --- | --- | --- |
| 10 g | [Play](evidence/job-1273420-light-20261114T153654Z-3955123/recording/camera.mp4) | [Receipt](evidence/job-1273420-light-20261114T153654Z-3955123/recording/receipt.json) | [Result](evidence/job-1273420-light-20261114T153654Z-3955123/result.json) | [Startup](evidence/job-1273420-light-20261114T153654Z-3955123/startup.log) |
| 40 g | [Play](evidence/job-1273420-heavy-20261114T153817Z-3955121/recording/camera.mp4) | [Receipt](evidence/job-1273420-heavy-20261114T153817Z-3955121/recording/receipt.json) | [Result](evidence/job-1273420-heavy-20261114T153817Z-3955121/result.json) | [Startup](evidence/job-1273420-heavy-20261114T153817Z-3955121/startup.log) |

[Independent evidence review](evidence/final-independent-review.txt) · [Science comparison](science-experiment/report.md) · [Machine-readable comparison](science-experiment/report.json) · [Slurm accounting](evidence/slurm-1273420-accounting.log) · [Final invocation log](evidence/slurm-1273420-final-skills.log) · [Complete reviewer bundle](OpenArms-Isaac-evidence.zip).

Each recording directory also contains `execution.json`, `state.jsonl`, `events.jsonl`, `trial-configuration.json`, `first-frame.png`, and the actual flattened `scene.usda`. The bundle includes these raw artifacts and the source Git bundle. Relative evidence links work when extracted together. Absolute paths in original receipts retain execution provenance; they are not rewritten.

## Execution identity

- Source commit: **`6afba01407b8036a0a22d5d8d6f261ac26424051`**, clean checkout. Feature branch `codex/isaac-runtime`, [PR 17](https://github.com/VictorJimenez3/OpenArms/pull/17); no push to shared main.
- Slurm allocation **1273420**, host **rlab7.cs.rutgers.edu**, allocated RTX A6000 UUID **`GPU-54287caa-e189-5677-f348-761437529e82`**, driver **580.178.04**, reported VRAM **46068 MiB**. Final two skills ran in step **1273420.2**, completed `0:0`.
- Isaac distribution **5.1.0.0**, isolated Python 3.11 environment at `/freespace/local/jdr317/openarms-isaac-5.1.0`; headless RTX rendering. Preflight logs record OS, kernel, memory, driver, allocation and runtime paths.
- Final light run started **2026-11-14 15:36:54 UTC**, heavy **15:38:17 UTC**. Both finished successfully. The holding allocation was then deliberately cancelled early to free the GPU; its parent `CANCELLED` status is not a failed simulator step. All three execution steps completed `0:0`.
- NVIDIA workshop commit **`ce807d99724cb65671abec01f908a2fcb4a6eab7`**. Asset `SO-ARM101-USD-NO-CAMERA.usd`, SHA256 **`71a03dd530e8dff75fd6de0cb4aacbb31653395fb01d9af835853f84841d4c77`**. Original articulation/collider assets and upstream licensing retained.

Video SHA256:

- Light: `2636cd20205cfb6d92748caeb56068d9c58cbd52bf4b97a535bb6a8866dcdada`
- Heavy: `7caa23716eb3bf2676d3a55b3d246f0ee243c80bc807f07835ac9161ce054b7c`

## Scene and measured success

Meters, Z up, gravity 9.81 m/s², physics 120 Hz, external camera 30 fps / 960×720 H264. White printed plastic `(0.95,0.95,0.95)`, dark motors, no onboard camera. A dynamic 20 mm block starts at `(0.23,0,0.01)` m and is placed in a fixed tray with target center `(0.20,0.10,0.014)` m. Robot movement uses joint drive targets. There are no post-reset object pose writes, parenting, welds, or attachments.

All active colliders use 0.5 mm contact offsets, zero rest offsets and zero added torsional-patch radii. Raw contact points, normals, normal forces and separations are recorded. During the heavy trial's hold/carry, loaded contacts (>0.001 N) had separation ranges approximately −0.081 to −0.021 mm for the gripper and −0.518 to −0.048 mm for the jaw. These are simulator contact-model measurements, not real-material calibration.

Acceptance requires both finger-body forces above 0.05 N, at least 40 mm lift sustained for 0.25 seconds, no sustained contact loss before release, arrival in the tray, upright support, release, over 50 mm retreat, and at least one continuous second below 0.01 m/s and 0.1 rad/s. The final heavy block center was approximately `(0.199883,0.100775,0.0139999)` m, gripper distance 64.0 mm, and settled duration 2.867 seconds. First, held, and placed frames were visually inspected; videos contain the actual Isaac render.

The prior corrected light/heavy pair at commit `002e9a7cbd7f60f7cbd763369881dd0c34922d29` also passed in steps 1273420.0 and .1. The final skill pair repeats the reset and manipulation through the integration entry point. These bounded runs do not establish physical-robot readiness or broad reliability.

## Student-controlled science and integration

Students choose **10 g** or **40 g**. Motion, geometry, friction, gravity, receiver and acceptance rules stay fixed. The measured quantity is signed upward tray normal force over the final closed one-second settling window: **121 contiguous raw samples per condition**. No failed samples are discarded. Normal-contact telemetry is not a complete tangential friction force balance.

| Mass | Measured mean support force | Separately calculated prediction `m*g` |
| ---: | ---: | ---: |
| 10 g | 0.098099999 N | 0.0981 N |
| 40 g | 0.392399992 N | 0.3924 N |

The measured force ratio is approximately **4×**. The report verifies artifact hashes, successful external exits, finite continuous data, settling and identical controls. Analytic predictions are explicitly distinguished from simulated measurements. No chemistry or liquid model is implied.

The existing canonical request envelope is preserved:

```json
{"request_id":"student-trial-001","session_id":"student-session-001",
 "skill_id":"isaac.mass_weight.light.v1",
 "parameters":{"object":"sample","source":"A","destination":"B"}}
```

Select `isaac.mass_weight.heavy.v1` for 40 g. `known_station_transfer.v1` provides the bounded 10 g transfer. The tested process interface writes `result.json`/stdout with SIMULATED provenance, measured values, separate predictions and evidence links; `physical_success` is always null. Phase/completion events stream to `recording/events.jsonl`. The application retains confirmation and request deduplication. Registration as an application backend is an integration step, not claimed completed here.

STOP is SIGTERM to the skill process. A real earlier experimental run was stopped through this interface and returned `stopped`, preserving its partial recording. The interface never imports physical robot control.

## Reproduce

Clone the supplied source bundle or repository into an isolated checkout and select the exact execution commit:

```bash
git clone source/OpenArms-runtime.bundle OpenArms
cd OpenArms
git checkout --detach 6afba01407b8036a0a22d5d8d6f261ac26424051
```

Use an approved Linux RTX allocation and isolated Isaac 5.1 installation. On a fresh Rutgers environment, run `simulation/isaac/bootstrap.sh` and `prepare_assets.sh` in approved installation jobs after accepting NVIDIA's EULA. Fetch real workshop Git LFS assets. The verified environment is node-local on rlab7; do not launch GPU work from a login node.

```bash
export OPENARMS_ISAAC_ROOT=/freespace/local/jdr317/openarms-isaac-5.1.0
export OPENARMS_EVIDENCE_ROOT=/common/users/jdr317/openarms-isaac/evidence
sbatch --partition=unlimited --nodelist=rlab7 -G a6000:1 \
  --mem=32G --time=00:15:00 --job-name=openarms-mass-light \
  --output="$OPENARMS_EVIDENCE_ROOT/slurm-%j.log" --export=ALL \
  simulation/isaac/skill_job.sh light
# Repeat with heavy, retaining the exact source/configuration.
```

Actual final invocation inside the existing allocation:

```bash
srun --jobid=1273420 --overlap --ntasks=1 \
  env OPENARMS_ISAAC_ROOT=/freespace/local/jdr317/openarms-isaac-5.1.0 \
      OPENARMS_EVIDENCE_ROOT=/common/users/jdr317/openarms-isaac/evidence \
  bash -c 'cd /common/users/jdr317/openarms-isaac/code-skill-6afba01 &&
           bash simulation/isaac/skill_job.sh light &&
           bash simulation/isaac/skill_job.sh heavy'
```

Use your new job ID when repeating. The wrapper creates a unique request and fresh stage each time. Its default sensor/viewport teardown completed cleanly in these Rutgers trials. Each raw receipt records the exact child command. To re-audit the downloaded recordings without Isaac:

```bash
python3 -m simulation.isaac.experiment_report \
  --light /absolute/light-run/recording \
  --heavy /absolute/heavy-run/recording \
  --output /absolute/new-comparison
```

## Preserved failures and temporary-host restoration

- Earlier Rutgers jobs [1273056](evidence/job-1273056) and [1273070](evidence/job-1273070) recorded articulation but crashed during shutdown (139 / native −6). They are not clean job successes.
- Native IGVC RTX 3060 / driver 595 attempts failed during Isaac startup. The user declined a host driver replacement; none was performed.
- The authorized temporary passthrough VM used guest driver 580. Its first attempt lacked `libGLU.so.1` and failed to render; that failure remains in [temporary-VM evidence](evidence/temporary-vm).
- A first manipulation trial stopped at 13.19 s on NumPy boolean JSON serialization. The fix did not relax physics acceptance.
- An earlier complete manipulation used oversized Cuboid contact defaults. It is superseded by the corrected millimetre-scale contact runs, not represented as the final qualified model.
- Both corrected VM conditions passed. The VM was shut down. [Restoration log](evidence/temporary-vm/restoration.log), [cleanup log](evidence/temporary-vm/final-cleanup.log), and [final verification](evidence/temporary-vm/final-verification.log) establish original host driver **595.99.02**, exact GPU UUID, original GPU/audio bindings, console state and active GDM/persistence services. A queued NVIDIA device-event loop required a temporary `/run` rule override; the override was removed and the queue settled. Restoration verified at **15:40:40 UTC**.
- VM disks, ephemeral access key, controllers and timers were removed. All 18 task-installed VM packages were removed; normalized package-name inventories match the original 3,095 entries. No host reboot or driver replacement was needed. Evidence and the separately isolated Isaac installation remain available.

Synthetic unit checks support implementation correctness; they are not substituted for any execution claim above. Full historical failures remain in the outputs evidence directory; the compact reviewer bundle focuses on the final runs and restoration proof.
