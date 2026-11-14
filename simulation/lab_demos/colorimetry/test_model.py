import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("colorimetry_run", Path(__file__).with_name("run.py"))
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def test_beer_lambert_prediction_scales_with_concentration():
    low = demo.beer_lambert(0.30)
    high = demo.beer_lambert(0.52)
    assert high > low
    assert abs(low - 0.6907755) < 1e-6
    assert abs(high - 1.1973442) < 1e-6


def test_rendered_rgb_proxy_reports_more_attenuation_for_darker_sample():
    ref = demo.rgb_sensor_proxy((61, 140, 230))
    unknown = demo.rgb_sensor_proxy((46, 110, 209))
    assert unknown > ref


def test_ik_does_not_move_live_robot_state():
    import numpy as np
    m,d,adr,act,site=demo.build()
    before=d.qpos.copy()
    velocity=d.qvel.copy()
    q,error=demo.ik(m,d,adr,site,np.array([.27,0,.30]),demo.HOME.copy())
    assert error < .008
    np.testing.assert_array_equal(d.qpos,before)
    np.testing.assert_array_equal(d.qvel,velocity)
