"""Render the 30 fps Smartivity Magic Snow presentation."""
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
from .smartivity_snow import SnowWorld
from .smartivity_video import FPS
from .smartivity_world import REPLAY_HEIGHT as HEIGHT, REPLAY_WIDTH as WIDTH

FONT = {size: _font(size) for size in (16, 21, 32, 50)}
AQUA = (143, 220, 244, 255)
TEXT = (244, 250, 252, 255)
PANEL = (9, 22, 34, 230)


def _caption(rgb, heading, detail, view, *, title=False, seconds=None):
    image = Image.fromarray(rgb)
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((34, 25, 307, 64), radius=7, fill=PANEL)
    draw.text((47, 45), "OPENARMS  /  SCRIPTED SIMULATION", font=FONT[16], fill=AQUA, anchor="lm")
    if seconds is None:
        draw.text((WIDTH - 34, 45), view, font=FONT[16], fill=TEXT, anchor="rm",
                  stroke_width=2, stroke_fill=(7, 20, 29, 220))
    else:
        draw.rounded_rectangle((WIDTH - 250, 25, WIDTH - 34, 83), radius=8, fill=PANEL)
        elapsed = int(seconds)
        clock = f"{elapsed // 60}:{elapsed % 60:02d}"
        draw.text((WIDTH - 234, 48), "TIME-LAPSE", font=FONT[16], fill=AQUA, anchor="lm")
        draw.text((WIDTH - 50, 48), clock, font=FONT[21], fill=TEXT, anchor="rm")
        end = WIDTH - 50
        left = WIDTH - 234
        draw.rounded_rectangle((left, 68, end, 72), radius=2, fill=(65, 97, 113, 255))
        draw.rounded_rectangle((left, 68, left + (end-left) * seconds/120, 72), radius=2, fill=AQUA)

    size = 50 if title else 32
    width = max(draw.textlength(heading, font=FONT[size]), draw.textlength(detail, font=FONT[21]))
    top = HEIGHT - (131 if title else 113)
    draw.rounded_rectangle((34, top, 87 + int(width), HEIGHT - 29), radius=10, fill=PANEL)
    draw.rectangle((47, top + 13, 50, HEIGHT - 44), fill=AQUA)
    draw.text((61, top + 4), heading, font=FONT[size], fill=TEXT)
    draw.text((61, HEIGHT - 61), detail, font=FONT[21], fill=(207, 231, 242, 255))
    return np.asarray(image)


def _motion(world):
    frames = [("setup", world.visual_state())]
    for action in ("pick", "pour", "return_cup", "home"):
        world.start(action)
        while world.busy:
            world.tick()
            fault = world.proprioception()["fault"]
            if fault:
                raise RuntimeError(fault)
            if world.sim_time + 1e-9 >= len(frames) / FPS:
                frames.append((action, world.visual_state()))
    return frames


def _shot(action, state, first_release, last_release):
    if first_release - .5 <= state.sim_time <= last_release + .55:
        return "reaction", "Add the snow powder", "The arm tips in three premeasured kit spoons."
    if action == "pick":
        return "wide", "Pick up the measured dose", "The cup is prefilled with 50 mL of water."
    if action == "pour":
        return "wide", "Move above the cup", "The beaker dispenses the premeasured powder."
    if action == "home":
        return "wide", "Park the arm", "The polymer starts absorbing water."
    return "wide", "Return the beaker", "The polymer starts absorbing water."


def render_magic_snow(output: Path, *, preview_dir=None, layout=None):
    output.parent.mkdir(parents=True, exist_ok=True)
    with closing(SnowWorld(layout=layout)) as world:
        frames = _motion(world)
        metrics = world.evaluate()
        if not metrics["success"]:
            raise RuntimeError(f"Scripted motion failed transfer or placement checks: {metrics}")
        print(json.dumps(metrics, indent=2), flush=True)

        first_release = world.releases[0][0]
        last_release = world.releases[-1][0]
        parked = frames[-1][1]
        start_age = parked.sim_time - first_release
        fully_absorbed = world.time_lapse_state(world.soak_seconds, parked)
        setup_image = world.replay_rgb(frames[0][1], "reaction")
        result_image = world.replay_rgb(fully_absorbed, "reaction")
        if preview_dir is not None:
            preview_dir.mkdir(parents=True, exist_ok=True)
            pour = min(frames, key=lambda sample: abs(sample[1].sim_time - first_release - .55))[1]
            midpoint = world.time_lapse_state(45, parked)
            for name, rgb in (("water", setup_image), ("powder", world.replay_rgb(pour, "reaction")),
                              ("swelling", world.replay_rgb(midpoint, "reaction")), ("snow", result_image)):
                Image.fromarray(rgb).resize((640, 360)).save(preview_dir / f"{name}.png")

        counts = Counter()
        with NamedTemporaryFile(prefix=".magic-snow-", suffix=".mp4", dir=output.parent, delete=False) as file:
            temporary = Path(file.name)
        try:
            with imageio.get_writer(
                temporary, fps=FPS, codec="libx264", quality=None, macro_block_size=2,
                pixelformat="yuv420p", ffmpeg_log_level="error",
                output_params=["-crf", "16", "-preset", "fast", "-movflags", "+faststart",
                               "-metadata", "title=OpenArms | Magic Snow"],
            ) as writer:
                def emit(label, image, repeat=1):
                    for _ in range(repeat):
                        writer.append_data(image)
                    counts[label] += repeat

                emit("title", _caption(result_image, "Magic Snow", "Smartivity My First Science Kit  /  Activity 03",
                                      "RESULT PREVIEW", title=True), 48)
                emit("setup", _caption(setup_image, "Start with water", "50 mL in the cup, as directed in the kit.",
                                      "CUP CLOSE-UP"), 51)
                for action, state in frames[1:]:
                    camera, heading, detail = _shot(action, state, first_release, last_release)
                    view = "BENCH VIEW" if camera == "wide" else "CUP CLOSE-UP"
                    emit(action, _caption(world.replay_rgb(state, camera), heading, detail, view))
                # Explicitly compress the booklet's 120-second waiting period.
                for age in np.linspace(start_age, world.soak_seconds, 147):
                    frame = world.time_lapse_state(float(age), parked)
                    emit("time_lapse", _caption(world.replay_rgb(frame, "reaction"), "The polymer swells",
                                                "Sodium polyacrylate absorbs water and forms a snowy mound.",
                                                "CUP CLOSE-UP", seconds=float(age)))
                emit("result", _caption(result_image, "From liquid to fluffy snow",
                                        "The model shows the swollen, water-filled polymer.",
                                        "MODEL RESULT"), 54)
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)

        result = {
            **metrics,
            "provenance": "SIMULATED",
            "mode": "scripted",
            "effect_model": "illustrative sodium polyacrylate swelling",
            "fps": FPS,
            "width": WIDTH,
            "height": HEIGHT,
            "frames": sum(counts.values()),
            "sections": dict(counts),
            "source": world.manifest["source"],
            "motion_duration_seconds": parked.sim_time,
            "first_powder_release_seconds": first_release,
            "last_powder_release_seconds": last_release,
            "time_lapse_start_seconds_after_powder": start_age,
            "model_final_absorbed_water_ml": metrics["water_preloaded_ml"] * fully_absorbed.effects.hydrate_fraction,
        }
        output.with_suffix(".video.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Destination MP4")
    parser.add_argument("--preview-dir", type=Path, help="Optional directory for four frame previews")
    args = parser.parse_args()
    if args.out.suffix.lower() != ".mp4":
        parser.error("--out must end with .mp4")
    render_magic_snow(args.out, preview_dir=args.preview_dir)


if __name__ == "__main__":
    main()
