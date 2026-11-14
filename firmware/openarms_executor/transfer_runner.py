"""Physical TransferRunner for Joseph's voice relay: moves the mandarin A -> B by replaying saved poses.

Run: PYTHONPATH=<repo root> OPENARMS_FOLLOWER_PORT=/dev/tty.usbmodem... python relay.py --dialogue agy \
       --runner firmware.openarms_executor.transfer_runner:create_runner   (OPENARMS_FAKE_ROBOT=1 for no hardware)
"""
import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from .motion import move_to
from .poses import GRIPPER, load_poses
from .robot import connect

ROOT = Path(__file__).resolve().parents[2]
HOME_TOL = 5.0  # shortcut: guessed units, set at the bench once we know degrees vs the -100..100 scale


@dataclass(frozen=True)
class ExecutionResult:  # same fields as relay/runner.py; the relay only reads the attributes
    plan_id: str
    mode: str
    status: str
    placement: str | None = None
    operator_authorized: bool = False


class PoseTransferRunner:
    mode = "physical"

    def __init__(self, robot, poses: dict, seconds: float = 1.5, hz: float = 30, ask=input) -> None:
        self.robot, self.poses, self.seconds, self.hz, self.ask = robot, poses, seconds, hz, ask
        self.script = self._script()  # a missing pose fails at startup, not mid-transfer
        self._authorized: set[str] = set()
        self._stop = False
        self._faulted = False  # arm position unknown after a fault or stop: no motion until a restart
        self._motion = None  # the motion thread's future; it can't be killed, so it is never forgotten
        self._prompt = None  # the open operator prompt; a stale one would swallow the next answer

    def _script(self) -> list[dict]:
        p, g = self.poses["poses"], self.poses["gripper"]
        names = ["ABOVE_A", "GRASP_A", "ABOVE_B", "GRASP_B", "HOME"]
        missing = [n for n in names if n not in p] + [n for n in ("open", "cup") if n not in g]
        if missing:
            raise SystemExit(f"pose file is missing {missing}: record them with teleop_record")
        o, c = {GRIPPER: g["open"]}, {GRIPPER: g["cup"]}
        return [o, p["ABOVE_A"], p["GRASP_A"], c, p["ABOVE_A"], p["ABOVE_B"], p["GRASP_B"], o, p["ABOVE_B"], p["HOME"]]

    async def authorize(self, plan: dict) -> bool:
        if self._faulted:
            print("Arm faulted or stopped in an earlier transfer: check the bench and restart the relay.")
            return False
        if self._moving():
            print(f"Refused plan {plan.get('plan_id')}: a transfer is still moving.")
            return False
        if self._prompt is not None and not self._prompt.done():
            print(f"Refused plan {plan.get('plan_id')}: an earlier prompt is still open; answer it n, then ask again.")
            return False
        q = (f"\nPlan {plan.get('plan_id')}: move the {plan.get('object')} {plan.get('source')} -> "
             f"{plan.get('destination')}. Mandarin at A, arm at HOME, bench clear? y/n> ")
        self._prompt = asyncio.ensure_future(asyncio.to_thread(self.ask, q))
        ok = (await self._prompt).strip().lower() in ("y", "yes")
        if ok:
            self._authorized.add(plan["plan_id"])
        return ok

    async def execute(self, plan: dict) -> ExecutionResult:
        pid = plan["plan_id"]
        def result(status: str) -> ExecutionResult:
            # placement=None: a finished script is not proof the mandarin landed at B
            return ExecutionResult(pid, self.mode, status, None, True)
        if pid not in self._authorized:
            raise ValueError(f"plan {pid} was not authorized by the bench operator")
        self._authorized.discard(pid)  # one authorization, one run
        if (plan.get("object"), plan.get("source"), plan.get("destination")) != ("mandarin", "A", "B"):
            return result("failed")
        if self._faulted or self._moving():
            return result("failed")
        self._stop = False
        task = self._motion = asyncio.ensure_future(asyncio.to_thread(self._run))
        try:
            return result(await asyncio.shield(task))
        except asyncio.CancelledError:
            # stop after the current move and wait it out, even through repeated cancels, so no motion runs untracked
            self._stop = True
            while not task.done():
                try:
                    await asyncio.wait({task})
                except asyncio.CancelledError:
                    pass
            raise

    def _moving(self) -> bool:
        return self._motion is not None and not self._motion.done()

    def _run(self) -> str:
        obs = self.robot.get_observation()
        off = {k: v for k, v in self.poses["poses"]["HOME"].items() if abs(float(obs[k]) - v) > HOME_TOL}
        if off:  # the first move is a fixed-time straight line, so starting elsewhere could sweep the bench
            print(f"Not at HOME (off: {sorted(off)}); move the arm to HOME first.")
            return "failed"
        try:
            for target in self.script:
                move_to(self.robot, target, self.seconds, self.hz)
                if self._stop:
                    self._fault()
                    return "stopped"
        except BaseException:
            self._fault()
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
