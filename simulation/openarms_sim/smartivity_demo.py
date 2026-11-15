"""Render Smartivity demonstrations on the standalone OpenArms demo bench."""
import argparse
from contextlib import closing
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from .smartivity_lava_video import render_lava_lamp
from .smartivity_layout import demo_layout
from .smartivity_snow_video import render_magic_snow
from .smartivity_video import FPS, render_movie
from .smartivity_world import POTION_STEPS, World

VIDEOS = {
    "volcano": "Volcano",
    "potions": "Magic-Potions",
    "lava_lamp": "Lava-Lamp",
    "magic_snow": "Magic-Snow",
}
RENDERERS = {
    "lava_lamp": render_lava_lamp,
    "magic_snow": render_magic_snow,
}


def render_transfer(scenario, output, layout):
    """Record a fresh, scripted transfer for Volcano or Magic Potions."""
    with closing(World(scenario=scenario, layout=layout)) as world:
        preparation = []
        if scenario == "potions":
            preparation.append((world.preparation_stage, world.visual_state()))
            for step in POTION_STEPS:
                world.prepare(step)
                preparation.append((world.preparation_stage, world.visual_state()))

        frames = [(world.sim_time, None, world.visual_state())]

        def tick(action):
            world.tick()
            fault = world.proprioception()["fault"]
            if fault:
                raise RuntimeError(fault)
            if world.sim_time + 1e-9 >= len(frames) / FPS:
                frames.append((world.sim_time, action, world.visual_state()))

        if not preparation:
            for _ in range(round(1.0 / world.timestep)):
                tick(None)
        for action in ("pick", "pour", "return_cup", "home"):
            world.start(action)
            while world.busy:
                tick(action)
        for _ in range(round(1.6 / world.timestep)):
            tick(None)

        result = world.evaluate()
        if not result["success"] or result["collisions"] or result["spilled_ml"] > 1e-6:
            raise RuntimeError(f"Transfer failed the simulation outcome checks: {result}")
        title = "Erupting Volcano" if scenario == "volcano" else "Magic Potions 1 & 2"
        receipt = render_movie(world, frames, output, title=title, mode="scripted_simulation",
                               episode_id=uuid4().hex, preparation=preparation)
        return {**receipt, "evaluation": result}


def render_demo(scenario, out_dir, layout):
    output = out_dir / f"{VIDEOS[scenario]}.mp4"
    if scenario in RENDERERS:
        receipt = RENDERERS[scenario](output, layout=layout)
    else:
        receipt = render_transfer(scenario, output, layout)
    receipt["bench_layout"] = layout.receipt()
    output.with_suffix(".video.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("all", *VIDEOS), default="all")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--layout-seed", type=int, default=0)
    parser.add_argument("--spread-mm", type=float, default=0.,
                        help="Maximum seeded displacement per ruler axis. Zero uses the demo bench.")
    args = parser.parse_args()
    try:
        layout = demo_layout(layout_seed=args.layout_seed, spread_mm=args.spread_mm)
    except ValueError as error:
        parser.error(str(error))
    scenarios = VIDEOS if args.scenario == "all" else (args.scenario,)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".smartivity-", dir=args.out_dir) as temporary:
        stage = Path(temporary)
        recordings = []
        for scenario in scenarios:
            try:
                recordings.append(render_demo(scenario, stage, layout))
            except (RuntimeError, ValueError) as error:
                parser.exit(1, f"{scenario} could not render on layout seed {args.layout_seed}: {error}\n")
        for output in recordings:
            output.with_suffix(".video.json").replace(args.out_dir / output.with_suffix(".video.json").name)
            destination = args.out_dir / output.name
            output.replace(destination)
            print(destination, flush=True)


if __name__ == "__main__":
    main()
