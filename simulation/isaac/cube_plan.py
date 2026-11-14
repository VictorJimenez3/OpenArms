"""Offline planning for the camera-free SO-101 block candidate; no dynamics proof."""
from dataclasses import asdict
import numpy as np
from scipy.spatial.transform import Rotation


def make_plan(model):
    source = np.array([.23, 0., .01])
    phases = []
    # Triangle-clipped distal collider geometry: fixed inner face x=-7.9mm.
    # A 20mm block needs its center at x=+2.1mm, not the nominal x=0 TCP.
    # Open approach gives another 3.9mm of clearance on that side.
    held_offset = .00210000038147
    model.lower[4] = -1.6034-1e-9
    model.upper[4] = -1.6034+1e-9
    open_jaw, contact_jaw = .3, .058077488073
    closed_jaw = .05  # About 0.586mm of blocked geometric overtravel.
    seed = np.array([-.2736, -.6109, -.0745, 1.5148, -1.6034, open_jaw])

    def solve(xyz, offset, jaw, previous):
        model.tool_transform[:3, 3] = [offset, 0., -.100]
        q, report = model.solve(xyz, [0., 0., -1.], previous)
        if q is None:
            raise RuntimeError(f'Block waypoint IK rejected: {report}')
        q[5] = jaw
        return q, report

    contact_q, _ = solve(source, held_offset, contact_jaw, seed)
    contact_pose = model.fk(contact_q)
    yaw = float(np.arctan2(contact_pose[1, 0], contact_pose[0, 0]))
    orientation = Rotation.from_euler('z', yaw).as_quat()[[3, 0, 1, 2]]
    approach = source-contact_pose[:3, 0]*.004
    approach[2] = .01
    receiver_q, _ = solve([.20, .10, .018], held_offset, closed_jaw, contact_q)
    backoff = np.array([.20, .10, .018])-model.fk(receiver_q)[:3, 0]*.004
    backoff[2] = .018
    initial_q, _ = solve([*approach[:2], .08], held_offset, open_jaw, seed)
    previous = initial_q.copy()
    # Flat receiver floor top=4mm; release at z=18mm leaves a 4mm drop.
    specs = [('approach', 1., [*approach[:2], .08], held_offset, open_jaw),
             ('descend', 3., approach.tolist(), held_offset, open_jaw),
             ('close', 2., source.tolist(), held_offset, closed_jaw),
             ('lift', 3., [.23, 0., .08], held_offset, closed_jaw),
             ('hold', 2., [.23, 0., .08], held_offset, closed_jaw),
             ('carry', 3., [.20, .10, .08], held_offset, closed_jaw),
             ('lower', 3., [.20, .10, .018], held_offset, closed_jaw),
             ('release', 2., backoff.tolist(), held_offset, open_jaw),
             ('retreat', 3., [*backoff[:2], .08], held_offset, open_jaw),
             ('settle', 2., [*backoff[:2], .08], held_offset, open_jaw)]
    start = 0.
    for name, duration, xyz, offset, jaw in specs:
        q, report = solve(xyz, offset, jaw, previous)
        phases.append({'name': name, 'start_s': start, 'end_s': start+duration,
                            'from_rad': previous.tolist(), 'to_rad': q.tolist(),
                            'target_xyz_m': xyz, 'tcp_gripper_m': [offset, 0., -.100],
                            'ik': asdict(report)})
        previous = q.copy()
        start += duration
    duration_s = start
    return initial_q, phases, duration_s, orientation, yaw, contact_jaw, closed_jaw
