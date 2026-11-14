"""Physical mandarin transfer runner. A uses saved poses, and an optional pan offset enables C.

Run: PYTHONPATH=<repo root> OPENARMS_FOLLOWER_PORT=/dev/tty.usbmodem... python relay.py --dialogue agy \
       --runner firmware.openarms_executor.transfer_runner:create_runner   (OPENARMS_FAKE_ROBOT=1 for no hardware)
"""
import asyncio
import math
import os
from dataclasses import dataclass
from pathlib import Path

from .motion import move_to
from .poses import ARM_JOINTS, GRIPPER, load_poses
from .robot import connect

ROOT = Path(__file__).resolve().parents[2]
HOME_TOL = 5.0  # degrees with the pinned LeRobot follower configuration
PAN = "shoulder_pan.pos"
MAX_SOURCE_OFFSET_DEG = 8.0  # first trials are restricted to a small arc around the shoulder pivot
HIGH_CARRY_DELTA = {"shoulder_lift.pos": -6.4, "elbow_flex.pos": -0.8, "wrist_flex.pos": 5.3}


@dataclass(frozen=True)
class ExecutionResult:  # same fields as relay/runner.py; the relay only reads the attributes
    plan_id: str
    mode: str
    status: str
    placement: str | None = None
    operator_authorized: bool = False


class PoseTransferRunner:
    mode = "physical"

    def __init__(self, robot, poses: dict, seconds: float = 1.5, hz: float = 30, ask=input,
                 *, pan_offset_deg: float | None = None, pan_limits: tuple[float, float] | None = None,
                 taught_pickup: dict | None = None, dry_approach: bool = False,
                 empty: bool = False, trace=None, high_carry: bool = False,
                 joint_limits: dict | None = None, confirm_lift=None) -> None:
        self.robot, self.poses, self.seconds, self.hz, self.ask = robot, poses, seconds, hz, ask
        self.pan_offset_deg, self.dry_approach = pan_offset_deg, dry_approach
        self.empty, self.trace = empty, trace
        self.high_carry, self.confirm_lift = high_carry, confirm_lift
        baseline = self._script()
        self.scripts = {} if dry_approach else {"A": baseline}
        pickup = []
        if taught_pickup is not None:
            if pan_offset_deg is not None:
                raise ValueError("choose a taught C pickup or a pan offset")
            pickup = [taught_pickup.get(name, {}) for name in ("ABOVE_C", "GRASP_C")]
        if pan_offset_deg is not None:
            if not 0 < abs(pan_offset_deg) <= MAX_SOURCE_OFFSET_DEG or not pan_limits:
                raise ValueError(f"C needs calibrated pan limits and a nonzero offset up to {MAX_SOURCE_OFFSET_DEG:g}°")
            for name in ("ABOVE_A", "GRASP_A"):
                pose = dict(self.poses["poses"][name])
                pose[PAN] = pose.get(PAN, math.nan) + pan_offset_deg
                if not pan_limits[0] <= pose[PAN] <= pan_limits[1]:
                    raise ValueError(f"offset {name} is outside the calibrated shoulder pan range")
                pickup.append(pose)
        if high_carry and (pan_offset_deg is None or not joint_limits or (not dry_approach and confirm_lift is None)):
            raise ValueError("high carry requires an offset, calibrated joint limits and a lift confirmation for loaded runs")
        if pickup:
            for pose in pickup:
                if set(pose) != set(ARM_JOINTS) or not all(math.isfinite(v) for v in pose.values()):
                    raise ValueError("C needs complete, finite approach and grasp joint positions")
            self.scripts["C"] = self._script(*pickup, dry_approach=dry_approach, high_carry=high_carry)
            if high_carry:
                for target in self.scripts["C"]:
                    if set(target) not in (set(ARM_JOINTS), {GRIPPER}):
                        raise ValueError("high carry requires complete arm poses and separate gripper targets")
                    for joint, value in target.items():
                        low, high = joint_limits.get(joint, (math.inf, -math.inf))
                        if not low <= value <= high:
                            raise ValueError(f"high-carry target for {joint} is outside its calibrated range")
        elif dry_approach:
            raise ValueError("dry approach requires a C pickup")
        self._authorized: dict[str, tuple] = {}
        self._stop = False
        self._faulted = False  # arm position unknown after a fault or stop: no motion until a restart
        self._motion = None  # the motion thread's future; it can't be killed, so it is never forgotten
        self._prompt = None  # the open operator prompt; a stale one would swallow the next answer

    def _script(self, above: dict | None = None, grasp: dict | None = None,
                *, dry_approach: bool = False, high_carry: bool = False) -> list[dict]:
        p, g = self.poses["poses"], self.poses["gripper"]
        names = ["ABOVE_A", "GRASP_A", "ABOVE_B", "GRASP_B", "HOME"]
        missing = [n for n in names if n not in p] + [n for n in ("open", "cup") if n not in g]
        if missing:
            raise SystemExit(f"pose file is missing {missing}: record them with teleop_record")
        o, c = {GRIPPER: g["open"]}, {GRIPPER: g["cup"]}
        above = p["ABOVE_A"] if above is None else above
        grasp = p["GRASP_A"] if grasp is None else grasp
        pickup = [o, above, grasp]
        if high_carry:
            def raised(pose):
                return {joint: value + HIGH_CARRY_DELTA.get(joint, 0) for joint, value in pose.items()}

            return pickup + [o if dry_approach else c, above, raised(above), raised(p["ABOVE_B"]),
                             p["ABOVE_B"], p["GRASP_B"], o, p["ABOVE_B"], p["HOME"]]
        if dry_approach:
            return pickup + [above, p["ABOVE_B"], p["HOME"]]
        return pickup + [o if self.empty else c, above, p["ABOVE_B"], p["GRASP_B"], o, p["ABOVE_B"], p["HOME"]]

    def _plan_route(self, plan: dict) -> tuple | None:
        obj, source, dest = (plan.get(key) for key in ("object", "source", "destination"))
        if obj == "mandarin" and dest == "B" and isinstance(source, str) and source in self.scripts:
            return obj, source, dest
        return None

    async def authorize(self, plan: dict) -> bool:
        route = self._plan_route(plan)
        if route is None:
            return False
        if self._faulted:
            print("Arm faulted or stopped in an earlier transfer: check the bench and restart the relay.")
            return False
        if self._moving():
            print(f"Refused plan {plan.get('plan_id')}: a transfer is still moving.")
            return False
        if self._prompt is not None and not self._prompt.done():
            print(f"Refused plan {plan.get('plan_id')}: an earlier prompt is still open; answer it n, then ask again.")
            return False
        pid = plan["plan_id"]
        self._authorized.pop(pid, None)
        source = route[1]
        pickup = "taught pickup" if self.pan_offset_deg is None else f"pan offset {self.pan_offset_deg:+g}°"
        if source == "C" and self.high_carry:
            pickup += ", raised carry"
        if self.dry_approach:
            action = "empty C -> B waypoint check" if self.high_carry else "empty approach to C"
            q = (f"\nPlan {pid}: {action} ({pickup}), then HOME. "
                 "C empty, arm at HOME, bench clear? y/n> ")
        elif self.empty:
            q = (f"\nPlan {pid}: empty {source} -> B waypoint check. "
                 "Mandarin removed, gripper and bench clear, arm at HOME? y/n> ")
        else:
            note = f" ({pickup})" if source == "C" else ""
            q = (f"\nPlan {pid}: move the mandarin {source} -> B{note}. "
                 f"Mandarin at {source}, arm at HOME, bench clear? y/n> ")
        self._prompt = asyncio.ensure_future(asyncio.to_thread(self.ask, q))
        ok = (await self._prompt).strip().lower() in ("y", "yes")
        if ok:
            self._authorized[pid] = route
        return ok

    async def execute(self, plan: dict) -> ExecutionResult:
        pid = plan["plan_id"]
        def result(status: str) -> ExecutionResult:
            # placement=None: a finished script is not proof the mandarin landed at B
            return ExecutionResult(pid, self.mode, status, None, True)
        if pid not in self._authorized:
            raise ValueError(f"plan {pid} was not authorized by the bench operator")
        route = self._authorized.pop(pid)  # one authorization, one run
        if self._plan_route(plan) != route:
            return result("failed")
        if self._faulted or self._moving():
            return result("failed")
        self._stop = False
        task = self._motion = asyncio.ensure_future(asyncio.to_thread(self._run, route[1]))
        try:
            return result(await asyncio.shield(task))
        except asyncio.CancelledError:
            # Wait through repeated cancels so no motion runs untracked.
            self._stop = True
            while not task.done():
                try:
                    await asyncio.wait({task})
                except asyncio.CancelledError:
                    pass
            raise

    def _moving(self) -> bool:
        return self._motion is not None and not self._motion.done()

    def _run(self, source: str) -> str:
        obs = self.robot.get_observation()
        if self.trace:
            self.trace("start_pose", joints={k: float(v) for k, v in obs.items() if k.endswith(".pos")})
        off = {k: v for k, v in self.poses["poses"]["HOME"].items() if abs(float(obs[k]) - v) > HOME_TOL}
        if off:  # the first move is a fixed-time straight line, so starting elsewhere could sweep the bench
            print(f"Not at HOME (off: {sorted(off)}); move the arm to HOME first.")
            return "failed"
        try:
            # New trajectories check stop within a segment and avoid overshoot from nudging.
            options = {"should_stop": lambda: self._stop, "nudges": 0} if source == "C" or self.empty else {}
            for index, target in enumerate(self.scripts[source], start=1):
                if not self._stop:
                    raised_segment = source == "C" and self.high_carry and index in (6, 7)
                    if self.trace:
                        self.trace("waypoint", number=index, target=target)
                    move_to(self.robot, target, self.seconds * (5 / 3) if raised_segment else self.seconds,
                            self.hz, tol=4 if raised_segment else 3, **options)
                    if source == "C" and self.high_carry and index == 6 and not self.dry_approach and not self._stop:
                        confirmed = self.confirm_lift(lambda: self._stop)
                        if self.trace:
                            self.trace("lift_observation", confirmed=confirmed)
                        # Failed observation leaves the arm holding. The operator decides recovery.
                        if not confirmed:
                            self._stop = True
                if self._stop:
                    self._fault()
                    return "stopped"
        except BaseException as exc:
            self._fault()
            if self.trace:
                self.trace("motion_error", error=f"{type(exc).__name__}: {exc}")
            return "unknown"  # mid-script the mandarin may still be in the gripper
        return "completed"

    def _fault(self) -> None:
        self._faulted = True
        try:  # hold the arm joints where they are; leave the grip alone so nothing drops
            obs = self.robot.get_observation()
            self.robot.send_action({k: float(v) for k, v in obs.items() if k.endswith(".pos") and k != GRIPPER})
        except Exception:
            pass

    async def stop(self) -> None:
        # the relay calls this on every session close too, so it only acts while a transfer is moving
        if self._moving():
            self._stop = True


_runner = None


def create_runner() -> PoseTransferRunner:
    # the relay calls this per phone session; one serial port means one shared runner
    global _runner
    if _runner is None:
        poses = load_poses(os.environ.get("OPENARMS_POSES", ROOT / "firmware/openarms_executor/poses.json"))
        fake = os.environ.get("OPENARMS_FAKE_ROBOT") == "1"
        _runner = PoseTransferRunner(connect(fake, os.environ.get("OPENARMS_FOLLOWER_PORT")), poses)
    return _runner
