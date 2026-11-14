"""Fresh raw two-vessel frames adapted to the sole lab evidence contract."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import time

import numpy as np
from bench_vision.perception import observation
from simulation.openarms_sim import two_vessel as fixture

from .mujoco_scene import MujocoSceneService, artifact_name
from .scene import camera_metadata
from .two_vessel_worker import run_worker

PROVENANCE = 'SIMULATED'
METHOD = 'two-vessel-fiducials-rims-water-v1'
SCENE = {'scene_id': fixture.SCENE_ID, 'scene_version': fixture.SCENE_VERSION,
         'control_mode': 'mujoco_kinematic_water_pour'}
LIMITATIONS = [*fixture.LIMITATIONS,
              'Water motion demonstration only; no indicator, pH, or kit recipe is modeled.',
              'Kinematic commanded motion and rendered water appearance do not establish physical grasp, liquid delivery, or spill safety.']
CAMERA = {**camera_metadata(fixture.CAMERA_ID, fixture.CONFIGURATION_ID),
          'calibration_id': fixture.CALIBRATION_ID}
ALIASES = {'a': 'source', 'donor': 'source', 'source_cup': 'source', 'sample_cup': 'source',
           'c': 'receiver', 'cup': 'receiver', 'receiver_cup': 'receiver'}


class TwoVesselSceneService(MujocoSceneService):
    feature_schema = {'readable': {'type': 'boolean'},
                      'receiver_appearance': {'enum': ['dark_base_visible', 'water_appearance']},
                      'sample_cup_station': {'enum': ['A']}, 'sample_cup_held': {'type': 'boolean'}}

    def __init__(self, artifact_dir):
        super().__init__(artifact_dir)
        self._raw = {}
        self._references = {}
        self.variant = 'nominal'  # Offline fault injection only; never part of observation input.

    def generation(self, sid):
        return self._revisions.get(sid, 0)

    async def cancel_captures(self, sid):
        # Invalidate even a capture which finished while cancellation was queued.
        self._advance(sid)
        await super().cancel_captures(sid)

    async def inspect_scene(self, sid, view='primary'):
        # The contract has two view names; this apparatus has exactly one overview.
        # Both names are explicit aliases, never claimed as independent viewpoints.
        if view not in ('primary', 'secondary'):
            raise ValueError('Unknown overview view.')
        if sid in self._active:
            raise RuntimeError('Two-vessel inspection requires the arm to be idle.')
        if sid in self._invalid:
            raise RuntimeError('Prepare a fresh trial after a stopped or failed execution.')
        revision = self.generation(sid)
        capture = asyncio.create_task(run_worker(self.folder(sid), {
            'kind': 'capture', 'state': self._saved_states.get(sid), 'variant': self.variant,
            'generation': revision, 'reference': sid not in self._references}))
        captures = self._captures.setdefault(sid, set())
        captures.add(capture)
        try:
            result = await asyncio.shield(capture)
        except asyncio.CancelledError:
            if not capture.done() and not capture.cancelling():
                capture.cancel()
            await asyncio.gather(capture, return_exceptions=True)
            raise
        finally:
            captures.discard(capture)
            if not captures:
                self._captures.pop(sid, None)
        if revision != self.generation(sid):
            raise RuntimeError('Two-vessel trial changed during capture.')
        if result.get('reference'):
            self._references[sid] = result['reference']['raw_frame']
        reference = self.record_frame(sid, result, view)
        self._latest[sid] = reference
        raw = self._observe_pixels(sid, reference['evidence_id'])
        captured = reference['captured_at']
        return {'evidence_id': reference['evidence_id'], 'provenance': PROVENANCE, 'images': [reference],
                'scene': {**SCENE, **CAMERA, 'frame_id': reference['evidence_id'], 'captured_at': captured,
                          'fresh': True, 'expires_at': captured + 180, 'view': view,
                          'provenance': PROVENANCE, 'width': fixture.WIDTH, 'height': fixture.HEIGHT,
                          'motion_seconds': result['motion_seconds'], 'generation': revision,
                          'fixture_registration_valid': raw['camera_registration'] == 'registered',
                          'available_samples': ['water'], 'recognition_labels': ['source', 'receiver', 'A', 'C'],
                          'object_descriptions': {'source': 'small water donor in dock A',
                                                  'receiver': 'wide clear receiver in dock C'},
                          'observable_features': copy.deepcopy(self.feature_schema),
                          'limitations': [*LIMITATIONS, 'Primary and secondary both name the same overview camera.']}}

    def record_frame(self, sid, message, view='primary'):
        name = message['frame_name']
        if not artifact_name(name, 'png'):
            raise RuntimeError('Invalid two-vessel image name.')
        raw = message['raw_frame']
        path = self.folder(sid) / name
        if (raw['evidence_id'] != path.stem or raw['path'] != str(path.resolve()) or
                raw['captured_at'] != message['captured_at'] or
                raw['sha256'] != hashlib.sha256(path.read_bytes()).hexdigest()):
            raise RuntimeError('Two-vessel image metadata mismatch.')
        reference = {key: raw[key] for key in ('path', 'evidence_id', 'captured_at', 'provenance', 'sha256')}
        self.frames[sid, path.stem] = (reference, view)
        self._raw[sid, path.stem] = copy.deepcopy(raw)
        return copy.deepcopy(reference)

    def _observe_pixels(self, sid, evidence_id):
        if (sid, evidence_id) not in self.frames:
            raise ValueError('Frame is not owned by this session.')
        raw = self._raw[sid, evidence_id]
        # Integrity violations are errors, not a trustworthy UNKNOWN image.
        fixture._pixels(raw)
        return fixture.observe(raw, self._references[sid], now_s=time.time(), generation=self.generation(sid), max_age_s=180)

    async def localize_objects(self, sid, evidence_id, labels):
        result = self._observe_pixels(sid, evidence_id)
        pixels = fixture._pixels(self._raw[sid, evidence_id])
        r, g, b = pixels.transpose(2, 0, 1)
        masks = {'source': (r > 120) & (b > 105) & (r-g > 70) & (b-g > 70),
                 'receiver': (g > 120) & (b > 120) & (g-r > 70) & (b-r > 70)}
        reference, _view = self.frames[sid, evidence_id]
        detections, verified = [], []
        for label in labels:
            name = ALIASES.get(label.lower(), label.lower())
            station = {'source': 'A', 'receiver': 'C'}.get(name)
            found = result['ready'] and name in masks
            box = None
            if found:
                y, x = np.nonzero(masks[name])
                box = [int(x.min()), int(y.min()), int(x.max())+1, int(y.max())+1]
                verified.append(label)
            detection = observation({'object_id': label, 'frame_id': evidence_id,
                                     'timestamp_s': reference['captured_at'], 'provenance': PROVENANCE,
                                     **CAMERA}, METHOD, box=box, reason=None if found else result.get('reason') or 'Unsupported vessel label.')
            detections.append({**detection, **CAMERA, 'vessel_id': name if found else None,
                               'dock_id': station if found else None, 'held': False if found else None,
                               'fixture_registration_valid': result['camera_registration'] == 'registered'})
        return {'evidence_id': evidence_id, 'provenance': PROVENANCE, 'verified_labels': verified,
                'supported_labels': ['source', 'receiver', 'A', 'C'], 'detections': detections, 'method': METHOD,
                'limitations': LIMITATIONS}

    async def observe(self, sid, execution_receipt):
        # Controller status, expected feature, and condition are deliberately ignored.
        frame = await self.inspect_scene(sid, execution_receipt.get('view', 'primary'))
        raw = self._observe_pixels(sid, frame['evidence_id'])
        appearance = raw['receiver_appearance']['state']
        readable = raw['ready'] and appearance in ('dark_base_visible', 'water_appearance')
        features = {'readable': readable}
        if readable:
            features.update(receiver_appearance=appearance, sample_cup_station='A', sample_cup_held=False)
        return {**frame, 'status': 'observed' if readable else 'unknown', 'observer_version': METHOD,
                'features': features, 'pixel_observation': raw,
                'text': ('The simulated receiver shows water appearance; the donor is visible at A.'
                         if readable and appearance == 'water_appearance' else
                         'The simulated receiver shows its dark base; the donor is visible at A.' if readable else
                         'The two-vessel overview is unreadable or unregistered; the outcome is unknown.'),
                'reason': None if readable else raw.get('reason') or 'Receiver appearance is unknown.'}
