"""The real ArmPort: each arm step replays saved poses and gripper values through move_to."""
import copy
import time
from typing import Any

from agentic.openarms_agent.types import ArmError, ArmState
from agentic.openarms_agent.validator import apply_step, initial_point_holds

from .motion import move_to
from .poses import GRIPPER


class PoseArm:
    def __init__(self, robot, poses: dict, stations: dict, seconds: float = 1.5, hz: float = 30,
                 pour_hold: float = 2.0) -> None:
        self.robot, self.poses, self.stations = robot, poses, stations
        self.seconds, self.hz, self.pour_hold = seconds, hz, pour_hold
        self._stopped, self._slot = False, None
        self._state: ArmState = {
            "at": "HOME", "holding": None, "armed": True,
            "portions_left": {k: s.get("portions", 0) for k, s in stations.items() if s.get("kind") == "source"},
            "receiver_load": {k: 0 for k, s in stations.items() if s.get("kind") == "receiver"},
        }
        if points := initial_point_holds(stations):
            self._state["point_holds"] = points
            # go_to may name any position that was really recorded, and no other
            self._state["poses"] = sorted(poses["poses"])

    def run_step(self, action: str, args: dict[str, Any]) -> None:
        if self._stopped:
            raise ArmError(action, "the arm is stopped")
        nxt = copy.deepcopy(self._state)
        try:
            apply_step(nxt, self.stations, {"action": action, "args": args})
        except (ValueError, KeyError, TypeError) as e:
            raise ArmError(action, f"bad step: {e}") from None
        # Build the whole script first so a missing pose fails before any motion.
        script, slot = self._script(action, args)
        try:
            for target in script:
                # STOP lets the current move finish (never freezes mid-arc), then holds; waits are cut short
                if isinstance(target, (int, float)):
                    self._hold(target)
                else:
                    move_to(self.robot, target, self.seconds, self.hz)
                if self._stopped:
                    raise ArmError(action, "stopped after the current move; the arm is holding there")
        except BaseException as e:  # includes Ctrl-C, so an interrupted step still latches
            # mid-step the cup may or may not be gripped: lock and disarm until a person checks the bench
            self._stopped = True
            self._state.update(at="unknown", armed=False)
            self._hold_here()
            if isinstance(e, ArmError) or not isinstance(e, Exception):
                raise
            raise ArmError(action, f"{type(e).__name__}: {e}") from e
        self._state, self._slot = nxt, slot

    def stop(self) -> None:
        self._stopped = True
        self._state["armed"] = False  # so the validator refuses new plans instead of every run failing at step 1

    def _hold_here(self) -> None:
        # retarget arm joints to where they are, so freeing a snag can't make the arm jump; leave the gripper's grip alone
        try:
            obs = self.robot.get_observation()
            self.robot.send_action({k: float(v) for k, v in obs.items() if k.endswith(".pos") and k != GRIPPER})
        except Exception:
            pass  # the link may be what failed; the servos then keep their last goal

    def state(self) -> ArmState:
        return copy.deepcopy(self._state)

    def _script(self, action: str, args: dict[str, Any]) -> tuple[list, Any]:
        def pose(name: str) -> dict:
            if name not in self.poses["poses"]:
                raise ArmError(action, f"no saved pose {name}")
            return self.poses["poses"][name]

        def grip(name: str) -> dict:
            if name not in self.poses["gripper"]:
                raise ArmError(action, f"no saved gripper value '{name}'")
            return {GRIPPER: self.poses["gripper"][name]}

        def slotted(base: str, s: str, n) -> dict:
            have = [f"{b}_{s}{n}" in self.poses["poses"] for b in ("ABOVE", "GRASP")]
            if any(have) and not all(have):  # half a slot would descend diagonally across the next cup
                raise ArmError(action, f"slot {s}{n} needs both ABOVE_{s}{n} and GRASP_{s}{n}")
            return pose(f"{base}_{s}{n}" if all(have) else f"{base}_{s}")

        if action in ("pick", "place") and self.stations[args["station"]].get("kind") == "point":
            # a loose object on a marked point: no cup slots; "cup" is the gripper value closed on the object
            s = args["station"]
            above, grasp = pose(f"ABOVE_{s}"), pose(f"GRASP_{s}")
            if action == "pick":
                return [grip("open"), above, grasp, grip("cup"), above], None
            return [above, grasp, grip("open"), above], None
        if action == "pick":
            s = args["station"]
            n = self.stations[s].get("portions", 0) - self._state["portions_left"][s] + 1  # 1st, 2nd... cup taken
            return [grip("open"), slotted("ABOVE", s, n), slotted("GRASP", s, n), grip("cup"), slotted("ABOVE", s, n)], n
        if action == "pour":
            r = args["into"]
            return [pose(f"ABOVE_{r}"), pose(f"TIP_{r}"), self.pour_hold, pose(f"ABOVE_{r}")], self._slot
        if action == "return_cup":
            s, n = args["station"], self._slot
            return [slotted("ABOVE", s, n), slotted("GRASP", s, n), grip("open"), slotted("ABOVE", s, n)], None
        if action == "go_to":
            return [pose(args["pose"])], self._slot
        if action == "gripper":
            return [grip("open" if args["state"] == "open" else "cup")], self._slot
        if action == "home":
            return [pose("HOME")], self._slot
        if action == "wait":
            return [float(args.get("seconds", 0))], self._slot
        return [], self._slot  # look: the camera's job, no motion

    def _hold(self, seconds: float) -> bool:
        end = time.monotonic() + seconds
        while not self._stopped and time.monotonic() < end:
            time.sleep(min(0.05, max(0.0, end - time.monotonic())))
        return not self._stopped
