"""Dry-runs one arm step N times on PoseArm and marks it verified at >= 9/10 human-confirmed successes."""
import argparse
import json
import time
from pathlib import Path

from agentic.openarms_agent.types import ArmError

from .pose_arm import PoseArm
from .poses import load_poses
from .robot import connect

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--action", required=True, choices=["pick", "return_cup", "pour", "home"])
ap.add_argument("--station", default="A", help="source station (pick, return_cup, and the cup used for pour)")
ap.add_argument("--into", default="C", help="receiver for pour")
ap.add_argument("--runs", type=int, default=10)
ap.add_argument("--fake", action="store_true")
ap.add_argument("--yes", action="store_true", help="answer y to every 'worked?'")
ap.add_argument("--poses", default=str(HERE / "poses.json"))
ap.add_argument("--stations", default=str(HERE.parents[1] / "agentic/contracts/stations.example.json"))
ap.add_argument("--seconds", type=float, default=1.5, help="time per move")
ap.add_argument("--port")
a = ap.parse_args()

pick, back = ("pick", {"station": a.station}), ("return_cup", {"station": a.station})
# Each run includes the inverse step so the bench ends as it started.
script = {"pick": [pick, back], "return_cup": [pick, back], "home": [("home", {})],
          "pour": [pick, ("pour", {"into": a.into}), back]}[a.action]
poses, stations = load_poses(a.poses), json.loads(Path(a.stations).read_text())
robot = connect(a.fake, a.port)
results = []
try:
    for i in range(1, a.runs + 1):
        arm = PoseArm(robot, poses, stations, seconds=a.seconds)  # fresh state: a dry run uses no real portions
        try:
            for action, args in script:
                arm.run_step(action, args)
        except ArmError as e:
            results.append({"run": i, "ok": False, "reason": str(e)})
            print(f"run {i}: {e}; stopping (no retries)")
            break
        ok = a.yes or input(f"run {i}: worked? y/n ").strip().lower().startswith("y")
        results.append({"run": i, "ok": ok})
finally:
    robot.disconnect()

n_ok = sum(r["ok"] for r in results)
verified = n_ok >= 0.9 * a.runs
out = Path("outputs/arm_tests.json")
log = json.loads(out.read_text()) if out.exists() else []
log.append({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": a.action, "station": a.station, "into": a.into,
            "fake": a.fake, "runs": a.runs, "ok": n_ok, "verified": verified, "results": results})
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(log, indent=2) + "\n")
print(f"{n_ok}/{a.runs} {'verified' if verified else 'not verified'}")
