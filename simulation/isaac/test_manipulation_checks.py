"""Synthetic evaluator checks. These do not launch or validate Isaac."""
import unittest
from simulation.isaac.manipulation_checks import Sample,TransferCheck

class Checks(unittest.TestCase):
    def setUp(self):
        self.check=TransferCheck((.2,-.1,.0125),(.2,.1,.0125))
        self.t=0.
    def sample(self,position=(.2,.1,.0125),forces=(0.,0.),speed=0.,distance=.15,release=True):
        self.t+=.01
        return self.check.update(Sample(self.t,position,speed,0.,forces,distance,release))
    def lift(self):
        for _ in range(40):self.sample((.2,-.1,.07),(.2,.2),distance=.01,release=False)
    def settle(self):
        for _ in range(120):out=self.sample()
        return out
    def test_valid_transfer_and_live_failure(self):
        self.lift();self.assertTrue(self.settle()['success'])
        self.assertFalse(self.sample(position=(.2,.1,-.3))['success'])
    def test_prepositioned_object_is_not_transfer(self):
        self.assertFalse(self.settle()['success'])
    def test_one_finger_push_is_not_lift(self):
        for _ in range(50):self.sample((.2,-.1,.07),(.2,0.),release=False)
        self.assertFalse(self.settle()['success'])
    def test_fall_below_receiver_rejected(self):
        self.lift()
        for _ in range(120):out=self.sample(position=(.2,.1,-1.))
        self.assertFalse(out['success'])
    def test_unreleased_or_unstable_not_success(self):
        self.lift()
        for _ in range(120):out=self.sample(forces=(.2,.2),distance=.01,release=False)
        self.assertFalse(out['success'])
        for _ in range(120):out=self.sample(speed=.2)
        self.assertFalse(out['success'])
    def test_nan_and_gaps_rejected(self):
        with self.assertRaises(ValueError):self.sample(position=(float('nan'),0.,0.))
        self.sample();self.t+=1.
        with self.assertRaises(ValueError):self.sample()

if __name__=='__main__':unittest.main()
