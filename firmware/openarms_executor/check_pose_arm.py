"""Self-check for PoseArm on FakeRobot with the example poses and contract steps."""
import copy
import json
import threading
from pathlib import Path

from agentic.openarms_agent.types import ArmError

from .motion import FakeRobot
from .pose_arm import PoseArm
from .poses import load_poses

ROOT = Path(__file__).resolve().parents[2]
stations = json.loads((ROOT / "agentic/contracts/stations.example.json").read_text())
steps = json.loads((ROOT / "agentic/contracts/expanded_steps.example.json").read_text())
poses = load_poses(Path(__file__).with_name("poses.example.json"))

robot = FakeRobot()
arm = PoseArm(robot, poses, stations, seconds=0.05, pour_hold=0.0)
for s in steps:
    arm.run_step(s["action"], {"seconds": 0} if s["action"] == "wait" else s["args"])
st = arm.state()
assert all(robot.pos[k] == v for k, v in poses["poses"]["HOME"].items()), robot.pos
assert st["at"] == "HOME" and st["holding"] is None, st
assert st["portions_left"]["A"] == 1 and st["receiver_load"]["C"] == 1, st

no_tip = copy.deepcopy(poses)
del no_tip["poses"]["TIP_C"]
r2 = FakeRobot()
arm2 = PoseArm(r2, no_tip, stations, seconds=0.01)
arm2.run_step("pick", {"station": "A"})
before = r2.get_observation()
try:
    arm2.run_step("pour", {"into": "C"})
    raise AssertionError("missing TIP_C did not raise")
except ArmError as e:
    assert e.step == "pour" and r2.get_observation() == before, e

try:
    PoseArm(FakeRobot(), poses, stations).run_step("pour", {"into": "C"})
    raise AssertionError("pour with an empty gripper did not raise")
except ArmError as e:
    assert e.step == "pour"

arm3 = PoseArm(FakeRobot(), poses, stations, seconds=1.0)
threading.Timer(0.2, arm3.stop).start()
for action, args in [("pick", {"station": "A"}), ("home", {})]:
    try:
        arm3.run_step(action, args)
        raise AssertionError(f"{action} ran after stop")
    except ArmError as e:
        assert e.step == action
print("check_pose_arm ok:", st)
