"""Reproduce paired local-motion diagnostics without running an expert policy."""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import time

from .smartivity_world import World

ACTIONS = ("pick", "pour", "return_cup", "home")


def trial(seed, aim):
    started = time.monotonic()
    with closing(World(seed, aim=aim)) as world:
        for action in ACTIONS:
            world.start(action)
            deadline = world.sim_time + 20.
            while world.busy and world.sim_time < deadline:
                world.tick()
            if world.busy:
                world.halt()
                break
            if world.proprioception()["fault"]:
                break
        return world.evaluate() | {
            "policy_calls": 0,
            "interventions": 0,
            "initial_resets": 1,
            "wall_seconds": time.monotonic() - started,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 7, 18])
    args = parser.parse_args()
    trials = [trial(seed, aim) for seed in args.seeds for aim in ("mouth_center", "spout")]
    print(json.dumps({"mode": "SCRIPTED_DIAGNOSTIC", "realtime": False, "trials": trials}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
