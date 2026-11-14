# Six classic laboratory experiment scenes

One experiment per practical bench. These editable Blender assets supersede the earlier friction, lever and simple sorting candidates. They are **ART PREVIEW** assets: colored liquids, endpoints, particles and scientific readouts show illustrative outcomes, not executed chemistry or measurements.

| Scene | What an onlooker should recognize | Scientific response requiring implementation |
| --- | --- | --- |
| Serial dilution | Deep blue solution becomes progressively paler across a row | Conserved volume and concentration model, transfer and mixing |
| Titration | Burette drips into a conical flask until a pink endpoint | Dosed volume, mixing, specified titration/indicator response |
| Color comparison | Unknown sample is compared with light-to-dark standards | Optical/concentration model and independent sensor readback |
| Dissolution | Equal solid samples dissolve at different rates when stirred | Dissolution kinetics and controlled comparison |
| Filtration | Dirty water enters a paper funnel; clearer water collects below | Particle capture/transport model; clarity is not potability |
| Precipitation | Combining clear solutions produces cloudy solid | A specified reaction/yield/particle appearance model |

## Files

The downloadable bundle includes the editable Blender projects. The Git branch keeps sources, USDs, preview images, and manifests; regenerate the Blender projects from `build.py` when using only the checkout.

Each numbered directory contains `Scene.blend`, `Environment.usdc`, actual Blender renders (`Front.png`, `Overhead.png`, `Result.png`), `build.py`, `manifest.json`, and `EXPERIMENT.md`. Live scene objects and materials are editable. The environment USD excludes the static robot and has no active physics. Static original SO-101 meshes appear only in the Blender preview; the existing runtime articulation stays authoritative.

`assets/Robot_STATIC_ART_ONLY.usdc` contains static, white, camera-free original NVIDIA workshop geometry for regeneration. Licensing and source attribution accompany it. No original mechanical robot was rebuilt. New apparatus geometry is procedural; individual experiment notes identify any additional sources.

## Common interchange contract

Meters, right-handed Z-up, tabletop z=0. Table is 1.00 × 0.75 m and 44 mm thick below the work plane, centered at x=0.12, y=0. Floor top z=-0.76 m. Default environment prim `/ClassicLab`. Robot runtime reference base (-0.05,0,0); retain the runtime's authored orientation. Exact fixed front, overhead and result camera transforms are in each manifest.

Import only one scene at a time. Do not duplicate the existing articulated robot or coincident runtime floor. Camera views are deliberately external; there is no robot-mounted camera. Tall stands/reservoirs are passive fixtures, not a claim that the SO-101 reaches their tops. Active source, target and proposed fixture locations are documented per experiment; reach, grasp, collision and controller qualification remain outstanding.

`TableColliderProxy.usda` is an opt-in invisible guide mesh, not active physics. Detailed apparatus visual meshes and analytical response geometry are separate from physics. Receivers, funnels, tubing, glassware openings and moving mechanisms require purpose-built collision proxies and runtime physics. A solid convex hull across a vessel opening is not an acceptable replacement.

## Regeneration and validation

Use Blender 4.5 LTS and run an experiment's `build.py` according to its `EXPERIMENT.md` or `--help`. The shared robot source is in `assets/`. Regeneration does not require Isaac or an API key. Keep the exported USD beside its manifest and experiment notes.

`tools/validate_usd.py` checks USD metadata, geometry, dependencies, PreviewSurface materials and absence of physics schemas. Use a Python environment with `usd-core` installed:

```sh
python tools/finalize_usd_materials.py /absolute/path/to/classic_lab
python tools/validate_usd.py 01_serial_dilution/Environment.usdc --require-self-contained
blender -b -t 2 --python tools/check_blender_import.py -- /absolute/path/to/classic_lab
```

`tools/finalize_usd_materials.py` is a required post-export step. It authors explicit PreviewSurface opacity approximations for glass/clear liquids whose Blender transmission or mixed shaders otherwise export as opaque. The shipped USDs already include these changes; exact values are in `usd_opacity_fallbacks.json`. Blender renders retain their original materials.

Validation reports prove file structure and Blender import, not target-simulator rendering or an executed experiment. USD glass/transmission, liquid appearance, area-light exposure, tone mapping, and layered transparent surfaces can differ from Cycles. Inspect these in Isaac before final capture. USD colors or animation must never be interpreted as validated chemistry.

## Runtime and evaluation handoff

The separate actual Isaac two-mass block-transfer experiment is measured execution evidence. It does not validate these six environments. None of the six has an integrated runtime scientific response, contact-qualified controller or demonstrated application backend registration yet. No harness improvement is claimed.

Each experiment needs reset conditions, a bounded action sequence, independently read observations, success/failure criteria and a versioned science model where needed. Labels and camera-mounted title/provenance overlays are presentation assets. Expected results, hidden state and model oracle values must not leak into policy observations during evaluation. Any model-produced result must retain MODEL-PREDICTED provenance; observed simulation contact behavior remains SIMULATED, never physical evidence.
