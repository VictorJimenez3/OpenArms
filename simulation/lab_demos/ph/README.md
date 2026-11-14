# Indicator pH simulation baseline

This optional Devpost/presentation simulation is outside the main architecture and acceptance requirements. It is not a Smartivity kit implementation. Scene version 2 uses neutral indicator identifiers; existing receipts retain their original identities and new reusable skills require fresh admission. The analytical color rules are unchanged.

The session backend uses the white SO-101, bench, pump and metered dropper from [titration](../titration/README.md), imported from source revision `16a975e`. The adaptation uses one fixed dropper and one stationary indicator dish. The source carries the selected prepared vinegar, water or dissolved baking soda sample. The receiver starts purple.

The arm follows a fixed approach, press, release and return path through MuJoCo position actuators. Each target has a five-second simulated deadline. The controller checks joint bounds and finite state every timestep and records measured joint positions, velocities summarized by their maximum, actuator commands and actuator forces at convergence. The measured gripper-frame position must reach within 14 mm of the paddle target after approaching from more than 28 mm away. This triggers one illustrative 0.12 mL dose. The color changes when the animated drop reaches the liquid surface. Vinegar yields pink, water remains purple, and baking soda yields blue in this teaching model. The disabled-action control drives the arm to the same targets and leaves the indicator purple.

The model uses illustrative joint poses, a geometric trigger, an animated drop and a qualitative indicator rule. It provides no calibrated pH, fluid dynamics, force-contact measurement or hardware qualification. The actuator forces in the trace are model outputs from the arm motors.

## Session integration

Run the existing gateway from the repository checkout with `OPENARMS_EXECUTION=mujoco` and `PYTHONPATH=agentic:simulation:.`. The worker imports this source tree and uses MuJoCo, NumPy, OpenCV, Pillow, ImageIO and ImageIO-FFmpeg. The checked-in SO-101 XML, mesh assets and block pose file are also required. The worker was verified with MuJoCo 4.0.1.

- `mock_prepared_sample` and the A/C route retain their wire meanings as aliases for a single dose from the fixed source into the receiver.
- `simulation` state and receipts identify `indicator_ph_metered_dropper`, scene version `2`, source revision `16a975e` and control mode `mujoco_position_actuator_feedback`. Successful execution includes the convergence and dose trace, live phase frames and a completed MP4. Artifact URLs still use the session's authenticated PNG and MP4 routes.
- Fresh 1280×720 captures rebuild the apparatus with the saved MuJoCo integration state and delivered-dose state. The scene service classifies receiver pixels only. The green dropper and gold dish base support localization within two fixed camera views. These are image-space detections for this scene.
- STOP cancels the isolated renderer and encoder process group. A stopped trial requires a fresh preparation before another execution or inspection.

The qualitative teaching rationale is documented in the [educational simulation research](../../../research/victor/educational-simulation.md).
