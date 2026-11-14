import json

import mujoco
import numpy as np
import pytest

from openarms_sim.smartivity_world import World


def run(world, action):
    world.start(action)
    end = world.sim_time + 20
    while world.busy and world.sim_time < end:
        world.tick()
    assert not world.busy
    assert world.evaluate()["fault"] is None


def test_volcano_actions_and_hollow_geometry():
    world = World()
    for vessel, xy in (("beaker", world.dock), ("flask", world.receiver)):
        geom_id = np.array([-1], dtype=np.int32)
        distance = mujoco.mj_ray(world.model, world.data, xy + [0, 0, .15], np.array([0., 0., -1.]),
                                np.array([0, 0, 0, 1, 0, 0], dtype=np.uint8), True, -1, geom_id)
        assert distance > .14
        assert world.model.geom(geom_id.item()).name == vessel + "_bottom"
    with pytest.raises(ValueError, match="gripper state"):
        world.start("pour")
    run(world, "pick")
    assert world.evaluate()["foam_peak"] == 0.
    run(world, "pour")
    state = world.evaluate()
    assert not state["success"]
    assert state["foam_peak"] > 0.
    assert state["delivered_ml"] == pytest.approx(15.)
    assert state["spilled_ml"] == 0.
    assert state["remaining"]["flask"]["citric_acid_kit_spoons"] == pytest.approx(4.)
    run(world, "return_cup")
    assert world.evaluate()["success"]
    run(world, "home")
    json.dumps(world.proprioception(), allow_nan=False)
    json.dumps(world.evaluate(), allow_nan=False)
    assert world.evaluate()["collisions"] == world.evaluate()["drops"] == 0


def test_paired_seed_distinguishes_foam_from_success_and_conserves_material():
    baseline = World(18, aim="mouth_center")
    candidate = World(18)
    for world in (baseline, candidate):
        for action in ("pick", "pour", "return_cup", "home"):
            run(world, action)
        state = world.evaluate()
        for component, amount in state["preloaded"]["beaker"].items():
            remaining = sum(vessel.get(component, 0.) for vessel in state["remaining"].values())
            prepared_flask = state["preloaded"]["flask"].get(component, 0.)
            assert remaining + state["spill"][component] == pytest.approx(amount + prepared_flask)
        assert state["foam_peak"] > 0.
        assert state["placed"]
    assert baseline.evaluate()["spilled_ml"] > 3.
    assert not baseline.evaluate()["success"]
    assert candidate.evaluate()["spilled_ml"] == 0.
    assert candidate.evaluate()["success"]


def test_halt_aborts_skill_but_physics_keeps_stepping():
    world = World()
    world.start("pick")
    for _ in range(100):
        world.tick()
    world.halt()
    now = world.sim_time
    world.tick()
    assert world.sim_time == pytest.approx(now + world.timestep)
    assert not world.busy
    assert world.evaluate()["delivered_ml"] == 0.
    assert world.phase == "halted"
