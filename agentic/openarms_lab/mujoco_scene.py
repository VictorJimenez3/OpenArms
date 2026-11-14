"""Timestamped evidence and pixel-only observation of the MuJoCo liquid fixture."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import re
from pathlib import Path

import cv2
import numpy as np

from bench_vision.perception import observation

from .mujoco_process import run_worker

PROVENANCE = 'SIMULATED'
CONDITIONS = ('vinegar', 'baking_soda', 'water')
LIMITATIONS = (
    'The SO-101 uses placeholder poses and an unmeasured joint map.',
    'The arm moves kinematically and holds cups by attachment. Liquid and color use a qualitative rule table.',
    'This simulation supplies no measured pH, physical result, or calibration.',
)
METHOD = 'mujoco-liquid-fixture-pixels-v1'
CAMERA_SETUP = 'mujoco-liquid-v1'
# Regions around the fixed station marks in the two 640×480 camera views.
REGIONS = {
    'primary': {'source': (425, 280, 475, 312), 'receiver': (229, 304, 313, 351)},
    'secondary': {'source': (419, 249, 471, 301), 'receiver': (237, 278, 315, 354)},
}
# Hue bounds and saturation floors measured in the two rendered views.
HUES = {
    'primary': {'pink': (151, 179, 45), 'purple': (123, 150, 45), 'blue': (99, 121, 45)},
    'secondary': {'pink': (149, 179, 25), 'purple': (123, 148, 45), 'blue': (99, 121, 45)},
}
ALIASES = {'a': 'source', 'source_cup': 'source', 'sample_cup': 'source',
           'c': 'receiver', 'cup': 'receiver', 'receiver_cup': 'receiver'}


def artifact_name(name, extension):
    return isinstance(name, str) and re.fullmatch(r'[0-9a-f]{32}\.' + extension, name) is not None


def _fixture_box(hsv, view, label):
    if label not in REGIONS[view]:
        return None
    x, y, x2, y2 = REGIONS[view][label]
    hue, saturation, value = np.moveaxis(hsv[y:y2, x:x2], -1, 0)
    low, high = (96, 115) if label == 'source' else (15, 35)
    ys, xs = np.nonzero((hue >= low) & (hue <= high) & (saturation >= 145) & (value >= 150))
    if len(xs) < 65:
        return None
    return [x + int(xs.min()), y + int(ys.min()), x + int(xs.max()) + 1, y + int(ys.max()) + 1]


def _receiver_color(hsv, marker, view):
    left, _, right, bottom = marker
    # Read the pigment above and inside the receiver ring, away from the orange rim.
    center = (left + right) // 2
    hue, saturation, value = np.moveaxis(hsv[bottom-36:bottom-20, center-10:center+10], -1, 0)
    for name, (low, high, saturation_min) in HUES[view].items():
        matches = (hue >= low) & (hue <= high) & (saturation >= saturation_min) & (value >= 105)
        if np.mean(matches) >= .7:
            return name
    return None


class MujocoSceneService:
    feature_schema = {'readable': {'type': 'boolean'}, 'color': {'enum': list(HUES['primary'])}}

    def __init__(self, artifact_dir):
        self.artifact_dir = Path(artifact_dir).resolve()
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.frames = {}
        self._contents = {}
        self._captures = {}
        self._active = set()
        self._invalid = set()
        self._latest = {}
        self._revisions = {}

    def folder(self, sid):
        if not isinstance(sid, str) or not re.fullmatch(r'[0-9A-Za-z_-]{1,128}', sid):
            raise ValueError('Invalid MuJoCo session ID.')
        folder = self.artifact_dir / sid
        folder.mkdir(exist_ok=True)
        return folder

    def reset(self, sid):
        self._advance(sid)
        self._contents.pop(sid, None)
        self._latest.pop(sid, None)
        self._invalid.discard(sid)

    def latest_frame(self, sid):
        return self._latest.get(sid)

    def _advance(self, sid):
        self._revisions[sid] = self._revisions.get(sid, 0) + 1

    def begin(self, sid):
        self._advance(sid)
        self._active.add(sid)

    def finish(self, sid, contents=None):
        if contents is not None:
            self._contents[sid] = contents
        else:
            self._invalid.add(sid)
        self._active.discard(sid)

    async def cancel_captures(self, sid):
        captures = tuple(self._captures.get(sid, ()))
        for capture in captures:
            if not capture.done() and not capture.cancelling():
                capture.cancel()
        if captures:
            await asyncio.gather(*captures, return_exceptions=True)

    async def inspect_scene(self, sid, view='primary'):
        if view not in REGIONS:
            raise ValueError('Unknown MuJoCo camera view.')
        if sid in self._active:
            raise RuntimeError('MuJoCo inspection requires the arm to be idle.')
        if sid in self._invalid:
            raise RuntimeError('Prepare a fresh trial after a failed or stopped MuJoCo execution.')
        folder = self.folder(sid)
        revision = self._revisions.get(sid, 0)
        capture = asyncio.create_task(run_worker(folder, {
            'kind': 'capture', 'view': view, 'contents': self._contents.get(sid, {}),
        }))
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
        if revision != self._revisions.get(sid, 0):
            raise RuntimeError('MuJoCo trial changed during capture.')
        reference = self.record_frame(sid, result, view)
        captured, evidence_id = reference['captured_at'], reference['evidence_id']
        self._latest[sid] = reference
        return {'evidence_id': evidence_id, 'provenance': PROVENANCE, 'images': [reference],
                'scene': {'frame_id': evidence_id, 'captured_at': captured, 'clock': 'unix_seconds',
                          'fresh': True, 'expires_at': captured + 180, 'view': view, 'provenance': PROVENANCE,
                          'calibration_id': CAMERA_SETUP, 'coordinate_frame': 'image_pixels',
                          'geometry_valid': False, 'physical_execution': False,
                          'available_samples': list(CONDITIONS),
                          'recognition_labels': ['source', 'receiver'],
                          'object_descriptions': {'source': 'station A source fixture',
                                                  'receiver': 'station C cabbage indicator receiver'},
                          'observable_features': copy.deepcopy(self.feature_schema),
                          'limitations': [*LIMITATIONS, 'Recognition is limited to the rendered fixture and two fixed views.']}}

    def record_frame(self, sid, message, view='primary'):
        name = message['frame_name']
        if not artifact_name(name, 'png'):
            raise RuntimeError('MuJoCo worker returned an invalid image name.')
        evidence_id = name.removesuffix('.png')
        path = self.folder(sid) / name
        reference = {'path': str(path), 'evidence_id': evidence_id, 'captured_at': message['captured_at'],
                     'provenance': PROVENANCE, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        self.frames[sid, evidence_id] = (reference, view)
        return copy.deepcopy(reference)

    def _read(self, sid, evidence_id):
        record = self.frames.get((sid, evidence_id))
        if record is None:
            raise ValueError('Frame is not owned by this session.')
        reference, view = record
        data = Path(reference['path']).read_bytes()
        if hashlib.sha256(data).hexdigest() != reference['sha256']:
            raise ValueError('Evidence bytes changed after capture.')
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.shape != (480, 640, 3):
            raise ValueError('Unreadable MuJoCo scene image.')
        return cv2.cvtColor(image, cv2.COLOR_BGR2HSV), reference, view

    async def localize_objects(self, sid, evidence_id, labels):
        hsv, reference, view = self._read(sid, evidence_id)
        detections, verified = [], []
        for label in labels:
            normalized = ALIASES.get(label.lower(), label.lower())
            box = _fixture_box(hsv, view, normalized)
            if box:
                verified.append(label)
            detections.append(observation({
                'object_id': label, 'camera_id': 'mujoco-' + view,
                'frame_id': evidence_id, 'timestamp_s': reference['captured_at'],
                'calibration_id': CAMERA_SETUP, 'provenance': PROVENANCE,
            }, METHOD, box=box, reason=None if box else 'Supported fixture mark is not visible.'))
        return {'evidence_id': evidence_id, 'provenance': PROVENANCE, 'verified_labels': verified,
                'supported_labels': ['source', 'receiver'], 'detections': detections, 'method': METHOD,
                'limitations': ['Color mark localization in fixed MuJoCo views provides image coordinates.']}

    async def observe(self, sid, execution_receipt):
        # Only view selection is taken from execution metadata.
        view = execution_receipt.get('view', 'primary')
        result = await self._observe_view(sid, view)
        alternate = execution_receipt.get('fallback_view')
        if result['status'] == 'unknown' and alternate and alternate != view:
            fallback = await self._observe_view(sid, alternate)
            fallback['attempts'] = [result['evidence_id'], fallback['evidence_id']]
            fallback['images'] = result['images'] + fallback['images']
            return fallback
        return result

    async def _observe_view(self, sid, view):
        frame = await self.inspect_scene(sid, view)
        color = None
        try:
            hsv, _, _ = self._read(sid, frame['evidence_id'])
            marker = _fixture_box(hsv, view, 'receiver')
            if marker:
                color = _receiver_color(hsv, marker, view)
        except (ValueError, OSError, cv2.error):
            pass  # An unreadable capture is independent UNKNOWN evidence.
        features = {'readable': bool(color)}
        if color:
            features['color'] = color
        return {**frame, 'status': 'observed' if color else 'unknown',
                'observer_version': METHOD, 'features': features,
                'text': (f'The rendered MuJoCo receiver appears {color}. This is a qualitative simulated color.'
                         if color else 'The rendered MuJoCo receiver color is unknown.'),
                'reason': None if color else 'Receiver pixels are missing, obscured, or unrecognized.'}
