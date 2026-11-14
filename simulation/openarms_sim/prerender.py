"""Renders the preview video for every one-step plan ahead of time, so
`preview()` answers instantly from its cache during the demo.

    python -m openarms_sim.prerender            # the active setup
    python -m openarms_sim.prerender --setup liquid

Run it again after changing anything in config/.
"""

from __future__ import annotations

import argparse
import time

from .config import load_bench, setup_name
from .preview import example_plan, preview


def main() -> None:
    ap = argparse.ArgumentParser(description="Render and cache every one-step preview.")
    ap.add_argument("--setup", help="block or liquid (default: the active setup)")
    setup = setup_name(ap.parse_args().setup)
    bench = load_bench(setup)
    jobs = []  # (label, plan, objects)
    for a in bench.points:
        for b in bench.points:
            if a != b:
                for name in bench.objects:
                    jobs.append((f"{name} {a} -> {b}", example_plan(a, b, setup=setup), {name: a}))
    for s in bench.sources:
        for r in bench.receivers:
            jobs.append((f"{s} -> {r}", example_plan(s, r, setup=setup), None))
    for label, plan, objects in jobs:
        t0 = time.time()
        out = preview(plan, objects=objects, setup=setup)
        state = "cached" if out["cached"] else f"rendered in {time.time() - t0:.1f} s"
        blocks = [i["message"] for i in out["issues"] if i["severity"] == "block"]
        print(f"{label}: ok={out['ok']} ({state})" + "".join(f"\n    {m}" for m in blocks))


if __name__ == "__main__":
    main()
