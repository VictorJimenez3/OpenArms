"""Renders the simulated bench to an MP4 with captions."""

from __future__ import annotations

from pathlib import Path

import imageio
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .player import Player

WIDTH, HEIGHT = 640, 480


def _font(size: int):
    for path in ("/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def camera() -> mujoco.MjvCamera:
    cam = mujoco.MjvCamera()
    cam.lookat[:] = [0.22, 0.0, 0.08]
    cam.distance = 0.95
    cam.azimuth = 180  # looking back at the arm from the far side of the bench
    cam.elevation = -32
    return cam


class VideoRecorder:
    """Use as `player.run(segments, fps, on_frame=recorder)`, then `close()`."""

    def __init__(self, scene, path: Path, fps: int = 30, speed: float = 1.0, show_blocks: bool = True):
        self.scene, self.path, self.fps = scene, Path(path), fps
        self.show_blocks = show_blocks  # off for recordings of the real arm, where nothing is being vetted
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._renderer = mujoco.Renderer(scene.model, HEIGHT, WIDTH)
        self._camera = camera()
        # Play faster than real time by keeping only every `speed`-th frame.
        self._keep_every = max(1, round(speed))
        self._seen = 0
        self._writer = imageio.get_writer(
            str(self.path), fps=fps, codec="libx264", quality=7, macro_block_size=16, pixelformat="yuv420p"
        )
        self._big, self._small = _font(20), _font(14)
        self.frames = 0

    def __call__(self, player: Player) -> None:
        self._seen += 1
        if self._seen % self._keep_every:
            return
        self._renderer.update_scene(self.scene.data, self._camera)
        img = Image.fromarray(self._renderer.render())
        draw = ImageDraw.Draw(img, "RGBA")
        draw.rectangle([0, 0, WIDTH, 34], fill=(20, 24, 32, 215))
        draw.text((12, 6), f"{player.step}  {player.label}", font=self._big, fill=(255, 255, 255, 255))
        draw.text((WIDTH - 150, 10), "SIMULATED PREVIEW", font=self._small, fill=(255, 210, 90, 255))
        y = HEIGHT - 30
        blocks = [i for i in player.issues if i.severity == "block"] if self.show_blocks else []
        if blocks:
            draw.rectangle([0, y - 4, WIDTH, HEIGHT], fill=(170, 30, 30, 230))
            draw.text((12, y), f"BLOCKED: {blocks[-1].message}"[:88], font=self._small, fill=(255, 255, 255, 255))
        elif player.caption:
            draw.rectangle([0, y - 4, WIDTH, HEIGHT], fill=(20, 24, 32, 215))
            draw.text((12, y), player.caption, font=self._small, fill=(255, 255, 255, 255))
        self._writer.append_data(np.asarray(img.convert("RGB")))
        self.frames += 1

    def close(self) -> None:
        self._writer.close()
        self._renderer.close()


def snapshot(scene, path: Path) -> None:
    """Saves one still of the current scene."""
    renderer = mujoco.Renderer(scene.model, HEIGHT, WIDTH)
    renderer.update_scene(scene.data, camera())
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    imageio.imwrite(str(path), renderer.render())
    renderer.close()
