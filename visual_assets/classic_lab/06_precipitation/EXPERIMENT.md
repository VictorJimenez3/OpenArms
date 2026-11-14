# Clear + clear → cloudy solid

**ART PREVIEW — the endpoint is illustrative.** Two initially clear liquids are compared with an equal-volume water control. A milky suspension and settled layer appear in the reactive beaker. The same black reference stripes remain visible through the clear control. This is one precipitation experiment with two prepared conditions.

The selected classroom reference is **calcium carbonate precipitation**: A represents aqueous calcium chloride and B represents aqueous sodium carbonate; the matched control replaces B with water. This is a conventional demonstration of forming a solid from dissolved reactants. [University of Colorado demonstration reference](https://www.colorado.edu/lab/lecture-demo-manual/general-reactions/s130-chemical-rxns-precipitation-cacl2-na2co3-caco3). The scene labels remain A/B for legibility. Its white material and particles illustrate the result; no reaction or transport model is implemented and no concentrations or calibrated yield are asserted.

## What the student changes

Replace the B dose with the same volume of water while holding the A dose, final volume, receiver geometry, mixing method, temperature, and observation interval constant. Both receiver beakers use identical dimensions and liquid fill depth. The dosing cups show remaining stock, not a simulated delivery mass balance. The two conditions are prepared side by side to make the difference immediately visible.

## High-level procedure

1. Prepare equal A portions in matched receiving beakers and select B or water as the comparison dose.
2. Deliver the selected dose using a qualified metering fixture; use identical mixing and observation intervals.
3. Compare the black reference pattern through each sample under the same illumination.
4. Record turbidity or calibrated optical transmission, and record settling separately. A cloudy appearance alone is not a calibrated solid fraction.

The scene stages the observed endpoint: **A + B: cloudy, visible illustrative solids; A + water: clear.** The white suspension, enlarged flecks, and sediment are artist-authored meshes/materials. They do not demonstrate an executed reaction.

## Apparatus and task interpretation

Open, thin-walled graduated beakers sit in matched locating seats on mixing stations with speed dials. Two suspended, open dosing vessels have identity plates, manual valve levers, glass delivery stems, and a braced stand. A white reference panel with black stripes provides a simple visual contrast target. A separate water bottle and stirring rod on a rest support the control workflow.

The illustrated dosing stems terminate above the reactive receiver. The control is already prepared; the asset does not contain an automated selector manifold. A runtime that prepares both conditions must add a selector or a qualified repositioning fixture. The mixing stations and valve handles are currently static geometry. The static robot pose does not imply contact or reach.

Robot base reference: (-0.05, 0, 0) m with no added yaw. The preview-only original SO101 mesh is translated to (-0.05, 0, -0.03008145) m and remains unscaled. The original white printed arm has no camera. The active receiver is at (0.235, -0.055) m, rim height 0.155 m. Elevated dosing fixtures, the control station, valve operation, and small-tool grasps need reach, collision, and controller qualification. Proposed 15 mm surrounding fixture clearance is an assumption, not a verified robot margin.

## What remains to make this executable science

- Calibrate equal-volume dosing, initial fills, reset states, and mixing/observation time.
- Supply a reaction/solubility model appropriate to selected reagents, plus particle nucleation, transport and settling assumptions if those quantities are to be predicted.
- Separate modeled solid mass fraction from optical turbidity; a measurement model must account for concentration, particle size, illumination, path length and detector calibration.
- Add robot articulation, collisions, valve actuation, grasp attachment, motion planning, stop behavior, sensor observations, and independent success checks.
- Validate the controller and selected classroom procedure on the real apparatus before physical use.

There is no liquid dynamics, chemistry solver, rigid-body configuration, or success detector in this asset. The solid layer is 7 mm tall and particles are deliberately enlarged for readability. Neither is a calculated yield. The scene is a visual specification, not experimental evidence.

## Packaging and reproduction

`Scene.blend` is editable and includes the original static robot solely for preview. `Environment.usdc` contains the bench, fixtures, sample states, cameras and lighting, excluding the robot and all physics APIs. Units are meters with Z up and tabletop at zero. Stable exported prim paths and object transforms are recorded in `manifest.json`.

Run Blender with `--background --threads 2 --python build.py -- --out DEST --robot ../assets/Robot_STATIC_ART_ONLY.usdc --render`. Omit `--render` to build/export only, or add `--view Front`, `Overhead`, or `Result` to select a render. All three images are actual Blender Cycles renders when delivered.

Approximate glass uses a transparent/opaque shader mix (12% opaque); water uses 5% opaque. It intentionally favors legibility over physically calibrated refraction. USD Preview Surface explicitly authors opacity 0.12 for glass, 0.05 for clear liquid, and 0.94 for the suspension; these values have been inspected in the exported file. Other renderers may still display approximate transparency differently. Geometry, transforms and materials are self-contained; no texture files are required.

Original robot attribution and license are packaged in `../assets/WORKSHOP_LICENSE`, `../assets/THIRD_PARTY_NOTICES`, and `../assets/source_receipt.json`. All experiment geometry and labels are newly authored procedurally for this deliverable. The upstream robot license governs the unchanged robot asset; no independent robot geometry was invented.
