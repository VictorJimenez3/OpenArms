"""Local operator commands for the mandarin bench trial."""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from .poses import load_poses
from .robot import FOLLOWER_ID, LEADER_ID

ROOT = Path(__file__).resolve().parents[2]
POSES = Path(__file__).with_name("poses.json")
PHOTOS = ROOT / "outputs" / "mandarin-bench"


def find_arms(poses: Path, *, show_joints: bool = False) -> dict[str, str]:
    """Identify the boards with servo reads only. Follower.connect configures torque."""
    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

    leader_file = ROOT / "calibration/teleoperators/so_leader" / f"{LEADER_ID}.json"
    leader_cal = json.loads(leader_file.read_text())
    home = load_poses(poses)["poses"]["HOME"]
    arms = {}
    for port in sorted(Path("/dev").glob("cu.usbmodem*")):
        busy = subprocess.run(
            ["lsof", str(port), str(port.with_name(port.name.replace("cu.", "tty.", 1)))],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if busy.returncode == 0:
            print(f"{port.name}: in use", flush=True)
            continue
        robot = SO101Follower(SO101FollowerConfig(port=str(port), id=FOLLOWER_ID))
        bus = robot.bus
        try:
            bus.connect(handshake=False)
            if not all(bus.ping(motor) == 777 for motor in bus.motors):
                print(f"{port.name}: not all six expected motors replied. Check motor power.", flush=True)
                continue
            calibration = bus.read_calibration()
            if calibration == robot.calibration:
                arms["follower"] = str(port)
                obs = bus.sync_read("Present_Position")
                actual = {joint: obs[joint.removesuffix(".pos")] for joint in home}
                error = max(abs(actual[joint] - target) for joint, target in home.items())
                print(f"Follower ready on {port.name}. Max distance from HOME: {error:.1f}°.", flush=True)
                if show_joints:
                    print("Joint              Current    HOME", flush=True)
                    for joint, target in home.items():
                        print(f"{joint.removesuffix('.pos'):18} {actual[joint]:7.1f} {target:7.1f}", flush=True)
            elif {name: vars(cal) for name, cal in calibration.items()} == leader_cal:
                arms["leader"] = str(port)
                print(f"Leader ready on {port.name}.", flush=True)
            else:
                print(f"{port.name}: six motors replied, calibration profile unrecognized.", flush=True)
        except (ConnectionError, RuntimeError) as exc:
            print(f"{port.name}: {exc}", flush=True)
        finally:
            if bus.is_connected:
                bus.disconnect(disable_torque=False)
    return arms


def save_photo(label: str, source: Path) -> None:
    from PIL import Image, ImageOps

    if Path(label).name != label or label in ("", ".", ".."):
        raise SystemExit("Use a short photo label such as A-before.")
    if not source.is_file():
        raise SystemExit(f"Image not found: {source}")
    PHOTOS.mkdir(parents=True, exist_ok=True)
    base = PHOTOS / f"{label}.jpg"
    dest = base
    suffix = 2
    while dest.exists():
        dest = base.with_stem(f"{label}-{suffix}")
        suffix += 1
    with tempfile.TemporaryDirectory() as tmp:
        converted = Path(tmp) / "photo.jpg"
        subprocess.run(["sips", "-s", "format", "jpeg", str(source.resolve()), "--out", str(converted)],
                       check=True, stdout=subprocess.DEVNULL)
        with Image.open(converted) as photo:
            ImageOps.exif_transpose(photo).convert("RGB").save(dest, quality=95)
    print(dest.relative_to(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(prog="openarms")
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="identify both arms and check motor replies without moving")
    status.add_argument("--joints", action="store_true", help="show current and saved HOME joint positions")
    status.add_argument("--poses", type=Path, default=POSES)
    photo = commands.add_parser("photo", help="save an AirDropped phone image as JPEG")
    photo.add_argument("label")
    photo.add_argument("path", type=Path)
    teach = commands.add_parser("teach", help="mirror the leader and record poses in a separate file")
    teach.add_argument("--poses", type=Path, default=PHOTOS / "taught-poses.json")
    capture = commands.add_parser("capture", help="record one guided demonstration and its reusable checkpoints")
    capture.add_argument("source", choices=("A", "C", "water"), nargs="?", default="A")
    capture.add_argument("--take", help="label for a separate demonstration, e.g. 02")
    commands.add_parser("home", help="guide the follower to the saved HOME using the leader")
    transfer = commands.add_parser("transfer", help="run the mandarin transfer to B")
    transfer.add_argument("source", choices=("A", "C"), nargs="?", default="A")
    pose_file = transfer.add_mutually_exclusive_group()
    pose_file.add_argument("--poses", type=Path)
    pose_file.add_argument("--bench", action="store_true", help="use the locally captured A and B checkpoints")
    pickup = transfer.add_mutually_exclusive_group()
    pickup.add_argument("--offset", type=float, help="signed C shoulder-pan offset in degrees")
    pickup.add_argument("--taught", nargs="?", type=Path, const=PHOTOS / "taught-poses.json",
                        help="reuse taught C poses from the optional file")
    transfer.add_argument("--dry", action="store_true", help="empty C approach and high transit")
    transfer.add_argument("--high-carry", action="store_true", help="use the raised C lift and carry")
    transfer.add_argument("--empty", action="store_true", help="check A to B with the gripper open and no object")
    transfer.add_argument("--preview", action="store_true", help="print targets offline")
    pour = commands.add_parser("pour", help="run one fixed A-to-C cup pour and return HOME")
    pour.add_argument("mode", choices=("dry", "water", "preview"))
    pour.add_argument("--poses", type=Path, default=PHOTOS / "bench-water.json")
    compare = commands.add_parser("compare-pours", help="evaluate captured pour combinations on a fake arm")
    compare.add_argument("takes", nargs="*", type=Path)
    compare.add_argument("--out", type=Path)
    compare.add_argument("--watch", nargs="?", type=Path, const=PHOTOS, metavar="CAPTURE_DIR")
    args = parser.parse_args()

    if args.command == "photo":
        save_photo(args.label, args.path)
        return
    if args.command == "status":
        arms = find_arms(args.poses, show_joints=args.joints)
        for arm in ("leader", "follower"):
            if arm not in arms:
                print(f"{arm.capitalize()} not detected.")
        return
    if args.command in ("teach", "home", "capture"):
        if args.command == "capture":
            if args.take is not None and not re.fullmatch(r"[A-Za-z0-9_-]+", args.take):
                parser.error("use letters, numbers, underscores or dashes for --take")
            suffix = f"-{args.take}" if args.take else ""
            path = PHOTOS / f"bench-{args.source.lower()}{suffix}.json"
            if path.exists():
                raise SystemExit(f"A completed capture already exists at {path.relative_to(ROOT)}.")
        arms = find_arms(POSES)
        if not {"leader", "follower"} <= arms.keys():
            raise SystemExit("Connect and power both arms to use the leader.")
        if args.command == "teach" and args.poses.resolve() == POSES:
            raise SystemExit("Choose a separate teach file to preserve the existing baseline.")
        if args.command == "capture":
            print("Clear the bench. Hold the leader comfortably and still until capture starts.", flush=True)
        else:
            print("Support the follower, match the leader to its current pose, and clear the bench.", flush=True)
        if input("Ready to start mirroring? y/n> ").strip().lower() not in ("y", "yes"):
            return
        if args.command == "capture":
            mode = ["--capture", str(path), "--source", args.source]
        elif args.command == "home":
            mode = ["--home", str(POSES)]
        else:
            mode = ["--out", str(args.poses)]
        command = ["teleop_record", *mode, "--follower-port", arms["follower"],
                   "--leader-port", arms["leader"]]
    elif args.command == "compare-pours":
        command = ["compare_pour_takes", *(str(path) for path in args.takes)]
        if args.out:
            command.extend(["--out", str(args.out)])
        if args.watch is not None:
            command.extend(["--watch", str(args.watch)])
    elif args.command == "pour":
        if not args.poses.is_file():
            raise SystemExit("Capture the cup and receiver first with `openarms capture water`.")
        command = ["pour_once", args.mode, "--poses", str(args.poses), "--receipt-dir", str(PHOTOS / "runs")]
        if args.mode != "preview":
            arms = find_arms(args.poses)
            if "follower" not in arms:
                raise SystemExit("Follower unavailable. Connect its USB data cable and switch on motor power.")
            command.extend(["--port", arms["follower"]])
    else:
        poses = PHOTOS / "bench-a.json" if args.bench else (args.poses or POSES)
        if not poses.is_file():
            raise SystemExit(f"Pose file missing: {poses}. Run `openarms capture A` for a bench capture.")
        command = ["transfer_once", "--source", args.source, "--poses", str(poses)]
        if args.offset is not None:
            command.append(f"--pan-offset-deg={args.offset}")
        if args.taught is not None:
            command.extend(["--pickup", str(args.taught)])
        elif args.bench and args.source == "C" and args.offset is None:
            command.extend(["--pickup", str(PHOTOS / "bench-c.json")])
        if args.dry:
            command.append("--dry-approach")
        if args.high_carry:
            command.append("--high-carry")
        if args.empty:
            command.append("--empty")
        if args.preview:
            command.append("--preview")
        else:
            arms = find_arms(poses)
            if "follower" not in arms:
                raise SystemExit("Follower unavailable. Connect its USB data cable and switch on motor power.")
            command.extend(["--port", arms["follower"], "--receipt-dir", str(PHOTOS / "runs")])
    os.execv(sys.executable, [sys.executable, "-m", f"firmware.openarms_executor.{command[0]}", *command[1:]])


if __name__ == "__main__":
    main()
