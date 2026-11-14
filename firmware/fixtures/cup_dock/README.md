# OpenArms cup fixture — provisional v0.3

Two independent tabletop docks for the existing A → C pour. The source is now based on the **Diamond 2 oz clear shot glass**, Target TCIN 94991464. Target publishes **48 mm overall width × 51 mm height**; it does **not** publish the bottom diameter. The 38 mm source base is an engineering placeholder, not a product fact. Receiver dimensions remain provisional. Nothing attaches to the cup; the existing jaws grip it directly.

Print a fit gauge first. These exports are CAD-validated, not physically qualified. No servo behavior, saved poses, calibration files or other live software was changed.

## Parts and parameters

| Parameter | Source A | Receiver C | Evidence |
|---|---:|---:|---|
| Cup bottom outer diameter | 38 mm | 59 mm | Estimates; measure |
| Cup top outer diameter | 48 mm | 73.7 mm | A uses published overall width as provisional rim diameter; C estimate |
| Cup height | 51 mm | 63.5 mm | A published overall height; C estimate |
| Radial running clearance | 0.8 mm | 0.8 mm | Starting design allowance |
| Guide height above floor | 6 mm | 6 mm | Selected design, not measured requirement |
| Guide wall thickness | 3 mm | 3 mm | Design |
| Dock floor / overall height | 3 / 9 mm | 3 / 9 mm | Design |
| Dock footprint | 100 × 132 mm | 100 × 132 mm | Design |
| Fit-gauge cup-base candidates | 36 / 38 / 40 mm | 57 / 59 / 61 mm | Labels indicate cup diameter; bore adds clearance |

`fixture.scad` is the editable source. `source-A.stl` and `receiver-C.stl` are separate print parts. Each `gauge-*.stl` is one small connected part. Gauge labels are **assumed cup bottom diameters**, not bore diameters. The gauges have no floor: place the cup and gauge on the same flat surface. They reproduce the guide's cup-relative height and taper.

The 240° U guides open toward local **−Y**. They are **top-drop / vertical-lift**, not slide-in holders. The tapered bore widens upward, has no lip or undercut, and leaves the front visible. A full ring would bound lateral play more tightly, but the U is easier to inspect and leaves front access. Neither shape removes the need to test extraction with the actual flexible cup.

The 0.8 mm clearance is **not** a positioning-accuracy claim. With an ideal upright rigid cup, this U permits roughly 2.5 mm total fore–aft play (about 0.8 mm rearward and 1.7 mm toward the opening). Print error and cup flex add uncertainty. Manually reset against the same rear datum and measure the actual scatter. The robot's release and next grasp must tolerate that scatter. If necessary, reduce clearance only after fit and repeated return tests.

## Print and update

Start with ordinary PLA, 0.4 mm nozzle, 0.2 mm layers, 3 walls and about 15–20% infill, subject to the printer's normal profile. Print the flat underside on the bed. The model has no designed support requirement. Preview the first layer and toolpath before printing. No slicer or printer profile was available here, so **print time and real filament consumption are unknown**. `validation.json` records geometric volumes and a clearly labeled solid-PLA equivalent, not a slicer estimate.

1. Measure the cup's base outer diameter, outer diameter at 6 mm above its seating plane, rim diameter and height. Check for a flared foot, ribs or nonlinear taper. Measure the intended jaw-contact diameter and usable jaw opening with any pads installed.
2. Edit `source_bottom_d`, `source_top_d`, `source_height` and the corresponding receiver values near the top of `fixture.scad`. For a nonlinear cup, fit the guide to the **local lower 6 mm**, not a guessed full-height taper. One equivalent CAD top value is `bottom + (measured_d_at_6-bottom)*height/6`; note that the preview rim will then be illustrative only.
3. Export `part="gauge_single"`, `gauge_cup="source"` or `"receiver"`; `gauge_delta` shifts both diameters equally. Or use the supplied candidate gauges if their sizes bracket the measurements.
4. Confirm easy insertion, consistent seating and free straight-up extraction. Print the full dock only after this check. The gauge is loose on the table; judge fit separately from its own weight.
5. Secure each dock inside a rigid catch tray using tape on its margins/underside or the four 3.6 mm mounting holes. A lightweight unsecured dock can lift with the cup. Keep tape and anti-slip material thickness consistent when teaching.

To regenerate all artifacts, install the dependencies listed in `build.py`, then run:

```sh
python build.py --out /absolute/path/to/exports
```

For one STL using OpenSCAD directly:

```sh
openscad -o source-A.stl -D 'part="source"' fixture.scad
```

The default two-dock preview uses 125 mm centre spacing. This is **illustrative only**. Put the docks where the real arm can reach and pour, then secure them. No robot reach or full jaw-sweep clearance is asserted. Four cups can later use additional independently positioned docks, with distinct station labels/marker IDs and newly taught poses; the first working route needs only A and C.

## Camera references and calibration

Each tile's CAD origin is its front-left underside: +X right, +Y toward the rear, +Z up. The cup seat centre is `(50, 88, 3)` mm; the marker centre is `(50, 26)` mm. Each marker's **black square is 36 mm**, on a 44 mm paper square. A uses `DICT_4X4_50` ID 10; C uses ID 12. Keep printed orientation aligned with the preview (+Y toward marker top). The JSON records the corners. The paper surface height is 3 mm **plus measured paper and adhesive thickness**.

Print `printable-markers.pdf` at **100% / Actual Size**, not Fit to Page. Measure its 100 mm line and each black square, cut while preserving the white border, and mount between the cross marks. The engraved ruler has ten 10 mm intervals. Printed dimensions must be measured; nominal CAD dimensions do not certify printer accuracy.

These references can support identification and later calibration. They do not themselves estimate arbitrary depth, establish cup presence or certify seating. ArUco metric pose requires camera intrinsics/distortion calibration and measured marker size. The existing [`bench_vision/geometry.py`](https://github.com/VictorJimenez3/OpenArms/blob/171a21a393a12e37a2ad5e3e075ce5949b262bd4/bench_vision/geometry.py) instead fits a planar pixel-to-mm mapping from at least four measured fit points and checks it using at least four separate held-out points; inference checks current anchors, uncertainty, camera identity and plane height. Its output deliberately has `grasp_pose=None`.

The front marker does **not** surround the cup centre. Its corners alone cannot qualify localization at the cup under the existing no-extrapolation checks. For a later plane map, add measured same-plane rear/outboard references around the relevant region. Never interpret elevated cup-rim pixels as tabletop points. Start with **`taught_fixture_only`**, already supported in [`bench_vision/skills.py`](https://github.com/VictorJimenez3/OpenArms/blob/171a21a393a12e37a2ad5e3e075ce5949b262bd4/bench_vision/skills.py), and operator observations.

## Teach and qualify the real setup

The existing [wet-lab workflow](https://github.com/VictorJimenez3/OpenArms/blob/171a21a393a12e37a2ad5e3e075ce5949b262bd4/docs/WET_LAB.md) already supplies `openarms capture water`, `openarms pour dry` and `openarms pour water`. Teach new `HOME`, `ABOVE_A`, `GRASP_A`, `ABOVE_C`, `TIP_C` and separate `open` / `cup` jaw settings. Do not reuse the mandarin poses or replace measured robot coordinates with CAD coordinates. The executor interpolates between named checkpoints, so inspect the entire swept path, not only its endpoints.

With a 3 mm floor and 6 mm guide, the lowest part of the jaws must clear **z = 9 mm plus a physically checked margin** when approaching/closing. The smaller estimated source has about 41.9 mm diameter at 20 mm above its base and 43.9 mm at 30 mm. Actual jaw opening, grip setting, pad thickness and cup stiffness remain unknown. Neither the simulator's hinge angles nor servo torque establish usable millimetre opening or grip force. The saved grip is a position setting, not a measured force guarantee.

After the gauge and mounting checks:

1. Teach an empty-cup take, including vertical lift and return clearances.
2. Run supervised empty-cup trials. Confirm lift, tilt clearance, controlled placement and free jaw release without moving the dock.
3. Add one small pre-measured water portion; observe slip, deformation, delivery, spill, return and reset. Repeat the final setup before relying on it. Keep the last successful configuration.
4. Record actual cup measurements, dock spacing/orientation relative to the secured arm, marker sizes, mounting thickness, jaw contact height/opening, recorded pose file and outcome evidence.
5. Associate the installed setup with existing `fixture_id`, `cup_id`, `calibration_id`, `camera_mount_id`, `robot_id` and geometry fields in the skill context. `fixture-reference.json` is design metadata with null physical IDs, **not a runnable calibration or pose file**. The repository already checks changed setup IDs/geometry in offline adaptation; this design adds no registry.
6. Moving a dock/camera, changing cups, pads or guide geometry requires updating the setup identity and rechecking the affected teaching/calibration. Fixed A/C transforms are meaningful only after measuring or teaching their relation to the actual arm.

A fixed image region and reference-image comparison may eventually provide a cheap occupancy check. Transparent cups make that uncertain; the repository's orange-object detector is not a validated cup detector. For now a visible marker proves the dock is visible, not that a cup is present. Preserve independent operator confirmation and before/after evidence.

## Evidence and sources

- [Target Diamond product, TCIN 94991464](https://www.target.com/p/-/A-94991464): published overall size, not base geometry or local inventory.
- [Live physical-demo decisions](https://app.notion.com/p/41871c9c107e816fab14f3549f6a8fd6): pH-only student demo, fixed fixtures and direct-grip first. One manually selected condition at A is enough initially.
- [Existing physical transfer evidence](https://github.com/VictorJimenez3/OpenArms/blob/171a21a393a12e37a2ad5e3e075ce5949b262bd4/research/joseph/mandarin-transfer-2026-11-14/README.md): mandarin success does not establish cup or liquid readiness.
- [Existing gripper uncertainty](https://github.com/VictorJimenez3/OpenArms/blob/171a21a393a12e37a2ad5e3e075ce5949b262bd4/research/victor/laboratory-experiments-and-feasibility.md): no measured usable jaw opening/force for these cups.
- [OpenCV ArUco documentation](https://docs.opencv.org/4.13.0/d5/dae/tutorial_aruco_detection.html): marker size, calibration and pose prerequisites.

Validation consists of OpenSCAD solid export and independent trimesh checks of watertightness, winding, connected-component count, positive volume, flat Z=0 underside and expected height for all eight individual STL parts. The preview uses those actual dock meshes, with estimated translucent cups. Marker images are decoded with OpenCV to check IDs. A slicer, real print, cup fit, robot collisions/reach, camera accuracy and liquid results remain unverified.

## Demo supplies

One shopping run: small source cups, a larger clear receiver, purple grape juice, household white vinegar, baking soda, tape, a rigid catch tray, paper towels, a ruler/calipers and matte white paper for markers. Dye is optional for a visible water-transfer rehearsal; dye mixing alone is not a pH experiment.

Purple grape juice is a practical cabbage alternative: [Caltech's educational activity](https://www.its.caltech.edu/~ccc/participants/volunteers/Acids-and-Bases.pdf) reports a reddish-purple to bluish-purple/dark change with baking-soda solution and a return toward reddish-purple with vinegar. My shopping preference is 100% purple grape juice to avoid relying on artificial coloring; 100% is not a universal chemical purity requirement or a guarantee of a vivid transition. Test a small sample in the actual receiver under the demo lighting; juice acidity, concentration and camera exposure affect visibility. [ACS explains](https://www.acs.org/content/dam/acsorg/education/outreach/activities/fruit-juice-sleuth/fruit-juice-sleuth-home.pdf) that anthocyanins in real berry/grape juices change with acid/base conditions while common artificial food dyes may not. Other berry juices are candidates, but are not validated substitutes for this particular demo. Prepare and observe the chosen conditions before teaching a loaded run; keep them in open cups with headroom for fizzing.
