# Stirred versus still dissolution

Run from the repository root with the project's simulation environment:

```bash
PYTHONPATH=simulation python simulation/lab_demos/dissolution/run.py \
  --output-dir simulation/lab_demos/dissolution/evidence/run --speed 4
```

This writes `dissolution.mp4` (1280x720, 24 fps), representative frames, a JSON summary, and a timestamped trace. `--speed` controls the labeled time-lapse rate; the elapsed-time overlay remains in model seconds. Add `--negative-control` to run the same arm motion while suppressing switch activation. In that run, both samples use the still-water rate and the result reports no stirring advantage.

## Model and policy

The policy is a deterministic state machine that moves a licensed SO-101 model through home, above-switch, press, retract, and home waypoints. It uses MuJoCo position actuators and measured joint positions with position tracking during each move. Targets are solved by bounded least squares against the measured end-effector site. Switch engagement occurs only when that site enters the switch's geometric press zone; no object is attached and no arm/sample teleport is used. The simulator runs `mj_step` throughout the robot motion and the timed comparison. This is an actuated simulation, not a learned policy.

The two vessels begin with equal normalized solid-sugar doses and 80 mL clear water each. Their stationary stir bars are identical; after actual geometric switch engagement, the stirred bar's orientation is animated as a visual cue. Dissolution is an analytical first-order model, `remaining fraction = exp(-integrated k dt)`: still water has `k=0.004 s⁻¹`, and the stirred vessel uses `k=0.030 s⁻¹` after activation. The displayed grains shrink with modeled remaining mass. To keep the contents visible in MuJoCo, the beakers use thin thin transparent wall panels and rims with a faint water surface instead of nested translucent cylinders. The model assumes constant ambient temperature and fixed rates; it does not simulate fluid motion, sugar crystal geometry, heat transfer, or measured material data. It preserves a clear-water appearance rather than depicting cloudiness. The bar animation is visual and does not generate fluid dynamics.

The negative control disables the switch event and applies the same baseline rate to both vessels. Tests cover the rate transition, conservation bounds, and equality in the disabled-action case. The main run's JSON also records joint bounds, finite state, reach error, engagement, matched dose/time and final comparison criteria.

## Limits

The robot model is the repository's placeholder SO-101 configuration. The press trigger is a geometric end-effector distance threshold, not collision/contact validation of a traveling button. The policy is scripted waypoint control, not learned. The chemistry and bar rotation are analytical/visual simplifications. Nothing in this demo commands physical hardware.
