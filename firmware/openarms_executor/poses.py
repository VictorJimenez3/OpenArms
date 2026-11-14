"""Named arm poses saved as joint readings: {"poses": {name: {joint: value}}, "gripper": {"open": v, "cup": v}}."""
import json
from pathlib import Path

ARM_JOINTS = ("shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos", "wrist_flex.pos", "wrist_roll.pos")
GRIPPER = "gripper.pos"


def load_poses(path) -> dict:
    data = json.loads(Path(path).read_text())
    return {"poses": data.get("poses", {}), "gripper": data.get("gripper", {})}


def save_pose(path, name: str, joints: dict) -> None:
    p = Path(path)
    data = load_poses(p) if p.exists() else {"poses": {}, "gripper": {}}
    # The gripper lives only in the gripper table, so a pose never opens or closes it.
    data["poses"][name] = {k: float(joints[k]) for k in ARM_JOINTS if k in joints}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")


def save_gripper(path, name: str, value: float) -> None:
    p = Path(path)
    data = load_poses(p) if p.exists() else {"poses": {}, "gripper": {}}
    data["gripper"][name] = float(value)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")
