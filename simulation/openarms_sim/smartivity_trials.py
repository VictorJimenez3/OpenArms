"""Reproduce paired local-motion diagnostics without running an expert policy."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import time

from .smartivity_world import World

ACTIONS = ("pick", "pour", "return_cup", "home")


def trial(seed, aim, *, position_variation_m=None, register=False, evidence_dir=None):
    started = time.monotonic()
    with closing(World(seed, aim=aim, position_variation_m=position_variation_m)) as world:
        registration = None
        if register:
            from PIL import Image
            from .smartivity_registration import locate_layout

            rgb = world.registration_image()
            calibration = world.registration_calibration()
            registration = {"calibration": calibration}
            if evidence_dir is not None:
                evidence_dir.mkdir(parents=True, exist_ok=True)
                path = evidence_dir / f"seed-{seed}-registration.png"
                Image.fromarray(rgb).save(path)
                registration.update(image=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            try:
                estimates = locate_layout(rgb, calibration)
                registration.update(estimates)
                world.register_layout(estimates["dock_xy"], estimates["receiver_xy"])
                registration["status"] = "registered"
            except (RuntimeError, ValueError) as exc:
                registration.update(status="rejected", reason=str(exc))
        action_trace = []
        for action in ACTIONS if not registration or registration["status"] == "registered" else ():
            start = world.sim_time
            world.start(action)
            deadline = world.sim_time + 20.
            while world.busy and world.sim_time < deadline:
                world.tick()
            fault = world.proprioception()["fault"]
            action_trace.append({"action": action, "sim_seconds": world.sim_time - start,
                                 "fault": fault, "timed_out": world.busy})
            if world.busy:
                world.halt()
                break
            if fault:
                break
        return world.evaluate() | {
            "position_variation_m": position_variation_m,
            "layout_mode": "camera_registered" if register else "fixed",
            "registration": registration,
            "evaluator_layout_xy": {"dock": world.dock[:2].tolist(), "receiver": world.receiver[:2].tolist()},
            "actions": action_trace,
            "policy_calls": 0,
            "interventions": 0,
            "initial_resets": 1,
            "wall_seconds": time.monotonic() - started,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 7, 18])
    parser.add_argument("--layout-study-mm", type=float, help="Compare fixed and pixel-registered targets at this XY spread.")
    parser.add_argument("--evidence-dir", type=Path, help="Save the actual registration images for paired layout trials.")
    args = parser.parse_args()
    if args.layout_study_mm is None:
        trials = [trial(seed, aim) for seed in args.seeds for aim in ("mouth_center", "spout")]
    else:
        spread = args.layout_study_mm / 1000
        if not 0 < spread <= 0.018:
            parser.error("Layout spread must be between 0 and 18 mm.")
        trials = [trial(seed, "spout", position_variation_m=spread, register=register,
                        evidence_dir=args.evidence_dir)
                  for seed in args.seeds for register in (False, True)]
    print(json.dumps({"mode": "SCRIPTED_DIAGNOSTIC", "realtime": False, "trials": trials}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
