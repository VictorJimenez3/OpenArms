"""Scripted robot motion with an illustrative two-phase lava-lamp effect."""
from dataclasses import dataclass
import math

import numpy as np
from scipy.optimize import brentq

from .smartivity_world import (
    BEAKER, FLASK, GOLDEN_ANGLE, UP, World, _VisualEffects, _geom, _mesh_geom, _vessel_radius,
)

WATER = (.79, .014, .075, .93)
OIL = (.98, .58, .10, .29)
GRAINS = 38
DROPLETS = 21


@dataclass(frozen=True, slots=True)
class LavaEffects(_VisualEffects):
    acid_remaining: float
    releases: tuple


class LavaWorld(World):
    _scenarios = ("lava_lamp",)

    def __init__(self, *, layout=None):
        self.releases = []
        self.spilled_acid = 0.
        self.deposited_acid = 0.
        super().__init__(scenario="lava_lamp", layout=layout)

    def _update_transfer(self):
        donor = self.contents[BEAKER]
        remaining = donor["modelled_acid_fraction"]
        if self._held is None or remaining <= 1e-8:
            return
        rotation = self._beaker_rotation()
        tilt = math.degrees(math.acos(np.clip(rotation[2, 2], -1., 1.)))
        if tilt < 104 or rotation[2, 1] > -.3:
            return
        lip = self.data.mocap_pos[self._beaker] + rotation @ np.array(
            [0., self.beaker_profile["outer_profile"][-1][1] / 1000, self.beaker_height]
        )
        mouth = self.receiver + UP * self.flask_height
        captured = lip[2] > mouth[2] and np.linalg.norm((lip - mouth)[:2]) < _vessel_radius(self.flask_profile) - .001
        released = min(self.timestep * .56, remaining)
        donor["modelled_acid_fraction"] -= released
        if captured:
            prior = self.deposited_acid
            self.deposited_acid += released
            if not self.releases or int(self.deposited_acid * 36) != int(prior * 36):
                self.releases.append((self.sim_time, tuple(float(x) for x in lip)))
        else:
            self.spilled_acid += released

    def evaluate(self):
        result = {
            "acid_fraction_deposited": self.deposited_acid,
            "acid_fraction_spilled": self.spilled_acid,
            "acid_fraction_remaining": self.contents[BEAKER]["modelled_acid_fraction"],
            "release_events": len(self.releases),
            "collisions": self.collisions,
            "drops": self.drops,
            "beaker_docked": bool(self._placed),
        }
        success = (self.deposited_acid >= .98 and self.spilled_acid <= 1e-7
                   and self._placed and not self.collisions and not self.drops and not self._fault)
        return {**result, "success": bool(success)}

    def _visual_effects(self):
        water = self.contents[FLASK]["water_ml"]
        return LavaEffects((0., water), ((.96, .90, .76, 1.), WATER), 0., 0., None,
                           self.contents[BEAKER]["modelled_acid_fraction"], tuple(self.releases))

    def _fill_height(self, volume_ml):
        heights, radii = np.asarray(self.flask_profile["inner_profile"]).T / 1000
        left = volume_ml * 1e-6
        for z0, z1, r0, r1 in zip(heights[:-1], heights[1:], radii[:-1], radii[1:]):
            def truncated_volume(fraction):
                r = r0 + (r1 - r0) * fraction
                return math.pi * (z1 - z0) * fraction * (r0*r0 + r0*r + r*r) / 3
            available = truncated_volume(1.)
            if left <= available:
                return z0 + brentq(lambda f: truncated_volume(f) - left, 0, 1) * (z1 - z0)
            left -= available
        raise ValueError("Flask cannot contain the specified volume.")

    def _liquid_layer(self, spec, name, bottom, top, rgba):
        profile = np.asarray(self.flask_profile["inner_profile"]) / 1000
        heights = [bottom, *(z for z in profile[:, 0] if bottom < z < top), top]
        angles = np.arange(64) * (math.tau / 64)
        vertices = []
        for height in heights:
            radius = np.interp(height, profile[:, 0], profile[:, 1]) - .0005
            vertices.extend((radius * math.cos(angle), radius * math.sin(angle), height) for angle in angles)
        vertices.extend([(0, 0, bottom), (0, 0, top)])
        faces = []
        for j in range(len(heights) - 1):
            for i in range(64):
                a, b = j*64 + i, j*64 + (i+1) % 64
                faces.extend([(a, b, b+64), (a, b+64, a+64)])
        offset = (len(heights)-1)*64
        for i in range(64):
            other = (i+1) % 64
            faces.extend([(len(vertices)-2, other, i), (len(vertices)-1, offset+i, offset+other)])
        _mesh_geom(spec, spec.body(FLASK), name, vertices, rgba, faces=faces)

    def _dress_presentation(self, spec):
        super()._dress_presentation(spec)
        water = self.contents[FLASK]["water_ml"]
        self.water_level = self._fill_height(water)
        self.oil_level = self._fill_height(water + self.contents[FLASK]["oil_ml"])
        self._liquid_layer(spec, "water_layer", .0022, self.water_level, WATER)
        self._liquid_layer(spec, "oil_layer", self.water_level + .00025, self.oil_level, OIL)
        spec.geom("flask_surface").rgba = [.74, .88, .98, .19]
        spec.geom("table").rgba = [.044, .066, .091, 1.]
        world = spec.worldbody
        glow = spec.add_material(name="lamp_glow", rgba=[.96, .26, .085, .55], emission=.76)
        _geom(world, "lamp_reflection", "CYLINDER", [.034, .00025, 0],
              self.receiver + [0., 0., -.0034], [1., 1., 1., .42], material=glow.name,
              contype=0, conaffinity=0)
        world.add_light(pos=self.receiver + [-.011, 0., .012], dir=[0, 0, 1],
                        diffuse=[.66, .31, .13], specular=[.45, .18, .075], castshadow=False)
        material = spec.add_material(name="red_droplet", rgba=[.91, .037, .108, 1.],
                                     emission=.27, specular=.68, shininess=.6)
        for index in range(DROPLETS):
            _geom(world, f"lava_drop_{index}", "ELLIPSOID", [.003, .003, .004], [0, 0, -.2],
                  [.91, .037, .108, 0.], material=material.name, contype=0, conaffinity=0)
            _geom(world, f"lava_bubble_{index}", "SPHERE", [.0013, 0, 0], [0, 0, -.2],
                  [1., .86, .58, 0.], contype=0, conaffinity=0)
        for index in range(GRAINS):
            _geom(world, f"acid_grain_{index}", "SPHERE", [.00065, 0, 0], [0, 0, -.2],
                  [1., .92, .76, 0.], contype=0, conaffinity=0)

    def _render_liquid(self, model, sim_time, effects):
        super()._render_liquid(model, sim_time, effects)
        # The oil and water have separately rendered profiles. The solid dose travels from the held beaker.
        model.geom("flask_liquid").rgba[3] = 0.
        powder = model.geom("beaker_liquid")
        powder.rgba[:] = [1., .94, .8, .98 if effects.acid_remaining > .025 else 0.]
        powder.size[:2] = [.013 * math.sqrt(max(0., effects.acid_remaining)), .0015]
        powder.pos[2] = .004

    def _presentation_foam(self, model, groups, state):
        releases = state.effects.releases
        time = state.sim_time
        profile = np.asarray(self.flask_profile["inner_profile"]) / 1000
        water, oil = self.water_level, self.oil_level
        for index in range(GRAINS):
            grain = model.geom(f"acid_grain_{index}")
            grain.rgba[3] = 0.
            if index >= len(releases):
                continue
            spawn, lip = releases[index]
            age = time - spawn
            if not 0 <= age < 1.35:
                continue
            # Accelerate in air, then drift down through the oil.
            lip = np.array(lip)
            into_oil = self.receiver + [.002, -.001, oil]
            if age < .20:
                progress = (age / .20) ** 1.65
                grain.pos[:] = lip * (1 - progress) + into_oil * progress
            else:
                fraction = min(1., (age - .20) / 1.15)
                drift = .0028 * math.sin(index * GOLDEN_ANGLE + age * 3) * math.sin(math.pi * fraction)
                grain.pos[:] = self.receiver + [.002 + drift, -.001, oil + (water - oil) * fraction]
            grain.rgba[3] = 1. if age < .20 else .76 * (1. - .45 * age)

        for index in range(DROPLETS):
            drop = model.geom(f"lava_drop_{index}")
            bubble = model.geom(f"lava_bubble_{index}")
            drop.rgba[3] = bubble.rgba[3] = 0.
            release = index // 2
            if release >= len(releases):
                continue
            start = releases[release][0] + 1.28 + .13 * index + .19 * (index % 2)
            cycle = 2.55 + .15 * (index % 6)
            elapsed = time - start
            repeat = index % 3 == 0
            if elapsed < 0 or elapsed >= cycle * (2 if repeat else 1):
                continue
            progress = (elapsed % cycle) / cycle
            size = .0023 + .00038 * (index % 6)
            # The gas lifts water to the oil surface. Water descends after the gas separates.
            up = progress < .53
            fraction = progress / .53 if up else (1 - progress) / .47
            fraction = max(0., min(1., fraction))
            z = water + size + (oil - water - 2.55*size) * (fraction ** .84)
            wall = np.interp(z, profile[:, 0], profile[:, 1])
            angle = GOLDEN_ANGLE * index + (.7 if up else 1.2) * progress
            spread = (wall - size - .001) * (.23 + .09 * (index % 6))
            drop.pos[:] = self.receiver + [spread * math.cos(angle), spread * math.sin(angle), z]
            stretch = 1.2 + .33 * math.sin(progress * math.pi * 3 + index)
            drop.size[:] = [size, size * .86, size * stretch]
            drop.rgba[:] = [.91, .037, .108, min(1., progress * 26, (1 - progress) * 23)]
            if up:
                bubble.pos[:] = drop.pos + UP * (size * stretch + .0011)
                bubble.size[0] = size * .52
                bubble.rgba[3] = min(.86, progress * 12)
            elif (elapsed % cycle) - .53 * cycle < .29:
                # Let the detached gas reach the oil surface while its payload sinks.
                age = ((elapsed % cycle) - .53 * cycle) / .29
                turn_z = oil - 1.55 * size
                turn_stretch = 1.2 + .33 * math.sin(.53 * math.pi * 3 + index)
                start_z = min(oil - .0008, turn_z + size * turn_stretch + .0011)
                radius = np.interp(turn_z, profile[:, 0], profile[:, 1])
                span = (radius - size - .001) * (.23 + .09 * (index % 6))
                turn_angle = GOLDEN_ANGLE * index + .7 * .53
                bubble.pos[:] = self.receiver + [
                    span * math.cos(turn_angle), span * math.sin(turn_angle),
                    start_z + (oil + .0006 - start_z) * age,
                ]
                bubble.size[0] = size * .52 * (1 - .45 * age)
                bubble.rgba[3] = .86 * (1 - age)
