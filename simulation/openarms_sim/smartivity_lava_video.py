"""Render the scripted Smartivity Lava Lamp presentation at 30 fps."""
import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw

from .render import _font
from .smartivity_lava import LavaWorld
from .smartivity_video import FPS
from .smartivity_world import REPLAY_WIDTH as WIDTH, REPLAY_HEIGHT as HEIGHT

FONT = {size: _font(size) for size in (17, 23, 36, 47)}


def caption(rgb, heading, detail, view, title=False):
    image = Image.fromarray(rgb)
    draw = ImageDraw.Draw(image, "RGBA")
    dark = (8, 16, 25, 232)
    text = (249, 246, 244, 255)
    highlight = (255, 166, 115, 255)

    draw.rounded_rectangle((32, 26, 266, 67), 7, fill=dark)
    draw.text((46, 47), "OPENARMS  /  SIMULATION", fill=highlight, font=FONT[17], anchor="lm")
    draw.text((WIDTH - 32, 47), view, fill=text, font=FONT[17], anchor="rm",
              stroke_width=2, stroke_fill=(11, 18, 30, 215))

    size = 47 if title else 36
    width = max(draw.textlength(heading, font=FONT[size]), draw.textlength(detail, font=FONT[23])) + 48
    draw.rounded_rectangle((32, HEIGHT - 116, 32 + int(width), HEIGHT - 29), 8, fill=dark)
    draw.rectangle((43, HEIGHT - 101, 46, HEIGHT - 45), fill=highlight)
    draw.text((56, HEIGHT - 110), heading, fill=text, font=FONT[size])
    draw.text((56, HEIGHT - 61), detail, fill=(226, 230, 235, 255), font=FONT[23])
    return image


def render_lava_lamp(output: Path) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    with closing(LavaWorld()) as world:
        setup = world.visual_state()
        frames = [(None, setup)]

        def sample(action):
            world.tick()
            fault = world.proprioception()["fault"]
            if fault:
                raise RuntimeError(fault)
            if world.sim_time + 1e-9 >= len(frames) / FPS:
                frames.append((action, world.visual_state()))

        for action in ("pick", "pour", "return_cup", "home"):
            world.start(action)
            while world.busy:
                sample(action)
        end = world.sim_time + 1.7
        while world.sim_time < end:
            sample(None)

        motion = world.evaluate()
        print(json.dumps(motion, indent=2), flush=True)
        if not motion["success"]:
            raise RuntimeError("Scripted run failed its transfer or placement checks.")

        first_release = world.releases[0][0]
        print(f"First acid release at {first_release:.3f}s", flush=True)
        # Reuse the true recorded robot pose for each frame. The two-phase effect is illustrative.
        hero = [state for _, state in frames if first_release + 2.5 <= state.sim_time < first_release + 4.5]
        if len(hero) <= 45:
            raise RuntimeError("The recorded reaction is too short for the preview.")
        layers = caption(world.replay_rgb(setup, "reaction"), "Oil floats on water",
                         "40 mL oil above 5 mL of red baking-soda solution", "FLASK CLOSE-UP")

        def describe(action, state):
            t = state.sim_time
            if action == "pick":
                return "wide", "Pick up the citric acid", "The prepared flask stays in its tray"
            if t < first_release:
                return "wide", "Align over the flask", "The robot brings the beaker above the opening"
            if t < first_release + 1.25:
                return "reaction", "Add citric acid slowly", "The grains sink through the oil"
            if t < first_release + 3.45:
                return "reaction", "CO₂ lifts the red water", "Gas forms when the acid reaches the baking-soda solution"
            if t < first_release + 6.65:
                return "reaction", "Red droplets rise and fall", "When the gas escapes, the heavier droplets sink"
            if action:
                return "wide", "Return the beaker", "The arm clears the flask and retracts"
            return "reaction", "After the bubbles fade", "Red water collects beneath the oil"

        timeline = Counter()
        with NamedTemporaryFile(prefix=".lava-", suffix=".mp4", dir=output.parent, delete=False) as file:
            temporary = Path(file.name)
        try:
            with imageio.get_writer(
                temporary, fps=FPS, codec="libx264", quality=None, macro_block_size=2, pixelformat="yuv420p",
                output_params=["-crf", "16", "-preset", "fast", "-movflags", "+faststart", "-metadata", "title=OpenArms | Lava Lamp"],
                ffmpeg_log_level="error",
            ) as writer:
                def emit(shot, image, repeat=1):
                    pixels = np.asarray(image)
                    for _ in range(repeat):
                        writer.append_data(pixels)
                    timeline[shot] += repeat

                for state in hero:
                    rgb = world.replay_rgb(state, "reaction")
                    emit("Opening", caption(rgb, "Lava Lamp",
                                            "Smartivity My First Science Kit  •  Activity 17",
                                            "REACTION PREVIEW", title=True))
                emit("Prep close-up", layers, 65)
                for action, state in frames[1:]:
                    camera, heading, detail = describe(action, state)
                    view = "BENCH VIEW" if camera == "wide" else "FLASK CLOSE-UP"
                    emit(heading, caption(world.replay_rgb(state, camera), heading, detail, view))
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
        receipt = {**motion, "provenance": "SIMULATED", "mode": "scripted",
                   "fps": FPS, "frames": sum(timeline.values()),
                   "source": world.manifest["source"], "shots": dict(timeline)}
        output.with_suffix(".video.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Destination MP4")
    args = parser.parse_args()
    if args.out.suffix.lower() != ".mp4":
        parser.error("--out must end with .mp4")
    render_lava_lamp(args.out)


if __name__ == "__main__":
    main()
