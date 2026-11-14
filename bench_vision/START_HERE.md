# Start here: bench vision and teaching tools

**What runs:** two-camera capture/replay aligned to the existing joint trace; nine event-selected phase views; image-grounded review; guarded camera/table mapping; immutable demonstration candidates, observed-outcome receipts and rollback; optional local source-pose interpolation; actual pretrained GPU comparisons and policy preflight. Motor, calibration, conversation, UI and simulation implementations were not replaced.

**What is not qualified:** real camera capture, actual-cup handling, pouring, unseen-position pickup and physical policy execution. No arm or camera was actuated during this work. The complete runnable teaching example is explicitly synthetic.

## Run in a fresh checkout

```sh
python3.12 -m venv outputs/bench-env
outputs/bench-env/bin/pip install -r bench_vision/requirements.txt pytest==8.4.2
outputs/bench-env/bin/python -m bench_vision demo --out outputs/bench-demo
outputs/bench-env/bin/python -m pytest bench_vision/tests -q
```

Open `outputs/bench-demo/summary/index.html`. Inspect `receipt.json`, `candidates/*.json`, `rollback.json`, `geometry.json`, and `adaptation.json`. Use a new directory per run. Optional source-map experiment:

```sh
outputs/bench-env/bin/python -m bench_vision adaptation synthetic --out outputs/source-map.json
```

## Actual measurements

- Synthetic replay: **81 overview + 78 side frames**, 89 trace rows, nine phases, 18 selected views. Three deliberate side-view drops produce two stale matches and a 400 ms maximum gap. Receipt timestamps show 12/27 ms median alignment skew; this does not establish hardware exposure synchronization.
- GPU comparison: Grounding DINO tiny localized **10/12 positive cases**, HSV and SSDLite **1/12**. False positives on four negative cases: DINO **0**, HSV **1**, SSDLite **0**. DINO warm local end-to-end latency **1.60 s median / 1.80 s p95**. Keep it for offline/keyframe review. Four original mandarin images plus correlated transformations and provisional agent-drawn boxes are not actual-cup qualification. [Full methods, exact revisions and receipts](MODELS.md).
- Synthetic affine source-map experiment: four fit placements, two held-out placements; ~`7.1e-15°` maximum target error versus `0.95°` for unchanged poses. This intentionally affine fixture tests implementation, not real generalization. Receiver, tip, HOME and gripper settings remain unchanged; all proposals remain offline.
- Unit, integration and existing fake-executor checks are recorded in [validation receipt](evidence/validation.json). An additional parent-run GPU check reproduced detections on the four original frames; cold-start timings were slower and are kept separately rather than substituted for the repeated warm benchmark.

## Shortest human path to teaching the actual cup

1. **Fix the apparatus once.** Mount the actual source cup/receiver in the tray and the two external cameras. Verify camera serial/labels against device selectors. Retain the working motor environment, calibration, HOME and physical stop. Use the taught fixed fixtures first; metric camera calibration is not required for this initial route.
2. **Record one supervised empty-cup take.** Start the camera-only command in [CAPTURE](CAPTURE.md), then run the existing `openarms capture water` in the bench environment. After both finish, attach the printed joint trace with `capture finalize --recorder-finished --same-host-clock`. Generate the contact sheet and compile using actual fixture/cup/calibration identities and limits, not the synthetic context example. Exact compiler command: [SKILLS](SKILLS.md).
3. **Observe dry, then water.** Use the existing supervised `openarms pour dry`, then one small pre-measured water portion when dry behavior is acceptable. Record grip/clearance, delivery, spills, cup return and HOME/reset independently. [OUTCOMES](OUTCOMES.md) attaches the existing receipt and explicit observer checks; controller completion alone stays unknown. Compile the reviewed revision with `--baseline` so rollback is retained.

Only after that route is qualified, collect real undistorted plane correspondences (≥4 fit + ≥4 independent check points), table-to-robot registration, actual cup grip geometry and source placements with separate held-out trials. The optional [source-map tool](ADAPTATION.md) can then propose bounded source poses for review. Dry and loaded supervised evaluation remain separate; no automatic promotion occurs.

## Specific blockers and retained work

- **Actual cup and aligned footage:** not present in the inspected saved inputs. Existing mandarin photos have unknown camera IDs/timestamps, so they cannot be aligned retrospectively by guesswork.
- **SAM 3:** anonymous config/weights requests returned HTTP 401; approval and an appropriate CUDA environment remain unverified. Grounding DINO ran on the available Apple M2 GPU. No project-specific Blackwell endpoint was supplied or tested.
- **MolmoAct2:** public SO100_101 config and normalization downloaded; exact camera arrangement and Hiwonder joint units/signs/offsets are unverified. The checker rejects deployment. No policy training/inference ran; ACT/SmolVLA await aligned actual-task episodes and held-out positions.
- **Relocation:** no real validated empirical source map, actual grip geometry or robot-base registration. Synthetic previews cannot qualify physical execution.
- **Integration:** the other branch’s conversational registry owns student dispatch. This package exports evidence and candidates at [INTERFACE](INTERFACE.md); physical water A→C is not silently equated with its modeled dilution A/C→B. Isaac remains independently owned. Segmentation, richer summaries, learned routing, more phases, policy training and broader trials remain deferred, not removed.

## Integrator handoff

Branch: `codex/bench-vision`. All new tooling is under `bench_vision/`; one research-index row links this handoff. Each implementation lane used its own branch/worktree and was reviewed before integration. No motor/calibration files were changed. The other worktree’s UI/voice build was independently checked and merged into **local main at `b49d399`** on the user’s request; its prior uncommitted docs were preserved, and the unrelated local AGENTS edit was retained. Remote main remains unchanged. Bench tooling is reconciled with that local main and handed over as a separate reviewed branch/bundle.
