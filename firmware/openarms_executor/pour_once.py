"""One supervised water pour using the existing add_sample skill."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from agentic.openarms_agent.catalog import expand
from agentic.openarms_agent.runner import run
from agentic.openarms_agent.validator import validate

from .motion import FakeRobot
from .pose_arm import PoseArm
from .poses import ARM_JOINTS, GRIPPER, load_poses
from .robot import FOLLOWER_ID, connect
from .transfer_runner import HOME_TOL

ROOT = Path(__file__).resolve().parents[2]
STATIONS = {"A": {"kind": "source", "contents": "water", "portions": 1},
            "C": {"kind": "receiver", "contents": "water", "capacity": 1}}
PLAN = {"plan_id": "bench-pour", "steps": [
    {"action": "add_sample", "args": {"source": "A", "into": "C", "portions": 1}},
]}
POSE_NAMES = ("HOME", "ABOVE_A", "GRASP_A", "ABOVE_C", "TIP_C")
# A pour accepts the arm stopping this close to a pose instead of failing: the real arm at long reach stops up to
# about 6 degrees short of (or past) its goal, and a grasp that meets the table stops early. Past it the move fails.
GIVE_DEG = 7.0


def preflight(data: dict, limits: dict) -> None:
    for name in POSE_NAMES:
        pose = data["poses"].get(name, {})
        if set(pose) != set(ARM_JOINTS):
            raise ValueError(f"record all joints at {name} before running")
        for joint, value in pose.items():
            low, high = limits[joint]
            if type(value) not in (int, float) or not low <= value <= high:
                raise ValueError(f"{name}: {joint} outside calibrated range")
    close, opened = (data["gripper"].get(k) for k in ("cup", "open"))
    if not all(type(v) in (int, float) for v in (close, opened)) or not 0 <= close < opened <= 100:
        raise ValueError("record a separate open and cup grip before running")


def bench_limits() -> dict:
    calibration = json.loads((ROOT / "calibration/robots/so_follower" / f"{FOLLOWER_ID}.json").read_text())
    return {f"{name}.pos": tuple(sign * (cal["range_max"] - cal["range_min"]) * 180 / 4095 for sign in (-1, 1))
            for name, cal in calibration.items() if f"{name}.pos" in ARM_JOINTS}


class ObservedPour(PoseArm):
    def __init__(self, robot, poses, *, note, fake: bool, limits: dict | None = None, seconds: float = 3.0):
        super().__init__(robot, poses, STATIONS, seconds=0.01 if fake else max(1.0, float(seconds)), pour_hold=0 if fake else 2,
                         stop_within_move=True, give=GIVE_DEG,
                         on_give=lambda pose, report: note("arrival_accepted", pose=pose, **report), limits=limits)
        self.note = note

    def run_step(self, action, args):
        self.note("step_started", action=action, args=args)
        super().run_step(action, args)
        self.note("step_finished", action=action)

    def stop(self):
        super().stop()
        self._hold_here()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preview", "dry", "water"))
    parser.add_argument("--poses", required=True, type=Path)
    parser.add_argument("--port")
    parser.add_argument("--receipt-dir", required=True, type=Path)
    parser.add_argument("--fake", action="store_true")
    args = parser.parse_args()
    poses = load_poses(args.poses)
    limits = bench_limits()
    try:
        preflight(poses, limits)
    except ValueError as exc:
        parser.error(str(exc))
    home = poses["poses"]["HOME"]
    if args.mode == "preview":
        print(json.dumps({"steps": expand(PLAN), "poses": {n: poses["poses"][n] for n in POSE_NAMES},
                          "gripper": poses["gripper"]}, indent=2))
        return 0
    setup = ("empty plastic cup at A" if args.mode == "dry"
             else "one pre-portioned water cup at A and room in the receiver")
    if input(f"One {args.mode} pour. Confirm {setup}, clear path, and follower at HOME. Start? y/n> ").strip().lower() != "y":
        return 1

    args.receipt_dir.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", prefix=f"pour-{args.mode}-", suffix=".jsonl",
                            dir=args.receipt_dir, delete=False) as receipt:
        print(f"Receipt: {receipt.name}")

        def note(event, **details):
            receipt.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "event": event, **details}) + "\n")
            receipt.flush()

        note("request", mode=args.mode, backend="fake" if args.fake else "physical", poses=str(args.poses))
        robot = None
        arm = None
        try:
            robot = FakeRobot(home) if args.fake else connect(False, args.port)
            start = robot.get_observation()
            note("start_pose", joints=start)
            if not all(abs(start[j] - home[j]) <= HOME_TOL for j in ARM_JOINTS):
                note("result", status="failed", reason="follower outside HOME tolerance")
                print("Follower outside HOME tolerance.")
                return 1

            arm = ObservedPour(robot, poses, note=note, fake=args.fake, limits=limits)
            verdict = validate(PLAN, arm.state(), STATIONS)
            if not verdict["ok"]:
                raise ValueError(verdict["reason"])

            def check_lift():
                if not arm.state()["holding"] or arm.state()["at"] != "A":
                    return False
                answer = input("Is the cup securely lifted and clear of its holder? y/n> ").strip().lower() == "y"
                note("cup_held_observed", confirmed=answer)
                return not answer

            result = run(PLAN, arm, should_stop=check_lift)
            note("end_pose", joints=robot.get_observation())
            note("result", **result)
            print(result["status"])
            if result["status"] == "executed":
                observation = input("Observed cup return and result (delivery, spills, or dry clearance)> ").strip()
                note("operator_observation", text=observation)
            return 0 if result["status"] == "executed" else 1
        except (EOFError, KeyboardInterrupt):
            if arm is not None:
                arm.stop()
            note("interrupted")
            return 130
        except Exception as exc:
            note("error", reason=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            if robot is not None:
                robot.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
