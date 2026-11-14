"""Qualitative indicator adaptation of the MuJoCo titration apparatus."""

WIDTH, HEIGHT = 1280, 720
CONDITIONS = ('vinegar', 'baking_soda', 'water')
SCENE = {
    'scene_id': 'indicator_ph_metered_dropper',
    'scene_version': 2,
    'source_revision': '16a975e',
    'control_mode': 'mujoco_position_actuator_feedback',
}
LIMITATIONS = (
    'MuJoCo position actuators follow illustrative SO-101 joint targets.',
    'A geometrically engaged paddle releases one modeled dose of prepared solution into the stationary indicator receiver.',
    'Droplet motion and indicator response are qualitative models. No force contact, calibrated pH, or physical execution.',
)
