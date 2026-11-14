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
    name = setup_name(setup)
    root = CONFIG_DIR / "setups"
    aliases = {"two_vessel": root / "liquid", "liquid_legacy": root / "liquid" / "legacy"}
    path = aliases.get(name, root / name)
    if not path.is_dir():
        known = sorted({p.name for p in root.iterdir() if p.is_dir()} | aliases.keys())
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


@dataclass(frozen=True)
class Docks:
    base_height: float
    nest_height: float
    radial_clearance: float
    backing_thickness: float
    backing_height: float


@dataclass(frozen=True)
class OverviewCamera:
    lookat: tuple[float, float, float]
    distance: float
    azimuth: float
    elevation: float
    shift_azimuth_deg: float
    registration_tolerance_px: float
    fiducials: dict[str, tuple[float, float]]


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
    spout_extension: float = 0.0
    receiver_radius: float = 0.040
    receiver_height: float = 0.060
    receiver_capacity: int = 4
    tip_angle_deg: float = 115.0
    pour_clearance: float = 0.050
    release_tolerance: float = 0.012  # how far from a mark a released thing may be
    grasp_tolerance: float = 0.015  # how far the gripper may be from the grasp point and still pick up
    docks: Docks | None = None
    camera: OverviewCamera | None = None

    @property
    def dock_height(self) -> float:
        return self.docks.base_height if self.docks else 0.0

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


def load_bench(setup: str | None = None) -> Bench:
    raw = _read_yaml(setup_dir(setup) / "bench.yaml")
    grasp = raw["grasp"]
    stations = {
        name: Station(name, s["kind"], tuple(s["pos"]), dict(s.get("contents") or {}))
        for name, s in raw["stations"].items()
    }
    objects = {
        name: ObjectSpec(name, tuple(o["size"]), o["at"], tuple(o.get("color", [0.9, 0.3, 0.15])))
        for name, o in (raw.get("objects") or {}).items()
    }
    extra = {}
    containers = raw.get("containers") or {}
    if "mini_cup" in containers:
        donor = containers["mini_cup"]
        extra.update(cup_radius=donor["radius"], cup_height=donor["height"],
                     spout_extension=donor.get("spout_extension", 0.0))
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
        docks=Docks(**raw["docks"]) if "docks" in raw else None,
        camera=OverviewCamera(**raw["camera"]) if "camera" in raw else None,
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
