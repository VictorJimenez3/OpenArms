# Offline SO-101 kinematics preparation

`kinematics.py` requires Python, `usd-core`, NumPy and SciPy, without Isaac,
GPU, MuJoCo or hardware. Evidence below used Python 3.11.14, usd-core 26.11,
NumPy 2.4.6 and SciPy 1.17.1 on 2026-11-14. The workshop checkout was verified
at `ce807d99724cb65671abec01f908a2fcb4a6eab7`, with resolved LFS assets.
Asset: `source/sim_to_real_so101/assets/usd/SO-ARM101-USD.usd`, SHA256
`11f5f0bb5f2fae3eefebbcd07dfafc6b14602f6c4e5dae8f21a4a46892991006`.
The loader validates structure/conventions; the caller must pin asset provenance.

## Interface and conventions

```python
from kinematics import Model
model = Model.from_usd(asset_path)
# Also accepts an authored Usd.Stage and prim_path='/World/Robot'.
seed = [-.2736, -.6109, -.0745, 1.5148, -1.6034, -.1465]
pose = model.fk(seed)                  # world nominal grasp-center frame
q, report = model.solve([.23, 0, .025], [0, 0, -1], seed)
if q is None:
    raise RuntimeError(report)         # never command a rejected solution
body_frames = model.body_poses(q)      # world transforms keyed by USD body path
```

Six-element q order: `Rotation, Pitch, Elbow, Wrist_Pitch, Wrist_Roll, Jaw`.
All q and angular residuals are radians; positions are meters. Matrices use
column vectors, unlike USD's row-vector `Gf.Matrix4d` convention. The stage
must be meters/Z-up. Rotations are positive right-handed rotations about each
USD joint axis. The recurrence is `W_child = W_parent @ J0 @ R(q) @ inv(J1)`;
joint quaternions are normalized to remove float-authoring norm error. Limits
come from USD degrees converted to radians. Base pose includes authored ancestor
transforms; `/so101_new_calib` already has an authored rotation. Do not add a
second copy of that rotation when referencing it into a runtime scene.

`fk` deliberately returns the **nominal grasp frame**, with gripper body axes
and an offset estimated from colliders. For the raw gripper body transform use
`body_poses(q)[model.gripper_path]`. `model.tool_axis_local` is gripper **-Z**,
pointing from the wrist toward the fingertips. Jaw changes its own body pose,
but does not move this fixed nominal TCP. IK holds Jaw at `seed[5]`.

IK uses bounded least squares on xyz plus unit-direction residuals (3+2
constraints), with a 0.1 m direction weight and weak 10 um/rad seed prior.
Defaults require <=1 mm position and <=0.02 rad direction error plus successful
optimizer termination. Reports expose both residual vectors, their norms and
evaluation count. Invalid/out-of-limit inputs raise `ValueError`; failed solves
return `None, report`. No arbitrary 6D orientation is requested. Local -Z is
nearly coaxial with Wrist_Roll, so roll is redundant for this TCP/direction;
the seed prior retains it. Task rank can drop; a five-joint arm does not guarantee
every xyz/direction pair. Failure can mean unreachable **or** a local solver miss.

## Geometry uncertainty

Collider meshes are inside instance proxies; traversal explicitly includes them.
For each finger body, vertices in its distal 10 mm slab along gripper -Z are
bounded in gripper coordinates. The midpoint between opposed inner X surfaces
and overlapping Y/Z ranges gives approximately `(0, 0, -0.100)` m, rounded to
1 mm. At authored Jaw=0 the geometric inner gap is about 15.8 mm. Fixed and
moving distal Z extents reach approximately -104.4 and -105.4 mm respectively.
`geometry_evidence` retains mesh paths and raw slab bounds for inspection.
Rounding is not an accuracy specification: collider approximation, real contact
surfaces, changing Jaw angle and object size can move the actual grasp center.
The candidate Jaw values below are inherited seeds, not grip/opening commands.

## Offline results and reproduction

```sh
python simulation/isaac/test_kinematics.py --asset /absolute/path/to/SO-ARM101-USD.usd -v --evidence
```

All **11 tests passed**, including 40 deterministic random seeded roundtrips,
positive/negative joint-axis conventions, collider proxy discovery, transformed
root references, limit/invalid-input rejection, unreachable and incompatible
direction targets, exhausted optimizer rejection and deliberate zero-frame
corruption. At q=0, all seven body poses agree with authored USD within
**1.64e-8 m / 6.68e-8 rad**. These are model consistency residuals, not accuracy
or control tolerances. `--evidence` prints asset hash, geometry, zero errors,
full q vectors and residuals as JSON, without writing files.

All six sequential candidates below solved with world tool direction `(0,0,-1)`.
World coordinates apply to the asset's authored placement. q is rounded here;
use the solver or printed JSON for full precision. All rows retain
`Wrist_Roll=-1.6034, Jaw=-0.1465` rad. Initial seed is the example above.

| Candidate | xyz (m) | Rotation, Pitch, Elbow, Wrist_Pitch (rad) | position error (m) | direction error (rad) |
| --- | --- | --- | --- | --- |
| Initial hover | .23, 0, .08 | .099293, .140283, .013545, 1.416975 | 6.00e-10 | 1.36e-6 |
| Source | .23, 0, .025 | .099292, .282887, .243355, 1.044561 | 4.56e-10 | 1.36e-6 |
| Source lift | .23, 0, .08 | .099293, .140283, .013545, 1.416975 | 4.90e-10 | 1.36e-6 |
| Receiver hover | .20, .08, .08 | -.323885, -.044845, .244766, 1.370880 | 4.78e-10 | 1.49e-6 |
| Receiver | .20, .08, .025 | -.323885, .122363, .472516, .975923 | 4.63e-10 | 1.48e-6 |
| Receiver retreat | .20, .08, .08 | -.323885, -.044845, .244766, 1.370880 | 4.67e-10 | 1.49e-6 |

These are reachable endpoint candidates for a small cube and flat receiver.
No path, table/receiver clearance, self-collision, actuation, contact, friction,
grip, dynamics or runtime success was tested. Existing scope guidance also
requires mapping reach/orientation and actual clearance before manipulation:
[laboratory feasibility note](../../research/victor/laboratory-experiments-and-feasibility.md#3-so-101-feasibility-findings).

Before controller use, the runtime owner must compare **measured** body world
poses and measured q using `compare_body_poses(q, measured)`, at zero and multiple
nonzero configurations including separate single-joint sign checks and Jaw.
Construct the model from the authored stage before stepping; do not reload a
moving articulation as though it were its zero pose. Convert runtime transforms
to column-vector 4x4 matrices and map referenced body paths consistently. Static
zero agreement alone cannot establish runtime joint signs. Review residuals and
contact geometry before any grasp claim. This module is preparation, not certified control.
