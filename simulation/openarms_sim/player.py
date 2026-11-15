"""Plays arm motion on the simulated bench and reports what would go wrong.

The arm is moved kinematically: each frame the joints are set to the commanded
angles. That shows where the arm was told to go. It does not model sag under
load, a slipping grasp, or real liquid.

Things on the bench are addressed by a key: a container by its station name
("A"), a loose object by its own name ("block").
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import mujoco
import numpy as np

from .chemistry import ChemistryModel, display_name, safety_issues
from .config import ARM_JOINTS
from .joints import JointMap
from .motion import Segment, blend
from .scene import STREAM_RADIUS, Scene

UP = np.array([0.0, 0.0, 1.0])
PENETRATION = 0.003  # overlaps shallower than this are ignored as modelling noise
POUR_ANGLE = math.radians(90)  # liquid leaves the cup once it is tipped past this
POUR_SECONDS = 1.0
TRUST_RADIUS = math.radians(30)  # how close to a taught pose its contacts are trusted

LINK_NAMES = {
    "base": "base",
    "shoulder": "shoulder",
    "upper_arm": "upper arm",
    "lower_arm": "forearm",
    "wrist": "wrist",
    "gripper": "gripper",
    "moving_jaw_so101_v1": "gripper jaw",
}


@dataclass
class Issue:
    severity: str  # "block": do not run this on the real arm. "note": worth knowing.
    code: str
    message: str
    step: str | None = None


@dataclass
class _Pour:
    """An in-progress pour animation."""

    source: str
    into: str | None
    t0: float
    color: np.ndarray
    old_color: np.ndarray | None
    old_level: float


class Player:
    def __init__(
        self,
        scene: Scene,
        jm: JointMap,
        chem_cfg: dict,
        chem: ChemistryModel,
        contents: dict | None = None,
        objects: dict | None = None,
        strict_limits: bool = True,
        trusted_poses: list[np.ndarray] | None = None,
        allow_simulation_only: bool = False,
    ):
        self.scene, self.jm, self.chem_cfg, self.chem = scene, jm, chem_cfg, chem
        # A simulation-only experiment may mix substances that are not on the real_bench list; that is
        # reported as a note, never cleared. Listed hazard combinations still block.
        self.allow_simulation_only = allow_simulation_only
        # Share of the tipped cup's contents one pour moves (1 = all of it; 0.5 leaves half behind).
        self.pour_fraction = 1.0
        # Planned poses must stay inside the model's joint range. A recording of the
        # real arm may go past it, because the real joints turn a little further.
        self.strict_limits = strict_limits
        # Poses the real arm has actually been in (model radians). Whatever the simulation
        # shows touching in one of them is touching in reality too, or is a modelling error,
        # so those same contacts are not reported while the arm is near that pose.
        self._trusted: list[tuple[np.ndarray, set]] = []
        self._trusted_poses = trusted_poses or []
        b = scene.bench
        containers = b.sources + b.receivers
        self.contents: dict[str, dict[str, float]] = {
            n: dict((contents or {}).get(n, b.stations[n].contents)) for n in containers
        }
        self.initial = {n: sum(c.values()) for n, c in self.contents.items()}

        # Where each thing that can be picked up is resting. Cups rest on their own station.
        self.location: dict[str, str | None] = {s: s for s in b.sources}
        for name, obj in b.objects.items():
            at = (objects or {}).get(name, obj.at)
            if at not in b.points:
                raise ValueError(f"the {name} cannot start at {at!r}; points are {b.points}")
            if at in [self.location[o] for o in b.objects if o in self.location]:
                raise ValueError(f"two objects cannot both start at {at}")
            self.location[name] = at
        for name in objects or {}:
            if name not in b.objects:
                raise ValueError(f"there is no object called {name!r} on this bench")
        self.start_location = dict(self.location)

        self.pos = {k: scene.rest_position(k, self.location.get(k)) for k in scene.kind}
        self.rot = {k: np.eye(3) for k in scene.kind}
        self.holding: str | None = None
        self._rel: tuple[np.ndarray, np.ndarray] | None = None
        self._touch_ok: str | None = None  # the thing the gripper is meant to be touching
        self.issues: list[Issue] = []
        self._seen: set[tuple[str, str]] = set()
        self.poured: list[dict] = []
        self._pour: _Pour | None = None
        self._poured_this_step = False
        self._aligned_pour_seconds = 0.0
        self.step = ""
        self.label = ""
        self.t = 0.0
        self.caption = ""  # latest outcome, for the video overlay
        self._refresh_liquids()
        self._write_mocap()
        mujoco.mj_forward(scene.model, scene.data)
        for q in self._trusted_poses:
            self._trusted.append((np.asarray(q, dtype=float), self._contact_pairs(q)))

    def _contact_pairs(self, q) -> set:
        """Which parts overlap in the simulation with the arm at pose `q`."""
        sc, m, d = self.scene, self.scene.model, self.scene.data
        for adr, v in zip(sc.arm_qadr, q):
            d.qpos[adr] = v
        mujoco.mj_forward(m, d)
        pairs = set()
        for i in range(d.ncon):
            c = d.contact[i]
            if c.dist <= 0:
                b1, b2 = int(m.geom_bodyid[c.geom1]), int(m.geom_bodyid[c.geom2])
                pairs.add((min(b1, b2), max(b1, b2)))
        return pairs

    def _is_trusted(self, b1: int, b2: int) -> bool:
        pair = (min(b1, b2), max(b1, b2))
        q = np.array([self.scene.data.qpos[a] for a in self.scene.arm_qadr])
        return any(pair in pairs and np.max(np.abs(q - tq)) < TRUST_RADIUS for tq, pairs in self._trusted)

    # ---- reporting ---------------------------------------------------------

    def _add(self, severity: str, code: str, message: str) -> None:
        if (code, message) not in self._seen:
            self._seen.add((code, message))
            self.issues.append(Issue(severity, code, message, self.step or None))

    def _name(self, key: str) -> str:
        kind = self.scene.kind[key]
        return {"cup": f"cup from {key}", "receiver": f"container at {key}"}.get(kind, key)

    # ---- geometry ----------------------------------------------------------

    def _site(self) -> tuple[np.ndarray, np.ndarray]:
        d = self.scene.data
        return d.site_xpos[self.scene.grasp_site].copy(), d.site_xmat[self.scene.grasp_site].reshape(3, 3).copy()

    def _grasp_point(self, key: str) -> np.ndarray:
        _, h = self.scene.size(key)
        return self.pos[key] + self.rot[key][:, 2] * (self.scene.bench.grasp_height - h / 2)

    def _tilt_deg(self, key: str) -> float:
        return math.degrees(math.acos(max(-1.0, min(1.0, self.rot[key][2, 2]))))

    def _lip(self, key: str) -> np.ndarray:
        """Lowest point of the cup's rim: where liquid leaves a tipped cup."""
        r, h = self.scene.size(key)
        axis = self.rot[key][:, 2]
        down = -(UP - (UP @ axis) * axis)
        n = np.linalg.norm(down)
        rim = self.pos[key] + axis * h / 2
        if self.scene.bench.spout_extension:
            return rim + self.rot[key][:, 1] * (r + self.scene.bench.spout_extension)
        return rim + (down / n * r if n > 1e-6 else 0)

    def _write_mocap(self) -> None:
        d = self.scene.data
        quat = np.zeros(4)
        for k, idx in self.scene.mocap.items():
            d.mocap_pos[idx] = self.pos[k]
            mujoco.mju_mat2Quat(quat, self.rot[k].flatten())
            d.mocap_quat[idx] = quat

    # ---- liquids -----------------------------------------------------------

    def _level(self, key: str) -> float:
        unit = 0.6 if self.scene.kind[key] == "cup" else 0.22
        return min(0.95, sum(self.contents[key].values()) * unit)

    def _color(self, key: str) -> np.ndarray:
        return np.array(self.chem.predict(self.contents[key]).color)

    def _set_liquid(self, key: str, level: float, color) -> None:
        m = self.scene.model
        r, h = self.scene.size(key)
        g = self.scene.liquid_geom[key]
        half = max(1e-4, level * h * 0.9 / 2)
        m.geom_size[g] = [r * 0.88, half, 0]
        m.geom_pos[g] = [0, 0, -h / 2 + 0.003 + half]
        m.geom_rgba[g] = [*color, 1.0 if level > 0.01 else 0.0]

    def _refresh_liquids(self) -> None:
        for k in self.contents:
            self._set_liquid(k, self._level(k), self._color(k))
        self.scene.model.geom_rgba[self.scene.stream_geom][3] = 0.0

    def _animate_pour(self) -> None:
        p = self._pour
        if p is None:
            return
        u = (self.t - p.t0) / POUR_SECONDS
        m, d = self.scene.model, self.scene.data
        if u >= 1.0:
            self._pour = None
            self._refresh_liquids()
            return
        self._set_liquid(p.source, (1 - u) * 0.6, p.color)
        lip = self._lip(p.source)
        bottom = 0.0
        if p.into is not None:
            self._set_liquid(
                p.into,
                p.old_level + (self._level(p.into) - p.old_level) * u,
                p.old_color + (self._color(p.into) - p.old_color) * blend(u),
            )
            bottom = 0.01
        g = self.scene.stream_geom
        half = max(0.002, (lip[2] - bottom) / 2)
        m.geom_size[g] = [STREAM_RADIUS, half, 0]
        m.geom_rgba[g] = [*p.color, 0.9]
        d.mocap_pos[m.body_mocapid[m.geom_bodyid[g]]] = [lip[0], lip[1], bottom + half]

    # ---- events ------------------------------------------------------------

    def _close(self) -> None:
        if self.holding:
            return
        p, R = self._site()
        near = [(float(np.linalg.norm(self._grasp_point(k) - p)), k) for k in self.location]
        dist, key = min(near) if near else (math.inf, None)
        if dist > self.scene.bench.grasp_tolerance:
            what = f"{dist * 100:.1f} cm away from the {self._name(key)}" if key else "with nothing on the bench"
            self._add("block", "missed_grasp", f"The gripper closed {what}, so it would not pick anything up.")
            return
        self.holding, self._touch_ok = key, key
        self._rel = (R.T @ (self.pos[key] - p), R.T @ self.rot[key])
        if self.scene.kind[key] == "object" or self.scene.bench.docks:
            self.location[key] = None

    def _open(self) -> None:
        key = self.holding
        if key is None:
            return
        self.holding, self._rel = None, None
        b = self.scene.bench
        tilt = self._tilt_deg(key)
        if self.scene.kind[key] == "cup":
            station = key
        else:
            station = min(b.points, key=lambda s: np.linalg.norm(self.pos[key][:2] - np.array(b.stations[s].pos)))
        rest = self.scene.rest_position(key, station)
        off = float(np.linalg.norm(self.pos[key] - rest))
        if off > b.release_tolerance or tilt > 8:
            self._add(
                "block",
                "bad_release",
                f"The {self._name(key)} was let go {off * 100:.1f} cm from the mark at {station}, "
                f"tilted {tilt:.0f} degrees.",
            )
            return
        if self.scene.kind[key] == "object":
            if station in [loc for k, loc in self.location.items() if k != key]:
                self._add("block", "occupied", f"There is already something at {station}.")
                return
            self.location[key] = station
            self.caption = f"The {key} is now at {station}"
        elif b.docks:
            self.location[key] = station
        self.pos[key], self.rot[key] = rest, np.eye(3)

    def _check_pour(self, dt: float) -> None:
        s = self.holding
        if s is None or self._poured_this_step or not self.step.startswith("pour") or self.scene.kind[s] != "cup":
            return
        if math.radians(self._tilt_deg(s)) < POUR_ANGLE:
            return
        liquid = {k: v * self.pour_fraction for k, v in self.contents[s].items() if v > 0}
        if not liquid:
            self._add("note", "empty_cup", f"The cup from {s} is already empty, so this pour adds nothing.")
            self._poured_this_step = True
            return
        b = self.scene.bench
        lip = self._lip(s)
        target = None
        for r in b.receivers:
            centre = self.scene.rest_position(r)
            if (np.linalg.norm(lip[:2] - centre[:2]) < b.receiver_radius - STREAM_RADIUS
                    and lip[2] > b.receiver_height + b.dock_height):
                target = r
        if b.docks:
            if target is None:
                self._add("block", "spill", f"The spout from {s} misses the receiver opening while tipped.")
                self._poured_this_step = True
                return
            if self.label != "hold while pouring" or any(i.severity == "block" for i in self.issues):
                return
            self._aligned_pour_seconds += dt
            if self._aligned_pour_seconds + 1e-8 < 0.25:
                return
            mixture = dict(self.contents[target])
            for key, amount in liquid.items():
                mixture[key] = mixture.get(key, 0) + amount
            reasons = self._unsafe_reasons(mixture)
            for reason in reasons:
                self._add("block", "unsafe_mix", reason)
            if sum(mixture.values()) > b.receiver_capacity:
                self._add("block", "overflow", f"The proposed transfer exceeds receiver {target}'s modeled capacity.")
            if reasons or sum(mixture.values()) > b.receiver_capacity:
                self._poured_this_step = True
                return
        self._poured_this_step = True
        color = self._color(s)
        kept = 1.0 - self.pour_fraction
        self.contents[s] = {k: v * kept for k, v in self.contents[s].items() if v * kept > 1e-9}
        if target is None:
            self._add("block", "spill", f"The cup from {s} would pour onto the table, not into a receiver.")
            self._pour = _Pour(s, None, self.t, color, None, 0.0)
            return
        old_color, old_level = self._color(target), self._level(target)
        for k, v in liquid.items():
            self.contents[target][k] = self.contents[target].get(k, 0) + v
        self._pour = _Pour(s, target, self.t, color, old_color, old_level)
        outcome = self.chem.predict(self.contents[target])
        names = " and ".join(display_name(self.chem_cfg, k) for k in liquid)
        self.caption = f"MODELED: receiver {target} appears {outcome.describe()}"
        self.poured.append({"source": s, "into": target, "added": liquid, "predicted": outcome.describe()})
        if sum(self.contents[target].values()) > b.receiver_capacity:
            self._add(
                "block", "overflow", f"Receiver {target} would overflow: it holds {b.receiver_capacity} portions in total."
            )
        if not b.docks:
            for reason in self._unsafe_reasons(self.contents[target]):
                self._add("block", "unsafe_mix", f"Adding {names} to {target}: {reason}.")

    def _unsafe_reasons(self, mixture: dict) -> list[str]:
        """Blocking safety reasons; a simulation-only experiment turns not-on-real_bench into a note."""
        reasons = safety_issues(self.chem_cfg, mixture)
        if self.allow_simulation_only:
            for reason in [r for r in reasons if r.endswith("is simulation-only and not allowed on the real bench")]:
                self._add("note", "simulation_only", reason + " (simulation-only experiment)")
                reasons.remove(reason)
        return reasons

    # ---- collisions --------------------------------------------------------

    def _check_collisions(self) -> None:
        sc, m, d = self.scene, self.scene.model, self.scene.data
        body_key = {bid: k for k, bid in sc.body.items()}
        for i in range(d.ncon):
            c = d.contact[i]
            if c.dist > -PENETRATION:
                continue
            b1, b2 = int(m.geom_bodyid[c.geom1]), int(m.geom_bodyid[c.geom2])
            if self._trusted and self._is_trusted(b1, b2):
                continue
            for arm, other, og in ((b1, b2, c.geom2), (b2, b1, c.geom1)):
                if arm not in sc.arm_bodies:
                    continue
                link = LINK_NAMES[m.body(arm).name]
                if og == sc.table_geom:
                    self._add("block", "hits_table", f"The {link} would hit the table.")
                elif og in sc.fixture_geom:
                    self._add("block", "hits_dock", f"The {link} would hit dock {sc.fixture_geom[og]}.")
                elif other in body_key:
                    key = body_key[other]
                    if key == self.holding or (key == self._touch_ok and arm in sc.gripper_bodies):
                        continue
                    self._add("block", "hits_object", f"The {link} would knock the {self._name(key)}.")
                elif other in sc.arm_bodies and arm < other:
                    self._add(
                        "block", "self_collision", f"The {link} would collide with the {LINK_NAMES[m.body(other).name]}."
                    )
        if self.holding:
            held = sc.geom[self.holding]
            fromto = np.zeros(6)
            if mujoco.mj_geomDistance(m, d, held, sc.table_geom, 0.05, fromto) < -PENETRATION:
                self._add("block", "held_hits_table", f"The {self._name(self.holding)} would be pushed into the table.")
            for g, station in sc.fixture_geom.items():
                if mujoco.mj_geomDistance(m, d, held, g, 0.05, fromto) < -PENETRATION:
                    self._add("block", "held_hits_dock", f"The {self._name(self.holding)} would hit dock {station}.")
            for k, g in sc.geom.items():
                if k != self.holding and mujoco.mj_geomDistance(m, d, held, g, 0.05, fromto) < -PENETRATION:
                    self._add(
                        "block",
                        "held_hits_object",
                        f"The {self._name(self.holding)} would hit the {self._name(k)}.",
                    )

    # ---- main loop ---------------------------------------------------------

    def _apply(self, q: np.ndarray, grip: float) -> None:
        sc, m, d = self.scene, self.scene.model, self.scene.data
        for name, adr, v in zip(ARM_JOINTS, sc.arm_qadr, q):
            lo, hi = m.jnt_range[m.joint(name).id]
            if v < lo - 1e-3 or v > hi + 1e-3:
                if self.strict_limits:
                    self._add(
                        "block",
                        "joint_limit",
                        f"The pose asks {name} for {math.degrees(v):.0f} degrees, outside the model's range "
                        f"({math.degrees(lo):.0f} to {math.degrees(hi):.0f}).",
                    )
                else:
                    self._add(
                        "note",
                        "beyond_model_range",
                        f"The real {name} joint turns past the model's range "
                        f"({math.degrees(lo):.0f} to {math.degrees(hi):.0f} degrees).",
                    )
            d.qpos[adr] = min(hi, max(lo, v)) if self.strict_limits else v
        d.qpos[sc.gripper_qadr] = self.jm.gripper_to_model(grip)
        mujoco.mj_kinematics(m, d)
        if self.holding:
            p, R = self._site()
            self.pos[self.holding] = p + R @ self._rel[0]
            self.rot[self.holding] = R @ self._rel[1]
        self._write_mocap()
        mujoco.mj_forward(m, d)

    def run(self, segments: list[Segment], fps: int = 30, on_frame: Callable[["Player"], None] | None = None):
        """Plays the moves in order. Calls `on_frame(self)` after every frame."""
        last_index = None
        for seg in segments:
            if seg.step_index != last_index:
                last_index, self._poured_this_step = seg.step_index, False
                self._aligned_pour_seconds = 0.0
                if seg.step.startswith("pick("):
                    station = seg.step[5:-1]
                    self._touch_ok = next((k for k, loc in self.location.items() if loc == station), None)
            self.step, self.label = seg.step, seg.label
            n = max(1, round(seg.duration * fps))
            for k in range(1, n + 1):
                u = blend(k / n)
                self._apply(seg.q0 + (seg.q1 - seg.q0) * u, seg.grip0 + (seg.grip1 - seg.grip0) * u)
                self.t += 1.0 / fps
                self._check_collisions()
                self._check_pour(1.0 / fps)
                self._animate_pour()
                if on_frame:
                    on_frame(self)
            if seg.step.startswith("pour") and seg.label == "hold while pouring":
                if self.holding and not self._poured_this_step:
                    self._add("block", "no_pour", "The motion did not complete an aligned, uninterrupted tipped hold.")
                elif not self.holding:
                    self._add("block", "nothing_held", "The arm goes through a pour with no cup in the gripper.")
            if seg.event == "close":
                self._close()
            elif seg.event == "open":
                if self.holding is None and seg.step.startswith(("place", "return")):
                    self._add("block", "nothing_held", f"The arm goes through {seg.step} with nothing in the gripper.")
                self._open()
        self._pour = None
        self._refresh_liquids()
        self.step = ""
        if self.holding:
            self._add("block", "still_holding", f"The plan ends with the {self._name(self.holding)} still in the gripper.")
        return self.issues
