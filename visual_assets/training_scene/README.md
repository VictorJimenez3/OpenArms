# OpenArms single-experiment training candidates

**Superseded visual candidates:** the current requested classic experiments are in [classic_lab](../classic_lab/README.md). This earlier simple-task collection is retained for provenance.

Six separate, plain workbench scenes with the original SO-101 mesh, white printed parts, dark motors, no wrist-camera assembly, and fixed front/overhead cameras. These replace the discarded branded laboratory. Each candidate has an editable Blender scene, portable environment USD, opt-in table proxy, two actual Blender renders and a geometry/camera manifest.

**Status:** visual assets and import checks are complete. These are not six verified runnable experiments. Robot articulation, controllers, contact physics, scientific models, reset, actual application integration and measured success belong to `simulation/isaac`. All images are static **ART PREVIEW**. The independently recorded Isaac articulation smoke video is separate evidence; it is not evidence of any candidate succeeding.

## Candidates

| Folder | Single task | Conditions / measurement |
| --- | --- | --- |
| `01_vial_placement` | Place one vial into a rack pocket | Nominal vs 8 mm shifted source; target error, tilt and repeatability |
| `02_sample_sorting` | Sort one sample by observed size | 16 vs 24 mm diameter; correct bin and supported placement |
| `03_density` | Release one sealed sample into water | 0.8 vs 1.2 g/mL, equal 20 mL displacement; explicitly modeled buoyancy |
| `04_ramp_friction` | Release a block on a 20-degree ramp | Two effective contact-friction pairs; measured slide distance |
| `05_lever_balance` | Place one weight on a lever | Two placement distances; measured post-unlock beam angle |
| `06_indicator` | Dip a fresh indicator tab into one prepared sample | pH 5 vs 9; explicitly modeled indicator response and camera readback |

`experiments.json` defines proposed conditions, units, acceptance rules and missing physics. It is evaluator configuration, **not policy input**. Numerical tolerances are proposed development settings, not proven robot capabilities. Density uses a low 75 mm receiver and 50 mm water depth. Its rounded 27.144 mm cube displaces approximately 20 mL. The original vial is approximately 33.896 mm wide; the rack top opening is approximately 48.11 mm. Runtime must qualify throat geometry, source stability, reach, gripper clearance and actual collider shape.

The repository keeps import-ready USDs and manifests in `usd/`. The delivered bundle also includes the editable projects, renders and pinned source assets.

## Bundle contents

- `BaseEnvironment.usdc`: bench, floor, lights, two cameras; no robot or task props. Best first reference into the existing workshop scene.
- Each candidate's `Experiment.usdc`: complete environment plus that experiment's named visual props. No robot, collision APIs, masses or articulation.
- `ColliderProxies.usdc`: simple table mesh only, hidden and marked `purpose=guide`; no active physics. This is not a complete collision model for apparatus.
- `Environment.blend`: editable environment and props. Live text/modifiers remain editable where applicable.
- `ART_PREVIEW.blend`: additionally includes the original static robot mesh and camera-mounted evidence labels. This robot is not articulated. It is excluded from all `Experiment.usdc` exports.
- `Front_ART_PREVIEW.png`, `Overhead_ART_PREVIEW.png`: 1440×900 Cycles renders.
- `manifest.json`: units, world bounds, object groups, exact camera transforms and provenance.
- `assets/`: pinned robot/vial/rack sources, source hashes and licenses. Render projects contain their own mesh/material data. No external textures are required by the exported environments.

## Interchange contract

Meters; right-handed; Z-up. **Tabletop is z=0**, matching the runtime agent's final request. The earlier 0.76 m origin was superseded. The table is 1.00×0.75 m, centered at x=0.12, y=0, with 44 mm thickness below the work plane; floor top is z=-0.76 m. Default USD prim is `/TrainingScene`.

Reference **one** environment at a time. An existing workshop robot remains the authoritative articulated model. Reuse its authored root orientation and runtime mapping; do not add a second copy of an already-authored yaw. The preview robot is a static original-mesh snapshot in an illustrative, grounded pose, not the runtime initial state.

Example from an existing USD stage:

```python
from pxr import UsdGeom
root = UsdGeom.Xform.Define(stage, '/World/ExperimentVisuals').GetPrim()
root.GetReferences().AddReference('/absolute/bundle/BaseEnvironment.usdc')
```

For a full candidate reference, replace the filename with `01_vial_placement/Experiment.usdc`. If the runtime already supplies its vial/rack, use the base environment or deactivate `/World/ExperimentVisuals/Experiment` to prevent duplicates. Hide a coincident workshop floor's *visual* surface to avoid z-fighting; preserve needed physics until the runtime replaces it deliberately.

Cameras are `/TrainingScene/Cameras/Camera_Front/Camera_Front` and `/TrainingScene/Cameras/Camera_Overhead/Camera_Overhead` before referencing. Front position is `(0.70,-1.05,0.32)` m, aimed at `(0.12,0.035,0.12)`, 52 mm lens. Overhead is `(0.14,0.035,1.20)` m, straight down, 44 mm lens. Both use 36 mm horizontal aperture and 1440×900 output. Their transforms stay fixed across all six scenes. Use imported USD cameras directly: USD camera aperture/focal values use tenths of a stage length unit, so JSON millimeter values must not be copied blindly to USD attributes.

## Rebuild

Verified with Blender **4.5.9 LTS**, Python 3.12 and `usd-core` 26.11. Blender requires no third-party Python modules. The source downloader and mesh snapshot utility run in ordinary Python; no simulator installation is needed to regenerate visuals.

Run these commands from the bundle `source/` directory (or this repository directory).

```sh
python3 -m venv work/usd-venv
work/usd-venv/bin/pip install usd-core==26.11
python3 fetch_assets.py /absolute/bundle
work/usd-venv/bin/python make_static_visual.py /absolute/bundle/assets/SO-ARM101-USD-NO-CAMERA.usd /absolute/bundle/assets/Robot_STATIC_ART_ONLY.usdc
work/usd-venv/bin/python make_static_visual.py /absolute/bundle/assets/Vial.usda /absolute/bundle/assets/Vial_STATIC_ART_ONLY.usdc
work/usd-venv/bin/python make_static_visual.py /absolute/bundle/assets/Vial_rack_simple.usda /absolute/bundle/assets/Rack_STATIC_ART_ONLY.usdc
blender -b -t 8 --python build_candidates.py -- --out /absolute/bundle --render
work/usd-venv/bin/python finalize_exports.py /absolute/bundle
blender -b -t 8 --python roundtrip_check.py -- /absolute/bundle
work/usd-venv/bin/python validate_usd.py /absolute/bundle/01_vial_placement/Experiment.usdc --require-self-contained
```

Use `--only 1` through `--only 6` to rebuild one candidate. Without `--render`, Blender saves/exports assets only. Copy `experiments.json`, this README, attribution and integration review alongside generated assets. The download receipt pins and hashes all upstream files; source XML is archival/reference material, never executed by this pipeline.

## Compatibility and evidence limits

- Environment files use constant `UsdPreviewSurface` materials; no shader-node baking or missing texture references. Glass uses an explicit alpha approximation in USD. Cycles transmission/refraction will differ in Isaac; inspect transparent receivers there.
- Lighting is neutral `UsdLux` area lighting. Exposure, intensity, tone mapping and glass sorting may differ in Isaac. Emissive or colored surfaces never implement science.
- Apparatus needs purpose-built collider proxies. A solid convex hull over a rack/receiver opening will make placement impossible. Water geometry must not become a solid contact surface.
- Lever requires a revolute joint and loading lock; friction requires explicit effective contact parameters; density and pH require versioned analytic models labeled `MODEL-PREDICTED`.
- Camera HUD titles/evidence labels exist only in the Blender art project. They are not in USD and must not enter training observations. Keep evaluator conditions, expected outcomes and hidden state out of policy prompts and camera-only observation channels.
- `INTEGRATION_REVIEW.md` records the actual current stack seam and gaps. `backend_factory` injection is available; a simulated backend, new experiment skill scopes, simulated evidence promotion and generic skill compilation are not established by these assets.

## Verification

`validation_summary.json`: base plus six candidate USDs pass explicit meters/Z-up/defaultPrim, topology, finite bounds, universal PreviewSurface materials, no unresolved/external dependencies, and no authored physics/articulation checks. `blender_roundtrip_validation.json`: all six candidate USDs import into fresh Blender scenes with both cameras. Separate per-asset reports retain warnings and detailed geometry.

These checks establish portable visual structure, not Isaac compatibility, successful manipulation, scientific validity or improvement of the real system. Actual execution receipts and videos remain the runtime agent's evidence.
