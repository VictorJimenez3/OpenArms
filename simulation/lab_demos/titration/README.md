# Tiny titration

A compact, rendered SO-101 titration teaching demonstration. Two prepared sample amounts are dosed by a fixed metered dropper. The arm repeatedly approaches and presses a paddle, returns to release it, observes the modeled indicator, and returns home. The second trial uses the larger prepared amount.

## Run

From the repository root:

```sh
OMP_NUM_THREADS=2 PYTHONPATH=simulation /Users/joeroche/Documents/Codex/2026-11-14/view-x20/work/mujoco-venv/bin/python simulation/lab_demos/titration/run.py --output-dir simulation/lab_demos/titration/evidence --speed 1
```

`--speed` labels the playback multiplier (1 is the simulated duration); the timeline and logged chemical observations use MuJoCo simulated seconds. `--negative-control` executes the same robot motion while disabling dose delivery. `--no-render` runs the policy and writes JSON without creating a video.

## Model and interpretation

- The SO-101 MuJoCo model uses its position actuators and feedback: each waypoint is held until measured joint error converges. A dose event occurs only when measured gripper-frame position is within 14 mm of the prepared paddle target. This is a geometric engagement trigger, not simulated force contact or calibrated pump mechanics.
- Two static, pre-mixed sample wells represent 5 mL and 8 mL teaching samples with normalized neutralization equivalents 0.50 and 0.80. The fixed dropper delivers 0.12 mL / 0.10 normalized base equivalent per paddle action.
- The indicator teaching rule shows blue-gray at or below the neutralization equivalent, faint pink for positive excess up to 0.10, then progressively darker pink for larger excess. Two repeat readings at 0.2 simulated seconds apart must remain faint pink before the policy stops. A finite 13-dose cap prevents unbounded dosing. This is a normalized stoichiometric / illustrative optical model, not a pH simulation or calibrated indicator response.
- The actual delivered-dose trajectory causes the color change; no animation timer changes sample chemistry. There is no handheld glassware, grasped object, force sensor, fluid dynamics, droplet breakup, or wet chemistry.
- Robot motion is dynamically stepped through MuJoCo position actuators. Pose targets and joint map remain inherited illustrative placeholders; this is not a physical-arm qualification and there are no physical robot commands.

## Evidence

`evidence/summary.json` reports trial outcomes, assumptions, bounds and success; `trace.json` records dose events and readings; `titration.mp4` is the rendered output. Small trial reaches persistent faint pink after 6 × 0.12 mL; the large trial after 9 × 0.12 mL. Their one-drop endpoint excess is within the stated model band. The negative control has zero dose events, no endpoint, and unchanged sample appearance.
