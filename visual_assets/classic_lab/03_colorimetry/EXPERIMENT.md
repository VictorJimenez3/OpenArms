# Find the unknown concentration with light

A rack of five square cuvettes progresses from nearly clear to deep magenta. A separate amber holder carries an UNKNOWN. The unknown matches standard 3. Behind the rack, a recognizable teaching photometer exposes the lamp, sample socket and detector; its screen reads **A 0.600 / C 3.0 units**. A food-color bottle and a detailed pipette in a stand convey sample preparation. This is one color-comparison / optical-measurement experiment.

**All renders are ART PREVIEW. Colors, match bracket, displayed values and duplicate unknown aliquots are staged. The optical response is MODEL-PREDICTED, not measured, simulated in an optical solver, or demonstrated by a robot.**

## Student question and procedure

Which known concentration matches the unknown, and does its transmitted-light reading agree?

1. Prepare equal fill heights of benign food-color water in identical, clean cuvettes. Keep the optical path and dye identity fixed. Use an instructor-provided reference series labeled 0, 1, 2, 3 and 4 relative units; these are arbitrary calibrated teaching units, not mg/L.
2. Visually compare the unknown with the ordered standards. Record the best match before reading the instrument.
3. Insert the zero reference into the photometer and establish the reference reading. Read the other standards to establish a calibration.
4. Grip the dry side flats of the unknown cuvette, lift it clear of the amber holder, and insert it vertically into the sample socket. Close the light cover for a real measurement. The cover is deliberately raised in this preview to reveal the sample and optical arrangement.
5. Record absorbance and infer concentration from the calibration. Compare this estimate with the visual match. Repeat with a different unknown.

The pipette and capped bottle are preparation props. This scene does not prescribe a robot liquid-handling procedure. Equal unknown aliquots appear both in the comparison holder and in the instrument so both stages are visible at once; a single-cuvette execution should reset to one movable unknown.

## Two meaningful conditions

Student variable: unknown relative concentration, with liquid depth and cuvette path fixed.

| Condition | Expected appearance | Assumed absorbance | Predicted transmitted fraction | Match |
|---|---|---:|---:|---|
| Unknown = 1 relative unit | Pale magenta | 0.200 | 0.631 | Reference 1 |
| Unknown = 3 relative units | Deep magenta; staged endpoint | 0.600 | 0.251 | Reference 3 |

The illustrative model assumes `A = 0.2 C` and `T = 10^(-A)`. The calibration coefficient is an authored teaching assumption. It is not a property measured for a particular dye. Materials provide an artist-authored monotonic magenta color ramp, not wavelength-dependent absorption. The green optical-path segments are explanatory geometry, not a claim that a beam would be visible in clean air. Actual optical simulation needs a calibrated source spectrum, filter, path length, extinction/absorption data, detector response, stray-light handling and independent measurements.

## Geometry, operation and runtime boundary

Meters, Z up, tabletop at Z=0. Table is 1.00 × 0.75 × 0.044 m centered at (0.12, 0, -0.022). Educational cuvettes have 18 × 18 × 69 mm outer dimensions, 15 mm internal path, separate thin open walls, bottom, rim, liquid and approximately 2 mL graduation spacing. Filled depth is 48 mm, about 10.8 mL. The source holder raises the comparison unknown 10 mm above the reference bases.

Stable environment paths:

- `/ClassicLab/Bench`: static bench and floor.
- `/ClassicLab/References/Reference_0` through `Reference_4`: potential movable cuvette assemblies; remaining References children are static rack, holders and teaching labels.
- `/ClassicLab/References/Unknown_comparison_aliquot`: removable unknown; base transform **(0.359, -0.128, 0.026)**, identity rotation.
- `/ClassicLab/Photometer/Unknown_in_optical_holder`: staged removable duplicate; base transform **(0.267, 0.130, 0.057)**, identity rotation.
- `/ClassicLab/Photometer`: static instrument, except that removable cuvette child. `/ClassicLab/Photometer/Sample_holder_floor` and window posts define the insertion target; the nominal socket interior is 22 mm wide for an 18 mm cuvette. The raised cover is a static art pose, not an articulated hinge.
- `/ClassicLab/Preparation`: static source bottle and pipette fixture; the tool is assembled from editable named components. No tool motion or dosing is implemented.

Intended cuvette grasp: opposite side flats, fingers parallel to X, local Z 54–63 mm. Avoid the front/back optical windows, rim and liquid. References are 43 mm apart, leaving 25 mm nominal between cuvettes before accounting for finger thickness. The source unknown is farther right than the nominal active zone; fixture repositioning or reach qualification may be necessary. Lift at least 40 mm clear of the holder before a lateral transfer; actual required clearance depends on the robot and grasp. These are design intentions, not collision or reach results. The instrument insertion target is within the approximate working region, but all approach paths remain unqualified.

The preview uses the original white, camera-free SO101 static asset at **(-0.05, 0, -0.03008145)** without added yaw or scaling. Runtime base reference remains **(-0.05, 0, 0)**. The robot is embedded only in `Scene.blend`; it is absent from `Environment.usdc`.

Runtime still needs an articulated robot, collision/mass assignments, reset states, grasp/insertion/button/cover controllers, tool fixture qualification, liquid transfer behavior, calibrated optical model, observations and success logic. USD contains no physics APIs. A successful Blender render supplies no evidence of task execution.

## Files and regeneration

`Scene.blend` contains editable geometry, materials, original text, three cameras, neutral lighting and the licensed static robot. `Environment.usdc` embeds robot-free environment geometry, exported text meshes, materials, cameras and lights under `/ClassicLab`; it has no external dependencies. `Front.png`, `Overhead.png` and `Result.png` are actual Blender renders. Camera matrices and apparatus transforms are in `manifest.json`; audit results are in `validation.json`.

Run Blender 4.5 or compatible in background mode with `--python build.py -- --render`. Supply `--robot PATH` if needed; the packaged default is `../assets/Robot_STATIC_ART_ONLY.usdc`. Optional `--out PATH` and `--samples N` are supported. The procedural environment is self-contained; the static preview robot is the only input asset. Production uses Cycles CPU, two threads, 40 samples and denoising at 1600 × 1000.

## Licenses and rendering limits

All new procedural apparatus geometry and composition were created for this task, without third-party textures. The original static robot is retained under the upstream license and notices packaged in `../assets/WORKSHOP_LICENSE`, `../assets/THIRD_PARTY_NOTICES` and `../assets/source_receipt.json`; those documents govern the source asset. No robot mechanics were remodeled.

Blender glass/refraction, bevels, AgX appearance and readable text have been reviewed in the rendered previews. USD Preview Surface may show different transmission, roughness, reflections and color; it is not a spectral optical renderer. Text is converted to meshes for USD, while Blender retains editable text. The marker bracket and result readout are teaching annotations and staged outcome geometry; runtime authors must update or hide them for unknown trials.
