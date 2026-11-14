# OpenArms bench vision

Runnable offline tooling for two-camera evidence, demonstration review, measured plane localization and versioned skill candidates. It reuses the existing joint recorder, action catalog, validator and pose executor. It does not start a robot, change calibration, register a live skill, or implement another student UI or simulator.

Start with [START_HERE](START_HERE.md) for results, the shortest actual-cup checklist and integrator handoff.

## Install independently

From the repository root:

```sh
python3.12 -m venv outputs/bench-env
outputs/bench-env/bin/pip install -r bench_vision/requirements.txt pytest==8.4.2
outputs/bench-env/bin/python -m bench_vision demo --out outputs/bench-demo
outputs/bench-env/bin/python -m pytest bench_vision/tests -q
```

Use a new output directory for each run. Open `outputs/bench-demo/summary/index.html`; inspect `receipt.json`, the two candidates, `rollback.json`, and rejected adaptation report. Everything in that demonstration is explicitly **synthetic**. Real camera capture is separately opt-in. Do not install model dependencies in the working LeRobot environment.

| Tool | Entry point / guide |
| --- | --- |
| Two-camera capture, immutable telemetry attachment, replay | `python -m bench_vision capture --help` · [CAPTURE](CAPTURE.md) |
| Alignment and event-selected evidence | `python -m bench_vision episode --help` / `keyframes --help` |
| Measured fixed-plane calibration and localization | `python -m bench_vision geometry --help` · below |
| Demonstration compiler, version verification, rollback | `python -m bench_vision skills --help` · [SKILLS](SKILLS.md) |
| Optional learned perception and GPU measurements | `python -m bench_vision benchmark --help` · [MODELS](MODELS.md) |
| Policy shape, normalization and data preflight | `python -m bench_vision policy --help` · [MODELS](MODELS.md) |
| Offline source-pose interpolation | `python -m bench_vision adaptation --help` · [ADAPTATION](ADAPTATION.md) |
| Independent observed-outcome receipts | `python -m bench_vision outcomes --help` · [OUTCOMES](OUTCOMES.md) |
| Integrator export boundary | [INTERFACE](INTERFACE.md) |

## Geometry: explicit measured plane, explicit unknown

The manual-click baseline takes measured fit/check points in an undistorted image and millimeters on one fixed plane. At least four fit points and four disjoint check points are required; no three check points may be collinear. The supplied intrinsic calibration ID, camera/mount ID, plane ID, clock identity, validation interval and measurement reference travel with the mapping. The code computes held-out residuals and rejects excessive residuals. It does not certify the authenticity of supplied physical measurements.

```sh
python -m bench_vision geometry fit bench_vision/examples/calibration-spec.synthetic.json \
  --out outputs/calibration.synthetic.json
python -m bench_vision geometry localize outputs/calibration.synthetic.json \
  bench_vision/examples/observation.synthetic.json --now 50.1
```

Every observation must include at least four current check anchors. The target and its uncertainty must lie inside both the declared workspace and independently checked anchor support. Re-observed anchors detect camera drift even when a mount ID was mistakenly unchanged. `uncertainty_px` bounds **each pixel axis**; the enclosing square is projected, rejecting a projective-horizon crossing. Reported uncertainty includes maximum measured check residual and current anchor discrepancy. This is a conservative declared error budget, not a statistically calibrated probability or a guarantee between measurements.

A `table_contact` feature must be at exactly the calibrated plane height. A detector's bounding-box center, an elevated rim, an unknown cup-bottom position, or a pixel in a distorted image is not accepted as a table feature. Outputs contain no grasp pose. Rigid camera mounting, real intrinsics/undistortion, measured table-to-robot registration, actual cup grip geometry, reachability and supervised dry trials remain necessary before relocation. The second view is complementary evidence, not automatic stereo triangulation.

## Attribution and provenance

New package code, fixtures, evidence compiler and comparisons were written for OpenArms. Existing OpenArms motion/validation code is imported, not replaced. Geometry uses the installed OpenCV library, following its [homography documentation](https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html); no AVA motor or IK implementation was copied. OpenCV is Apache-2.0; NumPy is BSD-3-Clause; pytest is MIT. Optional model source, exact versions/revisions and license notices are recorded in [MODELS](MODELS.md).

Requirements came from the team's [physical tooling assignment](https://app.notion.com/p/41871c9c107e81d3b516f9f759926517), [GPU experiment queue](https://app.notion.com/p/41871c9c107e8185977ce8c72365fcff), and [master workstreams](https://app.notion.com/p/41871c9c107e81d5b6fdfcb4ab71fdd5), read on 2026-11-14. Their proposed capabilities are requirements, not test evidence. Existing physical context remains in [WET_LAB](../docs/WET_LAB.md).
