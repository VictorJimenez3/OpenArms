# Smartivity simulations

The standalone MuJoCo runner renders Erupting Volcano, Magic Potions 1 & 2, Lava Lamp, and Magic Snow. It uses the demo bench's ruler frame and wrist convention with activity-specific vessels and modeled material effects. The four scenarios run without a robot, camera, expert, or student app.

With the simulation package installed in the environment described in the [simulation setup](../README.md#setup), run:

```sh
python -m openarms_sim.smartivity_demo --out-dir /tmp/smartivity-nominal
python -m openarms_sim.smartivity_demo --scenario volcano --layout-seed 18 --spread-mm 15 \
  --out-dir /tmp/smartivity-seed-18
```

On a headless Linux machine with GPU rendering, set `MUJOCO_GL=egl` before running these commands. Use `--scenario` to run only `volcano`, `potions`, `lava_lamp`, or `magic_snow`. Without a scenario the runner renders all four. Each clip has a JSON receipt with the simulated result and ruler coordinates. Passing a seed and a spread of up to 18 mm reproduces the same per-axis station offsets. The runner checks the resulting simulated motion and transfer before writing the output.

The [published videos and receipts](../../research/joseph/smartivity-bench-alignment-2026-11-15/README.md) include the nominal runs and two seeded examples from `a5a2b20`. They show simulated motion and effects. Physical bench registration and chemistry require separate qualification.
