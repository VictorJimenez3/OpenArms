# Two-vessel base plate

D1 bench fixture for [OpenArms #12](https://github.com/VictorJimenez3/OpenArms/issues/12). The Smartivity donor beaker sits at A and the wider stationary receiver sits at C. The latest [photo-derived vessel meshes](../../../simulation/models/vessels/measured_2026_11_14/README.md) supply the provisional profiles. Print the fixture and gauges. Use the original kit vessels for liquid.

Two shallow chamfered nests share a rigid ribbed base. This keeps their spacing fixed in a single print and leaves the catch tray exposed between the supports. Individual nests allow easier spacing changes and require a common backing and measured assembly. Use the small gauges to tune each fit before printing the full base. The [four-cup design](four-cup-v0.5/) is archived.

## Files

| File | Use |
| --- | --- |
| [Editable OpenSCAD](fixture.scad) | Plate, chamfers, approach openings, marker pockets and gauges |
| [Base plate STL](exports/two-vessel-base.stl) | Slice in millimetres with the flat underside down |
| [Gauge A](exports/fit-gauge-A.stl), [gauge C](exports/fit-gauge-C.stl) | Match the guide geometry at each station on a thin test floor |
| [Assembly render](exports/two-vessel-preview.png) | Actual fixture STL, existing vessel meshes, marker art and a blue arrow for the donor approach |
| [ArUco artwork](exports/aruco-markers.pdf) | One US Letter sheet for the four pockets |
| [Fixture reference](exports/fixture-reference.json) | Dock placement, guide and vessel profiles, marker corners and setup provenance |
| [Validation](exports/validation.json) | Build checks and pending bench qualification |

## Geometry

Coordinates are in millimetres. The origin is the front-left corner of the plate footprint projected onto its underside. +X points right, +Y rear, +Z up. Both vessels seat at Z=4 mm.

| Dimension | A | C |
| --- | --- | --- |
| Seat centre XYZ | (42, 76, 4) | (116, 80, 4) |
| Vessel base envelope OD, photo estimate | 31 (28–34) | 59 (54–66) |
| Circular rim OD, photo estimate | 41 (38–44) | 78 (75–82) |
| Outside height, photo estimate | 51 (47–56) | 32 (30–35) |
| Guide height above seat | 3.5 | 4.5 |
| Guide opening centred on −Y | 110° | 60° |
| Nominal radial clearance below the chamfer | 0.65 | 0.75 |
| Extra radial relief at the top of the chamfer | 1.0 | 1.1 |

The 4 mm deck has open spaces between ribs, a 2.6 mm minimum designed guide wall and two Ø3.6 mm through holes at XY (79, 48) and (79, 111). Use M3 hardware with an outside head/washer diameter up to 10 mm, or secure the flat underside to a dry catch tray with removable tape. The 170 × 156 × 8.5 mm envelope leaves the configured 4 mm margin per side on a usable 180 × 180 mm bed. Confirm the actual bed, reserved edges and any brim in the slicer.

The seats constrain translation and allow straight-up removal. Set the donor spout by hand toward the engraved arrow (3.094° counterclockwise from +X). The round donor body can still rotate in its guide. The modeled smooth grip band is 10–40 mm above the donor seat. The lowest moving jaw surface needs to clear the guide through approach and release. Cup spacing, opening angles, grip height and spout alignment still need the dry bench check.

## Fit and print

1. Print the A and C gauges flat. Try each empty vessel in its own gauge. It should sit level, lift out cleanly and settle when lowered slightly off centre. Check the lower outside diameter at the seat and at the guide height, including any ribs or flare. Note any bind, rocking, or excess play.
2. Update `radial_clearances` in [fixture.scad](fixture.scad) for fit tuning. For a quick comparison, export a gauge directly with `part="gauge"`, `gauge_index=0` for A or `1` for C, and `gauge_radial_adjustment` set to an extra clearance per side. For new measured profiles, pass `--vessel-dir` with matching parameters and regenerated metre-scale meshes. The standalone CAD defaults reproduce the current revision 2 profiles.
3. Slice the full plate with Z=0 on the bed. A starting profile is a 0.4 mm nozzle, 0.2 mm layers, at least three perimeters and 15–20% infill. The geometry is intended for support-free printing. Check the marker pocket floors and guide perimeter paths in the slicer. Print time and filament use still depend on the printer and profile.
4. Place and secure the plate in the catch tray so it cannot move relative to the arm. Set the empty donor's yaw. The bench owner can check insertion and removal by hand, then teach and verify the empty pickup, carry, lip-over-receiver approach, tilt, recovery and return with the existing supervised procedure before water. Record any grip slip, collisions, seating errors and camera occlusion.

## Fiducials and camera handoff

The four 40 mm pads and 37 mm square pockets are part of the print. Print the artwork at **Actual Size / 100%**, measure its 50 mm ruler and verify a **27 mm black square**. Cut and attach one 36 mm tile at a time with its 4.5 mm white border intact. Centre each tile in its pocket using thin removable adhesive. The artwork's top edges face +Y.

| ArUco `DICT_4X4_50` ID | Pad centre XYZ |
| --- | --- |
| 20 | (20, 20, 3.6) |
| 21 | (150, 20, 3.6) |
| 22 | (20, 136, 3.6) |
| 23 | (150, 136, 3.6) |

The manifest lists black-square corners in OpenCV's decoded top-left, top-right, bottom-right, bottom-left order. Z=3.6 mm is the bare pocket floor. The paper and adhesive set the final optical plane. Centre and survey the installed labels before relying on those coordinates.

The current [bench vision geometry](../../../bench_vision/geometry.py) takes undistorted correspondences on one plane and independent check points. Its pad-plane homography can register the fixture. Resolve the seat plane, raised rims and grasp points separately. Camera-to-fixture and robot-to-fixture transforms are distinct. The manifest leaves physical fixture ID, calibration ID and robot registration unset. When physically qualified, record the secured setup identity, camera mount and taught poses through the bench workflow.

## MuJoCo handoff

Import the base STL as a visual mesh with scale `0.001 0.001 0.001`. The existing vessel meshes are already in metres. Translate each support datum to its exported seat XYZ divided by 1000. Rotate the donor by the exported asset yaw (about −86.906° around +Z), since its local spout points along +Y. Use the published profiles, guide radii and gap angles to approximate collisions with separate convex segments and a flat seating surface. Convexifying the entire plate fills both guide openings and spaces between ribs. Use this geometry as CAD-derived simulation input. Physical robot coordinates and pose qualification come from the secured bench setup.

## Rebuild and status

```sh
python -m pip install numpy trimesh networkx rtree 'opencv-python-headless>=4.8' reportlab
python firmware/fixtures/cup_dock/build.py
```

OpenSCAD must be on PATH. Use `--out /absolute/path` to export a separate set. The builder checks the source meshes, plate and gauge solids and extents, guide walls and openings, nominal cup clearance, seating planes, marker pocket placement, screw holes and digital ArUco decoding. Independent CAD review checked the mesh sections and invalid parameter cases. Two builds reproduced the same mesh geometry. OpenCV decoded all four marker IDs from the PDF raster and from the assembled CAD view. MuJoCo 4.0.1 loaded the exported plate and both vessel meshes at the manifest positions. These checks cover the digital assets. The blue arrow in the preview shows the intended approach direction. Bench testing still needs the actual jaw envelope and camera view.

- [x] Digital CAD, gauge exports, artwork, reference geometry and assembly preview.
- [ ] Measure the actual lower profiles and confirm both gauge fits.
- [ ] Confirm available printer area, slice the plate and verify the printed dimensions.
- [ ] Secure the fixture, survey the applied markers and check visibility from the bench camera.
- [ ] Verify empty and water trials with the supervised arm, including spout alignment, grip, clearance, recovery and reset.
