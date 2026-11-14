# Dissolution demo verification

- Positive video: `final/dissolution.mp4`, 1280x720, 24 fps, 45.54 s.
- Rendered and visually inspected first, middle, and final frames plus the three-frame contact sheet. Camera view keeps the complete SO-101 and both vessels visible.
- The SO-101's five joints are driven by MuJoCo position actuators with measured joint tracking and `mj_step`; no physical arm commands are sent. Waypoint errors at completion were below 0.051 rad; joint bounds and finite-state checks passed.
- The robot site entered the switch press zone at 1.62 s; event distance to the modeled switch top was 0.0179 m. The rate change is conditional on that event.
- After 180 s of common comparison time, modeled solid remaining was 48.68% still and 0.452% stirred. At 4x the comparison portion displays in 45 s; elapsed labels show model seconds.
- Disabled-action control: no engagement, 48.68% remaining in each sample, no stirred advantage.
- Three focused pytest checks pass.

The first-order kinetic rates and clear-water visual are declared analytical assumptions. The switch uses a geometric site-distance trigger, not a collision-validated button. The stir-bar spin is a visual cue; fluid motion and real dissolution are not simulated or measured. The waypoint policy is scripted, not learned.
