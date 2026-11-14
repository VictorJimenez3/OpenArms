# Compile an inspectable taught-water candidate

This module exports demonstration evidence for the integrator. It does not add a second conversational skill registry, activate a skill, import LeRobot, or call a hardware connector. The integration lane owns `agentic/openarms_lab/skills.py`; its promotion and dispatch API remains separate.

The compiler reuses `pour_once.preflight`, `catalog.expand`, `validator.validate`, `PoseArm`, and `FakeRobot`. It checks the original recorder's water checkpoints against saved poses and commanded grip, then executes the existing `add_sample(A,C,1)` expansion on a fake arm. This verifies software compatibility, not collision clearance, grip, water delivery or repeatability. The existing [wet-lab protocol](../docs/WET_LAB.md) and [research index](../research/README.md) remain the physical evidence references.

## Run

From the repository root, use the isolated bench-vision Python environment:

```sh
python -m bench_vision.skills compile \
  --poses /path/to/episode/poses.json \
  --trace /path/to/episode/joint_trace.jsonl \
  --summary /path/to/summary/summary.json \
  --context bench_vision/examples/skill-context.json \
  --out /path/to/candidates
python -m bench_vision.skills verify /path/to/candidates/VERSION.json
python -m unittest bench_vision.tests.test_skills -v
```

The example context is **synthetic**, with broad fake-arm limits. For an actual recorded take, supply its actual calibration limits and stable setup identities. Never replace the physical calibration with this example. The compiler needs the named `HOME, open, ABOVE_A, GRASP_A, cup, ABOVE_C, TIP_C, finish` checkpoints plus samples; a pose-only mandarin take is not a water demonstration.

Python API:

```python
candidate = compile_candidate(poses, trace_rows, episode_summary, context, baseline=None)
path = write_candidate(candidate, candidate_directory)
```

`episode_summary` is the capture lane's schema version 1: `episode_id`, explicit `provenance`, `phases` with `name/t/views`, and an `outcome`. `telemetry_time_offset_s` is the explicit offset added to raw trace times for episode alignment (defaults to zero). Missing camera frames remain explicit in the candidate; they do not become successful observations. Each reported non-unknown outcome requires independent evidence entries with `provenance`, `reference`, and `observer`. The fake validation result always keeps `physical_outcome: unknown`.

Each artifact contains the original pose snapshot, fixed plan and expanded phases, setup preconditions, source hashes, checkpoint times, selected visual evidence, geometry assumptions, fake validation result, independent outcome evidence, and retained rollback snapshot. Its complete payload determines a 64-character SHA256 version. Writing the same version is idempotent; altered files cannot be overwritten. Content hashes detect drift but are not signatures or proof that human-supplied evidence is authentic. Original videos, raw traces and calibration receipts must remain alongside their episode.

## Retain a baseline and roll back

For a revised candidate, add `--baseline /path/to/retained/VERSION.json` when compiling. The complete baseline and its poses are retained inside the new candidate. Compilation never overwrites the baseline or the live pose file.

```sh
python -m bench_vision.skills rollback /path/to/new/VERSION.json \
  --out /path/to/rollback-review.json
```

The rollback receipt exports the original poses and their hash for integrator review. It makes no live change. The sole integrator chooses whether a reviewed version belongs in the existing runtime, and any physical execution still uses the original operator and HOME checks.

## Bounded source-position preview

`preview_adaptation(candidate, observation, current_context, now_s)` returns `rejected` with reasons, or `geometry_preview_only`. Both return `motor_targets: null`. A successful preview identifies a bounded tabletop target; it is not an adapted trajectory. No empirical joint correction map, matched Hiwonder FK/IK model or held-out dry-cup relocation evidence was available to this lane. Those remain blockers to generating motor targets.

The observation boundary is:

```json
{"status":"ok","object_id":"source-cup","camera_id":"overview","timestamp_s":200.0,
 "calibration_id":"measured-cal-v1","camera_mount_id":"fixed-pair-v1",
 "clock_id":"host-boot-identity","coordinate_frame":"measured-table-plane","units":"mm",
 "feature":"table_contact","xy_mm":[105.0,103.0],"uncertainty_mm":0.4,
 "provenance":"recorded"}
```

`now_s` and `timestamp_s` must use the same episode/host clock. The candidate context must retain identical calibration, fixture, cup, camera mount and robot IDs. Its `geometry` must contain:

- `status: validated`, `units: mm`, `feature: table_contact`, `camera_id`, `object_id`, `clock_id`, and the exact `coordinate_frame`/plane ID.
- Taught `source_xy_mm`, actual `grip_height_mm`, a measured `supported_region_mm` with `min/max`, `max_source_shift_mm`, and `max_total_error_mm`.
- `validation` with `provenance: physical`, `independent: true`, `held_out_count` of at least three, `max_error_mm`, and the validation `receipt` reference.

The preview rejects a different camera, changed setup, unknown/stale/future observation, cup-rim or box-center feature, missing physical held-out checks, missing two-camera teaching evidence, and targets whose uncertainty extends outside the tested region or shift limit. It adds localization uncertainty to the measured maximum residual. This is a conservative declared error bound, not a calibrated probability guarantee. Camera motion must change the mount identity or invalidate the geometry upstream; an unchanged string cannot prove that a physical camera stayed fixed.

```sh
python -m bench_vision.skills preview /path/to/candidates/VERSION.json \
  --observation /path/to/observation.json --context /path/to/current-context.json \
  --now-s 200.1
```

Exit 2 means rejected. Exit 0 means only a geometric preview is available. Receiver approach, tip, recovery and HOME remain untouched. Source pickup/return adaptation needs an independently evaluated controller, current robot-base registration, reachability/clearance validation and supervised dry then loaded trials. Training/policy candidates, automated evidence review, richer phase composition and physical promotion remain deferred, not removed.
