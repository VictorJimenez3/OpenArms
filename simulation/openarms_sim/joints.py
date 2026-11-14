"""Converts between the real arm's joint readings and the MuJoCo model's joints.

The real arm (LeRobot) reports the five arm joints in degrees and the gripper
as 0 (closed) to 100 (open). The model uses radians throughout. The per-joint
sign and offset come from config/joint_map.yaml.
"""

from __future__ import annotations

import math

from .config import ARM_JOINTS


class JointMap:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.measured = bool(cfg.get("measured", False))
        g = cfg["gripper"]
        self._closed = math.radians(g["closed_deg"])
        self._open = math.radians(g["open_deg"])
        self.gripper_open_value = float(g["open_value"])
        self.gripper_closed_value = float(g["closed_value"])
        # What to command the real gripper so it squeezes; the same as closed_value unless taught.
        self.gripper_closed_command = self.gripper_closed_value

    def use_taught_gripper(self, taught: dict | None) -> None:
        """Gripper values measured from a recording of the real arm holding the real object."""
        if taught:
            self.gripper_open_value = float(taught["open_value"])
            self.gripper_closed_value = float(taught["closed_value"])
            self.gripper_closed_command = float(taught["closed_command"])

    def gripper_command(self, shown: float) -> float:
        """Simulated gripper value -> what to send the real gripper. Open stays open; the
        closed end is pushed past where the jaw stops on the object, so it grips."""
        o, c = self.gripper_open_value, self.gripper_closed_value
        if o == c:
            return shown
        return o + (shown - o) * (o - self.gripper_closed_command) / (o - c)

    def to_model(self, joint: str, lerobot_deg: float) -> float:
        j = self.cfg["joints"][joint]
        return math.radians(j["sign"] * lerobot_deg + j["offset_deg"])

    def from_model(self, joint: str, model_rad: float) -> float:
        j = self.cfg["joints"][joint]
        return (math.degrees(model_rad) - j["offset_deg"]) / j["sign"]

    def pose_to_model(self, pose: dict[str, float]) -> list[float]:
        return [self.to_model(j, pose[j]) for j in ARM_JOINTS]

    def pose_from_model(self, q: list[float]) -> dict[str, float]:
        return {j: round(self.from_model(j, v), 2) for j, v in zip(ARM_JOINTS, q)}

    def gripper_to_model(self, value: float) -> float:
        """LeRobot 0..100 -> model jaw angle in radians."""
        return self._closed + (self._open - self._closed) * (value / 100.0)
