# Acid-base titration — the first faint pink endpoint

A tall graduated burette delivers one last drop into a conical flask on a white stirrer tile. The flask contains a faint pink illustrative endpoint. A small transparent reference vial and a discreet tabletop card show the clear starting appearance. This is one titration station, not multiple experiments.

## Student question and high-level sequence

**Question:** How does doubling the normalized acid amount, at the same starting sample volume, change the titrant dose required to reach the same persistent indicator color?

1. Identify the burette, dosing control, flask, and white endpoint background.
2. Read the initial burette level and observe the clear indicator-containing sample.
3. Adjust the dosing control while mixing the receiving flask; reduce addition near the color transition.
4. Observe the first persistent faint pink appearance and read the final burette level.
5. Compare the two readings and repeat to assess repeatability.

This is descriptive educational chemistry, not an operational chemical recipe. The supplied asset represents benign colored water. It contains no substance identities, concentrations, or hazardous preparation directions.

Across trials, the student changes the prepared sample’s normalized acid amount. During each trial, the student controls titrant dose and addition timing. The measurable observation is the burette reading difference at the chosen visual endpoint. An endpoint is an indicator response; this artwork does not establish a chemical equivalence point.

## Robot interaction

The original SO101 is included at true scale in `Scene.blend` only, using its unmodified licensed static mesh asset, no mounted camera and no extra yaw. Its runtime base reference is (-0.05, 0, 0) m; the static asset uses the documented z correction. Robot pose is illustrative, not a demonstrated controller state.

The widened teal dosing paddle is centered at (0.223, -0.098, 0.127) m. A conceptual metal extension joins it to the stopcock. This permits evaluating a low contact point while leaving the tall burette and retort stand passive. The stopcock rotates about X; the extension geometry requires real fixture design, calibrated angular stops, force limits, backlash testing, and reach/collision assessment before use. No reach or motion feasibility is claimed. The clamp stand stays aft/right of the active area. The receiving flask mouth is centered at (0.245, -0.055, 0.153) m with an approximately 24 mm opening. A removable drip catcher is stored beside the stand.

## Rendered science versus simulation

All three PNGs are actual Blender renders. The hanging drop and faint pink solution are artist-authored meshes and materials. They are **ILLUSTRATIVE STAGED STATE**, not measured chemistry, a fluid simulation, a successful robot execution, or evidence of manipulation readiness. No reaction model was executed. A runtime would need a separately declared concentration/indicator model, dosing-volume model, mixing and persistence model, and calibrated optical success metric. Rigid bodies alone cannot produce or validate this color endpoint.

`Environment.usdc` contains geometry, materials, lights, and cameras, in meters with Z up and default prim `/ClassicLab`. It excludes all robot meshes and art-overlay text and has no physics APIs. Runtime collision geometry, articulation, masses, joint limits, sensor setup, reset procedure, controller, and empirical success evidence remain separate work.

## Files and regeneration

- `Scene.blend`: editable full preview scene with the original static robot.
- `Environment_editable.blend`: editable apparatus and room before robot import, including editable text.
- `Environment.usdc`: portable robot-free scene.
- `Front.png`, `Overhead.png`, `Result.png`: fixed-view previews.
- `build.py`: procedural geometry source. Run Blender in background with `--python build.py -- --render`. Optional `--robot /absolute/path/Robot_STATIC_ART_ONLY.usdc` chooses the original robot source. Default source is `../assets/Robot_STATIC_ART_ONLY.usdc`.
- `manifest.json`: scales, positions, camera transforms, and evidence boundaries.
- `validation.json`: export and render checks.

The new laboratory geometry is original procedural work. Original robot provenance and license are retained in the accompanying `WORKSHOP_LICENSE`, `THIRD_PARTY_NOTICES`, and `source_receipt.json`, also packaged under the shared assets directory. USD Preview Surface transmission and refraction may differ from Cycles; translucent liquid, thin glass, and text shading need review in the destination renderer. Apparatus graduations are visual markings and are not calibrated volumetric instruments.

## Two meaningful controlled conditions

Compare two prepared samples with equal starting volume. Condition A has a normalized acid amount of 1×; condition B has 2×. Hold titrant strength, indicator response, mixing, and the persistence criterion for the faint-pink endpoint fixed. These are descriptive normalized model inputs, not substance concentrations or preparation instructions.

| Condition | Student-controlled variable | Measurable observation |
|---|---|---|
| Prepared sample A | Normalized acid amount = 1× | Burette dose V_A required for persistent faint pink |
| Prepared sample B | Normalized acid amount = 2× at the same starting volume | Burette dose V_B required for the same persistent faint pink |

An ideal declared neutralization model would predict V_B approximately twice V_A under these assumptions. That prediction is not computed or validated by this package. The useful comparison is endpoint dose versus prepared acid amount. Clear-below-endpoint and pink-at-endpoint are **execution stages within each condition**, not the two controlled conditions.

The render shows one staged endpoint, with a clear reference vial to communicate the color transition. A future runtime must reset the same station for both prepared conditions and report both dose observations. The supplied visual uses colored water and does not physically implement an acid–base reaction.

## Stable runtime interfaces

The USD uses these object-level prim paths. Geometry children underneath them are implementation details.

| Entity | Prim path | Intended behavior |
|---|---|---|
| Dosing paddle | `/ClassicLab/Titration/Accessible_dosing_paddle` | Intended movable stopcock fixture; no joint authored |
| Stopcock plug | `/ClassicLab/Titration/PTFE_stopcock_plug` | Intended rotation about world X |
| Receiving flask | `/ClassicLab/Glassware/Open_250_mL_conical_endpoint_flask` | Movable vessel, currently staged stationary |
| Burette | `/ClassicLab/Glassware/Graduated_burette_open_glass_tube` | Static clamped instrument |
| Stand and clamps | `/ClassicLab/Stand_and_clamps` | Static support fixture |
| Staged drop | `/ClassicLab/Titration/ONE_staged_hanging_titrant_drop` | Visual state only |
| Pink endpoint | `/ClassicLab/Glassware/ILLUSTRATIVE_faint_pink_liquid` | Visual state only |

The paddle is 29 × 12 × 20 mm. Its broad front/rear faces are the proposed gripper surfaces. Approach from -Y is a concept only; no finger-envelope clearance is certified. The paddle protrudes below its connecting shaft, but the surrounding vessel, tube, and adapter require joint collision assessment. The source frame is world-aligned at (0.223, -0.098, 0.127) m. The target frame is world-aligned at the flask mouth (0.245, -0.055, 0.153) m. Exact source object transform and aperture dimensions are also in the manifest. The body is approximately 78 mm wide and 118 mm high, labeled 250 mL; graduation marks are illustrative and uncalibrated.

Environment USD dependencies: none. No external textures. The full preview imports and embeds the original static robot meshes. Regeneration requires Blender and the configurable original robot USD; validation requires Python USD bindings. No robot controller, reaction/indicator model, mixing model, or observation detector is included.
