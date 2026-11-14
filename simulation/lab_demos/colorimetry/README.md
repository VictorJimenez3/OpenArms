# SO-101 colorimetry comparison

Run from the repository root with the shared simulation environment:

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  python \
  simulation/lab_demos/colorimetry/run.py \
  --output-dir simulation/lab_demos/colorimetry/evidence --speed 2
```

Use `--negative-control` to disable the reference pickup. The reader's measurement gate then remains closed for that vial and the comparison is withheld. `--speed` controls playback acceleration relative to simulation time; the report retains the MuJoCo elapsed time. Output contains a 1280×720 MP4, first/middle/last PNGs, contact sheet, quantitative summary, events and joint trace.

The deterministic policy controls the bundled SO-101's five position actuators and gripper, advances the model with `mj_step`, and uses current joint/site state to align the gripper. A pick/re-pick needs the end-effector site within the geometric engagement tolerance. After engagement, the upright vial follows the grasp site as a mocap object; this is a simplified grasp attachment, not contact-force or slip simulation. A measurement is emitted only after the vial reaches the reader slot tolerance. The final return leaves both vials on their marked starting stations and the arm at home.

## Science model

The analytical teaching prediction uses Beer-Lambert, `A = ε c l`, with `ε = ln(10) L mol⁻¹ cm⁻¹`, 1 cm path length, and illustrative concentrations 0.30 and 0.52 mol/L. These assumptions make `A` increase with concentration; they are not a calibrated dye system. Separately, the photometer display reports a bounded optical-density proxy derived from the colored vial's RGB material values. This second value is a rendered-material sensor proxy, not a physical photometer or a camera pixel measurement. The two outputs intentionally represent analytical prediction and rendered sensor-side observation separately.

## Limits

The robot geometry is the repository's original licensed SO-101 asset. Joint and fixture poses are illustrative and are not calibrated against hardware. The vials are mocap fixtures, grasp success uses a geometric threshold, the reader has a geometric placement gate, and the RGB sensor proxy uses material color under synthetic lighting. No physical robot commands are sent. This run does not validate real grasping, force, sample chemistry, instrument calibration, or camera colorimetry.
