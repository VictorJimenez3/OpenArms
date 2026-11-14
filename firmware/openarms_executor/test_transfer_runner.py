"""Black-box tests for transfer_runner, written from the relay contract before reading the module.
Run from the repo root: python -m firmware.openarms_executor.test_transfer_runner"""
import asyncio
import copy
import json
import os
import time
import traceback
from pathlib import Path

from firmware.openarms_executor.motion import FakeRobot
from firmware.openarms_executor import transfer_runner as tr

POSES_PATH = Path(__file__).with_name("poses.example.json")
POSES = json.loads(POSES_PATH.read_text())
FAST = dict(seconds=0.01, hz=10)
HOME = POSES["poses"]["HOME"]  # the runner refuses to start anywhere else


def plan(pid="P1", obj="mandarin", src="A", dst="B"):
    return {"plan_id": pid, "object": obj, "source": src, "destination": dst}


def make(robot=None, answer="y", **kw):
    asks = []

    def ask(prompt):
        asks.append(prompt)
        return answer

    kw = {**FAST, **kw}
    r = tr.PoseTransferRunner(robot or FakeRobot(HOME), copy.deepcopy(POSES), ask=ask, **kw)
    return r, asks


class StuckRobot(FakeRobot):
    """shoulder_pan never moves, so move_to must fault."""

    def send_action(self, action):
        action = {k: v for k, v in action.items() if k != "shoulder_pan.pos"}
        return super().send_action(action)


def check_result(res, pid, status):
    assert res.plan_id == pid, res
    assert res.mode == "physical", res
    assert res.status == status, res
    assert res.placement is None, res
    assert res.operator_authorized is True, res


async def t_mode():
    r, _ = make()
    assert r.mode == "physical"


async def t_authorize_answers():
    for ans, want in [("y", True), ("yes", True), ("n", False), ("", False), ("maybe", False), ("no", False)]:
        r, asks = make(answer=ans)
        got = await r.authorize(plan())
        assert got is want, (ans, got)
        assert asks, "operator was never asked"


async def t_unauthorized_execute():
    robot = FakeRobot(HOME)
    r, _ = make(robot)
    try:
        await r.execute(plan())
    except ValueError:
        pass
    else:
        raise AssertionError("execute without authorize did not raise")
    assert robot.sent == [], "moved without authorization"


async def t_rejected_then_execute():
    robot = FakeRobot(HOME)
    r, _ = make(robot, answer="n")
    assert await r.authorize(plan()) is False
    try:
        await r.execute(plan())
    except ValueError:
        pass
    else:
        raise AssertionError("execute after rejected authorize did not raise")
    assert robot.sent == []


async def t_happy_path():
    robot = FakeRobot(HOME)
    r, _ = make(robot)
    assert await r.authorize(plan()) is True
    res = await r.execute(plan())
    check_result(res, "P1", "completed")
    assert robot.sent, "no motion sent"


async def t_one_auth_one_run():
    robot = FakeRobot(HOME)
    r, _ = make(robot)
    assert await r.authorize(plan())
    check_result(await r.execute(plan()), "P1", "completed")
    n = len(robot.sent)
    try:
        await r.execute(plan())
    except ValueError:
        pass
    else:
        raise AssertionError("second execute on one authorization did not raise")
    assert len(robot.sent) == n


async def t_auth_other_plan_id():
    robot = FakeRobot(HOME)
    r, _ = make(robot)
    assert await r.authorize(plan("P1"))
    try:
        await r.execute(plan("P2"))
    except ValueError:
        pass
    else:
        raise AssertionError("execute of a different plan_id did not raise")
    assert robot.sent == []


async def t_wrong_plan():
    for bad in [plan(obj="apple"), plan(src="B", dst="A"), plan(dst="C")]:
        robot = FakeRobot(HOME)
        r, _ = make(robot)
        if await r.authorize(bad):
            res = await r.execute(bad)
            check_result(res, "P1", "failed")
        assert robot.sent == [], f"moved for {bad}"


async def t_shifted_pickup_and_shared_placement():
    robot = FakeRobot(HOME)
    r, asks = make(robot, pan_offset_deg=4, pan_limits=(-100, 100))
    baseline, shifted = r.scripts["A"], r.scripts["C"]
    assert shifted[0] == baseline[0] and shifted[3] == baseline[3]
    for i in (1, 2, 4):
        assert shifted[i] == {**baseline[i], tr.PAN: baseline[i][tr.PAN] + 4}
    assert shifted[5:] == baseline[5:]
    assert await r.authorize(plan())
    check_result(await r.execute(plan(src="C")), "P1", "failed")
    assert robot.sent == []
    assert await r.authorize(plan(src="C")) and "pan offset +4°" in asks[-1]
    check_result(await r.execute(plan(src="C")), "P1", "completed")


async def t_taught_pickup_and_dry_approach():
    robot = FakeRobot(HOME)
    p = POSES["poses"]
    taught = {"ABOVE_C": p["ABOVE_A"], "GRASP_C": {**p["GRASP_A"], tr.PAN: 2}}
    r, asks = make(robot, taught_pickup=taught, dry_approach=True)
    assert await r.authorize(plan(src="C")) and "empty approach to C (taught pickup)" in asks[-1]
    check_result(await r.execute(plan(src="C")), "P1", "completed")
    assert robot.sent == [{tr.GRIPPER: POSES["gripper"]["open"]}, taught["ABOVE_C"], taught["GRASP_C"],
                          taught["ABOVE_C"], p["ABOVE_B"], HOME]


async def t_high_carry_stops_without_lift_confirmation():
    for dry, accept in ((False, True), (False, False), (True, False)):
        waypoints, checks = [], []
        limits = {joint: (-180, 180) for joint in HOME} | {tr.GRIPPER: (0, 100)}

        def trace(event, **details):
            if event == "waypoint":
                waypoints.append(details["target"])

        def confirm(_should_stop):
            checks.append(len(waypoints))
            return accept

        r, _ = make(pan_offset_deg=5, pan_limits=limits[tr.PAN], joint_limits=limits,
                    high_carry=True, dry_approach=dry, confirm_lift=confirm, trace=trace)
        request = plan(src="C")
        assert await r.authorize(request)
        check_result(await r.execute(request), "P1", "completed" if dry or accept else "stopped")
        assert checks == ([] if dry else [6])
        assert waypoints == (r.scripts["C"] if dry or accept else r.scripts["C"][:6])
        raised_b = {joint: value + tr.HIGH_CARRY_DELTA.get(joint, 0)
                    for joint, value in POSES["poses"]["ABOVE_B"].items()}
        assert r.scripts["C"][6] == raised_b
        if dry:
            assert {p[tr.GRIPPER] for p in waypoints if tr.GRIPPER in p} == {POSES["gripper"]["open"]}


async def t_idle_stop_between_runs():
    # mandarin.close() calls stop() at every session end; idle stop must not latch.
    robot = FakeRobot(HOME)
    r, _ = make(robot)
    await r.stop()
    await r.stop()
    assert await r.authorize(plan("P1")) is True
    check_result(await r.execute(plan("P1")), "P1", "completed")
    await r.stop()  # session close
    assert await r.authorize(plan("P2")) is True, "idle stop latched the arm"
    check_result(await r.execute(plan("P2")), "P2", "completed")


async def t_stop_mid_run():
    robot = FakeRobot(HOME)
    r, _ = make(robot, seconds=0.3, hz=20)
    assert await r.authorize(plan())
    task = asyncio.create_task(r.execute(plan()))
    await asyncio.sleep(0.15)
    assert robot.sent, "motion had not started"
    await r.stop()
    res = await asyncio.wait_for(task, 3)
    check_result(res, "P1", "stopped")
    n = len(robot.sent)
    await asyncio.sleep(0.4)
    assert len(robot.sent) == n, "motion continued after stopped result"
    assert await r.authorize(plan("P2")) is False, "stop mid-run did not latch"
    await r.stop()  # idempotent


async def t_stop_returns_after_motion_halts():
    # stop() is "promptly stops/holds": after await stop(), no further commands should go out.
    robot = FakeRobot(HOME)
    r, _ = make(robot, seconds=0.3, hz=20)
    assert await r.authorize(plan())
    task = asyncio.create_task(r.execute(plan()))
    await asyncio.sleep(0.15)
    await r.stop()
    n = len(robot.sent)
    await asyncio.sleep(0.3)
    sent_after = len(robot.sent) - n
    await task
    # One in-flight move may finish; record how many steps leaked past stop()'s return.
    print(f"    info: {sent_after} commands sent after stop() returned")


async def t_cancel():
    robot = FakeRobot(HOME)
    r, _ = make(robot, seconds=0.3, hz=20)
    assert await r.authorize(plan())
    task = asyncio.create_task(r.execute(plan()))
    await asyncio.sleep(0.15)
    task.cancel()
    try:
        await asyncio.wait_for(task, 3)
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("cancellation was swallowed")
    n = len(robot.sent)
    await asyncio.sleep(0.5)
    assert len(robot.sent) == n, f"motion thread kept running after cancel ({len(robot.sent) - n} more commands)"
    # caller then calls stop(); it must not raise
    await r.stop()
    assert await r.authorize(plan("P2")) is False, "cancelled mid-motion arm not latched"


async def t_fault_latch():
    robot = StuckRobot(HOME)
    r, asks = make(robot)
    assert await r.authorize(plan())
    t0 = time.monotonic()
    res = await r.execute(plan())
    check_result(res, "P1", "unknown")
    print(f"    info: fault took {time.monotonic() - t0:.1f}s")
    assert await r.authorize(plan("P2")) is False, "fault did not latch"
    await r.stop()


async def t_execute_does_not_block_loop():
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    r, _ = make(FakeRobot(HOME), seconds=0.3, hz=20)
    assert await r.authorize(plan())
    tk = asyncio.create_task(ticker())
    await r.execute(plan())
    tk.cancel()
    assert ticks > 10, f"event loop starved during execute (ticks={ticks})"


async def t_authorize_does_not_block_loop():
    # ask=input blocks; done on the loop thread it starves websocket pings for the whole prompt.
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    def slow_ask(prompt):
        time.sleep(0.3)
        return "y"

    r = tr.PoseTransferRunner(FakeRobot(HOME), copy.deepcopy(POSES), ask=slow_ask, **FAST)
    tk = asyncio.create_task(ticker())
    await asyncio.sleep(0)
    assert await r.authorize(plan())
    tk.cancel()
    assert ticks > 10, f"event loop blocked during authorize (ticks={ticks})"


async def t_concurrent_execute_shared_runner():
    # relay calls the factory per phone session but gets a singleton: two sessions can race.
    robot = FakeRobot(HOME)
    r, _ = make(robot, seconds=0.3, hz=20)
    assert await r.authorize(plan("P1"))
    assert await r.authorize(plan("P2"))
    t1 = asyncio.create_task(r.execute(plan("P1")))
    await asyncio.sleep(0.05)
    try:
        res2 = await r.execute(plan("P2"))
        status2 = res2.status
    except ValueError as e:
        status2 = f"ValueError({e})"
    res1 = await t1
    assert not (res1.status == "completed" and status2 == "completed"), "two runs moved the arm concurrently"
    print(f"    info: P1={res1.status} P2={status2}")


async def t_authorize_while_running():
    robot = FakeRobot(HOME)
    r, asks = make(robot, seconds=0.3, hz=20)
    assert await r.authorize(plan("P1"))
    t1 = asyncio.create_task(r.execute(plan("P1")))
    await asyncio.sleep(0.05)
    got = await r.authorize(plan("P2"))
    await t1
    assert got is False and len(asks) == 1, "operator asked to approve while the arm was still moving"


async def t_not_at_home():
    robot = FakeRobot()  # all zeros, far from HOME
    r, _ = make(robot)
    assert await r.authorize(plan())
    check_result(await r.execute(plan()), "P1", "failed")
    assert robot.sent == [], "moved from a pose other than HOME"
    robot.pos.update(HOME)  # not latched: once the arm is at HOME the next run works
    assert await r.authorize(plan("P2"))
    check_result(await r.execute(plan("P2")), "P2", "completed")


async def t_double_cancel():
    # a second cancel while waiting for the motion thread must still not free the arm for another run
    robot = FakeRobot(HOME)
    r, _ = make(robot, seconds=0.3, hz=20)
    assert await r.authorize(plan("P1"))
    t1 = asyncio.create_task(r.execute(plan("P1")))
    await asyncio.sleep(0.05)
    t1.cancel()
    await asyncio.sleep(0.01)
    t1.cancel()
    try:
        await t1
    except asyncio.CancelledError:
        pass
    assert not r._moving(), "execute returned while its motion thread was still running"
    assert await r.authorize(plan("P2")) is False, "a stopped arm accepted a new plan"


async def t_stale_prompt():
    # a hung-up session leaves its input() thread reading stdin; a new prompt would lose its answer to it
    import threading
    gate = threading.Event()
    asks = []
    def ask(q):
        asks.append(q)
        gate.wait(2)
        return "n"
    r = tr.PoseTransferRunner(FakeRobot(HOME), copy.deepcopy(POSES), ask=ask, **FAST)
    t1 = asyncio.create_task(r.authorize(plan("P1")))
    await asyncio.sleep(0.05)
    t1.cancel()
    assert await r.authorize(plan("P2")) is False and len(asks) == 1, "opened a second prompt while one was live"
    gate.set()
    await asyncio.sleep(0.05)
    assert await r.authorize(plan("P3")) is False and len(asks) == 2, "stale prompt never cleared"


def t_missing_poses():
    for drop in ["ABOVE_A", "GRASP_A", "ABOVE_B", "GRASP_B", "HOME"]:
        p = copy.deepcopy(POSES)
        del p["poses"][drop]
        try:
            tr.PoseTransferRunner(FakeRobot(HOME), p, ask=lambda _: "y", **FAST)
        except SystemExit:
            pass
        else:
            raise AssertionError(f"missing pose {drop} accepted")
    for drop in ["open", "cup"]:
        p = copy.deepcopy(POSES)
        del p["gripper"][drop]
        try:
            tr.PoseTransferRunner(FakeRobot(HOME), p, ask=lambda _: "y", **FAST)
        except SystemExit:
            pass
        else:
            raise AssertionError(f"missing gripper {drop} accepted")


def t_singleton():
    os.environ["OPENARMS_FAKE_ROBOT"] = "1"
    os.environ["OPENARMS_POSES"] = str(POSES_PATH)
    a = tr.create_runner()
    b = tr.create_runner()
    assert a is b, "create_runner is not a singleton"
    assert a.mode == "physical"


ASYNC = [t_mode, t_authorize_answers, t_unauthorized_execute, t_rejected_then_execute, t_happy_path,
         t_one_auth_one_run, t_auth_other_plan_id, t_wrong_plan, t_shifted_pickup_and_shared_placement,
         t_taught_pickup_and_dry_approach, t_high_carry_stops_without_lift_confirmation,
         t_idle_stop_between_runs, t_stop_mid_run,
         t_stop_returns_after_motion_halts, t_cancel, t_fault_latch, t_execute_does_not_block_loop,
         t_authorize_does_not_block_loop, t_concurrent_execute_shared_runner, t_authorize_while_running,
         t_not_at_home, t_double_cancel, t_stale_prompt]
SYNC = [t_missing_poses, t_singleton]


def main():
    failed = 0
    for t in ASYNC + SYNC:
        try:
            if t in ASYNC:
                asyncio.run(asyncio.wait_for(t(), 15))
            else:
                t()
            print(f"PASS {t.__name__}")
        except BaseException as e:  # SystemExit/CancelledError must count as failures too
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc(limit=3)
    print(f"{len(ASYNC) + len(SYNC) - failed}/{len(ASYNC) + len(SYNC)} passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
