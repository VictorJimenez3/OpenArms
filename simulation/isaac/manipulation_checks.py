"""State-based acceptance for one contact-driven cube transfer.

This module evaluates measurements. Its unit tests are synthetic and are not
Isaac execution evidence. Distances are metres, forces newtons, time seconds.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Sample:
    time_s: float
    position: tuple[float, float, float]
    linear_speed: float
    angular_speed: float
    finger_forces: tuple[float, float]
    gripper_distance: float
    release_commanded: bool


class TransferCheck:
    def __init__(self, initial_position, destination, *, lift_m=.03,
                 lift_hold_s=.25, settle_s=1., xy_tolerance_m=.025,
                 z_tolerance_m=.008):
        values = [*initial_position, *destination, lift_m, lift_hold_s,
                  settle_s, xy_tolerance_m, z_tolerance_m]
        if len(initial_position)!=3 or len(destination)!=3 or not all(map(math.isfinite, values)):
            raise ValueError('Expected finite 3D initial and destination positions')
        if min(lift_m,lift_hold_s,settle_s,xy_tolerance_m,z_tolerance_m)<=0:
            raise ValueError('Acceptance thresholds must be positive')
        if math.dist(initial_position[:2],destination[:2]) < 2*xy_tolerance_m:
            raise ValueError('Source and destination acceptance regions overlap')
        self.initial, self.destination = tuple(initial_position), tuple(destination)
        self.lift_m,self.lift_hold_s,self.settle_s=lift_m,lift_hold_s,settle_s
        self.xy_tol,self.z_tol=xy_tolerance_m,z_tolerance_m
        self.last_time=None
        self.lift_since=None
        self.verified_lift=False
        self.settle_since=None
        self.success=False

    def update(self, s: Sample):
        values=[s.time_s,*s.position,s.linear_speed,s.angular_speed,*s.finger_forces,s.gripper_distance]
        if len(s.position)!=3 or len(s.finger_forces)!=2 or not all(map(math.isfinite,values)):
            raise ValueError('Incomplete or nonfinite physics measurement')
        if min(s.linear_speed,s.angular_speed,*s.finger_forces,s.gripper_distance)<0:
            raise ValueError('Speeds, force magnitudes and distance must be nonnegative')
        if self.last_time is not None and (s.time_s<=self.last_time or s.time_s-self.last_time>.05):
            raise ValueError('Samples must be strictly increasing with at most 50 ms gaps')
        self.last_time=s.time_s
        held = min(s.finger_forces)>.05 and s.position[2]>=self.initial[2]+self.lift_m
        self.lift_since = (s.time_s if self.lift_since is None else self.lift_since) if held else None
        if self.lift_since is not None and s.time_s-self.lift_since>=self.lift_hold_s:
            self.verified_lift=True
        in_receiver = (math.dist(s.position[:2],self.destination[:2])<=self.xy_tol
                       and abs(s.position[2]-self.destination[2])<=self.z_tol)
        released = s.release_commanded and max(s.finger_forces)<.02 and s.gripper_distance>.07
        stable = s.linear_speed<.03 and s.angular_speed<.3
        valid=self.verified_lift and in_receiver and released and stable
        self.settle_since=(s.time_s if self.settle_since is None else self.settle_since) if valid else None
        self.success=(self.settle_since is not None and s.time_s-self.settle_since>=self.settle_s)
        return {'verified_lift':self.verified_lift,'in_receiver':in_receiver,
                'released':released,'stable':stable,'success':self.success,
                'settled_s':0. if self.settle_since is None else s.time_s-self.settle_since}
