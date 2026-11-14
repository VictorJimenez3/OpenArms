# Dirty water filtration

One classic experiment: does folded filter paper retain coarse suspended particles? A brown, visibly gritty feed beaker sits beside two identical clamped glass funnels. White paper in the left funnel carries brown residue and drains much clearer liquid into its flask; the right funnel has no paper and drains brown liquid. Both stand in one practical spill tray. The contrast is staged and model-predicted, not an executed filtration result.

## Two meaningful conditions

The student changes **paper present versus paper absent**. Use aliquots from the same stirred, benign water-and-insoluble-particle mixture, identical funnels and collectors, equal starting volume, and a matched observation interval. The scene illustrates coarse brown particles large enough to be retained by the chosen paper. Fine particles can pass, and real clarity depends on the actual paper and particle distribution.

Compare collected liquid using a consistent backlit target or a calibrated turbidity measurement. Record visible retained residue as a second observation. “Clearer” is a relative optical observation: the scene does not establish clean drinking water, microbial safety, or removal of dissolved material.

## Proposed supervised procedure

1. Seat empty collecting flasks in their locating nests. Clamp both funnels and fit folded paper in the left funnel. Check that each stem is centered above its receiver.
2. Stir the prepared suspension immediately before taking each matched aliquot so settling does not become an unintended variable.
3. Deliver equal aliquots slowly to each funnel, keeping the liquid below the paper edge. A human sets up the paper, stands and glassware; robotic pouring is only a proposed later capability.
4. Allow drainage for the same observation period. Compare the collected liquid and inspect residue on the paper.
5. Record the condition and measurements. Dispose of the benign demonstration mixture appropriately and rinse the apparatus.

## Geometry and handling

All geometry is in meters, Z up, with tabletop at Z=0. The table is 1.00 × 0.75 × 0.044 m centered at (0.12, 0, -0.022). The shared spill tray is 0.365 × 0.275 m, centered at (0.300, 0.165). Its rim reaches Z=0.029.

| Item | Position and dimensions | Proposed interaction |
|---|---|---|
| Dirty input beaker | Center XY=(0.115,-0.155), bottom Z=0.013, outer radius 0.042, lip Z=0.118 | Grip the narrow collar-attached lug's opposing rubber pads at (0.043,-0.166,0.067) and (0.043,-0.144,0.067). Each face is 24 × 19 mm; nominal outside span 22 mm. |
| Paper station | Center XY=(0.235,0.155); flask bottom Z=0.027, lip Z=0.148 | Passive receiver in a teal locating nest. Proposed pour target (0.235,0.155,0.278). |
| No-paper control | Center XY=(0.405,0.155); same flask dimensions | Passive control receiver in an ochre locating nest. Proposed pour target (0.405,0.155,0.278). |
| Funnels | 114 mm outer rim diameter; stem tip Z=0.158, rim Z=0.273 | Statically clamped; robot should not grasp the thin glass cone. Effective proposed pour opening radius 47 mm. |
| Collecting flasks | 96 mm widest diameter; 121 mm height | Empty-flask placement could grasp exterior neck radius 16 mm at Z=0.115–0.138, before funnel installation. |
| Stand | Post center XY=(0.322,0.265), diameter 12 mm, top Z=0.357 | Fixed support with rings, connecting arms, tightening knobs and weighted foot. |

The existing SO-101 visual is imported unchanged from the provided original static asset, translated by (-0.05,0,-0.03008145), without extra yaw or an added camera. It appears only in `Scene.blend`. Its pose is illustrative. The runtime base reference is (-0.05,0,0).

**Robot qualification remains pending.** The narrow 22 mm grip lug is a proposed collar adaptor requiring fabrication and load testing; the glassware payload and gripping force are unqualified, the control station is farther from the nominal manipulation area, and a 278 mm pouring target is taller than ordinary pickup heights. A fixture-mediated dispenser or supervised human pour may be needed. Proposed approach clearance is 20 mm at the lug; this has not been collision-checked. Do not interpret this asset as a validated robot plan.

## Art and runtime boundary

Brown liquid, discrete coarse particles, retained grit, much clearer liquid and falling droplets are authored static meshes. The source beaker and both receiving volumes coexist as an explanatory staged state; volume conservation is not modeled. The droplets are frozen snapshots, not animation. No physics, collisions, rigid-body masses, fluid transport, porosity, filter flow rate, turbidity sensor or control policy is included. A runtime must supply and validate these separately, including reset conditions and observation criteria.

The open-wall beaker, shaped spout, rear handle, grip collar, hollow-stem funnels, folded paper, flask walls and lips, graduation ticks, locating nests, anti-roll stirrer rest, clamps and spill tray are editable authored Blender geometry. White paper with dark grit communicates retention without reliance on the short condition labels.

Glass deliberately uses a Transparent/Principled shader mix with opacity 0.13; outlines use 0.58 and clear-liquid geometry 0.42. This visibility approximation avoids strong refraction hiding the experiment. USD Preview Surface support for the mix is limited: a consuming renderer can make it more opaque or change appearance. No textures or external geometry dependencies are needed in `Environment.usdc`. Labels and rods are exported as meshes.

## Files and regeneration

`build.py` builds the editable scene and robot-free USD. Run with Blender 4.5 or newer using `--python build.py -- --out OUTPUT_DIRECTORY`; append `--render` for all three views. Use `--render-only` to render the saved `Scene.blend`. Default robot path is `../assets/Robot_STATIC_ART_ONLY.usdc`; `--robot PATH` overrides it. The fallback source path is documented in the build for the original production workstation. CPU rendering uses two threads, 40 samples and 1600 × 1000 resolution.

`manifest.json` contains exact object matrices, dimensions, camera transforms and staging assumptions. `validate.py`, run using Python with USD bindings, adds independently inspected actual USD prim paths and produces `validation.json`. It distinguishes missing render review from completed checks.

The geometry authored here is original procedural production work. The preview robot is the previously supplied original licensed robot mesh asset, not a remodeling; its upstream license and provenance are retained in the shared asset package (`WORKSHOP_LICENSE`, `THIRD_PARTY_NOTICES`, `source_receipt.json`). No robot geometry is distributed inside the environment USD.

## Final layout correction

The complete passive filtration rig (tray, funnels, stand, receiving flasks, samples and attached labels) is translated +0.10 m along Y from its first draft to clear the original static preview arm. The source cup remains at its original front position. Final funnel axes are (0.235, 0.155) m and (0.405, 0.155) m; pour-target height is 0.278 m. The stand axis is (0.322, 0.265) m. The final manifest and USD contain the updated world transforms. This removes the observed art-preview overlap; it does not qualify a runtime approach path.
