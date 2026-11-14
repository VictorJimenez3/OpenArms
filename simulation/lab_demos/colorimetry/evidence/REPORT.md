# Colorimetry run report

## Successful comparison

- Actuated MuJoCo SO-101: 70.2 s simulation time, 1,080 rendered frames, 36 s H.264 playback at 1280×720 and 30 fps (2× playback setting).
- Both samples were grasped and correctly placed; both measurement gates opened. The full joint trace was finite and within configured limits.
- Reference: Beer-Lambert prediction `A = 0.6908`; rendered-material RGB proxy `A* = 0.5738`, RGB `(61, 140, 230)`.
- Unknown: Beer-Lambert prediction `A = 1.1973`; rendered-material RGB proxy `A* = 0.7400`, RGB `(46, 110, 209)`.
- The rendered sensor proxy reports greater attenuation for the unknown. The analytical predictions are separate and use the documented illustrative concentrations and path length.

## Negative control

With `--negative-control`, the reference pickup action was disabled. The reference remained unmeasured, the unknown still passed its placement gate, and the policy withheld a two-sample comparison. This run is intentionally reported as `success: false` because the complete comparison did not occur. See `negative-control-summary.json` and `negative-control-trace.json`.

## Limits

The vial grasp uses a geometric 18 mm engagement gate followed by a mocap attachment. The rendered RGB sensor is a simplified material-color proxy rather than camera pixel sampling or a physical photometer. Joint/fixture geometry is illustrative, not calibrated against hardware. No physical robot was commanded.

Parent integration review: reduced lighting glare, added the 2× playback label, checked finite/joint-bound state on every simulation step, and added an IK-state-preservation regression test. Positive video regenerated successfully (1080 frames / 36 s); negative-control evidence still withholds the reference measurement.
