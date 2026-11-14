"""Black-box tests for the arm lane, written from tmp/tickets/arm.md (interface block, R1-R5).
Run from the repo root: python -m firmware.openarms_executor.test_arm"""
import copy
import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "agentic" / "contracts"
EXAMPLE_POSES = ROOT / "firmware" / "openarms_executor" / "poses.example.json"
ARM = ["shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos", "wrist_flex.pos", "wrist_roll.pos"]
ALL = ARM + ["gripper.pos"]
NINE = ["HOME", "ABOVE_A", "GRASP_A", "ABOVE_B", "GRASP_B", "ABOVE_C", "TIP_C", "ABOVE_D", "TIP_D"]
GRIPPER = {"open": 11.0, "cup": 66.0}
FAST = dict(seconds=0.01, hz=30, pour_hold=0)


def make_poses(names=NINE, drop=()):
    # Distinct values per pose so a visit can be identified from the joint readings alone.
    return {n: {k: float(10 * i + j + 1) for j, k in enumerate(ARM)}
            for i, n in enumerate(names) if n not in drop}


def write_pose_file(d, poses, gripper=GRIPPER):
    path = Path(d) / "poses.json"
    path.write_text(json.dumps({"poses": poses, "gripper": gripper}))
    return str(path)


def stations():
    return json.loads((CONTRACTS / "stations.example.json").read_text())


def steps():
    s = json.loads((CONTRACTS / "expanded_steps.example.json").read_text())
    for st in s:
        if st["action"] == "wait":
            st["args"]["seconds"] = 0
    return s


def log_robot(start=None):
    from firmware.openarms_executor.motion import FakeRobot

    class LogRobot(FakeRobot):
        def __init__(self, start=None):
            super().__init__(start)
            self.sent = []

        def send_action(self, action):
            self.sent.append(dict(action))
            return super().send_action(action)

    return LogRobot(start)


def visited(sent, pose, since=0):
    return any(all(k in a and abs(a[k] - v) < 1e-9 for k, v in pose.items()) for a in sent[since:])


def arm_with(d, poses, st=None, start=None):
    from firmware.openarms_executor.poses import load_poses
    from firmware.openarms_executor.pose_arm import PoseArm
    robot = log_robot(start)
    arm = PoseArm(robot, load_poses(write_pose_file(d, poses)), st or stations(), **FAST)
    return robot, arm


def raises_before_moving(robot, arm, action, args, step):
    from agentic.openarms_agent.types import ArmError
    before = robot.get_observation()
    try:
        arm.run_step(action, args)
    except ArmError as e:
        assert e.step == step, f"ArmError step {e.step!r}, expected {step!r}"
    else:
        raise AssertionError(f"{action} {args} did not raise ArmError")
    assert robot.get_observation() == before, "robot moved before raising"


# --- R1 pose file ---

def test_poses_round_trip():
    from firmware.openarms_executor.poses import load_poses, save_pose
    with tempfile.TemporaryDirectory() as d:
        path = write_pose_file(d, {})
        joints = make_poses(["HOME"])["HOME"]
        save_pose(path, "HOME", joints)
        assert load_poses(path)["poses"]["HOME"] == joints


def test_save_keeps_other_names():
    from firmware.openarms_executor.poses import load_poses, save_pose
    with tempfile.TemporaryDirectory() as d:
        poses = make_poses(["HOME", "ABOVE_A"])
        path = write_pose_file(d, poses)
        new = {k: -1.0 for k in ARM}
        save_pose(path, "GRASP_A", new)
        got = load_poses(path)
        assert got["poses"]["HOME"] == poses["HOME"] and got["poses"]["ABOVE_A"] == poses["ABOVE_A"]
        assert got["poses"]["GRASP_A"] == new
        assert got["gripper"] == GRIPPER, "save_pose dropped the gripper table"


def test_example_file_has_nine_names():
    from firmware.openarms_executor.poses import load_poses
    p = load_poses(str(EXAMPLE_POSES))
    assert sorted(p["poses"]) == sorted(NINE), sorted(p["poses"])
    assert {"open", "cup"} <= set(p["gripper"]), p["gripper"]
    for name, joints in p["poses"].items():
        assert sorted(joints) == sorted(ARM), f"{name} keys {sorted(joints)}"


# --- R2 smooth move ---

def test_fake_robot_defaults_to_zero():
    from firmware.openarms_executor.motion import FakeRobot
    assert FakeRobot().get_observation() == {k: 0.0 for k in ALL}


def test_fake_robot_start_overrides():
    from firmware.openarms_executor.motion import FakeRobot
    obs = FakeRobot({"elbow_flex.pos": 5.0}).get_observation()
    assert obs == {**{k: 0.0 for k in ALL}, "elbow_flex.pos": 5.0}, obs


def test_move_ends_on_target_and_steps_are_small():
    from firmware.openarms_executor.motion import move_to
    start = {k: float(i) for i, k in enumerate(ALL)}
    target = {"shoulder_pan.pos": 40.0, "elbow_flex.pos": -30.0, "gripper.pos": 50.0}
    seconds, hz = 0.2, 50
    robot = log_robot(start)
    assert move_to(robot, target, seconds=seconds, hz=hz) is True
    obs = robot.get_observation()
    for k, v in target.items():
        assert obs[k] == v, f"{k} ended at {obs[k]}, target {v}"
    for k in ALL:
        if k not in target:
            assert obs[k] == start[k], f"untouched {k} changed to {obs[k]}"
    for k, t in target.items():
        limit = abs(t - start[k]) / (seconds * hz) + 1e-9
        prev = start[k]
        for a in robot.sent:
            if k in a:
                assert abs(a[k] - prev) <= limit, f"{k} jumped {abs(a[k] - prev)} > {limit}"
                prev = a[k]
    for a in robot.sent:
        for k in ALL:
            if k not in target and k in a:
                assert a[k] == start[k], f"untouched {k} sent as {a[k]}"


def test_move_stop_midway_holds_between():
    from firmware.openarms_executor.motion import move_to
    start = {k: 0.0 for k in ALL}
    target = {"shoulder_pan.pos": 30.0, "wrist_flex.pos": -30.0}
    calls = [0]

    def should_stop():
        calls[0] += 1
        return calls[0] > 3

    robot = log_robot(start)
    assert move_to(robot, target, seconds=0.5, hz=30, should_stop=should_stop) is False
    obs = robot.get_observation()
    for k, t in target.items():
        lo, hi = sorted((start[k], t))
        assert lo <= obs[k] <= hi, f"{k}={obs[k]} outside [{lo}, {hi}]"
        assert obs[k] != t, f"{k} reached target despite stop"


def test_connect_fake_returns_fake_robot():
    from firmware.openarms_executor.motion import FakeRobot
    from firmware.openarms_executor.robot import connect
    assert isinstance(connect(fake=True, port=None, robot_id="test"), FakeRobot)


# --- R3 PoseArm ---

def test_expanded_steps_end_state():
    with tempfile.TemporaryDirectory() as d:
        poses = make_poses()
        robot, arm = arm_with(d, poses)
        s0 = arm.state()
        for st in steps():
            arm.run_step(st["action"], st["args"])
        s1 = arm.state()
        assert s1["at"] == "HOME", s1
        assert s1["holding"] is None, s1
        assert s1["portions_left"]["A"] == s0["portions_left"]["A"] - 1, (s0, s1)
        assert s1["receiver_load"]["C"] == s0["receiver_load"]["C"] + 1, (s0, s1)
        obs = robot.get_observation()
        for k, v in poses["HOME"].items():
            assert abs(obs[k] - v) < 1e-9, f"not at HOME: {k}={obs[k]}"


def test_initial_state_from_stations():
    with tempfile.TemporaryDirectory() as d:
        _, arm = arm_with(d, make_poses())
        s = arm.state()
        assert s["holding"] is None and s["portions_left"]["A"] == 2 and s["receiver_load"]["C"] == 0, s


def test_missing_tip_c_raises_on_pour():
    with tempfile.TemporaryDirectory() as d:
        robot, arm = arm_with(d, make_poses(drop=("TIP_C",)))
        arm.run_step("pick", {"station": "A"})
        raises_before_moving(robot, arm, "pour", {"into": "C"}, "pour")


def test_pick_empty_station_raises():
    with tempfile.TemporaryDirectory() as d:
        st = copy.deepcopy(stations())
        st["A"]["portions"] = 0
        robot, arm = arm_with(d, make_poses(), st)
        raises_before_moving(robot, arm, "pick", {"station": "A"}, "pick")


def test_pour_holding_nothing_raises():
    with tempfile.TemporaryDirectory() as d:
        robot, arm = arm_with(d, make_poses())
        raises_before_moving(robot, arm, "pour", {"into": "C"}, "pour")


def test_return_cup_wrong_station_raises():
    with tempfile.TemporaryDirectory() as d:
        robot, arm = arm_with(d, make_poses())
        arm.run_step("pick", {"station": "A"})
        raises_before_moving(robot, arm, "return_cup", {"station": "B"}, "return_cup")


def test_second_portion_uses_slot_two_poses():
    with tempfile.TemporaryDirectory() as d:
        poses = make_poses(NINE + ["ABOVE_A2", "GRASP_A2"])
        robot, arm = arm_with(d, poses)
        arm.run_step("pick", {"station": "A"})
        assert visited(robot.sent, poses["ABOVE_A"]) and visited(robot.sent, poses["GRASP_A"]), "first pick skipped ABOVE_A/GRASP_A"
        assert not visited(robot.sent, poses["ABOVE_A2"]), "first pick used slot 2"
        arm.run_step("pour", {"into": "C"})
        arm.run_step("return_cup", {"station": "A"})
        arm.run_step("home", {})
        mark = len(robot.sent)
        arm.run_step("pick", {"station": "A"})
        assert visited(robot.sent, poses["ABOVE_A2"], mark), "second pick never reached ABOVE_A2"
        assert visited(robot.sent, poses["GRASP_A2"], mark), "second pick never reached GRASP_A2"


def test_stop_then_run_step_raises():
    from agentic.openarms_agent.types import ArmError
    with tempfile.TemporaryDirectory() as d:
        robot, arm = arm_with(d, make_poses())
        arm.stop()
        before = robot.get_observation()
        try:
            arm.run_step("home", {})
        except ArmError:
            pass
        else:
            raise AssertionError("run_step after stop() did not raise ArmError")
        assert robot.get_observation() == before, "robot moved after stop()"


def test_gripper_uses_table_values():
    with tempfile.TemporaryDirectory() as d:
        robot, arm = arm_with(d, make_poses())
        arm.run_step("pick", {"station": "A"})
        assert visited(robot.sent, {"gripper.pos": GRIPPER["open"]}), "gripper never reached open"
        assert robot.get_observation()["gripper.pos"] == GRIPPER["cup"], "gripper not at cup after pick"
        arm.run_step("pour", {"into": "C"})
        arm.run_step("return_cup", {"station": "A"})
        assert robot.get_observation()["gripper.pos"] == GRIPPER["open"], "gripper not open after return_cup"


# --- R4 / R5 CLI ---

def run_cli(*args, stdin=subprocess.DEVNULL):
    return subprocess.run([sys.executable, "-m", *args], cwd=ROOT, stdin=stdin,
                          capture_output=True, text=True, timeout=120)


def test_cli_record_and_replay_fake():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "poses.fake.json")
        r = run_cli("firmware.openarms_executor.record_pose", "--fake", "--name", "HOME", "--out", out)
        assert r.returncode == 0, f"record_pose exit {r.returncode}: {r.stderr[-500:]}"
        from firmware.openarms_executor.poses import load_poses
        assert "HOME" in load_poses(out)["poses"], "record_pose did not save HOME"
        r = run_cli("firmware.openarms_executor.replay_test", "--fake")
        assert r.returncode == 0, f"replay_test exit {r.returncode}: {r.stderr[-500:]}"


def test_cli_test_action_verified():
    # test_action.py has no output flag, so restore outputs/arm_tests.json to how it was.
    outdir = ROOT / "outputs"
    log = outdir / "arm_tests.json"
    had_dir, old = outdir.exists(), log.read_bytes() if log.exists() else None
    try:
        r = run_cli("firmware.openarms_executor.test_action", "--action", "pick", "--station", "A",
                    "--runs", "10", "--fake", "--yes", "--seconds", "0.01", "--poses", str(EXAMPLE_POSES))
        assert r.returncode == 0, f"test_action exit {r.returncode}: {r.stderr[-500:]}"
        assert "10/10 verified" in r.stdout, f"stdout: {r.stdout[-500:]}"
    finally:
        if old is not None:
            log.write_bytes(old)
        elif log.exists():
            log.unlink()
        if not had_dir and outdir.exists() and not any(outdir.iterdir()):
            outdir.rmdir()


# --- arrival check: settle, then nudge past the target to cancel sag ---

def sagging_robot(droop, start=None):
    """A robot whose joints settle `droop` short of whatever they are commanded, like a loaded arm."""
    from firmware.openarms_executor.motion import FakeRobot

    class Sagging(FakeRobot):
        def get_observation(self):
            return {k: v - droop.get(k, 0.0) for k, v in self.pos.items()}

    return Sagging(start)


FAST_MOVE = dict(seconds=0.05, hz=60, settle=0.5)
LIFT, ELBOW, PAN = "shoulder_lift.pos", "elbow_flex.pos", "shoulder_pan.pos"


def test_sagging_arm_is_nudged_onto_its_target():
    from firmware.openarms_executor.motion import move_to
    # the shortfall measured on the real arm holding an object at 42 cm reach
    robot = sagging_robot({LIFT: 6.2, ELBOW: 3.6})
    target = {PAN: -21.0, LIFT: 47.0, ELBOW: -53.0}
    assert move_to(robot, target, **FAST_MOVE) is True
    obs = robot.get_observation()
    for k, v in target.items():
        assert abs(obs[k] - v) <= 3.0, f"{k} ended {obs[k] - v:+.1f} from target"
    last = robot.sent[-1]
    assert abs(last[LIFT] - (47.0 + 6.2)) < 1e-6 and abs(last[ELBOW] - (-53.0 + 3.6)) < 1e-6, last
    assert last[PAN] == -21.0, "a joint that arrived must not be nudged"


def test_nudge_never_commands_more_than_the_cap_past_the_target():
    from firmware.openarms_executor.motion import move_to
    robot = sagging_robot({LIFT: 11.5})  # under the snag limit, but more than the cap can correct
    try:
        move_to(robot, {LIFT: 40.0}, **FAST_MOVE)
    except RuntimeError as e:
        assert "after 2 nudges" in str(e), e
    else:
        raise AssertionError("no error for a sag the nudges cannot close")
    assert abs(max(a[LIFT] for a in robot.sent) - 48.0) < 1e-6, "cap is 8 past the target"


def test_blocked_joint_is_not_pushed_harder():
    from firmware.openarms_executor.motion import move_to
    robot = sagging_robot({LIFT: 20.0})  # far beyond sag: something is in the way
    try:
        move_to(robot, {LIFT: 40.0}, **FAST_MOVE)
    except RuntimeError as e:
        assert "blocking" in str(e), e
    else:
        raise AssertionError("no error for a blocked joint")
    assert max(a[LIFT] for a in robot.sent) <= 40.0, "no command went past the target"


def test_gripper_shortfall_is_never_nudged():
    from firmware.openarms_executor.motion import move_to
    robot = sagging_robot({"gripper.pos": 18.0})  # jaws stopped on the object
    assert move_to(robot, {"gripper.pos": 5.0}, **FAST_MOVE) is True
    assert robot.sent[-1] == {"gripper.pos": 5.0}


def test_stop_while_waiting_for_a_sagging_arm_returns_false():
    from firmware.openarms_executor.motion import move_to
    robot, calls = sagging_robot({LIFT: 6.0}), [0]

    def should_stop():
        calls[0] += 1
        return calls[0] > 6  # after the 3 interpolation steps, during the settle wait

    assert move_to(robot, {LIFT: 40.0}, should_stop=should_stop, **FAST_MOVE) is False
    assert max(a[LIFT] for a in robot.sent) <= 40.0, "stopped before any nudge"


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:
            failed += 1
            msg = str(e) or traceback.format_exception_only(type(e), e)[-1].strip()
            print(f"FAIL {name}: {type(e).__name__}: {msg}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
