"""Builds the MuJoCo scene: the SO-101 arm plus the bench from the active setup."""

from __future__ import annotations

from dataclasses import dataclass

import mujoco
import numpy as np

from .config import ARM_JOINTS, ARM_XML, Bench

TABLE_THICKNESS = 0.02
WALL_RGBA = [0.85, 0.90, 0.95, 0.30]
STREAM_RADIUS = 0.004
MARK_RGBA = {"source": [0.15, 0.45, 0.85, 1], "receiver": [0.90, 0.55, 0.10, 1], "point": [0.20, 0.60, 0.35, 1]}


@dataclass
class Scene:
    """Things on the bench are addressed by a key: a container by its station
    name ("A"), a loose object by its own name ("block")."""

    model: mujoco.MjModel
    data: mujoco.MjData
    bench: Bench
    arm_qadr: list[int]
    gripper_qadr: int
    grasp_site: int
    arm_bodies: set[int]
    gripper_bodies: set[int]
    table_geom: int
    kind: dict[str, str]  # key -> "cup", "receiver" or "object"
    body: dict[str, int]  # key -> body id
    mocap: dict[str, int]  # key -> mocap index
    geom: dict[str, int]  # key -> the geom used for collisions
    liquid_geom: dict[str, int]  # containers only
    stream_geom: int

    def size(self, key: str) -> tuple[float, float]:
        """(radius or half-width, height) of the thing with this key."""
        b = self.bench
        if self.kind[key] == "cup":
            return b.cup_radius, b.cup_height
        if self.kind[key] == "receiver":
            return b.receiver_radius, b.receiver_height
        w, _, h = b.objects[key].size
        return w / 2, h

    def rest_position(self, key: str, station: str | None = None) -> np.ndarray:
        """Centre of the thing when it stands on a station (its own, for a container)."""
        x, y = self.bench.stations[station or key].pos
        return np.array([x, y, self.size(key)[1] / 2])


def build_scene(bench: Bench) -> Scene:
    spec = mujoco.MjSpec.from_file(str(ARM_XML))
    spec.modelname = "openarms_bench"

    # Offscreen buffer large enough for the preview video.
    spec.visual.global_.offwidth = 1280
    spec.visual.global_.offheight = 960
    spec.visual.headlight.ambient = [0.45, 0.45, 0.45]
    spec.visual.headlight.diffuse = [0.55, 0.55, 0.55]
    spec.visual.headlight.specular = [0.1, 0.1, 0.1]

    spec.add_texture(
        name="sky",
        type=mujoco.mjtTexture.mjTEXTURE_SKYBOX,
        builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,
        rgb1=[0.80, 0.86, 0.92],
        rgb2=[0.55, 0.62, 0.72],
        width=256,
        height=1536,
    )

    world = spec.worldbody
    world.add_light(pos=[0.2, 0.0, 1.5], dir=[0, 0, -1], castshadow=False)

    # The grasp point: where the centre of a held cup or block sits, between the jaws.
    gripper = spec.body("gripper")
    gripper.add_site(name="grasp_point", pos=[0.022, 0.0, -0.079], quat=[0.707107, 0, 0.707107, 0], group=3)

    sx, sy = bench.table_size
    cx, cy = bench.table_center
    world.add_geom(
        name="table",
        type=mujoco.mjtGeom.mjGEOM_BOX,
        size=[sx / 2, sy / 2, TABLE_THICKNESS / 2],
        pos=[cx, cy, -TABLE_THICKNESS / 2],
        rgba=[0.93, 0.93, 0.90, 1],
    )

    kind: dict[str, str] = {}
    for name, st in bench.stations.items():
        x, y = st.pos
        if st.kind == "point":
            # Taped square the object stands on.
            world.add_geom(
                name=f"mark_{name}",
                type=mujoco.mjtGeom.mjGEOM_BOX,
                size=[0.030, 0.030, 0.0005],
                pos=[x, y, 0.0005],
                rgba=MARK_RGBA["point"],
                contype=0,
                conaffinity=0,
            )
            continue
        is_source = st.kind == "source"
        kind[name] = "cup" if is_source else "receiver"
        r = bench.cup_radius if is_source else bench.receiver_radius
        h = bench.cup_height if is_source else bench.receiver_height
        world.add_geom(
            name=f"mark_{name}",
            type=mujoco.mjtGeom.mjGEOM_CYLINDER,
            size=[r + 0.008, 0.0005, 0],
            pos=[x, y, 0.0005],
            rgba=MARK_RGBA[st.kind],
            contype=0,
            conaffinity=0,
        )
        body = world.add_body(name=f"thing_{name}", pos=[x, y, h / 2], mocap=True)
        body.add_geom(name=f"geom_{name}", type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=[r, h / 2, 0], rgba=WALL_RGBA)
        body.add_geom(
            name=f"liquid_{name}",
            type=mujoco.mjtGeom.mjGEOM_CYLINDER,
            size=[r * 0.88, h * 0.25, 0],
            pos=[0, 0, -h * 0.22],
            rgba=[0.5, 0.5, 0.5, 1],
            contype=0,
            conaffinity=0,
        )

    for name, obj in bench.objects.items():
        if name in bench.stations:
            raise ValueError(f"object {name!r} has the same name as a station")
        kind[name] = "object"
        w, dp, h = obj.size
        x, y = bench.stations[obj.at].pos
        body = world.add_body(name=f"thing_{name}", pos=[x, y, h / 2], mocap=True)
        body.add_geom(
            name=f"geom_{name}", type=mujoco.mjtGeom.mjGEOM_BOX, size=[w / 2, dp / 2, h / 2], rgba=[*obj.color, 1]
        )

    stream = world.add_body(name="pour_stream", mocap=True, pos=[0, 0, -1])
    stream.add_geom(
        name="stream",
        type=mujoco.mjtGeom.mjGEOM_CYLINDER,
        size=[STREAM_RADIUS, 0.02, 0],
        rgba=[0.5, 0.5, 0.5, 0],
        contype=0,
        conaffinity=0,
    )

    model = spec.compile()
    data = mujoco.MjData(model)

    def bid(n):
        return model.body(n).id

    arm_names = ["base", "shoulder", "upper_arm", "lower_arm", "wrist", "gripper", "moving_jaw_so101_v1"]
    scene = Scene(
        model=model,
        data=data,
        bench=bench,
        arm_qadr=[int(model.joint(j).qposadr[0]) for j in ARM_JOINTS],
        gripper_qadr=int(model.joint("gripper").qposadr[0]),
        grasp_site=model.site("grasp_point").id,
        arm_bodies={bid(n) for n in arm_names},
        gripper_bodies={bid("gripper"), bid("moving_jaw_so101_v1")},
        table_geom=model.geom("table").id,
        kind=kind,
        body={k: bid(f"thing_{k}") for k in kind},
        mocap={k: int(model.body_mocapid[bid(f"thing_{k}")]) for k in kind},
        geom={k: model.geom(f"geom_{k}").id for k in kind},
        liquid_geom={k: model.geom(f"liquid_{k}").id for k in kind if kind[k] != "object"},
        stream_geom=model.geom("stream").id,
    )
    mujoco.mj_forward(model, data)
    return scene
