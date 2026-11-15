# Smartivity presentation simulations

These three activities come from Smartivity’s *My First Science Kit*. All exports are 1280×720 at 30 fps. They show simulated arm motion and illustrative reactions.

| Activity | Booklet pages | Motion source | Video |
| --- | --- | --- | --- |
| Erupting Volcano | 26–27 | Recorded OpenArms expert policy, seed 18 | [28.00 s MP4](evidence/Volcano-own-policy.mp4) |
| Magic Potions 1 & 2 | 30–33 | Recorded OpenArms expert policy, seed 0 | [29.97 s MP4](evidence/Magic-Potions-1-and-2-own-policy.mp4) |
| Lava Lamp | 38–39 | Scripted MuJoCo pick, pour, dock and retract | [28.43 s MP4](evidence/Lava-Lamp.mp4) |

Volcano and Potions come from the `codex/smartivity-volcano` handoff at `90fac47`. The archived simulator states, minimal episode receipts and Potions preparation states are included for replay. Lava Lamp models preloaded red baking-soda solution under oil. The arm dispenses a normalized acid dose from a simulated beaker. The booklet uses a spoon and gives no acid quantity. The grain and droplet motion is illustrative. See the [Lava Lamp render receipt](evidence/Lava-Lamp.video.json) for the transfer checks.

## Render on a Linux GPU

From the repository root, in a Python 3.12 environment with a GPU allocated, install the simulation package and use MuJoCo's EGL backend. The original renders used MuJoCo 4.0.1 and an RTX 4500 Ada on iLab.

```sh
python -m pip install -e simulation 'mujoco==4.0.1'
export MUJOCO_GL=egl

python -m openarms_sim.smartivity_video simulation/smartivity/evidence/volcano \
  --out /tmp/smartivity/Erupting-Volcano.mp4
python -m openarms_sim.smartivity_video simulation/smartivity/evidence/potions \
  --out /tmp/smartivity/Magic-Potions.mp4
python -m openarms_sim.smartivity_lava_video --out /tmp/smartivity/Lava-Lamp.mp4
```

These commands need no expert credentials. The first two replay recorded states, and Lava Lamp runs the scripted scene before rendering. Each writes a JSON receipt beside the MP4.

To capture fresh Volcano or Potions policy trials, run `python -m agentic.openarms_lab.smartivity` with a configured expert, `--scenario volcano` or `--scenario potions`, and `--capture-only`, then pass the resulting episode directory to `smartivity_video`.
