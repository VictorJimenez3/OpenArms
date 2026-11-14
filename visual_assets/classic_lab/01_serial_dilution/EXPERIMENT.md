# Serial dilution — a blue solution fades in five measured steps

A deep-blue stock flask and five graduated glass beakers show an unmistakable blue-to-nearly-clear sequence. The same 50 mL volume remains in every beaker. The short instruction card and the rack's 1:2, 1:4, 1:8, 1:16, 1:32 labels expose the repeated operation. The removable 50 mL syringe, guide stand, water reservoir, clean tips, stirring rod and five-position cradle form one experiment.

**Evidence:** All images are actual Blender renders. The visible endpoint is **ILLUSTRATIVE / MODEL-PREDICTED** colored water, authored as geometry and materials. There is no fluid dynamics, executed robot motion, measured concentration, calibrated optical response or demonstrated reach.

## Student action and observation

Use benign food-coloring stock and water as the conceptual materials. Preload each beaker with 50 mL water. Transfer 50 mL stock to vessel 01, mix uniformly, then transfer 50 mL of that mixture to vessel 02. Mix before repeating through vessel 05. Remove 50 mL from the last beaker to leave equal 50 mL volumes throughout. The displayed scene depicts that completed endpoint, with the syringe parked over vessel 02. A removable tip/syringe must be rinsed or exchanged appropriately; the preview contains clean tips but does not simulate contamination.

The student changes the transfer-to-water volume ratio while keeping the number of steps fixed. Two meaningful model conditions:

- **Condition A, shown:** 50 mL transfer into 50 mL water. Relative concentrations after five steps are 0.5, 0.25, 0.125, 0.0625 and 0.03125.
- **Condition B, comparison:** 25 mL transfer into 50 mL water. Relative concentrations are 1/3, 1/9, 1/27, 1/81 and 1/243. Discard/transfer 25 mL at each step to leave 50 mL for observation; use a suitable measured 25 mL dose.

Observable: concentration versus step number, inferred qualitatively from diminishing blue intensity or measured by a separately specified, calibrated optical instrument. The general perfectly mixed bookkeeping model is `C_next = C_previous × V_transfer / (V_transfer + V_water)`. Render colors exaggerate visual separation and must not be read as a linear concentration or absorbance scale.

## Runtime handoff

The environment uses metres, Z up, tabletop z=0. Table dimensions are 1.00 × 0.75 × 0.044 m, centered at (0.12, 0, −0.022). `/ClassicLab` is the default prim. See `manifest.json` for exact measured-export prim paths, object transforms, vessel dimensions and cameras.

The five vessel assemblies are intended movable; their contained illustrative fluid meshes travel as part of the visual assembly and are not physical fluid. The rack, printed labels, stand base/upright and bench are intended static. Syringe and plunger require separate future articulation and dosing ownership. Stock and water reservoirs are passive fixtures in this composition. The guide pose alone does not define a valid actuation axis, controller, force limit or reliable dosing mechanism.

Potential beaker grasp band: smooth outer cylindrical wall, nominal 45.6 mm outer diameter, z=0.064–0.084 m, avoiding spout/rim and printed graduation regions. Adjacent centers are 70 mm apart; nominal glass-to-glass gap is 24.4 mm. This is geometric clearance only; required jaw dimensions and approach collision clearance have not been qualified. The syringe thumb flange is 34 mm diameter at z=0.258 m; its height and some outer station positions exceed the preferred small-arm work zone. A lower or relocated fixture, indexed rack, or revised station placement is required before reach can be claimed. Do not interpret static robot proximity as proof.

Missing runtime components: original articulated SO101 robot, collision shapes, mass/inertia, suitable grasp/fixture constraints, valid contact and joint limits, reset/randomization, measured dosing and mixing state, controller/planner, optical observation model, validation and success criteria. No physics APIs are authored here. The robot is present only in the editable preview and is absent from `Environment.usdc`.

## Rebuild and provenance

Run Blender with `--background --threads 2 --python build.py -- --out OUTPUT_DIRECTORY --robot ../assets/Robot_STATIC_ART_ONLY.usdc --render`. The script defaults to the robot asset beside the experiment directories under `../assets/`. No third-party Python packages are required inside Blender.

All apparatus, bench, text, materials, camera and lighting geometry were procedurally authored for this visualization. The static original SO101 geometry is imported unchanged from the supplied licensed workshop asset; no robot-mounted camera is added. See `../assets/WORKSHOP_LICENSE`, `../assets/THIRD_PARTY_NOTICES` and `../assets/source_receipt.json` in the shared package. The original robot is positioned at (−0.05, 0, −0.03008145) without additional yaw. Runtime robot base reference is (−0.05, 0, 0).

`Environment.usdc` is self-contained and contains no external asset or texture references. The preview deliberately uses 18% alpha glass with moderate transmission to keep the colored-water outcome readable, rather than claiming calibrated optics. Flat profile transitions prevent incorrect smooth cap/rim normals. Blender's USD Preview Surface material export does not preserve all Cycles glass/refraction behavior. The renders and editable Blender scene are the visual reference; test glass, transparency and color separately in the target renderer. Camera-space provenance annotations appear only in the Blender preview.
