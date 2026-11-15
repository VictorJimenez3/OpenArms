"""Persistent simulation of Smartivity scenes with a separate carrier-volume model."""
from __future__ import annotations

import math
from copy import copy, deepcopy
from dataclasses import dataclass, replace
from types import SimpleNamespace

import mujoco
import numpy as np
import yaml

from .config import ARM_JOINTS, ARM_XML, CONFIG_DIR, Station, load_joint_map
from .ik import HOME_MODEL, solve
from .joints import JointMap
from .motion import blend, build_segments, go_to_duration
from .vessel_assets import DEFAULT as VESSELS, _wedge, cavity_volume_ml, load_parameters, surface_mesh

JOINTS = (*ARM_JOINTS, "gripper")
CAMERAS = ("overview", "side")
REPLAY_CAMERAS = ("wide", "reaction")
REPLAY_WIDTH, REPLAY_HEIGHT = 1280, 720
PLUME_LOBES, RUNOFF_LOBES, TRAY_LOBES = 104, 72, 62
GOLDEN_ANGLE = 2.39996323
MAX_LAYOUT_VARIATION_M = .018
REGISTRATION_WIDTH, REGISTRATION_HEIGHT = 640, 480
REGISTRATION_CENTER = (.26, 0.)
REGISTRATION_VERTICAL_SPAN_M = .398
FIDUCIALS = {
    "dock": {"offset_xy_m": [.041, 0.], "rgb_min": [180, 0, 150], "rgb_max": [255, 120, 255],
             "radius_m": .006},
    "receiver": {"offset_xy_m": [.092, 0.], "rgb_min": [0, 175, 0], "rgb_max": [125, 255, 135],
                 "radius_m": .006},
}
UP = np.array([0., 0., 1.])
BEAKER = "beaker"
FLASK = "flask"
RGBA_WATER = (.4, .81, .97, .81)
RGBA_RED = (.74, .06, .17, .95)
RGBA_FROTH = (.98, .27, .38, 1)
RGBA_TEA = (.12, .21, .86, .94)
RGBA_PINK = (.87, .08, .45, .94)
RGBA_GREEN = (.14, .72, .22, .94)
RGBA_MIXED = (.52, .21, .81, .94)
RGBA_FIZZ = (.68, .46, .98, 1.)
SETUPS = CONFIG_DIR / "setups" / "smartivity"
POTION_STEPS = ("acidify_flask", "basify_cup")
POTION_STAGES = ("blue_tea_divided", "flask_pink", "cup_green")


def _geom(body, name, kind, size, pos, rgba, **kwargs):
    return body.add_geom(name=name, type=getattr(mujoco.mjtGeom, "mjGEOM_" + kind),
                         size=size, pos=pos, rgba=rgba, **kwargs)


def _mesh_geom(spec, body, name, points, rgba, *, faces=None, collision=False):
    mesh = spec.add_mesh(name=name)
    mesh.uservert = np.asarray(points, dtype=float).ravel().tolist()
    if faces is not None:
        mesh.userface = np.asarray(faces, dtype=int).ravel().tolist()
    return body.add_geom(name=name, type=mujoco.mjtGeom.mjGEOM_MESH, meshname=name,
                         rgba=rgba, group=3 if collision else 0,
                         contype=int(collision), conaffinity=int(collision))


def _vessel(spec, body, profile, rgba):
    points, faces = surface_mesh(profile, segments=60)
    _mesh_geom(spec, body, body.name + "_surface", points, rgba, faces=faces)
    floor = profile["inner_profile"][0][0]
    base = profile["outer_profile"][0][1] / 1000
    _geom(body, body.name + "_bottom", "CYLINDER", [base, floor / 2000, 0],
          [0, 0, floor / 2000], rgba, group=3)
    heights = sorted({h for label in ("inner_profile", "outer_profile") for h, _ in profile[label] if h >= floor})
    for level, (lo, hi) in enumerate(zip(heights, heights[1:])):
        for side in range(16):
            points = _wedge(profile, lo, hi, side, 16)
            _mesh_geom(spec, body, f"{body.name}_wall_{level}_{side}", points, rgba, collision=True)


def _profile(inner, thickness):
    return {
        "inner_profile": inner,
        "outer_profile": [[0, inner[0][1] + thickness], *[[z, r + thickness] for z, r in inner[1:]]],
        "spout": {"start_height_mm": inner[-1][0] - 1, "extension_mm": 0, "half_angle_deg": 20},
    }


def _vessel_radius(profile):
    return profile["inner_profile"][-1][1] / 1000


@dataclass(frozen=True, slots=True)
class _VisualEffects:
    water_ml: tuple[float, float]
    rgba: tuple[tuple[float, ...], tuple[float, ...]]
    foam: float
    foam_peak: float
    stream: tuple[float, ...] | None


@dataclass(frozen=True, slots=True)
class VisualState:
    """Presentation-only immutable sample; all tuples own their data."""

    sim_time: float
    seed: int
    scenario: str
    qpos: tuple[float, ...]
    mocap_pos: tuple[float, ...]
    mocap_quat: tuple[float, ...]
    effects: _VisualEffects

    def __post_init__(self):
        # Re-freeze arrays read back from a JSON recording.
        for name in ("qpos", "mocap_pos", "mocap_quat"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if isinstance(self.effects, dict):
            saved = self.effects
            effects = _VisualEffects(tuple(saved["water_ml"]), tuple(tuple(rgba) for rgba in saved["rgba"]),
                                     float(saved["foam"]), float(saved["foam_peak"]),
                                     tuple(saved["stream"]) if saved["stream"] is not None else None)
            object.__setattr__(self, "effects", effects)

    @property
    def foam(self) -> float:
        return self.effects.foam


class World:
    """Bounded joint goals and a separate carrier-volume model."""

    _scenarios = ("volcano", "potions")

    def __init__(self, seed: int = 0, *, aim: str = "spout", scenario: str = "volcano",
                 position_variation_m: float | None = None):
        if aim not in ("spout", "mouth_center"):
            raise ValueError("Unknown pour aim.")
        if scenario not in self._scenarios:
            raise ValueError("Unknown Smartivity experiment.")
        if position_variation_m is not None and (
                isinstance(position_variation_m, bool) or not 0 <= position_variation_m <= MAX_LAYOUT_VARIATION_M):
            raise ValueError("Position variation must be between 0 and 0.018 m.")
        self.position_variation_m = position_variation_m
        self._registered_layout = None
        self.aim = aim
        self.scenario = scenario
        base = yaml.safe_load((SETUPS / "volcano.yaml").read_text())
        source = base if scenario == "volcano" else yaml.safe_load((SETUPS / f"{scenario}.yaml").read_text())
        self.config = config = base["model"] | source["model"]
        self.manifest = {"source": source["source"], "preparation": source["preparation"]}
        self.preparation_history = []
        self._additions = source["preparation"].get("additions", {})
        self.seed = int(seed)
        self.joint_map = JointMap(load_joint_map())
        if scenario == "volcano":
            self.beaker_profile = load_parameters(VESSELS / "parameters.json")["vessels"]["donor_A"]
        else:
            self.beaker_profile = _profile(config["source_internal_profile_mm"], config["source_wall_mm"])
        self.flask_profile = _profile(config["flask_internal_profile_mm"], config["flask_wall_mm"])
        self.foam_color = RGBA_FROTH if scenario == "volcano" else RGBA_FIZZ
        self.capacity = {BEAKER: cavity_volume_ml(self.beaker_profile), FLASK: cavity_volume_ml(self.flask_profile)}
        self.beaker_height = self.beaker_profile["inner_profile"][-1][0] / 1000
        self.flask_height = self.flask_profile["inner_profile"][-1][0] / 1000
        self.nominal_beaker = np.r_[config["beaker_xy_m"], config["beaker_dock_height_m"]]
        self.nominal_flask = np.r_[config["flask_xy_m"], config["flask_base_m"]]
        rng = np.random.default_rng(seed)
        variation = config["variation"]
        if position_variation_m is None:
            delta = rng.uniform(-1, 1, (2, 2)) * variation["position_m"] if seed else np.zeros((2, 2))
        else:
            delta = rng.uniform(-1, 1, (2, 2)) * position_variation_m
        self.dock = self.nominal_beaker + np.r_[delta[0], 0]
        self.receiver = self.nominal_flask + np.r_[delta[1], 0]
        self.contents = {key: {k: float(v) for k, v in source["preparation"][key].items() if k != "stir_count"}
                         for key in (BEAKER, FLASK)}
        if seed:
            for contents in self.contents.values():
                contents["water_ml"] *= 1 + rng.uniform(-1, 1) * variation["water_fill_fraction"]
        self.initial = {key: dict(contents) for key, contents in self.contents.items()}
        self.spill = {name: 0. for name in self.contents[BEAKER]}
        self.overflow_ml = 0.
        self.delivered_ml = 0.
        self.collisions = 0
        self.drops = 0
        self._contacts = set()
        self._renderer = None
        self._replay = None
        self._held = None
        self._placed = False
        self._fault = None
        self._action = None
        self._segments = []
        self._elapsed = 0.
        self._flow = False
        self._foam = 0.
        self._max_foam = 0.
        self.phase = "ready"
        self.model = m = self._build()
        self.data = d = mujoco.MjData(m)
        self._joint_ids = [m.joint(name).id for name in JOINTS]
        self._qaddr = m.jnt_qposadr[self._joint_ids]
        self._vaddr = m.jnt_dofadr[self._joint_ids]
        self._actuators = [m.actuator(name).id for name in JOINTS]
        self._site = m.site("grasp_point").id
        self._beaker = m.body(BEAKER).mocapid.item()
        self._spout = self._build_motion()
        d.qpos[self._qaddr] = d.ctrl[self._actuators] = np.r_[HOME_MODEL, self._grip(self.joint_map.gripper_open_value)]
        self._rest_rotation = np.array([[self._spout[0], -self._spout[1], 0.],
                                        [self._spout[1], self._spout[0], 0.], [0., 0., 1.]])
        # The donor asset's local spout is +Y, so rotate local +Y to the chosen horizontal direction.
        self._rest_rotation = self._rest_rotation @ np.array([[0, 1, 0], [-1, 0, 0], [0, 0, 1]])
        d.mocap_pos[self._beaker] = self.dock
        mujoco.mju_mat2Quat(d.mocap_quat[self._beaker], self._rest_rotation.ravel())
        self._cameras = {}
        eye_shift = rng.uniform(-1, 1, (2, 2)) * variation["camera_deg"] if seed else np.zeros((2, 2))
        for i, (name, azimuth, elevation, distance) in enumerate((("overview", 180, -48, .65), ("side", 143, -19, .56))):
            cam = mujoco.MjvCamera()
            cam.lookat[:] = [.225, .01, .081]
            cam.distance = distance
            cam.azimuth, cam.elevation = azimuth + eye_shift[i, 0], elevation + eye_shift[i, 1]
            self._cameras[name] = cam
        self._camera_options = mujoco.MjvOption()
        self._camera_options.geomgroup[3] = 0
        self._render_liquid(m, self.sim_time, self._visual_effects())
        mujoco.mj_forward(m, d)

    def _build(self, *, presentation=False):
        spec = mujoco.MjSpec.from_file(str(ARM_XML))
        spec.modelname = "openarms_smartivity_" + self.scenario
        spec.option.timestep = .004
        spec.visual.global_.offwidth = 640
        spec.visual.global_.offheight = 480
        spec.visual.headlight.ambient = [.5, .5, .5]
        spec.visual.headlight.diffuse = [.55, .55, .55]
        spec.visual.headlight.specular = [.25, .25, .25]
        w = spec.worldbody
        w.add_light(pos=[.08, -.3, .55], dir=[.3, .5, -.8], castshadow=False)
        w.add_light(pos=[.5, .25, .52], dir=[-.4, -.3, -.8], castshadow=False)
        spec.body("gripper").add_site(name="grasp_point", pos=[.022, 0, -.079],
                                      quat=[.707107, 0, .707107, 0], group=3)
        _geom(w, "table", "BOX", [.34, .43, .014], [*self.config["table_centre_m"], -.014], [.10, .17, .19, 1])
        _geom(w, "dock_a", "CYLINDER", [.032, .0015, 0], self.dock - UP * .0015, [.08, .66, .76, 1])
        _geom(w, "tray_c", "BOX", [.078, .058, .002], self.receiver - UP * .002, [.22, .30, .26, 1])
        for x, y, sx, sy in ((.077, 0, .001, .058), (-.077, 0, .001, .058),
                             (0, .057, .076, .001), (0, -.057, .076, .001)):
            _geom(w, f"tray_border_{x}_{y}", "BOX", [sx, sy, .003],
                  self.receiver + [x, y, .002], [.33, .46, .40, 1])
        for key, profile, pos, rgba in ((BEAKER, self.beaker_profile, self.dock, [.75, .86, 1, .29]),
                                         (FLASK, self.flask_profile, self.receiver, [.72, .88, .89, .33])):
            body = w.add_body(name=key, pos=pos.tolist(), mocap=key == BEAKER)
            _vessel(spec, body, profile, rgba)
            r, height = _vessel_radius(profile), profile["inner_profile"][-1][0] / 1000
            rim_color = [.32, .83, .98, .55] if key == BEAKER else [.75, .94, .82, .5]
            sides = 24
            for side in range(sides):
                angle = math.tau * side / sides
                normal = np.array([math.cos(angle), math.sin(angle)])
                _geom(body, f"{key}_rim_{side}", "BOX", [.0009, r * math.tan(math.pi / sides), .001],
                      [*normal * (r + .001), height - .001], rim_color,
                      quat=[math.cos(angle / 2), 0, 0, math.sin(angle / 2)], contype=0, conaffinity=0)
            _geom(body, key + "_liquid", "CYLINDER", [r*.95, .008, 0], [0, 0, .011],
                  RGBA_WATER if key == BEAKER else RGBA_RED, contype=0, conaffinity=0)
        # The attached-object proxy does not qualify jaw friction or finger contact.
        for jaw in ("gripper", "moving_jaw_so101_v1"):
            spec.add_exclude(bodyname1=BEAKER, bodyname2=jaw)
        for index in range(24):
            _geom(w, f"foam_{index}", "SPHERE", [.004, 0, 0], [0, 0, -.1],
                  [*self.foam_color[:3], 0], contype=0, conaffinity=0)
        _geom(w, "foam_residue", "ELLIPSOID", [.027, .022, .001], self.receiver + [.026, -.009, .001],
              [*self.foam_color[:3], 0], contype=0, conaffinity=0)
        _geom(w, "stream", "CYLINDER", [.0018, .01, 0], [0, 0, -.1], [*RGBA_WATER[:3], 0],
              contype=0, conaffinity=0)
        if self.position_variation_m is not None:
            self._add_registration(spec)
        if presentation:
            self._dress_presentation(spec)
        return spec.compile()

    def _add_registration(self, spec):
        world = spec.worldbody
        world.add_camera(name="registration", pos=[*REGISTRATION_CENTER, .65], xyaxes=[0, -1, 0, 1, 0, 0],
                         fovy=REGISTRATION_VERTICAL_SPAN_M, proj=mujoco.mjtProjection.mjPROJ_ORTHOGRAPHIC)
        for label, world_pos, rgb in (("dock", self.dock, [1, 0, 1]),
                                       ("receiver", self.receiver, [0, 1, 0])):
            marker = FIDUCIALS[label]
            material = spec.add_material(name=f"registration_{label}", rgba=[*rgb, 1], emission=1.)
            xy = world_pos[:2] + marker["offset_xy_m"]
            _geom(world, f"fiducial_{label}", "CYLINDER", [marker["radius_m"], .0004, 0.],
                  [*xy, .003], [*rgb, 1], material=material.name, contype=0, conaffinity=0)

    def _dress_presentation(self, spec):
        """Add geometry to the spectator copy only. No new bodies or collision geoms."""
        world = spec.worldbody
        spec.visual.global_.offwidth = REPLAY_WIDTH
        spec.visual.global_.offheight = REPLAY_HEIGHT
        spec.visual.headlight.ambient = [.32, .34, .40]
        spec.visual.headlight.diffuse = [.47, .45, .43]
        spec.visual.headlight.specular = [.26, .26, .28]
        for light in world.lights:
            light.diffuse = [.46, .48, .54]
            light.specular = [.44, .45, .47]
        world.lights[0].castshadow = True
        spec.visual.quality.shadowsize = 2048
        spec.add_texture(name="studio_sky", type=mujoco.mjtTexture.mjTEXTURE_SKYBOX,
                         builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT, rgb1=[.17, .24, .31],
                         rgb2=[.035, .049, .082], width=256, height=1536)
        spec.geom("table").rgba = [.096, .143, .178, 1.]
        spec.geom("tray_c").rgba = [.19, .24, .25, 1.]
        spec.geom("dock_a").rgba = [.075, .29, .38, 1.]
        for name in (BEAKER, FLASK):
            body = spec.body(name)
            # Draw understated glass graduations at regular heights; labels are
            # omitted because only the donor geometry is photo-derived.
            profile = self.beaker_profile if name == BEAKER else self.flask_profile
            heights, radii = np.asarray(profile["outer_profile"]).T / 1000
            for index, z in enumerate(np.arange(.010, heights[-1] - .001, .006)):
                radius = float(np.interp(z, heights, radii)) + .0006
                _geom(body, f"graduation_{name}_{index}", "BOX", [.00027, .0034 if index % 2 == 0 else .0018, .00023],
                      [radius, 0, z], [.78, .90, .92, .82], contype=0, conaffinity=0)
        # Thin inlays maintain a readable tray and dock silhouette in the close-up.
        for index, (x, y) in enumerate(((.073, .051), (.073, -.051), (-.073, .051), (-.073, -.051))):
            _geom(world, f"tray_rivet_{index}", "CYLINDER", [.0024, .0004, 0],
                  self.receiver + [x, y, .001], [.56, .64, .66, 1], contype=0, conaffinity=0)
        _geom(world, "dock_outer", "CYLINDER", [.035, .00065, 0], self.dock - UP * .0025,
              [.38, .61, .64, 1.], contype=0, conaffinity=0)
        palette = ((.96, .48, .63), (.97, .64, .74), (.91, .29, .47), (.99, .76, .80))
        if self.scenario == "potions":
            palette = ((.73, .58, .93), (.82, .70, .98), (.63, .43, .95), (.88, .81, .98))
        for name, count in (("plume", PLUME_LOBES), ("runoff", RUNOFF_LOBES), ("tray", TRAY_LOBES)):
            for index in range(count):
                _geom(world, f"detail_{name}_{index}", "SPHERE", [.002, 0, 0], [0, 0, -.2],
                      [*palette[index % len(palette)], 0.], contype=0, conaffinity=0)

    def _site_pose(self):
        return self.data.site_xpos[self._site].copy(), self.data.site_xmat[self._site].reshape(3, 3).copy()

    def _build_motion(self, *, dock=None, receiver=None, fixed_spout=None):
        config = self.config
        grasp_height = config["beaker_grasp_height_m"]
        station_a = self.nominal_beaker if dock is None else dock
        station_c = self.nominal_flask if receiver is None else receiver
        grasp = station_a + UP * grasp_height
        # Runtime camera rendering updates visual geoms on the live model.
        # An off-thread registration solve gets its own model as well as data.
        model = self.model if dock is None else copy(self.model)
        planning_data = mujoco.MjData(model)
        lite = SimpleNamespace(model=model, data=planning_data, arm_qadr=self._qaddr[:5], grasp_site=self._site)
        q_grasp, Rg = self._solve(lite, grasp, 0.)
        q_lift, _ = self._solve(lite, grasp + UP * config["lift_m"], 0., q_grasp)
        tip = math.radians(config["tip_deg"])
        target_lip = station_c + UP * (self.flask_height + config["lip_clearance_m"])
        target_grasp = target_lip.copy()
        radius = (self.beaker_profile["outer_profile"][-1][1] + self.beaker_profile["spout"]["extension_mm"]) / 1000
        q_tip = q_lift
        for _ in range(5):
            q_tip, Rt = self._solve(lite, target_grasp, tip, q_tip)
            T = Rt @ Rg.T
            if fixed_spout is None:
                spout = -T.T @ UP
                spout[2] = 0
                spout /= np.linalg.norm(spout)
            else:
                spout = fixed_spout
            offset = T @ (UP * (self.beaker_height - grasp_height) + spout * radius)
            target_grasp = target_lip - offset
        if self.aim == "mouth_center":
            # Paired diagnostic: use the uncorrected center of the donor mouth
            # instead of vertically projecting the lip into the receiver.
            for _ in range(5):
                target_grasp = target_lip - (Rt @ Rg.T) @ (UP * (self.beaker_height - grasp_height))
                q_tip, Rt = self._solve(lite, target_grasp, tip, q_tip)
        q_above, _ = self._solve(lite, target_grasp, 0., q_lift)
        values = {"HOME": HOME_MODEL, "GRASP_A": q_grasp, "ABOVE_A": q_lift, "LIFT_A": q_lift,
                  "ABOVE_C": q_above, "TIP_C": q_tip}
        poses = {key: self.joint_map.pose_from_model(value) for key, value in values.items()}
        stations = {"A": Station("A", "source", tuple(station_a[:2])),
                    "C": Station("C", "receiver", tuple(station_c[:2]))}
        steps = [{"action": "pick", "args": {"station": "A"}}, {"action": "pour", "args": {"into": "C"}},
                 {"action": "return_cup"}, {"action": "home"}]
        segments = build_segments(steps, poses, self.joint_map, stations)
        self._scripts = {step["action"]: [s for s in segments if s.step_index == i] for i, step in enumerate(steps)}
        return spout

    def _solve(self, scene, target, roll, seed=None):
        q, error = solve(scene, target, roll, seed)
        if error > .004:
            raise RuntimeError(f"Smartivity fixture grasp/tilt unreachable ({error:.3f} m IK error)")
        scene.data.qpos[self._qaddr[:5]] = q
        mujoco.mj_kinematics(scene.model, scene.data)
        return q, scene.data.site_xmat[self._site].reshape(3, 3).copy()

    def registration_calibration(self):
        if self.position_variation_m is None:
            raise ValueError("Layout registration is disabled.")
        scale = REGISTRATION_VERTICAL_SPAN_M / REGISTRATION_HEIGHT
        x, y = REGISTRATION_CENTER
        return {
            "width_px": REGISTRATION_WIDTH, "height_px": REGISTRATION_HEIGHT,
            "pixel_to_world_xy": [[0., -scale, x + (REGISTRATION_HEIGHT - 1) / 2 * scale],
                                  [-scale, 0., y + (REGISTRATION_WIDTH - 1) / 2 * scale]],
            "markers": deepcopy(FIDUCIALS),
            "workspace_xy_m": [[.20, -.20], [.41, .20]],
        }

    def registration_image(self):
        if self.position_variation_m is None or self.phase != "ready" or self.busy:
            raise ValueError("Layout registration requires an idle, pre-pick scene.")
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.model, REGISTRATION_HEIGHT, REGISTRATION_WIDTH)
        self._render_liquid(self.model, self.sim_time, self._visual_effects())
        self._renderer.update_scene(self.data, "registration", scene_option=self._camera_options)
        return self._renderer.render()

    def register_layout(self, dock_xy, receiver_xy):
        """Resolve local skill targets from bounded pixel-derived estimates."""
        if self.position_variation_m is None or self.phase != "ready" or self.busy:
            raise ValueError("Layout registration requires an idle, pre-pick scene.")
        coordinates = []
        for xy, nominal in ((dock_xy, self.nominal_beaker), (receiver_xy, self.nominal_flask)):
            xy = np.asarray(xy, dtype=float)
            limit = MAX_LAYOUT_VARIATION_M + .0015  # projection/centroid pixel error margin
            if xy.shape != (2,) or not np.isfinite(xy).all() or np.any(np.abs(xy - nominal[:2]) > limit):
                raise ValueError("Estimated station lies outside its bounded fixture region.")
            coordinates.append(np.r_[xy, nominal[2]])
        # IK uses detached MjData, the estimates, and the dock's fixed nominal yaw.
        self._build_motion(dock=coordinates[0], receiver=coordinates[1], fixed_spout=self._rest_rotation[:, 1])
        self._registered_layout = [xy[:2].tolist() for xy in coordinates]

    @property
    def timestep(self):
        return float(self.model.opt.timestep)

    @property
    def sim_time(self):
        return float(self.data.time)

    @property
    def busy(self):
        return bool(self._segments)

    def _grip(self, value):
        return self.joint_map.gripper_to_model(value)

    def _le_grip(self, rad):
        g = self.joint_map.cfg["gripper"]
        return (math.degrees(rad) - g["closed_deg"]) / (g["open_deg"] - g["closed_deg"]) * 100

    @property
    def preparation_stage(self):
        if self.scenario != "potions":
            return "preloaded"
        return POTION_STAGES[len(self.preparation_history)]

    def prepare(self, step):
        """Apply a declared scene-preparation addition, with no robot motion."""
        index = len(self.preparation_history)
        if (self.scenario != "potions" or index >= len(POTION_STEPS) or step != POTION_STEPS[index]
                or self.busy or self._held is not None or self._fault or self.phase != "ready"):
            raise ValueError("That preparation step is unavailable in the current scene.")
        addition = self._additions[step]
        vessel, component, quantity = (addition[k] for k in ("vessel", "component", "quantity"))
        self.contents[vessel][component] = self.initial[vessel][component] = float(quantity)
        if vessel == BEAKER:
            self.spill[component] = 0.
        self.preparation_history.append({"step": step, "sim_seconds": self.sim_time,
                                         "performed_by": "scene_preparation", **addition})
        return self.preparation_stage

    def start(self, action):
        if self.scenario == "potions" and self.preparation_stage != "cup_green":
            raise ValueError("Complete scene preparation before commanding the robot.")
        if action not in self._scripts:
            raise ValueError("Unsupported simulated action.")
        if self.busy or self._fault:
            raise ValueError("Motion is busy or the world needs reset.")
        if (action in ("pour", "return_cup")) != (self._held is not None):
            raise ValueError("This action is incompatible with current gripper state.")
        if action == "pick" and self._placed:
            self._placed = False
        segments = self._scripts[action].copy()
        first = segments[0]
        cmd = self.data.ctrl[self._actuators]
        timing = self.joint_map.cfg["motion"]
        duration = go_to_duration(cmd[:5], first.q1, timing["max_speed_deg_s"], timing["min_duration_s"])
        segments[0] = replace(first, q0=cmd[:5], grip0=self._le_grip(cmd[-1]), duration=duration)
        goal = np.array([np.r_[s.q1, self._grip(s.grip1)] for s in segments])
        if (not np.isfinite(goal).all() or
                np.any(goal < self.model.actuator_ctrlrange[self._actuators, 0]) or
                np.any(goal > self.model.actuator_ctrlrange[self._actuators, 1])):
            raise ValueError("Action crosses a MuJoCo actuator limit.")
        self._segments, self._elapsed, self._action = segments, 0., action
        self.phase = f"{action}: {first.label}"

    def halt(self):
        self._segments.clear()
        bounds = self.model.actuator_ctrlrange[self._actuators].T
        self.data.ctrl[self._actuators] = np.clip(self.data.qpos[self._qaddr], *bounds)
        self._action = None
        self.phase = "halted"

    def _fail(self, reason):
        self.halt()
        self._fault = reason
        self.phase = "needs_reset"

    def _finish_segment(self, segment):
        d = self.data
        position, R = self._site_pose()
        if segment.event == "close":
            grip_center = d.mocap_pos[self._beaker] + UP * self.config["beaker_grasp_height_m"]
            if np.linalg.norm(position - grip_center) > .008:
                self._fail("The gripper missed the beaker grip band.")
                return
            self._held = (R.T @ (d.mocap_pos[self._beaker] - position), R.T @ self._rest_rotation)
        if segment.event == "open" and self._held is not None:
            self._placed = (np.linalg.norm(d.mocap_pos[self._beaker] - self.dock) < .008 and
                            self._beaker_rotation()[2, 2] > .98)
            self._held = None
            if not self._placed:
                self.drops += 1
                self._fail("The beaker was released outside its upright dock tolerance.")
                return
            d.mocap_pos[self._beaker] = self.dock
            mujoco.mju_mat2Quat(d.mocap_quat[self._beaker], self._rest_rotation.ravel())
        self._segments.pop(0)
        self._elapsed = 0.
        if self._segments:
            self.phase = f"{self._action}: {self._segments[0].label}"
        else:
            self.phase = f"{self._action}_completed"
            self._action = None

    def _beaker_rotation(self):
        values = np.empty(9)
        mujoco.mju_quat2Mat(values, self.data.mocap_quat[self._beaker])
        return values.reshape(3, 3)

    def _attach(self):
        if self._held is None:
            return
        point, R = self._site_pose()
        rel_pos, rel_rot = self._held
        self.data.mocap_pos[self._beaker] = point + R @ rel_pos
        mujoco.mju_mat2Quat(self.data.mocap_quat[self._beaker], (R @ rel_rot).ravel())

    def tick(self):
        d, m = self.data, self.model
        segment = self._segments[0] if self._segments else None
        if segment is not None:
            self._elapsed += self.timestep
            alpha = blend(self._elapsed / segment.duration)
            target = segment.q0 + alpha * (segment.q1 - segment.q0)
            d.ctrl[self._actuators] = np.r_[target, self._grip(segment.grip0 + alpha * (segment.grip1-segment.grip0))]
        previous_time = d.time
        mujoco.mj_step(m, d)
        if abs(d.time - previous_time - self.timestep) > 1e-9 or not np.isfinite(d.qpos).all():
            self._fail("MuJoCo integration failed.")
            return
        mujoco.mj_kinematics(m, d)
        self._attach()
        self._update_transfer()
        if segment is not None and self._elapsed >= segment.duration:
            goal = np.r_[segment.q1, self._grip(segment.grip1)]
            close = np.max(np.abs(d.qpos[self._qaddr] - goal)) < .028
            still = np.max(np.abs(d.qvel[self._vaddr])) < .15
            if close and still:
                self._finish_segment(segment)
            elif self._elapsed > segment.duration + 1.1:
                self._fail(f"Actuator failed to converge during {segment.label}.")
        self._update_contacts()

    def _update_contacts(self):
        pairs = set()
        for contact in self.data.contact:
            if contact.dist < -.001:
                pair = tuple(sorted(int(self.model.geom_bodyid[i]) for i in contact.geom))
                # World-table support of the mocap beaker is expected while in its dock.
                if pair != (0, self.model.body(BEAKER).id):
                    pairs.add(pair)
        self.collisions += len(pairs - self._contacts)
        self._contacts = pairs

    def _update_transfer(self):
        donor, receiver = self.contents[BEAKER], self.contents[FLASK]
        self._foam *= math.exp(-self.timestep / 5.)
        self._flow = False
        if self._held is None or donor["water_ml"] < 1e-6:
            return
        R = self._beaker_rotation()
        tilt = math.degrees(math.acos(float(np.clip(R[2, 2], -1, 1))))
        fill = donor["water_ml"] / self.capacity[BEAKER]
        threshold = 106 - 13 * fill
        lip = self.data.mocap_pos[self._beaker] + R @ np.array(
            [0., (self.beaker_profile["outer_profile"][-1][1] + self.beaker_profile["spout"]["extension_mm"]) / 1000,
             self.beaker_height]
        )
        if tilt < threshold or R[2, 1] > -.3:
            return
        flow = self.config["max_flow_ml_s"] * np.clip((tilt - threshold) / 8, 0, 1)
        amount = min(float(flow * self.timestep), donor["water_ml"])
        opening = self.receiver + UP * self.flask_height
        captured = lip[2] > opening[2] and np.linalg.norm((lip - opening)[:2]) <= _vessel_radius(self.flask_profile) - .001
        room = self.capacity[FLASK] - receiver["water_ml"]
        delivered = min(amount, max(float(room), 0.)) if captured else 0.
        old = donor["water_ml"]
        for name, qty in donor.items():
            donor[name] = qty * (1 - amount / old)
            receiver[name] = receiver.get(name, 0.) + qty * delivered / old
            self.spill[name] += qty * (amount - delivered) / old
        self.delivered_ml += delivered
        if captured:
            self.overflow_ml += amount - delivered
        acid_and_base = (receiver.get("baking_soda_kit_spoons", 0.) > 0 and
                         receiver.get("citric_acid_kit_spoons", 0.) > 0)
        if delivered > 0 and acid_and_base:
            if self.scenario == "potions" or receiver.get("liquid_soap_drops", 0.) > 0:
                self._foam = min(1., self._foam + delivered * .14)
                self._max_foam = max(self._max_foam, self._foam)
        self._flow, self._lip, self._stream_bottom = amount > 0, lip, opening[2] if captured else .005

    def _liquid_color(self, vessel):
        if self.scenario == "volcano":
            return RGBA_WATER if vessel == BEAKER else RGBA_RED
        contents = self.contents[vessel]
        acid = contents.get("citric_acid_kit_spoons", 0.) > 0
        base = contents.get("baking_soda_kit_spoons", 0.) > 0
        if acid and base:
            # Lavender is an illustrative interpretation of the booklet image.
            return RGBA_MIXED
        if acid:
            return RGBA_PINK
        if base:
            return RGBA_GREEN
        return RGBA_TEA

    def _visual_effects(self):
        volumes = tuple(self.contents[vessel]["water_ml"] for vessel in (BEAKER, FLASK))
        colors = tuple(self._liquid_color(vessel) for vessel in (BEAKER, FLASK))
        stream = (*self._lip.tolist(), float(self._stream_bottom)) if self._flow else None
        return _VisualEffects(volumes, colors, self._foam, self._max_foam, stream)

    def _render_liquid(self, model, sim_time, effects):
        for index, (vessel, profile) in enumerate(((BEAKER, self.beaker_profile), (FLASK, self.flask_profile))):
            fill = np.clip(effects.water_ml[index] / self.capacity[vessel], 0., 1.)
            geom = model.geom(vessel + "_liquid")
            bottom = profile["inner_profile"][0][0] / 1000
            height = profile["inner_profile"][-1][0] / 1000 - bottom
            radius = np.interp(bottom + height * fill, np.array(profile["inner_profile"])[:, 0] / 1000,
                               np.array(profile["inner_profile"])[:, 1] / 1000)
            geom.pos[2] = bottom + height * fill * .5
            geom.size[:2] = [radius * .93, max(.0002, height * fill * .5)]
            geom.rgba[:] = effects.rgba[index]
            if fill <= .001:
                geom.rgba[3] = 0.
        for i in range(24):
            bubble = model.geom(f"foam_{i}")
            alpha = (sim_time * (.37 + .025 * (i % 7)) + i * .173) % 1
            angle = i * 2.39996 + sim_time * .75
            scale = max(.005, effects.foam)
            spread = alpha * .019 * scale
            bubble.pos[:] = self.receiver + [spread * math.cos(angle), spread * math.sin(angle),
                                             self.flask_height + (alpha * .064 - .009) * scale]
            bubble.size[0] = (.004 + .002 * (i % 4)) * max(.22, min(scale*2, 1.))
            bubble.rgba[:] = [*self.foam_color[:3], min(scale * 3, 1.) if effects.foam > .04 else 0.]
        model.geom("foam_residue").rgba[3] = min(.94, effects.foam_peak) if effects.foam_peak > .22 else 0.
        stream = model.geom("stream")
        stream.rgba[:] = [*effects.rgba[0][:3], .86 if effects.stream is not None else 0.]
        if effects.stream is not None:
            x, y, lip_z, end_z = effects.stream
            stream.pos[:] = [x, y, (lip_z + end_z) / 2]
            stream.size[1] = max(.0005, (lip_z - end_z) / 2)

    def rgb(self, camera):
        if camera not in self._cameras:
            raise ValueError("Unknown Smartivity camera.")
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.model, 480, 640)
        self._render_liquid(self.model, self.sim_time, self._visual_effects())
        mujoco.mj_kinematics(self.model, self.data)
        self._renderer.update_scene(self.data, self._cameras[camera], scene_option=self._camera_options)
        return self._renderer.render()

    def visual_state(self):
        """Sample a tick for presentation replay without rendering or touching the model."""
        data = self.data
        return VisualState(self.sim_time, self.seed, self.scenario, tuple(data.qpos.tolist()),
                           tuple(data.mocap_pos.ravel().tolist()), tuple(data.mocap_quat.ravel().tolist()),
                           self._visual_effects())

    def _presentation_foam(self, model, groups, state):
        """Resolve the modeled foam level into illustrative plumes, drips and froth."""
        model.geom_rgba[groups["coarse"], 3] = 0.
        activity = state.effects.foam
        peak = state.effects.foam_peak
        lip = self.receiver + UP * self.flask_height
        time = state.sim_time

        indices = groups["plume"]
        pattern = np.arange(len(indices))
        age = (time * (.71 + (pattern % 9) * .036) + pattern * .117) % 1.
        angle = pattern * GOLDEN_ANGLE + time * .75
        strength = np.sqrt(activity)
        if self.scenario == "potions":
            # The tea fizzes in the flask. Reserve the tall plume and
            # exterior runoff for the soap-based volcano.
            radius = (.003 + .008 * age) * strength
            height = -.042 + .049 * age
            model.geom_pos[indices] = lip + np.column_stack((radius * np.cos(angle), radius * np.sin(angle), height))
            model.geom_size[indices, 0] = (.0006 + (pattern % 7) * .00026) * max(.15, strength)
            model.geom_rgba[indices, 3] = min(.83, 2.6 * activity)
            model.geom("foam_residue").rgba[3] = 0.
            return
        radius = (.002 + .014 * age) * strength
        height = (-.005 + .070 * age - .023 * age**3) * strength
        model.geom_pos[indices] = lip + np.column_stack((radius * np.cos(angle), radius * np.sin(angle), height))
        model.geom_size[indices, 0] = (.0011 + (pattern % 7) * .00055) * max(.15, strength)
        model.geom_rgba[indices, 3] = min(1., 3.5 * activity)

        indices = groups["runoff"]
        pattern = np.arange(len(indices))
        # Foam trails branch near the neck and follow the flask wall into the tray.
        age = (time * (.41 + (pattern % 5) * .063) + pattern * .083) % 1.
        angle = (pattern % 5) * math.tau / 5. + (pattern % 3 - 1) * .18 + .22 * age
        height = self.flask_height * (1. - age)
        radius = np.interp(height, [.0, .012, .049, self.flask_height], [.034, .035, .015, .0135])
        model.geom_pos[indices] = self.receiver + np.column_stack((radius * np.cos(angle), radius * np.sin(angle), height))
        model.geom_size[indices, 0] = (.001 + (pattern % 5) * .00046) * max(.15, strength)
        model.geom_rgba[indices, 3] = min(.97, max(0., activity - .2) * 2.1)

        indices = groups["tray"]
        pattern = np.arange(len(indices))
        angle = pattern * GOLDEN_ANGLE
        radius = (.027 + .0041 * np.sqrt(pattern)) * np.sqrt(peak)
        height = .0011 + (pattern % 5) * .00037
        model.geom_pos[indices] = self.receiver + np.column_stack((radius * np.cos(angle), .82 * radius * np.sin(angle), height))
        model.geom_size[indices, 0] = (.0013 + (pattern % 7) * .00038) * max(.15, np.sqrt(peak))
        model.geom_rgba[indices, 3] = min(.9, (peak - .22) * 1.4) if peak > .22 else 0.
        residue = model.geom("foam_residue")
        residue.rgba[:] = [*self.foam_color[:3], min(.62, peak * .66) if peak > .22 else 0.]
        residue.size[:2] = [.037, .029]
        residue.pos[:] = self.receiver + [.011, -.006, .0003]

    def replay_rgb(self, state, camera):
        """Render a recorded sample without stepping or mutating the live world."""
        if camera not in REPLAY_CAMERAS:
            raise ValueError("Unknown Smartivity presentation camera.")
        if not isinstance(state, VisualState) or (state.seed, state.scenario) != (self.seed, self.scenario):
            raise ValueError("Visual sample belongs to a different Smartivity scene.")
        if self._replay is None:
            model = self._build(presentation=True)
            groups = {name: np.array([model.geom(f"detail_{name}_{i}").id for i in range(count)])
                      for name, count in (("plume", PLUME_LOBES), ("runoff", RUNOFF_LOBES), ("tray", TRAY_LOBES))}
            groups["coarse"] = np.array([model.geom(f"foam_{i}").id for i in range(24)])
            cameras = {}
            configurations = (
                ("wide", [.208, .025, .094], .57, 155, -30),
                ("reaction", self.receiver + [-.013, .005, .081], .29, 175, -23),
            )
            if self.scenario == "lava_lamp":
                configurations = (configurations[0], ("reaction", self.receiver + [0., 0., .038], .168, 126, -13))
            for name, centre, distance, azimuth, elevation in configurations:
                cam = mujoco.MjvCamera()
                cam.lookat[:] = centre
                cam.distance, cam.azimuth, cam.elevation = distance, azimuth, elevation
                cameras[name] = cam
            data = mujoco.MjData(model)
            mujoco.mj_forward(model, data)
            self._replay = (model, data, mujoco.Renderer(model, REPLAY_HEIGHT, REPLAY_WIDTH), cameras, groups)
        model, data, renderer, cameras, groups = self._replay
        data.time = state.sim_time
        data.qpos[:] = state.qpos
        data.mocap_pos.flat = state.mocap_pos
        data.mocap_quat.flat = state.mocap_quat
        self._render_liquid(model, state.sim_time, state.effects)
        self._presentation_foam(model, groups, state)
        mujoco.mj_kinematics(model, data)
        renderer.update_scene(data, cameras[camera], scene_option=self._camera_options)
        return renderer.render()

    def proprioception(self):
        q = self.data.qpos[self._qaddr]
        return {"arm_position_deg": self.joint_map.pose_from_model(q[:5]),
                "gripper_position_0_100": round(self._le_grip(q[-1]), 3),
                "controller_phase": self.phase, "busy": self.busy, "fault": self._fault}

    def evaluate(self):
        source = self.initial[BEAKER]["water_ml"]
        success = (self.delivered_ml >= source * self.config["min_delivered_fraction"] and
                   self._max_foam >= .22 and self._placed and not self.drops and not self._fault)
        layout = {} if self.position_variation_m is None else {
            "position_variation_m": self.position_variation_m,
            "fixture_ground_truth_xy_m": [self.dock[:2].tolist(), self.receiver[:2].tolist()],
            "registration_estimate_xy_m": deepcopy(self._registered_layout),
        }
        return {**layout, "success": bool(success), "delivered_ml": self.delivered_ml, "spilled_ml": self.spill["water_ml"],
                "overflow_ml": self.overflow_ml, "collisions": self.collisions, "drops": self.drops,
                "placed": bool(self._placed), "foam_peak": self._max_foam, "elapsed_sim_s": self.sim_time,
                "aim": self.aim, "scenario": self.scenario, "seed": self.seed,
                "preparation_stage": self.preparation_stage, "preparation_history": deepcopy(self.preparation_history),
                "preloaded": deepcopy(self.initial),
                "remaining": deepcopy(self.contents), "spill": self.spill.copy(), "fault": self._fault}

    def close(self):
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None
        if self._replay is not None:
            self._replay[2].close()
            self._replay = None
