"""Independent image evidence for a clearly labeled synthetic pH bench.

The environment changes on an executed action. The observer reads saved pixels;
it never derives an outcome from a controller's success flag. This fixture is
software evidence, not calibrated chemistry or a physically qualified robot.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path

import cv2
import numpy as np

from bench_vision.perception import observation

COLORS = {'purple': (170, 70, 135), 'pink': (140, 60, 225), 'blue-green': (170, 150, 50)}
CONDITIONS = {'vinegar': 'pink', 'water': 'purple', 'baking_soda': 'blue-green'}
MARKERS = {'source': (230, 170, 30), 'receiver': (40, 180, 230),
           'bench': (92, 113, 14), 'base': (74, 22, 121)}
ALIASES = {'cup': 'receiver', 'source_cup': 'source', 'sample_cup': 'source',
           'receiver_cup': 'receiver', 'a': 'source', 'b': 'source', 'c': 'receiver'}
DOCKS = {'A': (170, 215), 'B': (360, 215), 'C': (575, 200)}
REGISTRATION_MARKS = {'bench': (75, 420), 'base': (730, 420)}
CAMERA_SETUP = 'synthetic-fixture-v1'
METHOD = 'synthetic-color-marker-v1'


def camera_metadata(camera_id, configuration):
    return {'camera_id': camera_id, 'camera_config_id': configuration, 'calibration_id': configuration,
            'coordinate_frame': 'image_pixels', 'units': 'px', 'clock': 'unix_seconds',
            'geometry_valid': False, 'base_registration_id': None, 'physical_execution': False}


def _near(box, point, tolerance):
    return box and all(abs((box[i] + box[i+2] - 1) / 2 - point[i]) <= tolerance[i] for i in range(2))


def _dock(box):
    return next((name for name, point in DOCKS.items() if _near(box, point, (40, 12))), None)


class SyntheticBench:
    def __init__(self):
        self.color = 'purple'
        self.sample_applied = False
        self.occluded_primary = False
        self.occluded_secondary = False
        self.source_missing = False
        self.receiver_missing = False
        self.vessels_swapped = False
        self.receiver_offset = 0
        self.camera_offset = 0
        self.base_offset = 0
        self.duplicate_receiver_marker = False
        self.stale = False
        self.source_offset = 0
        self.cup_station = 'A'
        self.cup_held = False
        self.sample_condition = 'vinegar'

    def reset(self):
        self.color, self.sample_applied = 'purple', False
        self.cup_station, self.cup_held = 'A', False

    def apply_sample(self, condition):
        # A deliberately qualitative synthetic response table, not a pH model.
        self.color = CONDITIONS[condition]
        self.sample_applied = True

    def render(self, view):
        image = np.full((480, 800, 3), (245, 246, 248), np.uint8)
        cv2.putText(image, 'SIMULATED pH BENCH - not a physical measurement', (20, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, .65, (70, 50, 60), 1, cv2.LINE_AA)
        cv2.line(image, (20, 370), (780, 370), (160, 150, 160), 2)
        for dock, (center, _) in DOCKS.items():
            cv2.putText(image, dock, (center-5, 392), cv2.FONT_HERSHEY_SIMPLEX, .55, (60, 50, 60), 1)
        source_center = DOCKS['C' if self.vessels_swapped else self.cup_station][0] + self.source_offset
        x = source_center - 70
        y = 75 if self.cup_held else 175 if self.vessels_swapped else 190
        if not self.source_missing:
            cv2.rectangle(image, (x, y), (x+140, y+170), (130, 130, 140), 3)
            cv2.rectangle(image, (x+4, y+70), (x+136, y+166), (220, 220, 220), -1)
            cv2.rectangle(image, (x+52, y+10), (x+88, y+40), MARKERS['source'], -1)
        receiver_dock = 'A' if self.vessels_swapped else 'C'
        center, marker_y = DOCKS[receiver_dock]
        center += self.receiver_offset
        if not self.receiver_missing:
            cv2.rectangle(image, (center-95, marker_y-30), (center+95, marker_y+160), (130, 130, 140), 3)
            cv2.rectangle(image, (center-91, marker_y+45), (center+91, marker_y+156), COLORS[self.color], -1)
            cv2.rectangle(image, (center-20, marker_y-15), (center+20, marker_y+15), MARKERS['receiver'], -1)
        for label, (x, y) in REGISTRATION_MARKS.items():
            x += self.base_offset if label == 'base' else 0
            cv2.rectangle(image, (x-8, y-8), (x+8, y+8), MARKERS[label], -1)
        occluded = self.occluded_primary if view == 'primary' else self.occluded_secondary
        if occluded:
            cv2.rectangle(image, (450, 155), (705, 365), (85, 85, 85), -1)
            cv2.putText(image, 'OBSCURED', (490, 270), cv2.FONT_HERSHEY_SIMPLEX, .7, (220, 220, 220), 2)
        if self.duplicate_receiver_marker:
            cv2.rectangle(image, (720, 185), (760, 215), MARKERS['receiver'], -1)
        cv2.putText(image, f'{view} camera | qualitative synthetic fixture', (20, 455),
                    cv2.FONT_HERSHEY_SIMPLEX, .55, (70, 50, 60), 1)
        if self.camera_offset:
            shift = np.float32([[1, 0, self.camera_offset], [0, 1, 0]])
            image = cv2.warpAffine(image, shift, (image.shape[1], image.shape[0]))
        return image


class SceneService:
    """Producer interface consumed by the single Lab runtime."""
    feature_schema = {'readable': {'type': 'boolean'}, 'color': {'enum': list(COLORS)},
                      'sample_cup_held': {'type': 'boolean'}, 'sample_cup_station': {'enum': ['A', 'B']}}

    def __init__(self, artifact_dir):
        self.artifact_dir = Path(artifact_dir).resolve()
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.worlds, self.frames, self._views = {}, {}, {}

    def world(self, sid):
        return self.worlds.setdefault(sid, SyntheticBench())

    async def inspect_scene(self, sid, view='primary'):
        if view not in ('primary', 'secondary'):
            raise ValueError('Unknown camera view.')
        world = self.world(sid)
        captured = time.time() - (120 if world.stale else 0)
        frame_id = uuid.uuid4().hex
        folder = self.artifact_dir/sid
        folder.mkdir(parents=True, exist_ok=True)
        path = folder/(frame_id+'.png')
        image = world.render(view)
        if not cv2.imwrite(str(path), image):
            raise OSError('Could not retain synthetic camera frame.')
        reference = {'path': str(path), 'evidence_id': frame_id, 'captured_at': captured,
                     'provenance': 'SYNTHETIC', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        self.frames[sid, frame_id] = reference
        self._views[sid, frame_id] = view
        return {'evidence_id': frame_id, 'provenance': 'SYNTHETIC', 'images': [reference.copy()],
                'scene': {'frame_id': frame_id, 'captured_at': captured,
                          'fresh': not world.stale, 'view': view, 'provenance': 'SYNTHETIC',
                          **camera_metadata('synthetic-' + view, CAMERA_SETUP),
                          'fixture_registration_valid': self._registered(image),
                          'width': image.shape[1], 'height': image.shape[0],
                          'available_samples': ['vinegar', 'baking_soda', 'water'],
                          'individual_pour_source_condition': world.sample_condition,
                          'recognition_labels': ['source', 'receiver', 'A', 'B', 'C'],
                          'object_descriptions': {'source': 'sample cup', 'receiver': 'indicator receiver',
                                                  'A': 'sample cup at dock A', 'B': 'sample cup at dock B',
                                                  'C': 'indicator receiver at dock C'},
                          'observable_features': self.feature_schema,
                          'limitations': ['Synthetic software fixture; no measured pH or physical geometry.']}}

    def _read(self, sid, evidence_id):
        reference = self.frames.get((sid, evidence_id))
        if not reference:
            raise ValueError('Frame is not owned by this session.')
        path = Path(reference['path'])
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != reference['sha256']:
            raise ValueError('Evidence bytes changed after capture.')
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError('Unreadable scene image.')
        return image, reference

    @staticmethod
    def _marker_box(image, label):
        color = MARKERS.get(label)
        if color is None:
            return None
        mask = cv2.inRange(image, np.array(color, np.uint8), np.array(color, np.uint8))
        count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        components = [stats[index] for index in range(1, count) if stats[index, cv2.CC_STAT_AREA] >= 100]
        if len(components) != 1:
            return None
        x, y, w, h, _ = map(int, components[0])
        return [x, y, x+w, y+h]

    @classmethod
    def _registered(cls, image):
        return all(_near(cls._marker_box(image, label), point, (2, 2))
                   for label, point in REGISTRATION_MARKS.items())

    async def localize_objects(self, sid, evidence_id, labels):
        image, reference = self._read(sid, evidence_id)
        view = self._views[sid, evidence_id]
        registered = self._registered(image)
        detections, verified = [], []
        for label in labels:
            normalized = ALIASES.get(label.lower(), label.lower())
            box = self._marker_box(image, normalized) if normalized in ('source', 'receiver') else None
            dock = _dock(box) if registered else None
            if label.lower() in ('a', 'b', 'c') and label.upper() != dock:
                box = None
            metadata = {'object_id': label, 'frame_id': evidence_id,
                        'timestamp_s': reference['captured_at'], 'provenance': 'SYNTHETIC',
                        **camera_metadata('synthetic-' + view, CAMERA_SETUP)}
            detection = observation(metadata, METHOD, box=box,
                                    reason=None if box else 'Supported fixture marker or dock occupancy not visible.')
            detections.append({**detection, 'vessel_id': normalized if box else None,
                               'dock_id': dock if box else None,
                               'held': bool(registered and box and normalized == 'source' and box[1] < 150),
                               'fixture_registration_valid': registered,
                               'camera_config_id': metadata['camera_config_id'], 'clock': metadata['clock'],
                               'coordinate_frame': metadata['coordinate_frame'], 'units': metadata['units']})
            if box:
                verified.append(label)
        return {'evidence_id': evidence_id, 'provenance': 'SYNTHETIC', 'verified_labels': verified,
                'supported_labels': ['source', 'receiver', 'A', 'B', 'C'],
                'detections': detections, 'method': METHOD,
                'limitations': ['Identity and dock occupancy use synthetic fixture markers. Geometry is pixel-only.']}

    async def observe(self, sid, execution_receipt):
        result = await self._observe_view(sid, execution_receipt.get('view', 'primary'))
        alternate = execution_receipt.get('fallback_view')
        if result['status'] == 'unknown' and alternate and alternate != execution_receipt.get('view', 'primary'):
            fallback = await self._observe_view(sid, alternate)
            fallback['attempts'] = [result['evidence_id'], fallback['evidence_id']]
            fallback['images'] = result['images'] + fallback['images']
            return fallback
        return result

    async def _observe_view(self, sid, view):
        # The only execution metadata used is camera selection. Success is ignored.
        frame = await self.inspect_scene(sid, view)
        image, _ = self._read(sid, frame['evidence_id'])
        marker = self._marker_box(image, 'receiver')
        source = self._marker_box(image, 'source')
        features = {'readable': False}
        if frame['scene']['fresh'] and frame['scene']['fixture_registration_valid']:
            dock = _dock(source)
            if source and source[1] < 150:
                features['sample_cup_held'] = True
            elif dock in ('A', 'B'):
                features.update(sample_cup_held=False, sample_cup_station=dock)
        if (_dock(marker) == 'C' and frame['scene']['fresh'] and
                frame['scene']['fixture_registration_valid']):
            # Read a region relative to the detected fixture marker, not controller state.
            cx, cy = (marker[0]+marker[2])//2, (marker[1]+marker[3])//2
            region = image[cy+65:cy+110, cx-35:cx+35]
            if region.size:
                median = np.median(region, axis=(0, 1))
                distances = {name: float(np.linalg.norm(median-np.array(color))) for name, color in COLORS.items()}
                color = min(distances, key=distances.get)
                if distances[color] < 25:
                    features.update(readable=True, color=color)
        return {**frame, 'status': 'observed' if features['readable'] else 'unknown',
                'observer_version': 'fixture-pixel-color-v1', 'features': features,
                'text': ('In the simulation, the receiver appears '+features['color']+'. This is not a measured pH.'
                         if features['readable'] else 'The simulated receiver is unreadable or the frame is stale.'),
                'reason': None if features['readable'] else 'missing, obscured, stale or unrecognized receiver'}
