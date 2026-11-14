# Dissolution demo verification

- Positive video: `final/dissolution.mp4`, decoded as 1280x720 at 24 fps, 45.54 s. The rerender preserves the existing actuated SO-101 policy and 180 s common comparison interval.
- Decoded first, middle and final frames from the encoded MP4 were inspected individually. All show the full SO-101 and both samples. Open glass edge rods and rims expose a faint clear-water surface and visibly separated amber sugar grains. Initial grains are plainly visible in both beakers; the 90 s frame shows a visibly reduced stirred dose while the still beaker retains grains; the 180 s result still has visible grains in the still beaker and a visible stir bar in the stirred beaker. The regenerated three-frame contact sheet is `final/contact-sheet.png`.
- Lighting was reduced and the camera moved closer and more overhead. No control, policy, model-time, kinetic-rate, or disabled-action behavior changed.
- The SO-101's five joints are driven by MuJoCo position actuators with measured joint tracking and `mj_step`; no physical arm commands are sent. Waypoint errors at completion were below 0.051 rad; joint bounds and finite-state checks passed.
- The robot site entered the switch press zone at 1.62 s; event distance to the modeled switch top was 0.0179 m. The rate change is conditional on that event.
- After 180 s of common comparison time, modeled solid remaining was 48.68% still and 0.452% stirred. At 4x the comparison portion displays in 45 s; elapsed labels show model seconds.
- Disabled-action control: no engagement, 48.68% remaining in each sample, no stirred advantage. Numerical control evidence is unchanged from the prior validated run because this revision changes scene geometry, lighting and camera only.
- Focused pytest checks: 3 passed. Video stream checked with `ffprobe`.

The first-order kinetic rates and clear-water visual are declared analytical assumptions. The glass is represented with thin open edge geometry for legibility; this is a visualization, not an optical or fluid simulation. The switch uses a geometric site-distance trigger, not a collision-validated button. The stir-bar spin is a visual cue; fluid motion and real dissolution are not simulated or measured. The waypoint policy is scripted, not learned.
