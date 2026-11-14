# Asset attribution

## Original robot and labware geometry

NVIDIA **Sim-to-Real SO-101 Workshop**, pinned commit `ce807d99724cb65671abec01f908a2fcb4a6eab7`:
https://github.com/isaac-sim/Sim-to-Real-SO-101-Workshop/tree/ce807d99724cb65671abec01f908a2fcb4a6eab7

Inputs: `SO-ARM101-USD-NO-CAMERA.usd`, `Vial.usda`, `Vial_rack_simple.usda`. Workshop Apache-2.0 license and full third-party notices are included under `assets/WORKSHOP_LICENSE` and `assets/THIRD_PARTY_NOTICES`.

Modifications for static art: evaluated original mesh transforms baked into independent visual meshes; physics/MDL networks omitted; printed parts colored white and motors/hardware kept dark; robot placed in an illustrative grounded pose. No mechanical geometry was modeled from scratch. The active runtime must retain the original articulated robot. Vial/rack retain original geometry; Blender adds a blue cap marker and simple source/target labeling for clarity.

## Google DeepMind source located at the user's request

Google DeepMind **MuJoCo Menagerie / robotstudio_so101**, pinned commit `370c43965323c0944b433b202aac5058b5f907a9`:
https://github.com/google-deepmind/mujoco_menagerie/tree/370c43965323c0944b433b202aac5058b5f907a9/robotstudio_so101

Apache-2.0; complete model source and license included in `assets/google-deepmind-so101/`. Its README traces the model to The Robot Studio's SO101 new-calibration description and lists Google's collision/actuator/camera-mount changes. It is supplied as the requested authoritative comparison source. **It is not silently substituted for the NVIDIA Isaac articulation, and its camera-mount geometry is not used in these previews.** No MuJoCo runtime was installed or run for this task.

Google DeepMind's Playground also documents SO-101 workflows:
https://github.com/google-deepmind/mujoco_playground

LeRobot itself is Hugging Face's open-source project:
https://github.com/huggingface/lerobot

## Original OpenArms assets

Workbench, floor, sample carriers, trays, water receivers, ramp, lever, indicator-tab fixture, labels, lighting and camera compositions were procedurally created for this task. No stock photos, HDRIs or external texture packs are used. Labels use Blender's built-in font; exported USD labels are mesh geometry. Blender 4.5.9 LTS was used for modeling and Cycles renders.

`assets/source_receipt.json` records exact upstream download URLs and SHA-256 hashes. `checksums.sha256` records the final delivered files separately.
