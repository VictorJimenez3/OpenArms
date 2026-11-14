# Tiny titration run report

**Run status:** successful deterministic MuJoCo actuator simulation; initialized at HOME with both sample wells at zero delivered dose (captured in `summary.json`). The positive policy took 32.848 simulated seconds. The video is 1280×720 H.264 at 30 fps, 34.1 seconds, 1.33 MB. Playback label is 1× simulated duration.

| Prepared sample | Modeled neutralization equivalent | Dose count | Dose volume | Observed endpoint |
| --- | ---: | ---: | ---: | --- |
| small, 5 mL | 0.50 normalized units | 6 | 0.72 mL | persistent faint pink |
| large, 8 mL | 0.80 normalized units | 9 | 1.08 mL | persistent faint pink |

The finite drop count and color response follow actual paddle engagements, not video time. The endpoint requires repeated readings without an additional dose. A disabled-action negative control moved the arm through the same path, recorded zero dose events in either trial, and reached no endpoint.

The SO-101 runs through MuJoCo position actuators and joint-state feedback with per-joint range and finite-state checks. Pump activation is a 14 mm geometric gripper-frame engagement trigger, not force contact. The small blue droplet animation and visible fill increment follow each triggered action. Joint targets remain inherited placeholder poses, so reachability is validated only against this model; this is not a real-arm or force-contact qualification. Chemistry assumes stoichiometric normalized neutralization and a fixed 0.12 mL / 0.10-equivalent drop. Colors are illustrative and are not calibrated pH or indicator measurements.

The test file has two passing checks covering both endpoints, dose totals, and the action-disabled control. See `summary.json` and `trace.json` for full state, policy timeline, action events, and measurement observations.
