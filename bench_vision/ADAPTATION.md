# Offline empirical source-map experiment

This optional experiment predicts **absolute source poses** from measured source XY. It changes only `ABOVE_A` and `GRASP_A` in a copied pose file; the existing executor uses those same poses to return the cup. Receiver approach, `TIP_C`, all other station poses, HOME and gripper values remain exactly equal to the retained baseline. No registry entry, calibration file, motor software or live pose file is changed.

This is a local empirical affine map, not inverse kinematics or a general Cartesian servo offset. Independent training placements must share the actual robot, joint convention, calibration, fixtures, cup and camera/robot-base registration. The held-out comparison measures joint-target prediction error against separately taught source poses. It does not measure grasp success, collision clearance or water delivery.

## Run the synthetic software check

Use the separate vision environment, from the repository root:

```sh
python -m bench_vision.adaptation synthetic --out /path/to/affine-synthetic-receipt.json
python -m unittest bench_vision.tests.test_adaptation -v
```

The receipt contains the full constructed input, model, held-out comparison, observation and fake-executed proposal. Four constructed training placements and two distinct held-out placements follow an exactly affine formula. Therefore a near-zero affine error is expected by construction; it is **not evidence of physical benefit** or a real policy benchmark. The retained constant-pose baseline is evaluated on the exact same held-out positions and joints. Synthetic evidence always blocks a physical recommendation, even if a caller labels the query image physical.

## Fit actual supplied measurements offline

```sh
python -m bench_vision.adaptation fit /path/to/source-map-spec.json \
  --out /path/to/source-map-model.json
python -m bench_vision.adaptation propose /path/to/source-map-model.json \
  /path/to/localized-source.json /path/to/current-setup.json \
  --now 1234.5 --out /path/to/source-pose-proposal.json
```

Output files are exclusive writes; existing evidence is never overwritten. Exit 2 means the model or proposal was rejected. All proposals have `execution: offline_only` and `physical_authorization: not_granted`. A passing fake run is explicitly tagged `fake`.

The synthetic receipt supplies a complete schema example. A measured specification includes:

- `mapping_id`, `object_id`, `coordinate_frame`, `clock_id`, and `geometry_hash` (the exact calibrated-geometry artifact hash).
- `setup` IDs for calibration, fixture, cup, camera mount, robot, robot-base coordinate registration, and joint convention. Every ID must match the current setup at proposal time.
- Explicit units `{position: mm, arm_joints: deg, gripper: percent_0_100}`, actual joint limits, unchanged `baseline_poses`, and measured `baseline_source_xy_mm`.
- Positive maximum source shift, held-out joint error, target error and observation age; explicit `valid_from_s/valid_until_s` on the same clock.
- `training`: at least three distinct noncollinear source placements. Each has a unique `id`, a unique `episode_id`, a receipt reference, `xy_mm`, and complete five-joint `source_poses` for `ABOVE_A` and `GRASP_A`.
- `held_out`: at least two different placements, with IDs, episodes and XY disjoint from training. These must lie inside the training convex hull and declared shift bound. Reusing adjacent frames from a training episode is rejected.
- `provenance: physical_measured` only for actual measurements; otherwise `synthetic`. Receipt claims are retained, not authenticated by this tool.

The localized source observation must contain `status: ok`, the taught `object_id`, `feature: table_contact`, `xy_mm`, Euclidean error radius `uncertainty_mm`, `units: mm`, explicit provenance and timestamp, and matching calibration/mount/clock/frame/geometry identities. Root `geometry.localize` produces the geometric fields; retain its calibration hash as `geometry_hash`. The source-map tool never maps an elevated cup rim or box center directly to a grasp pose.

## Admission checks and limits

The fit centers and scales XY before least squares and rejects rank-deficient or ill-conditioned inputs. Training and held-out poses must be inside supplied calibrated joint ranges. Fit and held-out residuals must both stay below the declared tolerance.

Proposals reject extrapolation: the entire position-error disk must lie inside the measured training convex hull and source-shift bound. Each joint's affine sensitivity propagates that disk using the exact gradient norm; the larger measured fit/held-out residual is added. Targets and their error intervals must remain inside the supplied joint limits. The proposal then passes the existing pour preflight and executes the existing plan on `FakeRobot`.

The empirical residual is a measured sample error, not a guaranteed error bound between placements. More observations, mechanical compliance and path constraints can invalidate an apparently good affine fit. Actual geometry can also drift without its software ID changing; independently recheck the camera markers, cup and fixtures before use. The model does not grant permission to move, and the tool makes no unattended physical calls.

**Current blocker:** no actual cup source-position dataset or held-out physical relocation receipts were supplied. The synthetic receipt verifies the software path only. Before considering a real candidate, the operator must collect compatible source poses, verify current geometry and independently review the proposed approach/return joins. Supervised empty-cup trials precede loaded validation. The retained baseline remains available in every proposal for rollback review.

Implementation is original OpenArms glue using NumPy least squares (NumPy's BSD-3-Clause distribution) and the existing project pose executor. No external robot's kinematics or motor driver was copied. See the [skills compiler](SKILLS.md) and [wet-lab protocol](../docs/WET_LAB.md) for the separate candidate and physical evidence boundaries.
