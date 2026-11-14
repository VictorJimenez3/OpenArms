# SO-101 one-step dilution

Run from the repository root with the shared MuJoCo environment:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 PYTHONPATH=simulation \
  python \
  simulation/lab_demos/dilution/run.py \
  --output-dir simulation/lab_demos/dilution/evidence/final --speed 1
```

Use `--speed 2` or `--speed 4` for accelerated playback; the trace timestamps
remain in simulation seconds. `--disable-action` runs the
negative control: the same motion policy omits dispenser engagement, so the
sample remains unchanged. The video is 1280x720 at 30 fps and labels accelerated
playback speed.

## Demo and model

Two matching 20 mL blue-dye samples begin at the same modeled concentration.
The SO-101 position actuators follow a deterministic quintic waypoint policy:
folded home, approach a fixed plunger, press, retract, and folded home. A measured
`gripperframe` site is compared with a fixed geometric engagement target during
the press phase. The analytical dispenser supplies one 20 mL
dose over 0.65 s of engagement (30.77 mL/s), capped at 20 mL. The measured site remained inside the engagement threshold long enough to deliver the capped dose. A fixed outlet is positioned above the
treated vessel; no cup is picked up or poured.

Liquid volume and color are an analytical visualization. It assumes additive
volumes, instant homogeneous mixing, no evaporation or spill, and conserved dye
mass. Relative concentration is `C_final = C_initial * V_initial /
(V_initial + V_water)`. Here it falls from 1.00× to 0.50×; the untouched control
stays at 1.00×. It is not a fluid simulation or a calibrated optical reading.

## Evidence and limits

`evidence/final/` contains the MP4, first/press/final renders, contact sheet,
event trace and quantitative summary. `evidence/negative-control/summary.json`
records the disabled-action run. Joint bounds, finite joint values, geometric
button engagement, return-home error, dose, concentration, and dye-mass
conservation are checked or recorded.

The arm uses MuJoCo position actuators and measured joint/site state in the
feedback loop. Waypoints and fixture locations are placeholders and are not
real-arm calibrated. Button engagement is a geometric site threshold, not
contact-validated button mechanics; liquid transfer and mixing are analytical.
This is a deterministic scripted policy, not a learned policy. The run does not
validate collisions, flow, or an actual laboratory experiment.

Integration review corrected the milliliter-to-cubic-meter conversion for liquid height, reset the IK scratch pose before runtime, and stopped the visible stream after the capped dose. The positive and disabled-action recordings were regenerated; both numerical results remain consistent.
