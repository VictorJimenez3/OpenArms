# One platform, four cups — OpenArms v0.4

**One continuous printable platform with four cup slots in a 2×2 layout.** All four cups sit on the same base. This replaces the earlier two-separate-dock design. Use ordinary small plastic cups from Target or another store; laboratory cups, custom handles and cup-mounted attachments are not required.

The four slots are labeled A, B, C and D. Their experiment roles can be assigned after the actual cups and liquids are chosen. The current model uses four identical provisional small cups. Equipment we do not own can appear in a clearly identified simulation; physical-demo claims still come from observing the real cups and robot.

## Files

- `four-cup-platform.stl`: the **single full platform**, including all four cup guides. Print once.
- `fit-gauge-36mm.stl`, `fit-gauge-38mm.stl`, `fit-gauge-40mm.stl`: optional small fit checks, not separate cup stations.
- `fixture.scad`: editable CAD; defaults to the full four-cup platform.
- `four-cup-preview.png`: actual exported platform geometry with four illustrative translucent cups.
- `printable-markers.pdf`: two platform reference markers, not two cup stations.
- `fixture-reference.json` and `validation.json`: dimensions, coordinates and geometry checks.

## Starting dimensions — not measured cup fit

| Parameter | Default |
|---|---:|
| Platform | 200 × 200 mm |
| Continuous floor | 3 mm |
| Four guides above floor | 6 mm |
| Overall printed height | 9 mm |
| Cup base / rim / height | 38 / 48 / 51 mm, each slot |
| Radial clearance | 0.8 mm |
| Guide wall | 3 mm |
| Column / row pitch | 90 / 82 mm |
| Slot A / B centres | (55,78) / (145,78) mm |
| Slot C / D centres | (55,160) / (145,160) mm |

The nominal 48 mm width and 51 mm height came from the previously considered [Diamond 2 oz retail cup](https://www.target.com/p/-/A-94991464). The 38 mm bottom diameter is an engineering estimate. **No specific brand is required.** Measure whichever cups are purchased. Larger Starbucks cups will need changed cup dimensions and may require a larger platform; do not assume they fit these small-cup slots.

Edit the top parameters in `fixture.scad`. `slot_cups` supports a different `[bottom_d, top_d, height]` for each of A/B/C/D. Adjust platform size, row/column pitch and first-row position when increasing cup size. Assertions check guide/rim separation and plate margins. They do not certify robot jaw clearance.

## Fit, print and use

1. Measure the actual cup base, diameter 6 mm above its seating plane, rim and height. The linear taper is a provisional approximation; lower-wall ribs or a flared foot must be accounted for.
2. Print a small matching gauge first. Gauge labels are assumed **cup base diameters**; the bore includes 1.6 mm diametral clearance. Put the floorless gauge and cup on the same flat surface. Check easy insertion and straight-up removal.
3. Print **one** full platform flat on the bed. A usable bed larger than the 200×200 mm footprint is needed for any brim/margins; actual printer capacity is unconfirmed. Typical starting settings: PLA, 0.4 mm nozzle, 0.2 mm layers, 3 walls, 15–20% infill. Geometry is designed without support requirements, but inspect the slicer preview. No slicing or print-time estimate was performed.
4. Secure the entire platform inside a catch tray using tape or the four mounting holes. The cup slots are shallow U-shaped top-drop/vertical-lift guides. They do not clamp the cups and are not lateral slide-in slots.
5. Teach the existing jaws to grip the actual cup directly at a consistent height and closing position. Nothing needs to be mounted on the cup. The lowest swept jaw surface must clear the 9 mm guide top plus a tested margin. Grip position is not a measured-force guarantee; check empty-cup and then small-water tilt trials.
6. Teach the desired four-slot routes only after securing the platform. Preserve existing operator confirmation and independent observations of lift, pour, spill, return and reset.

The U guides permit approximately 2.5 mm total ideal fore–aft play at the default clearance, before printing errors and cup flexibility. Seat cups consistently against the rear datum and test the actual reset scatter. Clearance can be tuned after a gauge test; it is not a positioning-accuracy claim.

## Existing robot and camera integration

Use the existing taught-pose workflow and `taught_fixture_only` mode. This change does not alter servo control, recorded poses or calibration. CAD coordinates belong to the **whole platform**, with origin at its front-left underside, +X right, +Y rear and +Z up. Each cup seating plane is z=3 mm. These are not automatically robot coordinates.

The project already has `fixture_id`, `cup_id`, `calibration_id`, `camera_mount_id` and `robot_id` context fields. Record the secured four-slot arrangement and actual cup dimensions under a new setup identity, and teach/revalidate the relevant named poses. Do not reuse the previous two-independent-dock geometry or mandarin poses. Moving the platform, changing cup geometry or changing camera mounting requires the relevant retesting.

The two paper fiducials belong to the **one platform**: DICT_4X4_50 IDs 10 and 12, centres (50,24) and (150,24) mm. The black square is 36 mm and paper is 44 mm. Print the PDF at Actual Size, verify its 100 mm line, and preserve the white margins. Surface height includes measured paper/adhesive thickness above the 3 mm floor.

`bench_vision/geometry.py` maps pixels to measured positions on one plane, using at least four fit points and four independent check points. It does not determine arbitrary 3D depth or produce a grasp pose. These front markers alone do not surround the rear cup slots; later metric plane mapping needs same-plane reference points surrounding the region and camera calibration. Markers do not prove cup presence or successful pouring. Fixed taught positions and physical observation remain enough for bring-up.

## Rebuild and evidence

Install OpenSCAD and the Python dependencies named in `build.py`, then run:

```sh
python build.py --out /absolute/path/to/exports
```

The builder exports the full platform and three gauges, validates each mesh as one watertight consistently wound positive-volume solid, checks dimensions and flat underside, and checks that a horizontal section above the base contains **exactly four separate cup-guide contours**. It also generates the preview and decodable markers. Physical cup fit, gripping, robot reach/collisions, printing and liquid behavior remain unverified.
