"""Loads the shared config files: bench layout, joint map, poses, chemistry.

A "setup" is one bench layout with its poses, in config/setups/<name>/.
`block` moves a block between marked points; `liquid` pours mini-cups into
receivers. The active setup is `block` unless OPENARMS_SETUP says otherwise
or a function is given `setup=` explicitly.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SIM_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = SIM_ROOT / "config"
ARM_XML = SIM_ROOT / "models" / "so101" / "so101_new_calib.xml"
OUTPUT_DIR = SIM_ROOT / "outputs"
DEFAULT_SETUP = "block"

ARM_JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]


def setup_name(setup: str | None = None) -> str:
    return setup or os.environ.get("OPENARMS_SETUP") or DEFAULT_SETUP


def setup_dir(setup: str | None = None) -> Path:
    path = CONFIG_DIR / "setups" / setup_name(setup)
    if not path.is_dir():
        known = sorted(p.name for p in (CONFIG_DIR / "setups").iterdir() if p.is_dir())
        raise ValueError(f"unknown setup {setup_name(setup)!r}; known: {known}")
    return path


@dataclass
class Station:
    name: str
    kind: str  # "point" (a mark an object can stand on), "source" (mini-cup) or "receiver"
    pos: tuple[float, float]
    contents: dict[str, float] = field(default_factory=dict)


@dataclass
class ObjectSpec:
    name: str
    size: tuple[float, float, float]  # width, depth, height
    at: str  # station it starts on
    color: tuple[float, float, float]


@dataclass
class Bench:
    table_size: tuple[float, float]
    table_center: tuple[float, float]
    stations: dict[str, Station]
    objects: dict[str, ObjectSpec]
    grasp_height: float
    lift: float
    cup_radius: float = 0.019
    cup_height: float = 0.070
    receiver_radius: float = 0.040
    receiver_height: float = 0.060
    receiver_capacity: int = 4
    tip_angle_deg: float = 115.0
    pour_clearance: float = 0.050
    release_tolerance: float = 0.012  # how far from a mark a released thing may be
    grasp_tolerance: float = 0.015  # how far the gripper may be from the grasp point and still pick up

    def _of_kind(self, kind: str) -> list[str]:
        return [n for n, s in self.stations.items() if s.kind == kind]

    @property
    def sources(self) -> list[str]:
        return self._of_kind("source")

    @property
    def receivers(self) -> list[str]:
        return self._of_kind("receiver")

    @property
    def points(self) -> list[str]:
        return self._of_kind("point")


def _read_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def ruler_to_arm(point_cm, frame: dict) -> tuple[float, float]:
    """A point read off the two bench rulers, in centimetres, as metres in the arm's frame.

    The rulers form an L. The ruler frame's origin is their inner corner, X runs along one
    ruler and Y along the other, with Y a quarter turn clockwise from X seen from above
    (X to the right and Y toward you, standing at the bottom of the L). `frame` says where
    the arm's base axis sits in that frame (`arm_cm`) and which way the arm points
    (`arm_heading_deg`: 0 along +X, 90 along +Y, -90 along -Y). Arm frame: +x forward, +y left."""
    import math

    try:  # hand-edited numbers: "4,6" or a missing space must fail clearly, not as arithmetic on text
        ax, ay = (float(v) for v in frame["arm_cm"])
        point_cm = [float(v) for v in point_cm]
        h = math.radians(float(frame["arm_heading_deg"]))
    except (TypeError, ValueError) as e:
        raise ValueError(f"ruler positions must be two numbers in centimetres, like [4.6, 4.2]: {e}") from None
    if len(point_cm) != 2:
        raise ValueError("a ruler position is two numbers in centimetres, like [4.6, 4.2]")
    fx, fy = math.cos(h), math.sin(h)
    dx, dy = (point_cm[0] - ax) / 100.0, (point_cm[1] - ay) / 100.0
    # Seen from above with Y toward the viewer, the arm's left is its forward turned counter-clockwise.
    return round(dx * fx + dy * fy, 4), round(dx * fy - dy * fx, 4)


def _station_pos(name: str, spec: dict, frame: dict | None) -> tuple[float, float]:
    if "ruler" in spec:
        if not frame:
            raise ValueError(f"station {name} is given in ruler centimetres, but bench.yaml has no ruler_frame")
        return ruler_to_arm(spec["ruler"], frame)
    return tuple(spec["pos"])


def load_bench(setup: str | None = None) -> Bench:
    raw = _read_yaml(setup_dir(setup) / "bench.yaml")
    grasp = raw["grasp"]
    frame = raw.get("ruler_frame")
    stations = {
        name: Station(name, s["kind"], _station_pos(name, s, frame), dict(s.get("contents") or {}))
        for name, s in raw["stations"].items()
    }
    objects = {
        name: ObjectSpec(name, tuple(o["size"]), o["at"], tuple(o.get("color", [0.9, 0.3, 0.15])))
        for name, o in (raw.get("objects") or {}).items()
    }
    extra = {}
    containers = raw.get("containers") or {}
    if "mini_cup" in containers:
        extra.update(cup_radius=containers["mini_cup"]["radius"], cup_height=containers["mini_cup"]["height"])
    if "receiver" in containers:
        rec = containers["receiver"]
        extra.update(
            receiver_radius=rec["radius"], receiver_height=rec["height"], receiver_capacity=rec["capacity_portions"]
        )
    for key in ("tip_angle_deg", "pour_clearance", "release_tolerance", "grasp_tolerance"):
        if key in grasp:
            extra[key] = grasp[key]
    return Bench(
        table_size=tuple(raw["table"]["size"]),
        table_center=tuple(raw["table"]["center"]),
        stations=stations,
        objects=objects,
        grasp_height=grasp["height"],
        lift=grasp["lift"],
        **extra,
    )


def load_joint_map() -> dict:
    return _read_yaml(CONFIG_DIR / "joint_map.yaml")


def load_chemistry_config() -> dict:
    return _read_yaml(CONFIG_DIR / "chemistry.yaml")


def poses_path(setup: str | None = None) -> Path:
    return setup_dir(setup) / "poses.json"


def load_poses(setup: str | None = None) -> dict[str, dict[str, float]]:
    """Named poses in LeRobot units (degrees per arm joint)."""
    with open(poses_path(setup)) as f:
        return json.load(f)["poses"]


def load_pose_file(setup: str | None = None) -> dict:
    """The whole poses.json: `source`, `poses`, and for a taught setup `gripper` and `taught`."""
    with open(poses_path(setup)) as f:
        return json.load(f)


def poses_are_placeholder(setup: str | None = None) -> bool:
    """True if the poses were invented by the simulation, not taken from the real arm."""
    return load_pose_file(setup).get("source", "placeholder") == "placeholder"
