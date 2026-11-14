"""Compare named pour phases from multiple takes on a single fixed bench."""
import argparse
import itertools
import json
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("takes", nargs="+", type=Path, help="water capture files from the same fixed fixture")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    trials = list(compare(args.takes))
    folder = args.out.parent if args.out else ROOT / "outputs/mandarin-bench/runs"
    folder.mkdir(parents=True, exist_ok=True)
    report = args.out.open("x") if args.out else NamedTemporaryFile(
        mode="w", prefix="compare-pours-", suffix=".json", dir=folder, delete=False)
    with report:
        json.dump({"backend": "fake", "trials": trials}, report, indent=2)
        report.write("\n")
    print(f"Saved {len(trials)} fake-arm trials to {report.name}. Inspect transit clearance before a physical review.")


if __name__ == "__main__":
    main()
