"""Command line for the preview: `python -m openarms_sim --from A --to B`."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .preview import example_plan, preview


def add_plan_arguments(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--setup", help="block or liquid (default: block, or $OPENARMS_SETUP)")
    ap.add_argument("--plan", help="plan as JSON, or a path to a JSON file")
    ap.add_argument("--from", "--source", dest="source", help="station to pick up from")
    ap.add_argument("--to", "--into", dest="into", help="station to place on or pour into")
    ap.add_argument("--portions", type=int, default=1, help="liquid setup only")
    ap.add_argument("--objects", help='where objects start, as JSON, e.g. \'{"block": "B"}\'')
    ap.add_argument("--contents", help='what containers hold at the start, as JSON, e.g. \'{"A": {"bleach": 1}}\'')


def plan_from_arguments(a: argparse.Namespace) -> tuple[dict, dict | None, dict | None]:
    """Returns (plan, objects, contents)."""
    if a.plan:
        plan = json.loads(Path(a.plan).read_text() if Path(a.plan).exists() else a.plan)
    else:
        plan = example_plan(a.source, a.into, a.portions, a.setup)
    return plan, json.loads(a.objects) if a.objects else None, json.loads(a.contents) if a.contents else None


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m openarms_sim", description="Preview a plan in the simulation.")
    add_plan_arguments(ap)
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()
    plan, objects, contents = plan_from_arguments(a)
    t0 = time.time()
    out = preview(plan, contents, objects, not a.no_video, not a.no_cache, setup=a.setup)
    print(json.dumps(out, indent=2))
    print(f"\ntook {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
