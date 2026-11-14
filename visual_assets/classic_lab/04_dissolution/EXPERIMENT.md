# Dissolving: stir versus still

**ART PREVIEW — MODEL-PREDICTED / ILLUSTRATIVE ENDPOINT.** This is a static, editable apparatus scene. The grains and 01:00 display are authored comparison cues, not a measured experiment, animation, fluid simulation, or successful robot execution.

The question is whether stirring changes how quickly sugar dissolves. Two identical open beakers sit at the same height. The teal station drives a stir bar; the amber station is an inert matched-height riser. **No heating is represented.** A large bed of distinct sugar grains remains in the still vessel; only three grains remain in the stirred vessel. Both liquids stay clear. The result cue is remaining visible solid, never cloudy water.

## Student variable and controlled conditions

| Condition | Mixing | Other represented conditions |
| --- | --- | --- |
| STIR | Magnetic bar driven | Same vessel, water fill, initial sugar dose, grain-size distribution, room temperature, and elapsed time |
| STILL | No mixing; identical bar remains stationary | Same controlled quantities |

Each beaker is approximately 94 mm outside diameter and 116 mm tall, with a 1.5 mm wall and 3 mm base. The liquid cylinder has radius 45.3 mm and depth 72 mm, representing approximately 464 mL. The nominal vessel capacity label is 600 mL. Graduation marks are visual guides, not calibrated measurements. Identical empty dosing cups are labeled “10 g START” to indicate the equal initial doses, already added in this endpoint scene. A single timer reads an **illustrative** 60 seconds; that duration does not predict complete dissolution for a real sample.

## High-level procedure

1. Set both identical vessels on their respective platforms. Put the same bar in each vessel; add equal room-temperature water volumes and prepare equal weighed sugar doses of the same grain size.
2. Add the two doses at the same starting time. Begin the shared timer and stir only the teal station, without heat.
3. At a common observation time, compare visible solids on the vessel bottoms. Repeat while holding initial dose, water volume, temperature, and grain size constant.
4. A fuller real experiment can record time until no visible solid remains, with the same observation criterion for both vessels. These rendered grains provide no calibrated dissolved mass or concentration.

## Robot and fixture requirements

The original camera-free SO-101 is included only as a static white preview in `Scene.blend`, at translation (-0.05, 0, -0.03008145) m with no added yaw. It is excluded from `Environment.usdc`. Runtime's nominal robot base remains (-0.05, 0, 0) m. Mechanical geometry is retained from the original asset; nothing here establishes reach, grip, collision clearance, or a working articulated controller.

The two beaker centers are (0.145, 0.075, 0.038) and (0.325, 0.075, 0.038) m at the bottom faces. The clear wall-to-wall gap is about 86 mm. Their rims are at z=0.154 m. The dosing cup handles start at (0.182, -0.105, 0.013) and (0.362, -0.105, 0.013) m; the latter is deliberately identified as requiring reach qualification. Handles have flat opposed +/-Y grip faces and dimensions 31 x 14 x 13 mm. Proposed handling clearance is 5 mm on each side and a 15 mm initial vertical lift; pouring approach proposes 25 mm above the rim. These are proposed fixture dimensions, not validated paths. Dose simultaneity likely needs a dual release fixture or measured, synchronized manual preparation; one static arm does not demonstrate simultaneous pours.

The beakers, bars, cups, and spoon are movable apparatus; the riser, stir plate, timer, bench, and lights are static fixtures during the experiment. Runtime should add appropriately chosen collision, mass, contact, reset, and controller representations. Do not assign robot motion directly from this render. Fixture calibration, spill handling, grip qualification, and observation calibration remain open.

## Authored geometry and missing science

All apparatus is procedural editable Blender geometry: open thin-walled beakers with pouring spouts, bottom disks, rims, graduated marks and clear fill; differentiated plate controls and power lead; identical PTFE bars; individual angular sugar grains; matching open dose cups with grasp handles; spoon and rest; shared timer; table and floor. Grains are deterministically arranged (135 still, 3 stirred) and enlarged for legibility. They are illustrative visual elements, not particle mass, molecule counts, calibrated sugar crystals, or simulated trajectories.

No dissolution kinetics, saturation model, diffusion or advection, water velocity field, temperature evolution, sugar surface-area evolution, particle transport, or mass conservation is implemented. Apparent grain loss and timer values are staged. A future science layer must couple an explicit validated model and observation definition to the scene; a rigid-body simulation alone cannot produce the science result.

For clear visibility through multiple surfaces, glass is an explicitly approximate alpha material (walls 0.09, rim 0.35), and water alpha is 0.025. There is no physical refractive optics. USD Preview Surface transparency support varies; downstream renderers may display the glass incorrectly if alpha blending is disabled. The scene uses no external image textures. Environment USD has no robot and no physics APIs.

## Regeneration and licenses

Run Blender 4.5 with `--background --threads 2 --python build.py -- --out <output-directory>` to rebuild the editable scene and environment. Add `--render` for all three renders, or `--render-only` to render the existing `Scene.blend`. The portable robot default is `../assets/Robot_STATIC_ART_ONLY.usdc`; `--robot <path>` overrides it. CPU rendering uses two threads and 48 denoised Cycles samples. Exact camera matrices, apparatus dimensions, and exported prim paths are in `manifest.json`.

New apparatus and source are procedurally authored for this project and include no downloaded textures or third-party apparatus models. The robot derives from the existing licensed original static workshop asset. Preserve the parent package's `assets/WORKSHOP_LICENSE`, `assets/THIRD_PARTY_NOTICES`, and `assets/source_receipt.json`; those files govern the original robot asset. This document does not replace its license.
