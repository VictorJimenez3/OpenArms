"""Terminal REPL: you type as the student, then approve plans as the teacher. MockArm by default; --real drives PoseArm."""
import argparse
import json
import time
from pathlib import Path

from agentic.openarms_agent import runner
from agentic.openarms_agent.catalog import expand
from agentic.openarms_agent.brain import Brain
from agentic.openarms_agent.mock_arm import MockArm
from agentic.openarms_agent.validator import validate

ROOT = Path(__file__).resolve().parents[2]


def pose_arm(port: str | None, poses: str, fake_robot: bool):
    # firmware is imported only here, so the default MockArm path never needs it
    from firmware.openarms_executor.pose_arm import PoseArm
    from firmware.openarms_executor.poses import load_poses
    from firmware.openarms_executor.robot import connect
    stations = json.loads((ROOT / "agentic/contracts/stations.example.json").read_text())
    if not Path(poses).exists():
        raise SystemExit(f"No pose file at {poses}: record poses first (record_pose) or pass --poses.")
    saved = load_poses(poses)  # load before connecting so a bad file never leaves the arm connected
    if input("Is the arm at HOME, every source cup full and in its holder? y/n> ").strip().lower() != "y":
        raise SystemExit("Set up the bench first: PoseArm assumes it starts at HOME with full cups.")
    return PoseArm(connect(fake_robot, port), saved, stations), stations


def approve(plan, brain: Brain):
    if input("teacher approve? y/n> ").strip().lower() not in ("y", "yes"):
        comment = input("teacher comment> ").strip()
        return {"plan_id": plan["plan_id"], "status": "teacher_rejected", "steps_done": [], "failed_step": None,
                "reason": comment or None}
    # re-check against the arm's live state: the approved plan was validated before the teacher looked
    check = validate(plan, brain.session.arm.state(), brain.session.stations)
    if not check["ok"]:
        return {"plan_id": plan["plan_id"], "status": "rejected", "steps_done": [], "failed_step": None,
                "reason": check["reason"]}
    try:
        return runner.run(plan, brain.session.arm, should_stop=lambda: brain.session.stop_requested)
    except KeyboardInterrupt:  # Ctrl-C is the only mid-run stop in this single-threaded REPL
        brain.session.arm.stop()
        return {"plan_id": plan["plan_id"], "status": "stopped", "steps_done": [], "failed_step": None,
                "reason": "stopped with Ctrl-C mid-run; check the bench before going on"}


def main(brain: Brain | None = None) -> None:
    brain = brain or Brain(f"repl-{int(time.time())}", arm=MockArm())
    print("Type as the student. Ctrl-D to quit. Ctrl-C during a run stops the arm.")
    turn = 0
    try:
        while True:
            try:
                text = input("student> ").strip()
            except EOFError:
                break
            if not text:
                continue
            turn += 1
            try:
                reply = brain.handle_turn(f"t{turn}", text)
            except Exception as e:  # a wifi or API blip should not end the session
                print(f"brain error ({type(e).__name__}: {e}); say that again")
                continue
            print(f"brain [{reply['status']}]> {reply['text']}")
            if reply["status"] != "awaiting_teacher":
                continue
            print("teacher sees:", json.dumps(expand(reply["plan"])))
            try:
                result = approve(reply["plan"], brain)
            except EOFError:
                break
            print("run:", json.dumps(result))
            print(f"brain> {brain.notify(result)['text']}")
    finally:  # keep the record and release the port however the session ends; torque stays on
        print("notebook saved to", brain.session.notebook.save())
        robot = getattr(brain.session.arm, "robot", None)
        if robot is not None:
            robot.disconnect()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true", help="drive the SO-101 through PoseArm (needs --port)")
    ap.add_argument("--fake-robot", action="store_true", help="PoseArm on a FakeRobot: the --real path without hardware")
    ap.add_argument("--port", help="follower serial port, from lerobot-find-port")
    ap.add_argument("--poses", default=str(ROOT / "firmware/openarms_executor/poses.json"))
    a = ap.parse_args()
    if a.port and not a.real:
        raise SystemExit("--port only makes sense with --real; without it nothing moves.")
    if a.real or a.fake_robot:
        arm, stations = pose_arm(a.port, a.poses, fake_robot=not a.real)
        main(Brain(f"repl-{int(time.time())}", stations=stations, arm=arm))
    else:
        main()
