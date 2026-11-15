"""Lab adapter for the openarms_sim `demo` bench (ruler bench matched to a recorded real pour).

One typed action, `add_sample(source=A, into=C, portions=1)`: pick the beaker at A, pour once
into the container at C, return the beaker to A and go HOME. Reuses the two-vessel consent,
STOP, receipt and evidence machinery through its worker/command seams.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import time

import numpy as np
from bench_vision.perception import observation
from simulation.openarms_sim.render import OVERVIEW_HEIGHT, OVERVIEW_WIDTH

from .contracts import AddSampleArguments
from .demo_bench_worker import CONFIGURATION_ID, CAMERA_ID, SETUP, run_worker
from .scene import camera_metadata
from .skills import compute_skill_hash
from .two_vessel_backend import TwoVesselBackend
from .two_vessel_evaluation import TwoVesselSkillEvaluator
from .two_vessel_scene import TwoVesselSceneService
from . import two_vessel_scene

OPERATION = 'add_sample'
PROVENANCE = 'SIMULATED'
METHOD = 'demo-bench-markers-donor-fill-v1'
SCENE = {'scene_id': 'openarms_sim_demo', 'scene_version': 1, 'setup': SETUP,
         'control_mode': 'mujoco_kinematic_add_sample'}
CAMERA = {**camera_metadata(CAMERA_ID, CONFIGURATION_ID), 'calibration_id': CONFIGURATION_ID}
LIMITATIONS = [
    'Poses are solved by the simulation from bench.yaml, matched to one recorded real pour; joint_map.yaml is unmeasured.',
    'Liquid is drawn, not simulated: colours come from chemistry.yaml, so receiver colour is not a chemistry result.',
    'Pixel observation of the rendered overview: donor fill and station markers only; no measured volume.',
    'No physical grasp, liquid delivery or spill safety is established. Physical dispatch is disabled.',
]
EXPERIMENT = {'id': 'demo_bench_pour', 'title': 'Demo bench pour — simulation', 'mode': 'SIMULATED',
              'question': 'Can the arm pour the beaker at A into the container at C, return the beaker and go HOME?',
              'description': 'openarms_sim demo setup: citric acid beaker at A, volcano mix container at C.'}
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
    identity = {'experiment': EXPERIMENT, 'versions': {'mujoco': mujoco.__version__, 'numpy': numpy.__version__,
                                                       'pillow': PIL.__version__, 'pydantic': pydantic.__version__},
                'sources': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    return 'demo-bench-' + compute_skill_hash(identity)[:16]


def _masks(pixels):
    r, g, b = pixels.transpose(2, 0, 1)
    low = np.zeros_like(r, bool)
    low[OVERVIEW_HEIGHT * 54 // 100:] = True  # Below the arm, where the station markers lie.
    return {'marker_a': (b > 180) & (r < 120) & low, 'marker_c': (r > 200) & (g > 130) & (g < 200) & (b < 80) & low,
            'red': (r > 180) & (g < 160) & (b < 160) & (r - g > 60)}


def _centre(mask, minimum=60):
    y, x = np.nonzero(mask)
    return None if len(x) < minimum else np.array([x.mean(), y.mean()])


def anchors(reference):
    """Station anchors from the nominal frame taken at reset; later frames are read at these pixels."""
    masks = _masks(reference)
    a, c = _centre(masks['marker_a']), _centre(masks['marker_c'])
    if a is None or c is None:
        raise ValueError('The reference frame does not show both station markers.')
    return {'A': a, 'C': c, 'red_c': int(masks['red'][int(c[1])-30:int(c[1])+20, int(c[0])-45:int(c[0])+45].sum())}


def read_pixels(pixels, anchor, tolerance_px=6):
    """Pixel-only reading of one overview frame. Never sees the receipt, plan or prediction."""
    masks = _masks(pixels)
    result = {'status': 'unknown', 'ready': False, 'camera_registration': 'unknown', 'method': METHOD,
              'provenance': PROVENANCE, 'donor': 'unknown', 'receiver': 'unknown', 'reason': None}
    drift = {k: (None if (p := _centre(masks['marker_' + k.lower()])) is None else float(np.linalg.norm(p - anchor[k])))
             for k in ('A', 'C')}
    result['marker_drift_px'] = drift
    if any(d is None or d > tolerance_px for d in drift.values()):
        result.update(camera_registration='shifted', reason='Station markers moved or are hidden; camera registration failed.')
        return result
    result['camera_registration'] = 'registered'
    ax, ay = np.rint(anchor['A']).astype(int)
    cx, cy = np.rint(anchor['C']).astype(int)
    red = masks['red']
    if red[ay-30:ay+20, ax-45:ax+45].sum() > 50 or red[cy-30:cy+20, cx-45:cx+45].sum() < 0.6 * anchor['red_c']:
        result['reason'] = 'The receiver is not where station C expects it.'
        return result
    result['receiver'] = 'red_liquid'
    r, g, b = pixels.transpose(2, 0, 1).astype(int)
    wall = (slice(ay-24, ay-17), slice(ax-6, ax+6))
    fill = (slice(ay-10, ay), slice(ax-6, ax+6))
    has_wall = ((r[wall] > 210) & (r[wall] < 245) & (b[wall] > r[wall])).mean() >= .5
    liquid = ((g[fill] - b[fill] >= 10) & (r[fill] > 170) & (r[fill] < 235)).mean()
    glass = ((b[fill] - r[fill] > 30) & (r[fill] >= 110)).mean()
    if has_wall and liquid >= .7:
        result['donor'] = 'liquid_visible'
    elif has_wall and glass >= .7:
        result['donor'] = 'empty'
    else:
        result['reason'] = 'The beaker at A is missing, hidden or unreadable.'
        return result
    result.update(status='ok', ready=True)
    return result


class DemoBenchSceneService(TwoVesselSceneService):
    feature_schema = {'readable': {'type': 'boolean'},
                      'donor_appearance': {'enum': ['liquid_visible', 'empty']},
                      'receiver_appearance': {'enum': ['red_liquid']},
                      'sample_cup_station': {'enum': ['A']}, 'sample_cup_held': {'type': 'boolean'}}
    worker = staticmethod(run_worker)

    async def inspect_scene(self, sid, view='primary'):
        result = await super().inspect_scene(sid, view)
        # Replace the water fixture's identity with this setup's; frame checks above stay shared.
        result['scene'].update({**SCENE, **CAMERA, 'width': OVERVIEW_WIDTH, 'height': OVERVIEW_HEIGHT,
                                'available_samples': ['prepared'],
                                'object_descriptions': {'source': 'small beaker with citric acid on the blue mark A',
                                                        'receiver': 'wide round container with the volcano mix on the orange mark C'},
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
        return read_pixels(two_vessel_scene.fixture._pixels(raw), anchors(two_vessel_scene.fixture._pixels(reference)))

    async def localize_objects(self, sid, evidence_id, labels):
        result = self._observe_pixels(sid, evidence_id)
        reference, _view = self.frames[sid, evidence_id]
        anchor = anchors(two_vessel_scene.fixture._pixels(self._references[sid]))
        boxes = {'source': (anchor['A'], 14, 34, 8), 'receiver': (anchor['C'], 45, 30, 20)}
        detections, verified = [], []
        for label in labels:
            name = two_vessel_scene.ALIASES.get(label.lower(), label.lower())
            found = result['ready'] and name in boxes
            box = None
            if found:
                (x, y), half, up, down = boxes[name]
                box = [int(x - half), int(y - up), int(x + half) + 1, int(y + down) + 1]
                verified.append(label)
            detection = observation({'object_id': label, 'frame_id': evidence_id, 'timestamp_s': reference['captured_at'],
                                     'provenance': PROVENANCE, **CAMERA}, METHOD, box=box,
                                    reason=None if found else result.get('reason') or 'Unsupported vessel label.')
            detections.append({**detection, **CAMERA, 'vessel_id': name if found else None,
                               'dock_id': {'source': 'A', 'receiver': 'C'}[name] if found else None,
                               'held': False if found else None,
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
            features.update(donor_appearance=raw['donor'], receiver_appearance=raw['receiver'],
                            sample_cup_station='A', sample_cup_held=False)
        text = ('The beaker at A looks empty and is back on its mark; the container at C shows red liquid.'
                if raw['ready'] and raw['donor'] == 'empty' else
                'The beaker at A still shows liquid; the container at C shows red liquid.' if raw['ready'] else
                'The overview is unreadable or unregistered; the outcome is unknown.')
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
                'supported_operations': [OPERATION], **SCENE, 'measurement': False,
                'observation_provenance': PROVENANCE,
                'skill_admission': {
                    'required_expected_state': {'at': 'HOME'},
                    'expected_state_contract': 'SkillDefinition.expected_state describes the final controller state. '
                        'Declare at=HOME; it is not a camera-observed feature or physical success.',
                    'required_outcome_checks': [{'feature': 'donor_appearance', 'expected': 'empty'}],
                    'outcome_checks_contract': 'outcome_checks are checked independently against fresh SIMULATED '
                        'image features in scene.observable_features. The receiver is red before and after the pour '
                        '(its mix is pre-coloured), so the transfer is evidenced by the beaker at A reading empty.',
                    'qualification': 'Simulated capability on the openarms_sim demo setup only; not chemistry or physical readiness.',
                },
                'action_description': 'pour the beaker at A into the container at C once, return the beaker to A and go HOME',
                'limitations': [*LIMITATIONS, 'One pour from the beaker at A into the container at C; no other route or amount.']}

    def check_step(self, operation, arguments):
        if operation != OPERATION:
            raise ValueError('The demo bench supports only add_sample from A into C.')
        request = AddSampleArguments.model_validate(arguments)
        if self.session_id is None or self._state['simulation']['status'] != 'ready' or not self._idle.is_set():
            raise ValueError('Prepare a fresh MuJoCo trial before executing.')
        return request

    @staticmethod
    def _command(request):
        return {'source': request.source, 'into': request.into, 'portions': request.portions}


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
