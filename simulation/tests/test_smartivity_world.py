from contextlib import closing

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


def test_potions_preparation_progression_and_mix_are_visible():
    with closing(World(scenario="potions")) as world:
        blue = world.rgb("overview").astype(int)
        with pytest.raises(ValueError, match="preparation"):
            world.start("pick")
        with pytest.raises(ValueError, match="preparation"):
            world.prepare("basify_cup")
        assert world.prepare("acidify_flask") == "flask_pink"
        pink = world.rgb("overview").astype(int)
        assert world.prepare("basify_cup") == "cup_green"
        green = world.rgb("overview").astype(int)
        assert world.evaluate()["foam_peak"] == 0.
        assert world.sim_time == 0.

        def pink_count(image):
            r, g, b = image[250:355, 195:277].transpose(2, 0, 1)
            return np.count_nonzero((r >= 225) & (b - g >= 30) & (r - b >= 6))

        def green_count(image):
            r, g, b = image[266:335, 391:468].transpose(2, 0, 1)
            return np.count_nonzero((g >= 130) & (g - r >= 40) & (g - b >= 10))

        assert pink_count(pink) - pink_count(blue) > 300
        assert green_count(green) - green_count(pink) > 300
        for action in ("pick", "pour", "return_cup", "home"):
            run(world, action)

        final = world.rgb("side").astype(int)
        r, g, b = final.transpose(2, 0, 1)
        assert np.count_nonzero((r >= 200) & (b >= 231) & (b - r >= 5) & (b - g >= 32)) > 300
        state = world.evaluate()
        assert state["success"]
        assert state["delivered_ml"] == pytest.approx(25.)
        assert state["remaining"]["flask"] == pytest.approx({
            "water_ml": 50., "prepared_tea_fraction": 1.,
            "citric_acid_kit_spoons": 1., "baking_soda_kit_spoons": 1.,
        })


def test_camera_registration_recovers_shifted_fixture(tmp_path):
    from openarms_sim.smartivity_trials import trial

    fixed = trial(1, "spout", position_variation_m=.018)
    corrected = trial(1, "spout", position_variation_m=.018, register=True, evidence_dir=tmp_path)
    assert fixed["delivered_ml"] == 0
    assert "missed" in fixed["fault"]
    assert fixed["evaluator_layout_xy"] == corrected["evaluator_layout_xy"]
    assert corrected["registration"]["status"] == "registered"
    assert corrected["success"] and corrected["placed"]
    assert corrected["delivered_ml"] == pytest.approx(corrected["preloaded"]["beaker"]["water_ml"])
    assert corrected["spilled_ml"] == corrected["collisions"] == corrected["drops"] == 0
    assert (tmp_path / corrected["registration"]["image"]).is_file()
