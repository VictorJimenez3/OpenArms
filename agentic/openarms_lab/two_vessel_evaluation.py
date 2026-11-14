"""Independent, bounded admission of a water-only two-vessel skill.

Replays the submitted definition through the existing Lab. Initial admission
compares against no capability; it is not evidence of a substantive improvement.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import itertools
import json
from pathlib import Path
import time
import uuid

from .contracts import EvaluationReceipt, PlanDraft, SkillDefinition
from .evaluation import _PinnedPlanner
from .runtime import Lab, LabError
from .skills import SkillRegistry, compute_skill_hash
from .two_vessel_backend import TwoVesselBackend
from .two_vessel_configuration import CONDITIONS, EXPERIMENT, execution_scope
from .two_vessel_scene import TwoVesselSceneService

SUITE = {'version': 'two-vessel-water-admission-v1',
         'positive': ['nominal'],
         'negative': ['camera_shift', 'missing', 'swapped', 'occluded', 'stale', 'integrity'],
         'controls': ['consent', 'stop'],
         'scope': 'SIMULATED water A-to-C complete pour; one overview; no physical or chemistry qualification.'}


def _definition(record):
    definition = SkillDefinition.model_validate({k: v for k, v in record.items() if k not in ('version', 'status')})
    if compute_skill_hash(definition) != record['version']:
        raise ValueError('Definition does not match its frozen version.')
    return definition


def _bindings(definition):
    parameters = definition.parameter_schema
    if any(not spec.enum for spec in parameters.values()):
        raise ValueError('Two-vessel admission requires finite enum parameters.')
    combinations = [dict(zip(parameters, values)) for values in itertools.product(*(s.enum for s in parameters.values()))]
    if len(combinations) > 4:
        raise ValueError('Two-vessel admission supports at most four declared bindings.')
    return combinations


class _FaultScene(TwoVesselSceneService):
    """Frozen negative evidence cases; outputs still pass the actual Lab checks."""
    def __init__(self, folder, case):
        super().__init__(folder)
        self.case = case
        self.variant = case if case in SUITE['negative'][:4] else 'nominal'

    async def inspect_scene(self, sid, view='primary'):
        result = await super().inspect_scene(sid, view)
        image = result['images'][0]
        if self.case == 'stale':
            stale = image['captured_at'] - 181
            image['captured_at'] = stale
            self.frames[sid, image['evidence_id']][0]['captured_at'] = stale
            self._raw[sid, image['evidence_id']]['captured_at'] = stale
            result['scene'].update(captured_at=stale, expires_at=stale+180, fresh=False)
        elif self.case == 'integrity':
            # Keep the original expected hash: this must fail closed at ingestion.
            with Path(image['path']).open('ab') as stream:
                stream.write(b'\nchanged-after-capture')
        return result


class TwoVesselSkillEvaluator:
    def __init__(self, artifact_dir):
        self.artifact_dir = Path(artifact_dir)
        self._lock = asyncio.Lock()

    async def _case(self, folder, definition, bindings, case):
        scene = _FaultScene(folder/'images', case)
        motion_started = asyncio.Event()

        class ControlledBackend(TwoVesselBackend):
            async def execute_step(self, request_id, arguments, progress, **kwargs):
                async def report(phase):
                    await progress(phase)
                    motion_started.set()
                    if case == 'stop':
                        # Pause only the progress consumer, with a real renderer
                        # alive. Lab STOP must cancel and reap it before return.
                        await asyncio.Event().wait()
                return await super().execute_step(request_id, arguments, report, **kwargs)

        lab = Lab(folder, perception=scene,
                  expert=_PinnedPlanner(definition.model_dump(mode='json'), bindings),
                  backend_factory=lambda: ControlledBackend(scene), execution_timeout=90,
                  experiment=EXPERIMENT, conditions=CONDITIONS)
        started = time.perf_counter()
        sid = (await lab.create())['session_id']
        control_passed = False
        try:
            handle = await lab.start_task(sid, 'Replay the frozen two-vessel water skill for admission.')
            async def settled():
                await asyncio.wait_for(asyncio.shield(lab.workers[handle['task_id']]), 120)
            await settled()
            proposal = lab.snapshot(sid)['pending']
            if proposal:
                exact = (sid, proposal['request_id'], proposal['proposal_version'])
                if case == 'consent':
                    try:
                        await lab.confirm(*exact)
                    except LabError:
                        control_passed = lab.backends[sid].executions == 0
                else:
                    await lab.present(*exact)
                    await lab.confirm(*exact)
                    if case == 'stop':
                        await asyncio.wait_for(motion_started.wait(), 30)
                        await lab.stop(sid)
                        backend = lab.backends[sid]
                        control_passed = (backend._worker is None and backend._idle.is_set() and
                            backend.executions == 1 and backend.state()['simulation']['status'] == 'stopped' and
                            backend.state()['simulation']['video_name'] is None and
                            not list(scene.folder(sid).glob('*.mp4')))
                    else:
                        await settled()
            state = lab.snapshot(sid)
            task, backend = state['tasks'][-1], lab.backends[sid]
            observed = task['observations'][-1] if task['observations'] else None
            features = observed.get('features', {}) if observed else {}
            simulation = backend.state()['simulation']
            recovered = bool(task['status'] == 'completed' and observed and
                observed['status'] == 'observed' and observed['provenance'] == 'SIMULATED' and
                observed.get('checks') and all(observed['checks'].values()) and
                features.get('receiver_appearance') == 'water_appearance' and
                features.get('sample_cup_station') == 'A' and features.get('sample_cup_held') is False and
                simulation['status'] == 'completed' and simulation['dose_count'] == 1 and
                simulation['returned_to_dock'] and simulation['home_reached'])
            if case == 'stop':
                control_passed = control_passed and task['status'] == 'cancelled' and not state['pending'] and not observed
            row = {'case': case, 'bindings': bindings, 'recovered': recovered,
                   'control_passed': control_passed, 'task_status': task['status'],
                   'executions': backend.executions, 'observed': observed,
                   'reason': task.get('summary'), 'elapsed_ms': (time.perf_counter()-started)*1000,
                   'motion_seconds': simulation['motion_seconds'], 'provenance': 'SIMULATED',
                   'actual_model_used': False}
            (folder/'replay.json').write_text(json.dumps({'summary': row, 'state': state}, indent=2))
            return row
        finally:
            await lab.shutdown()

    @staticmethod
    def _validate(folder, definitions):
        registry = SkillRegistry(folder/'compile-only.json')
        for definition in definitions.values():
            if definition.expected_state.get('at') != 'HOME' or not any(
                    c.feature == 'receiver_appearance' and c.expected == 'water_appearance'
                    for c in definition.outcome_checks):
                raise ValueError('Water admission requires declared water appearance and final HOME checks.')
            for binding in _bindings(definition):
                plan = registry.compile(PlanDraft(skill_definition=definition, bindings=binding))
                actions = [s for s in plan['steps'] if s['operation'].startswith('mock_')]
                if (len(actions) != 1 or actions[0]['operation'] != 'mock_prepared_sample' or
                        actions[0]['arguments']['condition_id'] != 'water'):
                    raise ValueError('Only one complete water A-to-C operation can be admitted.')
        if 'baseline' in definitions:
            previous, revised = definitions['baseline'], definitions['candidate']
            if (previous.skill_id != revised.skill_id or previous.parameter_schema != revised.parameter_schema or
                    not {compute_skill_hash(c) for c in previous.outcome_checks}.issubset(
                        {compute_skill_hash(c) for c in revised.outcome_checks}) or
                    any(revised.expected_state.get(k) != v for k,v in previous.expected_state.items())):
                raise ValueError('Revision must preserve the baseline domain and outcome/final-state checks.')

    @staticmethod
    def _routing(folder, definition, baseline, combinations):
        registry = SkillRegistry(folder/'routing-only.json')
        version = registry.candidate(definition)
        registry.data['versions'][version]['status'] = 'active'
        registry.data['active'][definition.skill_id] = version
        rows = []
        for binding in combinations:
            for template in dict.fromkeys([*definition.retrieval_examples,
                                           *(baseline.retrieval_examples if baseline else [])]):
                text = template
                for key, value in binding.items():
                    text = text.replace('{'+key+'}', str(value).replace('_',' '))
                match = registry.match(text)
                rows.append({'text': text, 'matched': bool(match and match.bindings == binding and
                              match.skill_version == version),
                             'negation_rejected': registry.match('Do not '+text) is None})
        (folder/'routing.json').write_text(json.dumps(rows, indent=2))
        return bool(rows) and all(r['matched'] and r['negation_rejected'] for r in rows)

    async def evaluate_candidate(self, sid, candidate, baseline):
        async with self._lock:
            folder = self.artifact_dir/uuid.uuid4().hex
            folder.mkdir(parents=True)
            scope = execution_scope()
            suite = {**SUITE, 'source_scope': scope,
                     'evaluator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
            frozen = {'suite': suite, 'candidate': copy.deepcopy(candidate),
                      'unchanged_baseline': copy.deepcopy(baseline), 'requesting_session': sid}
            (folder/'frozen-inputs.json').write_text(json.dumps(frozen, indent=2))
            definitions, comparisons, controls, reasons = {}, {}, {}, []
            gates = dict.fromkeys(('routing','outcome','unknown','consent','stop','source_unchanged'), False)
            try:
                definitions = {'candidate': _definition(frozen['candidate'])}
                if baseline:
                    definitions['baseline'] = _definition(frozen['unchanged_baseline'])
                self._validate(folder, definitions)
                combinations = _bindings(definitions['candidate'])
                gates['routing'] = self._routing(folder, definitions['candidate'], definitions.get('baseline'), combinations)
                for label, definition in definitions.items():
                    comparisons[label] = []
                    for bi, binding in enumerate(combinations):
                        for case in SUITE['positive'] + SUITE['negative']:
                            comparisons[label].append(await self._case(folder/label/f'{bi}-{case}', definition, binding, case))
                for control in SUITE['controls']:
                    controls[control] = await self._case(folder/control, definitions['candidate'], combinations[0], control)
                rows = comparisons['candidate']
                previous = {(r['case'], compute_skill_hash(r['bindings'])) for r in comparisons.get('baseline',[]) if r['recovered']}
                current = {(r['case'], compute_skill_hash(r['bindings'])) for r in rows if r['recovered']}
                gates.update(outcome=previous.issubset(current) and all(r['recovered'] for r in rows if r['case']=='nominal'),
                             unknown=all(not r['recovered'] and r['executions']==0 and not r['observed']
                                         for r in rows if r['case'] in SUITE['negative']),
                             consent=controls['consent']['control_passed'], stop=controls['stop']['control_passed'])
            except (ValueError, KeyError) as exc:
                reasons.append(str(exc))
            gates['source_unchanged'] = (scope == execution_scope() and
                suite['evaluator_sha256'] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
            score = lambda label: sum(r['recovered'] for r in comparisons.get(label,[]) if r['case']=='nominal')
            gain = score('candidate') - score('baseline')
            reasons.append('Initial admission against absent capability; this is not a substantive improvement.' if not baseline else
                           'Unchanged baseline replayed on the same cases; equivalent outcomes are not an improvement.')
            reasons.extend(f'Failed {key} gate.' for key,value in gates.items() if not value)
            reasons.append(f'Observed nominal successes: baseline {score("baseline")}, candidate {score("candidate")}.')
            if gain <= 0:
                reasons.append('No measured recovered-case gain; retain the existing active skill.')
            metrics = {'cases': comparisons, 'controls': controls, 'source_scope': scope,
                       'initial_admission': baseline is None, 'substantive_improvement': baseline is not None and gain > 0,
                       'actual_model_used': False, 'physical_qualification': False, 'provenance': 'SIMULATED'}
            (folder/'comparison.json').write_text(json.dumps(metrics, indent=2))
            manifest = {str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in sorted(folder.rglob('*')) if path.is_file()}
            (folder/'artifact-manifest.json').write_text(json.dumps(manifest, indent=2))
            artifacts = ['frozen-inputs.json','comparison.json','artifact-manifest.json'] + (['routing.json'] if (folder/'routing.json').exists() else [])
            receipt = EvaluationReceipt.model_validate({
                'evaluation_id': folder.name, 'suite_hash': compute_skill_hash(suite),
                'candidate_hash': candidate['version'], 'baseline_hash': baseline['version'] if baseline else None,
                'artifact_hashes': [hashlib.sha256((folder/p).read_bytes()).hexdigest() for p in artifacts],
                'baseline_recovered': score('baseline'), 'candidate_recovered': score('candidate'),
                'regression_gates': gates, 'passed': all(gates.values()) and gain > 0,
                'reasons': reasons, 'metrics': metrics}).model_dump(mode='json')
            (folder/'receipt.json').write_text(json.dumps(receipt, indent=2))
            return receipt
