"""Opens the simulated bench in MuJoCo's interactive viewer and plays a plan on a loop.

On macOS the viewer needs `mjpython` (installed with mujoco) instead of `python`:

    mjpython -m openarms_sim.view --from A --to B

Drag with the mouse to orbit, scroll to zoom. Close the window to quit.
"""

from __future__ import annotations

import argparse
import time

import mujoco.viewer

from .__main__ import add_plan_arguments, plan_from_arguments
from .chemistry import load_model
from .config import load_bench, load_chemistry_config, load_joint_map, load_poses
from .joints import JointMap
from .motion import build_segments, expand_plan
from .player import Player
from .preview import FPS
from .render import camera
from .scene import build_scene


def main() -> None:
    ap = argparse.ArgumentParser(description="Play a plan in the interactive MuJoCo viewer.")
    add_plan_arguments(ap)
    ap.add_argument("--seconds", type=float, help="quit after this long (default: until the window closes)")
    a = ap.parse_args()
    plan, objects, contents = plan_from_arguments(a)

    bench, jm, chem_cfg = load_bench(a.setup), JointMap(load_joint_map()), load_chemistry_config()
    segments = build_segments(expand_plan(plan), load_poses(a.setup), jm, bench.stations)
    scene = build_scene(bench)
    start = time.time()

    with mujoco.viewer.launch_passive(scene.model, scene.data, show_left_ui=False, show_right_ui=False) as viewer:
        cam = camera()
        viewer.cam.lookat[:], viewer.cam.distance = cam.lookat, cam.distance
        viewer.cam.azimuth, viewer.cam.elevation = cam.azimuth, cam.elevation

        def running() -> bool:
            return viewer.is_running() and (a.seconds is None or time.time() - start < a.seconds)

        while running():
            player = Player(scene, jm, chem_cfg, load_model(chem_cfg), contents, objects)
            printed = 0
            next_frame = time.time()

            def on_frame(p: Player) -> None:
                nonlocal printed, next_frame
                if not running():
                    raise StopIteration
                for issue in p.issues[printed:]:
                    print(f"[{issue.severity}] {issue.step}: {issue.message}")
                printed = len(p.issues)
                viewer.sync()
                next_frame += 1.0 / FPS
                time.sleep(max(0.0, next_frame - time.time()))

            try:
                player.run(segments, FPS, on_frame)
            except StopIteration:
                break
            if player.caption:
                print(player.caption)
            pause_until = time.time() + 2.0
            while running() and time.time() < pause_until:
                viewer.sync()
                time.sleep(0.05)


if __name__ == "__main__":
    main()
