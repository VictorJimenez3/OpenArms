"""Lab adapter for the openarms_sim `demo` bench (ruler bench matched to a recorded real pour).

Runs a complete pour or separate pick, pour and return actions on the same
simulated bench. The existing lab owns consent, STOP and evidence.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import time

import numpy as np
from bench_vision.perception import observation
from simulation.openarms_sim.render import OVERVIEW_HEIGHT, OVERVIEW_WIDTH

from .contracts import PRIMITIVE_SCHEMAS
from .demo_bench_worker import (CONFIGURATION_ID, CAMERA_ID, EXPERIMENTS_FILE, SETUP, experiment_contents,
                                experiment_name, experiments, run_worker)
from .scene import camera_metadata
from .skills import compute_skill_hash
from .two_vessel_backend import TwoVesselBackend
from .two_vessel_evaluation import TwoVesselSkillEvaluator
from .two_vessel_scene import TwoVesselSceneService
from . import two_vessel_scene

OPERATION = 'add_sample'
ACTIONS = {
    'pick': 'Pick up the small beaker from A and hold it above the bench.',
    'pour': 'Pour the held beaker into the receiver at C and keep holding it.',
    'return_cup': 'Put the held beaker back on mark A and park the arm.',
    OPERATION: 'Pick up the beaker from A, pour into C, put the beaker back on A and park the arm.',
}
ACTION_CHECKS = {
    'pick': [{'feature': 'sample_cup_held', 'expected': True}],
    'pour': [{'feature': 'sample_cup_held', 'expected': True}, {'feature': 'donor_appearance', 'expected': 'empty'}],
    'return_cup': [{'feature': 'sample_cup_held', 'expected': False}, {'feature': 'sample_cup_station', 'expected': 'A'}],
    OPERATION: [{'feature': 'donor_appearance', 'expected': 'empty'}],
}
PROVENANCE = 'SIMULATED'
METHOD = 'demo-bench-vessel-marks-and-appearance-v5'
SCENE = {'scene_id': 'openarms_sim_demo', 'scene_version': 3, 'setup': SETUP,
         'control_mode': 'mujoco_kinematic_beaker_actions'}
CAMERA = {**camera_metadata(CAMERA_ID, CONFIGURATION_ID), 'calibration_id': CONFIGURATION_ID}
LIMITATIONS = [
    'Poses are solved by the simulation from bench.yaml, matched to one recorded real pour; joint_map.yaml is unmeasured.',
    'Liquid is drawn, not simulated: colours come from chemistry.yaml, so receiver colour is not a chemistry result.',
    'The rendered overview tracks the beaker mark and reads vessel appearance; no measured volume.',
    'No physical grasp, liquid delivery or spill safety is established. Physical dispatch is disabled.',
]


def experiment_metadata(name):
    """One Smartivity experiment on the unchanged demo bench; the id stays the bench's own capability."""
    config = experiments()[name]
    base = {'id': 'demo_bench_pour', 'variant': name, 'mode': 'SIMULATED',
            'question': 'What would you like the arm to do with the beaker?'}
    if name == 'volcano':
        return {**base, 'title': 'Demo bench pour — simulation',
                'description': 'openarms_sim demo setup: citric acid beaker at A, volcano mix container at C.'}
    return {**base, 'title': f"{config['title']} — demo bench simulation",
            'description': f"openarms_sim demo setup, Smartivity {config['title']}: {config['preparation']}",
            'source': config['source']}


VARIANT = experiment_name()
EXPERIMENT = experiment_metadata(VARIANT)
CONDITIONS = [{'id': 'prepared', 'title': 'Prepared demo bench contents'}]
# Expected skill outcome: the donor is seen empty again at A; receiver colour is pre-set by the mix.
OUTCOME = {'donor_appearance': 'empty', 'sample_cup_station': 'A', 'sample_cup_held': False}


def execution_scope():
    import mujoco
    import numpy
    import PIL
    import pydantic
    root = Path(__file__).resolve().parents[2]
    sources = [root/'agentic/openarms_lab'/name for name in (
        'demo_bench.py', 'demo_bench_worker.py', 'two_vessel_backend.py', 'two_vessel_scene.py', 'two_vessel_worker.py',
        'two_vessel_evaluation.py', 'mujoco_backend.py', 'mujoco_scene.py', 'scene.py', 'contracts.py', 'skills.py',
        'task_loop.py', 'runtime.py', 'evaluation.py', 'store.py', 'request_intent.py', 'conversation.py')]
    sources += sorted((root/'simulation/openarms_sim').glob('*.py'))
    sources += [root/'simulation/config'/name for name in (
        f'setups/{SETUP}/bench.yaml', f'setups/{SETUP}/poses.json', 'joint_map.yaml', 'chemistry.yaml')]
    sources.append(EXPERIMENTS_FILE)
    identity = {'experiment': experiment_metadata(experiment_name()), 'versions': {'mujoco': mujoco.__version__, 'numpy': numpy.__version__,
                                                       'pillow': PIL.__version__, 'pydantic': pydantic.__version__},
                'sources': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    return 'demo-bench-' + compute_skill_hash(identity)[:16]


# The empty clear beaker as the overview camera renders it (identical in every experiment).
EMPTY_GLASS = np.array([127, 186, 237])
RECEIVER_COLOUR_TOLERANCE = 45
RECEIVER_COLOUR_MARGIN = 15


def _masks(pixels):
    r, g, b = pixels.transpose(2, 0, 1)
    low = np.zeros_like(r, bool)
    low[OVERVIEW_HEIGHT * 54 // 100:] = True  # Below the arm, where the station markers lie.
    return {'marker_a': (b > 180) & (r < 120) & low,
            'marker_c': (r > 200) & (g > 130) & (g < 200) & (b < 80) & low}


def _centre(mask, minimum=60):
    y, x = np.nonzero(mask)
    return None if len(x) < minimum else np.array([x.mean(), y.mean()])


def receiver_palette():
    """Indicator-scale and individual dye appearances used by the demo experiments."""
    from simulation.openarms_sim.config import load_chemistry_config
    chemistry = load_chemistry_config()
    palette = {row['label'] + '_liquid': tuple(row['color']) for row in chemistry['indicator_scale']}
    for substance in chemistry['substances'].values():
        if substance.get('kind') == 'dye':
            palette.setdefault(substance['hue'] + '_liquid', tuple(substance['color']))
    return palette


def _prepared_receiver_colour():
    from simulation.openarms_sim.chemistry import load_model
    from simulation.openarms_sim.config import load_bench, load_chemistry_config
    contents = (experiment_contents() or {}).get('C') or load_bench(SETUP).stations['C'].contents
    return np.array(load_model(load_chemistry_config()).predict(contents).color) * 255


def _coloured(region):
    region = region.astype(int)
    return region.max(2) - region.min(2) > 40


def anchors(reference):
    """Station anchors from the nominal frame taken at reset; later frames are read at these pixels.

    The reset frame also calibrates how this camera renders colours: the prepared receiver's known
    colour against its rendered pixels gives one white-blend factor, and the full donor gives its
    filled appearance. Later readings never see the plan, receipt or predicted outcome.
    """
    masks = _masks(reference)
    a, c = _centre(masks['marker_a']), _centre(masks['marker_c'])
    if a is None or c is None:
        raise ValueError('The reference frame does not show both station markers.')
    (ax, ay), (cx, cy) = np.rint(a).astype(int), np.rint(c).astype(int)
    region = reference[cy-30:cy+20, cx-45:cx+45].astype(int)
    receiver = _coloured(region) & ~masks['marker_c'][cy-30:cy+20, cx-45:cx+45]
    if receiver.sum() < 60:
        raise ValueError('The reference frame does not show a readable receiver.')
    rendered = region[receiver].mean(0)
    prepared = _prepared_receiver_colour()
    gap = 255 - prepared
    blend = float(np.clip(((255 - rendered) * gap).sum() / max((gap * gap).sum(), 1e-6), 0.05, 1.0))
    if (not np.isfinite(blend) or
            np.linalg.norm(rendered - (255 - blend * gap)) > RECEIVER_COLOUR_TOLERANCE):
        raise ValueError('The reference frame cannot calibrate the receiver appearance.')
    return {'A': a, 'C': c, 'receiver_count': int(receiver.sum()), 'receiver_rgb': rendered, 'blend': blend,
            'donor_rgb': reference[ay-10:ay, ax-6:ax+6].reshape(-1, 3).astype(int).mean(0)}


def _donor_marker(pixels):
    r, g, b = pixels.transpose(2, 0, 1).astype(int)
    return _centre((r > 150) & (b > 150) & (g < 120) & (r - g > 80) & (b - g > 80), minimum=12)


def _held_donor_reading(pixels, marker):
    # The mark travels with the beaker. The nearby interior patch stays clear of it.
    x, y = np.rint(marker).astype(int) + (9, 9)
    fill = pixels[y-3:y+4, x-3:x+4]
    if fill.shape != (7, 7, 3):
        return 'unknown'
    r, g, b = fill.transpose(2, 0, 1).astype(int)
    if ((r >= 155) & (r < 235) & (g - b >= 7)).mean() >= .7:
        return 'liquid_visible'
    if ((r >= 140) & (r < 240) & (b - r >= 12) & (b >= g)).mean() >= .7:
        return 'empty'
    return 'unknown'


def read_pixels(pixels, anchor, tolerance_px=6):
    """Pixel-only reading of one overview frame. Never sees the receipt, plan or prediction."""
    masks = _masks(pixels)
    result = {'status': 'unknown', 'ready': False, 'camera_registration': 'unknown', 'method': METHOD,
              'provenance': PROVENANCE, 'donor': 'unknown', 'receiver': 'unknown', 'reason': None}
    centres = {station: _centre(masks['marker_' + station.lower()]) for station in ('A', 'C')}
    drift = {station: None if centre is None else float(np.linalg.norm(centre - anchor[station]))
             for station, centre in centres.items()}
    result['marker_centres_px'] = {station: centre.tolist() for station, centre in centres.items() if centre is not None}
    result['marker_drift_px'] = drift
    if any(d is None or d > tolerance_px for d in drift.values()):
        result.update(camera_registration='shifted', reason='Station markers moved or are hidden; camera registration failed.')
        return result
    result['camera_registration'] = 'registered'
    ax, ay = np.rint(anchor['A']).astype(int)
    cx, cy = np.rint(anchor['C']).astype(int)
    frame = pixels.astype(int)
    at_c = frame[cy-30:cy+20, cx-45:cx+45]
    receiver = _coloured(at_c) & ~masks['marker_c'][cy-30:cy+20, cx-45:cx+45]
    at_a = frame[ay-30:ay+20, ax-45:ax+45]
    receiver_at_a = (np.linalg.norm(at_a - anchor['receiver_rgb'], axis=2) < 40) & _coloured(at_a)
    if receiver_at_a.sum() > 50 or receiver.sum() < 0.6 * anchor['receiver_count']:
        result['reason'] = 'The receiver is not where station C expects it.'
        return result
    seen = at_c[receiver].mean(0)
    rendered = {label: 255 - anchor['blend'] * (255 - np.array(colour) * 255) for label, colour in receiver_palette().items()}
    fits = sorted((float(np.linalg.norm(colour - seen)), label) for label, colour in rendered.items())
    (distance, receiver_label), (alternate, _) = fits[:2]
    # Nominal before/after renders are within 32 RGB units and at least 30 units from the next match.
    if (not np.isfinite(distance) or distance > RECEIVER_COLOUR_TOLERANCE or
            alternate - distance < RECEIVER_COLOUR_MARGIN):
        result['reason'] = 'The receiver appearance does not match a known simulated colour.'
        return result
    result['receiver'] = receiver_label
    marker = _donor_marker(pixels)
    if marker is None:
        result['reason'] = 'The small beaker mark is missing or obscured.'
        return result
    # In this fixed camera setup the rest region is directly above A. The other
    # recognized endpoints are the two verified upright poses above A and C.
    rest = centres['A'] + (-11, -19)
    lifted = centres['A'] + (-13, -90)
    over_receiver = centres['C'] + (-36, -55)
    if min(np.linalg.norm(marker - lifted), np.linalg.norm(marker - over_receiver)) <= 10:
        donor = _held_donor_reading(pixels, marker)
        if donor == 'unknown':
            result['reason'] = 'The beaker mark is visible but the beaker itself is unreadable.'
            return result
        x, y = np.rint(marker).astype(int)
        result.update(status='ok', ready=True, held=True, donor=donor,
                      donor_box=[int(x - 7), int(y - 25), int(x + 31), int(y + 28)])
        return result
    if np.linalg.norm(marker - rest) > 10:
        result['reason'] = 'The small beaker is outside the observable dock and gripper positions.'
        return result
    wall = (slice(ay-24, ay-17), slice(ax-6, ax+6))
    r, b = frame[..., 0], frame[..., 2]
    # The beaker's upper wall reads near-white over a pale fill, or glass-blue over a coloured one.
    has_wall = (((r[wall] > 210) & (r[wall] < 245) & (b[wall] > r[wall])).mean() >= .5 or
                float(np.linalg.norm(frame[wall].reshape(-1, 3).mean(0) - EMPTY_GLASS)) < 40)
    fill = frame[ay-10:ay, ax-6:ax+6].reshape(-1, 3).mean(0)
    to_full, to_glass = float(np.linalg.norm(fill - anchor['donor_rgb'])), float(np.linalg.norm(fill - EMPTY_GLASS))
    if has_wall and to_full < to_glass and to_full < 30:
        result['donor'] = 'liquid_visible'
    elif has_wall and to_glass < to_full and to_glass < 30:
        result['donor'] = 'empty'
    else:
        result['reason'] = 'The beaker at A is missing, hidden or unreadable.'
        return result
    result.update(status='ok', ready=True, held=False,
                  donor_box=[int(ax - 17), int(ay - 46), int(ax + 18), int(ay + 9)])
    return result


class DemoBenchSceneService(TwoVesselSceneService):
    feature_schema = {'readable': {'type': 'boolean'},
                      'donor_appearance': {'enum': ['liquid_visible', 'empty']},
                      'receiver_appearance': {'enum': sorted(receiver_palette())},
                      'sample_cup_station': {'enum': ['A']}, 'sample_cup_held': {'type': 'boolean'}}
    worker = staticmethod(run_worker)

    def continuation(self, sid):
        return self._saved_states.get(sid)

    async def inspect_scene(self, sid, view='primary'):
        result = await super().inspect_scene(sid, view)
        # Replace the water fixture's identity with this setup's; frame checks above stay shared.
        result['scene'].update({**SCENE, **CAMERA, 'width': OVERVIEW_WIDTH, 'height': OVERVIEW_HEIGHT,
                                'available_samples': ['prepared'],
                                'object_descriptions': dict(experiments()[experiment_name()]['descriptions']),
                                'observable_features': copy.deepcopy(self.feature_schema),
                                'limitations': [*LIMITATIONS, 'Primary and secondary both name the same overview camera.']})
        for key in two_vessel_scene.SCENE:
            if key not in SCENE:
                result['scene'].pop(key, None)
        return result

    def _observe_pixels(self, sid, evidence_id):
        if (sid, evidence_id) not in self.frames:
            raise ValueError('Frame is not owned by this session.')
        raw = self._raw[sid, evidence_id]
        if (raw.get('camera_id'), raw.get('configuration_id'), raw.get('generation')) != (CAMERA_ID, CONFIGURATION_ID, self.generation(sid)):
            return {'ready': False, 'camera_registration': 'unknown', 'reason': 'Frame is from another camera or setup generation.'}
        if not 0 <= time.time() - raw['captured_at'] <= 180:
            return {'ready': False, 'camera_registration': 'unknown', 'reason': 'Frame is stale or future-dated.'}
        reference = self._references[sid]
        try:
            anchor = anchors(two_vessel_scene.fixture._pixels(reference))
        except ValueError as exc:
            return {'ready': False, 'camera_registration': 'unknown', 'reason': str(exc)}
        return read_pixels(two_vessel_scene.fixture._pixels(raw), anchor)

    async def localize_objects(self, sid, evidence_id, labels):
        result = self._observe_pixels(sid, evidence_id)
        reference, _view = self.frames[sid, evidence_id]
        centres = result.get('marker_centres_px', {})
        cx, cy = centres.get('C', (0, 0))
        boxes = {'source': result.get('donor_box'),
                 'receiver': [int(cx - 45), int(cy - 30), int(cx + 46), int(cy + 21)] if result['ready'] else None}
        aliases = {**two_vessel_scene.ALIASES, 'beaker': 'source', 'container': 'receiver'}
        detections, verified = [], []
        for label in labels:
            name = aliases.get(label.lower(), label.lower())
            box = boxes.get(name)
            found = box is not None
            held = (name == 'source' and result['held']) if found else None
            if found:
                verified.append(label)
            detection = observation({'object_id': label, 'frame_id': evidence_id, 'timestamp_s': reference['captured_at'],
                                     'provenance': PROVENANCE, **CAMERA}, METHOD, box=box,
                                    reason=None if found else result.get('reason') or 'Unsupported vessel label.')
            detections.append({**detection, **CAMERA, 'vessel_id': name if found else None,
                               'dock_id': {'source': 'A', 'receiver': 'C'}[name] if found and not held else None,
                               'held': held,
                               'fixture_registration_valid': result['camera_registration'] == 'registered'})
        return {'evidence_id': evidence_id, 'provenance': PROVENANCE, 'verified_labels': verified,
                'supported_labels': ['source', 'receiver', 'A', 'C'], 'detections': detections, 'method': METHOD,
                'limitations': LIMITATIONS}

    async def observe(self, sid, execution_receipt):
        # Controller status and the plan's expectations are deliberately ignored.
        frame = await self.inspect_scene(sid, execution_receipt.get('view', 'primary'))
        raw = self._observe_pixels(sid, frame['evidence_id'])
        features = {'readable': raw['ready']}
        if raw['ready']:
            features.update(receiver_appearance=raw['receiver'], sample_cup_held=raw['held'])
            if raw['donor'] != 'unknown':
                features['donor_appearance'] = raw['donor']
            if not raw['held']:
                features['sample_cup_station'] = 'A'
        if not raw['ready']:
            text = 'The overview is unreadable or unregistered; the outcome is unknown.'
        else:
            colour = raw['receiver'].replace('_liquid', '') + ' liquid'
            location = 'The arm is holding the beaker' if raw['held'] else 'The beaker is back on its mark'
            fill = {'empty': 'looks empty', 'liquid_visible': 'still shows liquid',
                    'unknown': 'has unreadable fill'}[raw['donor']]
            text = f'{location}. The beaker {fill}; the container at C shows {colour}.'
        return {**frame, 'status': 'observed' if raw['ready'] else 'unknown', 'observer_version': METHOD,
                'features': features, 'pixel_observation': raw, 'text': text,
                'reason': None if raw['ready'] else raw.get('reason') or 'Outcome is unknown.'}


class DemoBenchBackend(TwoVesselBackend):
    worker = staticmethod(run_worker)

    def _reset_state(self):
        super()._reset_state()
        simulation = self._state['simulation']
        for key in two_vessel_scene.SCENE:
            simulation.pop(key, None)
        simulation.update(**SCENE, warnings=list(LIMITATIONS))

    @staticmethod
    def capabilities():
        return {'experiment_id': EXPERIMENT['id'], 'conditions': ['prepared'], 'routes': [['A', 'C']],
                'mock_execution': False, 'physical_execution': False, 'simulation_execution': True,
                'supported_operations': list(ACTIONS), 'supported_actions': dict(ACTIONS),
                'operation_outcome_checks': copy.deepcopy(ACTION_CHECKS),
                **SCENE, 'measurement': False,
                'observation_provenance': PROVENANCE,
                'skill_admission': {
                    'required_expected_state': {'at': 'HOME'},
                    'expected_state_contract': 'SkillDefinition.expected_state describes the final controller state. '
                        'Full-pour admission requires final HOME. Held actions end above the bench.',
                    'required_outcome_checks': copy.deepcopy(ACTION_CHECKS[OPERATION]),
                    'outcome_checks_contract': 'outcome_checks are checked independently against fresh SIMULATED '
                        'image features in scene.observable_features. The transfer is evidenced by the beaker at A '
                        'reading empty; the receiver colour is reported from the image and may or may not change.',
                    'qualification': 'Simulated capability on the openarms_sim demo setup only; not chemistry or physical readiness.',
                },
                'action_description': 'pour the beaker at A into the container at C once, return the beaker to A and go HOME',
                'limitations': [*LIMITATIONS, 'Only the small beaker at A moves. The receiver at C stays fixed.']}

    def check_step(self, operation, arguments):
        if operation not in ACTIONS:
            raise ValueError('The simulated bench supports picking up the beaker, pouring into C, and returning it to A.')
        request = PRIMITIVE_SCHEMAS[operation].model_validate(arguments)
        status = self._state['simulation']['status']
        if self.session_id is None or status not in ('ready', 'completed') or not self._idle.is_set():
            raise ValueError('Prepare a fresh MuJoCo trial before executing.')
        holding = self._state['holding'] == 'sample_cup'
        if holding and operation in ('pick', OPERATION):
            raise ValueError('The arm is already holding the beaker.')
        if not holding and operation in ('pour', 'return_cup'):
            raise ValueError('The arm needs to pick up the beaker first.')
        if operation in ('pour', OPERATION) and not self._state['cup_portions']:
            raise ValueError('The beaker is empty. Prepare a new trial for another pour.')
        return request

    def _worker_arguments(self, operation, request):
        return {'operation': operation, **request.model_dump(mode='json'),
                'state': self.scene_service.continuation(self.session_id)}

    def _completed_state(self, operation, result):
        return {**result['controller_state'], 'armed': True} if result['ok'] else None


class DemoBenchSkillEvaluator(TwoVesselSkillEvaluator):
    scene_class, backend_class = DemoBenchSceneService, DemoBenchBackend
    experiment, conditions = EXPERIMENT, CONDITIONS
    suite = {'version': 'demo-bench-add-sample-admission-v1', 'positive': ['nominal'],
             'negative': ['camera_shift', 'missing', 'swapped', 'occluded', 'stale', 'integrity'],
             'controls': ['consent', 'stop'],
             'scope': 'SIMULATED add_sample A-to-C on the openarms_sim demo setup; one overview; no physical or chemistry qualification.'}
    scope = staticmethod(execution_scope)
    recovered_features = OUTCOME

    @staticmethod
    def _check_definition(definition, plan):
        if definition.expected_state.get('at') != 'HOME' or not any(
                c.feature == 'donor_appearance' and c.expected == 'empty' for c in definition.outcome_checks):
            raise ValueError('Demo bench admission requires an empty-donor outcome check and final HOME.')
        actions = [s for s in plan['steps'] if s['operation'] in (OPERATION,) or s['operation'].startswith('mock_')]
        if len(actions) != 1 or actions[0]['operation'] != OPERATION:
            raise ValueError('Only one add_sample A-to-C operation can be admitted on the demo bench.')
