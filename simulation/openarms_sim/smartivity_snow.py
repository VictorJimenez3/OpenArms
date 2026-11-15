"""Magic Snow presentation worlds with a bounded powder-transfer proxy."""
from dataclasses import dataclass, replace
import math

import numpy as np

from .smartivity_world import BEAKER, FLASK, GOLDEN_ANGLE, UP, World, _geom, _VisualEffects

POWDER = (.91, .88, .81, 1.)
WATER = (.13, .38, .52, .64)
SNOW = (.84, .93, .99, 1.)
RELEASES = 49
GRAINS_PER_RELEASE = 3
CRYSTALS = 1080
CLUMPS = 63


@dataclass(frozen=True, slots=True)
class SnowEffects(_VisualEffects):
    powder_remaining: float
    hydrate_fraction: float
    releases: tuple


class SnowWorld(World):
    _scenarios = ("magic_snow",)

    def __init__(self, *, layout=None):
        self.releases = []
        self.delivered_spoons = 0.
        self._snow_geometry = None
        super().__init__(scenario="magic_snow", layout=layout)
        self.soak_seconds = self.manifest["preparation"]["soak_seconds"]

    def _update_transfer(self):
        if self._held is None:
            return
        donor = self.contents[BEAKER]
        powder = donor["snow_powder_kit_spoons"]
        rotation = self._beaker_rotation()
        tilt = math.degrees(math.acos(float(np.clip(rotation[2, 2], -1, 1))))
        if powder < 1e-8 or tilt < 103 or rotation[2, 1] > -.3:
            return
        lip = self.data.mocap_pos[self._beaker] + rotation @ np.array(
            [0, self.beaker_profile["outer_profile"][-1][1] / 1000, self.beaker_height]
        )
        opening = self.receiver + UP * self.flask_height
        amount = min(powder, 2.2 * self.timestep)
        donor["snow_powder_kit_spoons"] -= amount
        if lip[2] > opening[2] and np.linalg.norm((lip - opening)[:2]) <= .045:
            previous = self.delivered_spoons
            self.delivered_spoons += amount
            if not self.releases or int(self.delivered_spoons * 16) != int(previous * 16):
                self.releases.append((self.sim_time, tuple(float(coordinate) for coordinate in lip)))
        else:
            self.spill["snow_powder_kit_spoons"] += amount

    def _hydration(self, age):
        if not self.releases:
            return 0.
        # An illustrative uptake curve. The booklet specifies an observation
        # time, but provides no kinetic measurements or yield data.
        extent = np.clip((age - .21) / (self.soak_seconds - .21), 0., 1.)
        uptake = -np.expm1(-4.2 * extent) / -np.expm1(-4.2)
        dose = self.initial[BEAKER]["snow_powder_kit_spoons"]
        return float(uptake * self.delivered_spoons / dose)

    def time_lapse_state(self, age, state):
        """Advance only the illustrative absorption with the robot parked."""
        hydrate_fraction = self._hydration(age)
        remaining_water = self.initial[FLASK]["water_ml"] * (1. - hydrate_fraction)
        effects = replace(state.effects, hydrate_fraction=hydrate_fraction,
                          water_ml=(0., remaining_water), releases=())
        return replace(state, effects=effects, sim_time=self.releases[0][0] + age)

    def _visual_effects(self):
        age = self.sim_time - self.releases[0][0] if self.releases else 0.
        absorbed = self._hydration(age)
        carry = self.contents[BEAKER]["snow_powder_kit_spoons"]
        return SnowEffects((0., self.contents[FLASK]["water_ml"] * (1. - absorbed)),
                           (POWDER, WATER), 0., 0., None, carry, absorbed, tuple(self.releases))

    def evaluate(self):
        expected = self.initial[BEAKER]["snow_powder_kit_spoons"]
        spillage = self.spill["snow_powder_kit_spoons"]
        success = (abs(self.delivered_spoons - expected) < 1e-7 and spillage < 1e-7
                   and self._placed and not self.collisions and not self.drops and not self._fault)
        return {
            "success": bool(success),
            "powder_delivered_kit_spoons": self.delivered_spoons,
            "powder_spilled_kit_spoons": spillage,
            "water_preloaded_ml": self.initial[FLASK]["water_ml"],
            "model_wait_seconds": self.soak_seconds,
            "collisions": self.collisions,
            "drops": self.drops,
            "beaker_docked": bool(self._placed),
        }

    def _dress_presentation(self, spec):
        super()._dress_presentation(spec)
        bowl = spec.body(FLASK)
        spec.geom("table").rgba = [.052, .086, .132, 1.]
        spec.geom("tray_c").rgba = [.13, .21, .29, 1.]
        spec.geom("flask_surface").rgba = [.65, .87, .98, .30]
        for index in range(24):
            spec.geom(f"flask_rim_{index}").rgba = [.45, .79, .86, .70]
        # A cool side key shapes the individual snow grains in the detail shot.
        spec.worldbody.add_light(pos=self.receiver + [-.09, -.13, .19], dir=[.35, .52, -.80],
                                 diffuse=[.27, .34, .46], specular=[.08, .12, .19], castshadow=False)
        frost = spec.add_material(name="snow_crystal", rgba=SNOW, specular=.08, shininess=.16)
        _geom(bowl, "snow_core", "ELLIPSOID", [.02, .02, .004], [0, 0, .007], [.80, .90, .98, 0.],
              material=frost.name, contype=0, conaffinity=0)
        for index in range(CLUMPS):
            _geom(bowl, f"snow_clump_{index}", "ELLIPSOID", [.004, .004, .003], [0, 0, -.1],
                  [.83, .92, .99, 0.], material=frost.name, contype=0, conaffinity=0)
        for index in range(CRYSTALS):
            _geom(bowl, f"snow_crystal_{index}", "SPHERE", [.0011, 0, 0], [0, 0, -.1],
                  [.86, .93, .99, 0.], material=frost.name, contype=0, conaffinity=0)
        for index in range(RELEASES * GRAINS_PER_RELEASE):
            _geom(spec.worldbody, f"snow_powder_{index}", "SPHERE", [.00065, 0, 0], [0, 0, -.1],
                  [.98, .93, .87, 0.], contype=0, conaffinity=0)

    def _render_liquid(self, model, sim_time, effects):
        super()._render_liquid(model, sim_time, effects)
        powder = model.geom("beaker_liquid")
        carry = effects.powder_remaining / self.initial[BEAKER]["snow_powder_kit_spoons"]
        powder.rgba[:] = (*POWDER[:3], .96 if carry > .01 else 0.)
        powder.pos[2] = .0035
        powder.size[:2] = [.0135, .0006 + .0028 * carry]
        water = model.geom("flask_liquid")
        water.rgba[3] *= 1. - .62 * effects.hydrate_fraction

    def _presentation_foam(self, model, groups, state):
        self._draw_powder(model, state)
        self._draw_snow(model, state.effects.hydrate_fraction)

    def _draw_powder(self, model, state):
        for index in range(RELEASES * GRAINS_PER_RELEASE):
            grain = model.geom(f"snow_powder_{index}")
            grain.rgba[3] = 0.
            release, offset = divmod(index, GRAINS_PER_RELEASE)
            if release >= len(state.effects.releases):
                continue
            start, lip = state.effects.releases[release]
            age = state.sim_time - start - .005 * offset
            if not 0 <= age < .24:
                continue
            fraction = (age / .24) ** 1.8
            spread = .006 * math.sqrt(fraction)
            angle = GOLDEN_ANGLE * index
            target = self.receiver + [spread * math.cos(angle), spread * math.sin(angle), .014]
            grain.pos[:] = np.asarray(lip) * (1 - fraction) + target * fraction
            grain.size[0] = .00033 + .00029 * ((index * 37) % 11) / 10
            grain.rgba[3] = min(1., (1. - fraction) * 10.)

    def _draw_snow(self, model, hydration):
        core = model.geom("snow_core")
        if self._snow_geometry is None:
            rng = np.random.default_rng(241)
            groups = []
            for label, count, clump in (("snow_clump", CLUMPS, True), ("snow_crystal", CRYSTALS, False)):
                ids = [model.geom(f"{label}_{index}").id for index in range(count)]
                sequence = np.arange(count)
                fraction = np.sqrt((sequence + rng.uniform(.05, .95, count)) / count)
                fraction *= .93 if clump else .985
                angle = sequence * GOLDEN_ANGLE + rng.uniform(-.05, .05, count)
                size = rng.uniform(.0021, .0030, count) if clump else rng.uniform(.0004, .00115, count)
                tone = rng.uniform(.87, .99, count)
                rgb = np.stack((tone * .96, tone * .99, tone), axis=-1)
                waviness = .0013 * np.sin(fraction * 17 - np.sin(3 * angle) * 1.3)
                groups.append((ids, fraction, angle, size, rgb, waviness))
            self._snow_geometry = groups

        if hydration <= .001:
            core.rgba[3] = 0
            for ids, *_ in self._snow_geometry:
                model.geom_rgba[ids, 3] = 0
            return

        growth = hydration ** .62
        radius = .008 + .037 * growth
        half_height = .003 + .027 * hydration
        centre_z = .007 + .022 * hydration
        core.pos[2] = centre_z
        core.size[:] = [radius * .96, radius * .94, half_height * .96]
        core.rgba[3] = min(1., hydration * 24)

        for group, (ids, fraction, angle, size, rgb, waviness) in enumerate(self._snow_geometry):
            x = radius * fraction * np.cos(angle)
            y = radius * fraction * np.sin(angle)
            height = centre_z + half_height * np.sqrt(1 - fraction**2)
            height += waviness * growth
            size = size * (.57 + .43 * growth)
            if group == 0:
                model.geom_size[ids] = np.stack((size * 1.35, size * 1.18, size * .58), axis=-1)
                height -= size * .54
            else:
                model.geom_size[ids, 0] = size
                height -= size * .20
            model.geom_pos[ids] = np.stack((x, y, height), axis=-1)
            model.geom_rgba[ids, :3] = rgb
            model.geom_rgba[ids, 3] = np.clip((hydration - fraction * .27) * 18, 0, 1)
