# Photo-derived vessel assets — 14 November 2026

First model delivery for D1 / [issue #19](https://github.com/VictorJimenez3/OpenArms/issues/19). These are the best current **photo-derived estimates**, not exact manufacturer CAD or direct caliper measurements. All fourteen supplied photographs were inspected; revision 2 adds five receiver views. The physical vessels are the reference; older simulation sizes are not evidence. Fixtures, robot motion and physical calibration are excluded.

| Dimension, mm | Donor A | Receiver C | Evidence / method |
| --- | --- | --- | --- |
| Outside height | 51 (47–56) | 32 (30–35) | A: 9257/9265; C: upright/inverted 9270/9271; ruler-scaled |
| Circular rim outside diameter | 41 (38–44) | 78 (75–82) | A: 9259/9260; C: 9269, checked against 9261–9263; ruler-scaled |
| Opening diameter | 34 (31–37) | 75 (70–79) | Transparent edges; low confidence |
| Lower-body/base envelope diameter | 31 (28–34) | 59 (54–66) | A: 9259/9265; C: 9261/9264; low confidence |
| Spout extension beyond circular rim | 4 (2–6) | None visible | 9259/9260; approximate |
| Interior floor above exterior datum | **Assumed 2** (1–4) | **Assumed 1.2** (0.5–2.5) | Not measured; includes bottom stand-off |
| Interior bottom diameter | **Assumed 28** (25–31) | **Assumed 56** (51–63) | Conditional interior model |
| 25 mL line above exterior datum | 34 (29–39) | Not applicable | 9257/9258/9265 |

Ranges are judgment bounds, not statistical confidence intervals. No directly measured numerical dimensions were supplied. The donor's rounded lower edge has a 29 mm modeled support footprint inside its 31 mm lower-body envelope; that footprint remains an assumption. Smooth donor wall between approximately z=10–40 mm is a candidate grip region, not a qualified grasp.

## Evidence and volume consistency

`parameters.json` records input values, provenance classes, uncertainty, unknowns and original HEIC hashes. `image_measurements.json` records reproducible pixel endpoints; `evidence/` shows annotated ruler and feature locations, including the new side-plane measurements. Image coordinates refer to 2000×1500 derivatives (multiply by 2.856 for the original 5712×4284 images). Source originals remain in the user's Downloads. Exported images have no original EXIF metadata.

Receiver rim readings are about **76 mm in 9263 versus 83 mm in 9261**. Different camera angles and feature elevations make them incompatible as exact measurements. We retain a broad range rather than reduce uncertainty by averaging correlated views. Ruler bending, uncalibrated lens distortion, depth mismatch and unclear transparent edges remain systematic limitations. The new side views give apparent axial heights about 31 and 33 mm; revision 2 uses 32 mm (30–35 mm). This is still image-derived, not a directly reported ruler reading.

The donor has 5–25 mL raised fill marks. The receiver's **100 mL is embossed on its underside**, not at a recoverable fill height. Neither is established brim capacity.

Piecewise-linear interior radii are integrated as frusta: `V = π Δz (r₀² + r₀r₁ + r₁²) / 3`; cubic millimetres are divided by 1000 for mL. The selected donor profile gives **23.8 mL** at the estimated 25 mL line, **1.2 mL (5%) below** the label. This is a consistency check conditional on assumed interior dimensions, not a calibration. The model was not fitted to force 25 mL. Its axial cavity to the rim is **38.5 mL**; the receiver's is **110.2 mL**, about 10 mL above its nominal label. No receiver fill line is available to interpret that difference. These calculations exclude the small spout expansion and do not establish usable capacity or pour dose.

## Receiver refinement (revision 2)

IMG_9269 gives a near-central rim chord of approximately 77.2 mm, with contour interpretation supporting 78 mm OD (75–82 mm). Its ruler placement is more useful than the earlier separate-ruler views; this replaces the 80 mm nominal. IMG_9267/9268 show an inverted or ambiguous configuration with different feature planes, so their apparent 67 mm / 55 mm spans are not averaged into rim OD. IMG_9270/9271 expose axial plane centres and support 32 mm outside height (30–35 mm), superseding 36 mm. Profiles are regenerated with those changes; internal thickness and base dimensions remain uncertain.

## Assets and coordinates

- `donor_A.obj` / `.stl`, `receiver_C.obj` / `.stl`: watertight material shells with open cavities, modeled exterior, inner wall, floor and rim. **Coordinates are metres**, including the otherwise unitless STL files.
- `vessels.xml`: standalone MuJoCo scene; each body datum is the exterior support-plane centre, +Z up, donor spout +Y. Scene placements ±55 mm merely separate the assets for inspection; they are not bench station positions.
- One noncolliding visual mesh per vessel, plus a base and separate convex wall segments for an open collision cavity. Collision faceting and bottom simplification are approximations; inspect group 3 to see proxies. No single solid convex hull substitutes for a hollow vessel.
- `parameters.json` is the source of truth for these assets. Profile radii and heights are in millimetres; submillimetre entries describe assumed construction, not measurement precision. Lip shape, crease and bottom rounding are simplified; text embossing and tiny molding marks are omitted.
- No inferred mass, free joints, actuators, friction qualification or liquid dynamics. Existing robot scene/configuration, poses and calibration are unchanged in this first delivery.

## Reproduce and check

From the repository root using the existing simulation environment:

```sh
PYTHONPATH=simulation python -m openarms_sim.vessel_assets --render
PYTHONPATH=simulation python -m pytest simulation/tests/test_vessel_assets.py -q
```

`--parameters /absolute/path/parameters.json --output /absolute/output/directory` rebuilds another explicitly chosen parameter set. Tests check units, exact frustum integration, closed consistently oriented meshes, declared extents, malformed interiors and MuJoCo rays reaching each cavity floor. Rendering uses MuJoCo 4.0.1 in the checked environment. Side/top/oblique views are geometry illustrations, not calibrated photo registrations.

## Remaining gaps

Direct outside heights/diameters, internal depth, base/wall thickness and donor graduation height would reduce the principal uncertainties. Exact manufacturer/model identification remains unconfirmed; catalog resemblance must not replace evidence. Independent Account 2 review found no blocking issues; its fixed-caption finding was corrected before the first push. See REVIEW.md. Geometric similarity does not establish physical grasp, clearance, spill, pour or return reliability. Fixture CAD remains deferred.
