# Export boundary for the single integrator

This package is an offline producer. The other worktree owns `agentic/openarms_lab`, `ui/lab`, Gemini voice, its notebook and registry. No change here adds a dispatch path, edits those files, or silently registers `add_sample` as a conversational skill.

## Concrete data flow

1. Existing supervised `openarms capture water` produces `poses.json` and a `demo-water-*.jsonl` trace. Camera capture is separate and imports no motor module. After the recorder exits, `capture finalize` copies the trace into the episode once.
2. `keyframes` emits `summary.json`, a browser-readable contact sheet, selected raw images and hashes. Phase timestamps are in the manifest clock; `raw_trace_t` and `telemetry_time_offset_s` preserve the trace mapping.
3. `skills compile` verifies checkpoint values, phase/event correspondence, explicit setup identities and limits; it runs the existing `add_sample(A,C,1)` expansion on `FakeRobot` and emits a hash-versioned **offline candidate**. It retains the source pose file and baseline snapshot.
4. The integrator can display candidate phases, missing/stale evidence, outcome status and revision history using the existing UI. Selection/import into its registry is a separate reviewed change. The current conversational lane's mandarin A/C→B transfer and modeled dilution are not this physical A→C pour.

For the offline fixture, one candidate contains:

```json
{
  "schema_version": 1,
  "skill_id": "bench.add_sample.A.C",
  "status": "candidate",
  "execution": "offline_only",
  "controller_ref": "firmware.openarms_executor.pose_arm:PoseArm",
  "plan": {"plan_id":"bench-pour","steps":[{"action":"add_sample","args":{"source":"A","into":"C","portions":1}}]},
  "episode": {"id":"synthetic-cup-demo-v1","provenance":"synthetic"},
  "outcome": {"status":"unknown","evidence":[]}
}
```

This is an abbreviated example, not a complete loadable candidate. Use the generated `candidates/*.json` for the full hash-bound artifact. `receipt.json` resolves its paths. Image paths within the embedded episode summary are relative to the summary directory, not the candidate file; retain the whole output bundle. Image/source hashes detect later asset changes but are not signatures.

## Perception is evidence, not a motor action

Detector observations carry object/camera/frame IDs, timestamp or explicit legacy `null`, calibration ID, box/mask or unknown, pixel-feature meaning, method and confidence. `geometry_valid:false` and `grasp_pose:null` are deliberate. A camera observation must pass measured geometry checks before the separate adaptation validator can consider it.

Metric observations carry `timestamp_s`, `clock_id`, `coordinate_frame`, `units:"mm"`, `calibration_id`, `camera_mount_id`, `feature:"table_contact"`, `xy_mm`, `uncertainty_mm` and provenance. Unknown, mismatched or stale observations stop preview. A geometric preview never changes receiver, tip or HOME phases and never authorizes hardware.

## Ownership audit, 2026-11-14

Read-only inspection found integration branch `codex/software-integration` at `7b5d98a`, with uncommitted `README.md`, `docs/INTERFACES.md` and `docs/LAB_RUNBOOK.md`. Its last recorded external CLI turn completed at 07:12:42 America/New_York; no dedicated running CLI worker was found at inspection. The desktop task list did not expose that external session. This was a point-in-time observation, not abandonment of ownership. At the user’s subsequent request, inactivity was checked again; 378 tests and the provider-free demo passed independent review. The preserved documentation was committed as `b49d399`, and that branch was fast-forwarded into local `main`. Remote main was not pushed. Its claimed 355-test result was not rerun by this package.

No capture, camera geometry or water demonstration compiler overlapped those files. Keep shared `docs/INTERFACES.md` changes with that owner. This document supplies the concrete handoff without overwriting their in-progress interface notes.
