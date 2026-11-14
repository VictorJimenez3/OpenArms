"""Teleoperate the follower from the leader and save named poses while it runs, so torque never drops mid-recording."""
import argparse
import json
import math
import threading
import time
from pathlib import Path
from tempfile import NamedTemporaryFile

from .poses import ARM_JOINTS, GRIPPER, load_poses, save_gripper, save_pose
from .robot import connect, connect_leader
from .transfer_runner import HOME_TOL

ap = argparse.ArgumentParser()
mode = ap.add_mutually_exclusive_group(required=True)
mode.add_argument("--out", help="pose file, e.g. firmware/openarms_executor/poses.json")
mode.add_argument("--home", help="guide toward the saved HOME in this pose file")
mode.add_argument("--capture", type=Path, help="capture a guided transfer and its joint trace")
ap.add_argument("--source", choices=("A", "C", "water"), default="A")
ap.add_argument("--relative", action="store_true", help="start mirroring from the follower's current pose")
ap.add_argument("--follower-port")
ap.add_argument("--leader-port")
ap.add_argument("--fake", action="store_true")
ap.add_argument("--hz", type=float, default=30)
a = ap.parse_args()


def relative_control(follower, leader):
    """Start from the follower's actual pose and apply incremental leader movements."""
    joints = (*ARM_JOINTS, GRIPPER)
    target = follower.get_observation()
    previous = leader.get_action()
    bounds = {joint: (-180.0, 180.0) for joint in ARM_JOINTS}
    if hasattr(follower, "calibration"):
        for joint in ARM_JOINTS:
            cal = follower.calibration[joint.removesuffix(".pos")]
            half_span = (cal.range_max - cal.range_min) * 180 / 4095
            bounds[joint] = (-half_span, half_span)
    bounds[GRIPPER] = (0.0, 100.0)

    def command(current):
        for joint in joints:
            delta = current[joint] - previous[joint]
            if not math.isfinite(delta):
                raise ValueError(f"Invalid leader reading for {joint}")
            low, high = bounds[joint]
            # A parked joint at a limit stays put until the leader moves it inward.
            position = target[joint]
            target[joint] = min(max(high, position), max(min(low, position), position + delta))
            previous[joint] = current[joint]
        return dict(target)

    return command

def guide_home(follower, leader, home: dict, hz: float) -> bool:
    print(f"Move the leader slowly. Hold within {HOME_TOL:g}° to finish. Ctrl+C ends mirroring.")
    steady_since = None
    next_report = 0.0
    while True:
        action = {joint: value for joint, value in leader.get_action().items() if joint in home}
        follower.send_action(action)
        obs = follower.get_observation()
        now = time.monotonic()
        errors = {joint: target - obs[joint] for joint, target in home.items()}
        worst = max(errors, key=lambda joint: abs(errors[joint]))
        if now >= next_report:
            print(f"{abs(errors[worst]):5.1f}° from HOME | " + "  ".join(
                f"{joint.removesuffix('.pos')} {obs[joint]:.1f} → {home[joint]:.1f}"
                for joint in home if abs(errors[joint]) > HOME_TOL
            ), flush=True)
            next_report = now + 1.0
        if abs(errors[worst]) <= HOME_TOL and all(abs(action[j] - home[j]) <= HOME_TOL for j in home):
            steady_since = now if steady_since is None else steady_since
            if now - steady_since >= 0.5:
                print(f"HOME ready. All joints within {abs(errors[worst]):.1f}°. Follower is holding.", flush=True)
                return True
        else:
            steady_since = None
        time.sleep(1 / hz)


def record(follower, leader, path: str, hz: float, *, capture: Path | None = None, source: str = "A",
           relative: bool = False) -> None:
    bus, done = threading.Lock(), threading.Event()
    trace = None
    failure = None
    translate = relative_control(follower, leader) if capture is not None or relative else None
    last_command = None
    if capture is not None:
        capture.parent.mkdir(parents=True, exist_ok=True)
        trace = NamedTemporaryFile(mode="w", prefix=f"demo-{source}-", suffix=".jsonl",
                                   dir=capture.parent, delete=False)
        print(f"Recording joint trace to {trace.name}", flush=True)

    def log(event: str, **details) -> None:
        if trace:
            trace.write(json.dumps({"t": time.monotonic(), "event": event, **details}) + "\n")

    def mirror() -> None:
        nonlocal failure, last_command
        try:
            while not done.is_set():
                with bus:
                    leader_action = leader.get_action()
                    command = translate(leader_action) if translate else leader_action
                    sent = follower.send_action(command)
                    last_command = command
                    if trace:
                        log("sample", leader=leader_action, command=command, sent=sent, state=follower.get_observation())
                time.sleep(1 / hz)
        except Exception as exc:
            failure = exc
            done.set()
            print(f"\nMirroring stopped: {exc}. Press Enter to exit.", flush=True)

    worker = threading.Thread(target=mirror, daemon=True)
    worker.start()
    try:
        if capture is not None:
            checkpoints = (
                [("HOME", "Rest pose with the gripper clear"), ("open", "Open fingers")]
                if source != "C" else []
            )
            if source == "water":
                checkpoints += [("ABOVE_A", "Open fingers above the empty source cup at carry height"),
                                ("GRASP_A", "Open fingers around the source cup"),
                                ("cup", "Close the fingers around the cup without crushing it"),
                                ("ABOVE_C", "Lift clear and hold the cup upright above the receiver"),
                                ("TIP_C", "Tilt the empty cup at the pouring angle"),
                                ("finish", "Bring the cup upright, return it to A, release, and go back to rest")]
            else:
                checkpoints += [(f"ABOVE_{source}", f"Open fingers above {source} at carry height"),
                                (f"GRASP_{source}", f"Open fingers around the mandarin at {source}")]
            if source == "A":
                checkpoints += [("cup", "Close the fingers on the mandarin"),
                                ("ABOVE_B", "Lift clear and hold above the red card"),
                                ("GRASP_B", "Hold at the drop pose just before opening"),
                                ("finish", "Release the mandarin, lift clear, and return to your starting rest pose")]
            elif source == "C":
                checkpoints.append(("finish", "Lift clear of C and return the follower to rest"))
            data = {"poses": {}, "gripper": {}}
            for name, instruction in checkpoints:
                while True:
                    reply = input(f"{instruction}. Hold still and press Enter > ").strip().lower()
                    with bus:
                        if failure:
                            raise SystemExit(f"Capture stopped: {failure}")
                        obs = follower.get_observation()
                        command = last_command or obs
                        log("checkpoint", name=name, state=obs, command=command)
                    if name in ("open", "cup"):
                        # Keep the commanded closure that held the fruit under load.
                        data["gripper"][name] = command[GRIPPER] if name == "cup" else obs[GRIPPER]
                    elif name != "finish":
                        data["poses"][name] = {k: obs[k] for k in ARM_JOINTS}
                    elif source != "C" and max(abs(obs[k] - target) for k, target in data["poses"]["HOME"].items()) > HOME_TOL:
                        if reply != "keep":
                            print("Still more than 5° from your starting pose. Move closer, or type keep to save the take now.")
                            continue
                        print("Saved with the original HOME. Restore it before replay.")
                    break
            with capture.open("x") as out:
                json.dump(data, out, indent=2)
                out.write("\n")
            print(f"Saved checkpoints to {capture}", flush=True)
            return
        print("Move the leader; the follower copies it. Type a pose name to save, or press Enter to finish.")
        while name := input("save as> ").strip():
            time.sleep(0.3)
            with bus:
                if failure:
                    raise SystemExit(f"Capture stopped: {failure}")
                obs = follower.get_observation()
                grip = last_command[GRIPPER] if relative and name == "cup" and last_command else obs[GRIPPER]
            if name in ("open", "cup"):
                save_gripper(path, name, grip)
                print(f"  gripper {name} = {grip:.1f}")
            else:
                save_pose(path, name, obs)
                print(f"  {name}:", {k.removesuffix('.pos'): round(float(obs[k]), 1) for k in ARM_JOINTS})
    finally:
        done.set()
        worker.join()
        if trace:
            trace.close()


home = load_poses(a.home)["poses"]["HOME"] if a.home else None
follower = connect(a.fake, a.follower_port)
try:
    leader = connect_leader(a.fake, a.leader_port)
    try:
        if home is not None:
            guide_home(follower, leader, home, a.hz)
        else:
            record(follower, leader, a.out, a.hz, capture=a.capture, source=a.source, relative=a.relative)
    finally:
        leader.disconnect()
except (EOFError, KeyboardInterrupt):
    print("\nMirroring ended. Follower is holding its last position.")
finally:
    follower.disconnect()  # torque stays on (robot.py), so the arm holds its last pose
