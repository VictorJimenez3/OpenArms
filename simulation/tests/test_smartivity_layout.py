from contextlib import closing

import numpy as np
import pytest

from openarms_sim.config import load_bench
from openarms_sim.smartivity_layout import demo_layout
from openarms_sim.smartivity_world import World


def test_nominal_layout_uses_main_demo_stations():
    layout = demo_layout()
    bench = load_bench("demo")
    assert layout.donor_arm_m == bench.stations["A"].pos
    assert layout.receiver_arm_m == bench.stations["C"].pos
    assert layout.table_size_m == bench.table_size
    assert layout.wrist_roll_deg == bench.wrist_roll_deg
    assert layout.lift_m == bench.lift


def test_seeded_layout_is_reproducible_and_moves_both_vessels():
    nominal = demo_layout()
    layout = demo_layout(layout_seed=42, spread_mm=6.)
    assert layout == demo_layout(layout_seed=42, spread_mm=6.)
    assert layout != demo_layout(layout_seed=17, spread_mm=6.)
    for current, original in ((layout.donor_ruler_cm, nominal.donor_ruler_cm),
                              (layout.receiver_ruler_cm, nominal.receiver_ruler_cm)):
        displacement = np.abs(np.array(current) - original)
        assert np.any(displacement > 0)
        assert np.all(displacement <= .6 + 1e-12)


def test_layout_rejects_invalid_seed_and_spread():
    with pytest.raises(ValueError, match="seed"):
        demo_layout(layout_seed=-1)
    with pytest.raises(ValueError, match="spread"):
        demo_layout(spread_mm=float("nan"))


def test_transfer_replans_for_generated_demo_stations():
    layout = demo_layout(18, 15)
    with closing(World(layout=layout)) as world:
        assert tuple(world.dock[:2]) == layout.donor_arm_m
        assert tuple(world.receiver[:2]) == layout.receiver_arm_m
        for action in ("pick", "pour", "return_cup", "home"):
            world.start(action)
            deadline = world.sim_time + 20
            while world.busy and world.sim_time < deadline:
                world.tick()
            assert not world.busy
            assert world.proprioception()["fault"] is None
        result = world.evaluate()
        assert result["success"]
        assert result["spilled_ml"] == result["collisions"] == result["drops"] == 0
