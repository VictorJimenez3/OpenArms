"""Compare named pour phases from multiple takes on a single fixed bench."""
import argparse
import itertools
import json
import time
from pathlib import Path
from tempfile import NamedTemporaryFile

from agentic.openarms_agent.runner import run

from .motion import FakeRobot
from .poses import ARM_JOINTS, load_poses
from .pour_once import PLAN, ROOT, ObservedPour, bench_limits, preflight

PICKUP = ("HOME", "ABOVE_A", "GRASP_A")
RECEIVER = ("ABOVE_C", "TIP_C")


def compare(paths):
    limits = bench_limits()
    takes = {}
    for path in paths:
        data = load_poses(path)
        preflight(data, limits)
        takes[path] = data

    for pickup, receiver in itertools.product(takes, repeat=2):
        source, sink = takes[pickup], takes[receiver]
        poses = {key: source["poses"][key] for key in PICKUP}
        poses.update({key: sink["poses"][key] for key in RECEIVER})
        candidate = {"poses": poses, "gripper": source["gripper"]}
        arm = ObservedPour(FakeRobot(poses["HOME"]), candidate, note=lambda *args, **kwargs: None, fake=True)
        result = run(PLAN, arm)
        seam = max(abs(poses["ABOVE_A"][j] - poses["ABOVE_C"][j]) for j in ARM_JOINTS)
        yield {"pickup_take": str(pickup), "receiver_take": str(receiver),
               "same_take_baseline": pickup == receiver, "transit_max_joint_travel_deg": round(seam, 2),
               "fake_result": result, "candidate": candidate}


def write_report(paths, out=None, *, folder=None):
    trials = list(compare(paths))
    ranked = sorted((row for row in trials if row["fake_result"]["status"] == "executed"
                     and not row["same_take_baseline"]), key=lambda row: row["transit_max_joint_travel_deg"])
    folder = out.parent if out else (folder or ROOT / "outputs/mandarin-bench/runs")
    folder.mkdir(parents=True, exist_ok=True)
    report = out.open("x") if out else NamedTemporaryFile(
        mode="w", prefix="compare-pours-", suffix=".json", dir=folder, delete=False)
    with report:
        json.dump({"backend": "fake", "trials": trials, "shortlist": ranked[:3]}, report, indent=2)
        report.write("\n")
    print(f"Saved {len(trials)} fake-arm trials to {report.name}. Inspect transit clearance before a physical review.",
          flush=True)


def watch(folder):
    previous = ()
    print(f"Watching {folder} for new water takes. Ctrl+C ends the offline comparisons.", flush=True)
    while True:
        try:
            paths = sorted(folder.glob("bench-water*.json"))
            snapshot = tuple((path, path.stat().st_mtime_ns, path.stat().st_size) for path in paths)
            if len(paths) >= 2 and snapshot != previous:
                previous = snapshot
                write_report(paths, folder=folder / "runs")
        except (OSError, ValueError) as exc:
            print(f"Take set incomplete or unreadable: {exc}. Waiting for a change.", flush=True)
        time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("takes", nargs="*", type=Path, help="water capture files from the same fixed fixture")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--watch", type=Path, metavar="CAPTURE_DIR")
    args = parser.parse_args()
    if args.watch is not None:
        if args.takes or args.out:
            parser.error("--watch takes a capture directory and writes a fresh report on each change")
        try:
            watch(args.watch)
        except KeyboardInterrupt:
            pass
    elif args.takes:
        write_report(args.takes, args.out)
    else:
        parser.error("provide capture files or --watch CAPTURE_DIR")


if __name__ == "__main__":
    main()
