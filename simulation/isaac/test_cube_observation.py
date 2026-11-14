"""Mocked sensor regression checks, never Isaac or manipulation evidence."""
import sys
import json
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
# Only simulator import boundaries are replaced. Tests execute the actual
# CubeTrial.observe method with deliberate measurement fixtures.
modules = {}
for name, attrs in {
    'isaacsim.core.api.objects': ['DynamicCuboid', 'FixedCuboid'],
    'isaacsim.core.api.materials': ['PhysicsMaterial'],
    'isaacsim.core.prims': ['SingleRigidPrim', 'RigidPrim'],
}.items():
    module = types.ModuleType(name)
    for attr in attrs:
        setattr(module, attr, object)
    modules[name] = module
with patch.dict(sys.modules, modules):
    from cube_scene import CubeTrial
from manipulation_checks import TransferCheck


class Body:
    def __init__(self, position, quaternion=(1., 0., 0., 0.)):
        self.position, self.quaternion = np.array(position), np.array(quaternion)
    def get_world_pose(self): return self.position, self.quaternion
    def get_linear_velocity(self): return np.zeros(3)
    def get_angular_velocity(self): return np.zeros(3)


class CubeObservationTests(unittest.TestCase):
    @staticmethod
    def empty_contact_data(**_):
        return (np.zeros((1, 1)), np.zeros((1, 3)), np.zeros((1, 3)),
                np.zeros((1, 1)), np.zeros((1, 3)), np.zeros((1, 3)))

    def trial(self, quaternion):
        trial = CubeTrial.__new__(CubeTrial)
        trial.model = types.SimpleNamespace(gripper_path='gripper', base_path='base')
        trial.cube = Body((.2, .1, .014), quaternion)
        trial.floor = Body((.2, .1, .002))
        trial.bodies = {'gripper': Body((.2, .1, .180)), 'base': Body((0., 0., 0.))}
        trial.body_initial = {'base': np.zeros(3), 'receiver': trial.floor.position.copy(),
                              'base_quat': np.array([1., 0., 0., 0.]),
                              'receiver_quat': np.array([1., 0., 0., 0.])}
        trial.contact = types.SimpleNamespace(get_contact_force_matrix=lambda **_: np.array(
            [[[0., 0., 0.], [0., 0., 0.], [0., 0., .0981]]]),
            get_contact_force_data=self.empty_contact_data)
        trial.check = TransferCheck((.23, 0., .01), (.2, .1, .014), retreat_m=.05,
                                    max_linear_speed=.01, max_angular_speed=.1)
        trial.check.verified_lift = True  # Deliberate prior measurement fixture.
        trial.phase, trial.failure, trial.lost_since = 'settle', None, None
        return trial

    def test_tilted_cube_is_not_replaced_by_receiver_orientation(self):
        quaternion = [2**-.5, 2**-.5, 0., 0.]
        trial = self.trial(quaternion)
        for step in range(121): result = trial.observe(step/100)
        np.testing.assert_allclose(result['object_quaternion_wxyz'], quaternion)
        self.assertFalse(result['upright'])
        self.assertFalse(result['success'])

    def test_nominal_retreat_and_success_fields_agree(self):
        trial = self.trial([1., 0., 0., 0.])
        for step in range(121): result = trial.observe(step/100)
        self.assertTrue(.05 < result['gripper_distance_m'] < .07)
        self.assertTrue(result['released'])
        self.assertTrue(result['success'])
        self.assertGreaterEqual(result['settled_s'], 1.)

    def test_numpy_measurements_serialize_during_carry_and_settle(self):
        trial = self.trial([1., 0., 0., 0.])
        trial.phase = 'carry'
        trial.contact = types.SimpleNamespace(get_contact_force_matrix=lambda **_: np.array(
            [[[0., 2., 0.], [0., -2., 0.], [0., 0., 0.]]], dtype=np.float32),
            get_contact_force_data=self.empty_contact_data)
        trial.cube.position = np.array([.2104272, .0831413, .0802642], dtype=np.float32)
        json.dumps(trial.observe(13.191667), allow_nan=False)
        trial = self.trial([1., 0., 0., 0.])
        json.dumps(trial.observe(24.), allow_nan=False)


if __name__ == '__main__': unittest.main()
