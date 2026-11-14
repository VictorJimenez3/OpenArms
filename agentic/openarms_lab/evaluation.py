"""Frozen synthetic replay suite for pH skill admission and measured revisions.

Every result is produced by the same session runtime and pixel observer as the
app. A scripted planner pins the submitted definition; it does not generate,
improve, or judge a skill. No model or physical hardware is used by this suite.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import itertools
import json
import time
import uuid
from pathlib import Path

from .contracts import PlanDraft, SkillDefinition
from .runtime import Lab, LabError
from .scene import SceneService
from .simulated_backend import SceneBackend
from .skills import SkillRegistry, compute_skill_hash

SUITE = {
    'version': 'synthetic-ph-replay-v1',
    'scope': 'Qualitative prepared-sample skills; no chemistry or physical qualification.',
    'recoverable': [
        {'name': 'clear', 'world': {}},
        {'name': 'shifted_source', 'world': {'source_offset': 35}},
        {'name': 'primary_obscured', 'world': {'occluded_primary': True}},
        {'name': 'secondary_obscured', 'world': {'occluded_secondary': True}},
    ],
    'must_remain_unknown': [
        {'name': 'both_obscured', 'world': {'occluded_primary': True, 'occluded_secondary': True}},
        {'name': 'receiver_missing', 'world': {'receiver_missing': True}},
        {'name': 'ambiguous_marker', 'world': {'duplicate_receiver_marker': True}},
        {'name': 'stale', 'world': {'stale': True}},
    ],
    'gates': ['routing', 'outcome', 'unknown', 'consent', 'stop'],
}


class _PinnedPlanner:
    """Evaluation replay only; its output is never evidence of an outcome."""
    def __init__(self, definition, bindings):
        self.draft = {'skill_definition': definition, 'bindings': bindings}

    async def run(self, context, **kwargs):
        planning = context['phase'] == 'planning'
        # A failed checkpoint must not be turned into a successful outcome by the
        # replay planner. The exact definition is the subject of this evaluation.
        failed = any(event['type'] == 'checkpoint_failed' for event in context['feedback'])
        return {'kind': 'plan' if planning else 'clarification' if failed else 'complete',
                'payload': self.draft if planning else {} if failed else {'continue': True},
                'summary': 'Pinned evaluation replay; independent pixels determine results.',
                'provider': 'EVALUATION_SCRIPT', 'model': None, 'calls': 0,
                'usage': {}, 'tool_receipts': [], 'elapsed_ms': 0}


class SyntheticSkillEvaluator:
    def __init__(self, artifact_dir):
        self.artifact_dir = Path(artifact_dir)
        self._lock = asyncio.Lock()

    @staticmethod
    def _definition(record):
        return SkillDefinition.model_validate({key: value for key, value in record.items()
                                               if key not in ('version', 'status')})

    @staticmethod
    def _bindings(definition):
        keys, choices = [], []
        for key, spec in definition.parameter_schema.items():
            if not spec.enum:
                raise ValueError('This evaluator requires finite enum parameters.')
            keys.append(key)
            choices.append(spec.enum)
        combinations = [dict(zip(keys, values)) for values in itertools.product(*choices)]
        if len(combinations) > 12:
            raise ValueError('This evaluator supports at most 12 parameter combinations.')
        return combinations

    @staticmethod
    async def _settled(lab, sid):
        async with asyncio.timeout(5):
            while True:
                state = lab.snapshot(sid)
                if state['tasks'] and state['tasks'][-1]['status'] in {
                        'awaiting_confirmation', 'completed', 'failed', 'needs_clarification', 'cancelled'}:
                    return state
                await asyncio.sleep(.001)

    async def _replay(self, folder, definition, bindings, case, *, control=None):
        scene = SceneService(folder/'images')
        planner = _PinnedPlanner(definition.model_dump(mode='json'), bindings)
        lab = Lab(folder, expert=planner, perception=scene,
                  backend_factory=lambda: SceneBackend(scene, delay=.01 if control == 'stop' else 0))
        sid = (await lab.create())['session_id']
        started = time.perf_counter()
        try:
            for key, value in case['world'].items():
                setattr(scene.world(sid), key, value)
            await lab.start_task(sid, 'Replay this pinned candidate under the frozen evaluation case.')
            state = await self._settled(lab, sid)
            proposal = state['pending']
            control_passed = False
            if proposal:
                if control == 'consent':
                    try:
                        await lab.confirm(sid, proposal['request_id'], proposal['proposal_version'])
                    except LabError:
                        control_passed = lab.backends[sid].executions == 0
                else:
                    await lab.present(sid, proposal['request_id'], proposal['proposal_version'])
                    await lab.confirm(sid, proposal['request_id'], proposal['proposal_version'])
                    if control == 'stop':
                        async with asyncio.timeout(5):
                            while lab.backends[sid].executions == 0:
                                if lab.snapshot(sid)['tasks'][-1]['status'] in ('failed', 'needs_clarification'):
                                    break
                                await asyncio.sleep(.001)
                        await lab.stop(sid)
                        count = lab.backends[sid].executions
                        await asyncio.sleep(.04)
                        control_passed = (lab.snapshot(sid)['tasks'][-1]['status'] == 'cancelled' and
                                          not lab.backends[sid]._running and
                                          lab.backends[sid].executions == count and
                                          not lab.snapshot(sid)['pending'])
                    else:
                        state = await self._settled(lab, sid)
            state = lab.snapshot(sid)
            task = state['tasks'][-1]
            observed = task['observations'][-1] if task['observations'] else None
            checks = observed.get('checks', {}) if observed else {}
            recovered = bool(observed and observed['status'] == 'observed' and checks and all(checks.values()))
            summary = {'case': case['name'], 'bindings': bindings, 'control': control,
                       'control_passed': control_passed, 'recovered': recovered,
                       'observed': observed, 'task_status': task['status'],
                       'executions': lab.backends[sid].executions,
                       'elapsed_ms': (time.perf_counter()-started)*1000,
                       'provenance': 'SYNTHETIC', 'real_model_used': False}
            (folder/'replay.json').write_text(json.dumps({'summary': summary, 'state': state}, indent=2))
            return summary
        finally:
            await lab.shutdown()

    def _routing(self, folder, definition, combinations, previous_examples=()):
        registry = SkillRegistry(folder/'routing-only-registry.json')
        version = registry.candidate(definition)
        # Isolated routing exercise only: this does not promote the app registry.
        registry.data['versions'][version]['status'] = 'active'
        registry.data['active'][definition.skill_id] = version
        receipts = []
        for bindings in combinations:
            for template in dict.fromkeys([*definition.retrieval_examples, *previous_examples]):
                text = template
                for key, value in bindings.items():
                    text = text.replace('{'+key+'}', str(value).replace('_', ' '))
                match = registry.match(text)
                receipts.append({'text': text, 'bindings': bindings,
                                 'matched': bool(match and match.bindings == bindings),
                                 'negation_rejected': registry.match('Do not '+text) is None})
        (folder/'routing.json').write_text(json.dumps(receipts, indent=2))
        return bool(receipts) and all(r['matched'] and r['negation_rejected'] for r in receipts)

    async def evaluate_candidate(self, sid, candidate, baseline):
        async with self._lock:
            eid = uuid.uuid4().hex
            folder = self.artifact_dir/eid
            folder.mkdir(parents=True)
            # Freeze both definitions and the exact suite before executing either.
            frozen = {'suite': SUITE, 'candidate': candidate, 'baseline': baseline,
                      'requesting_session': sid, 'provenance': 'SYNTHETIC'}
            (folder/'frozen-inputs.json').write_text(json.dumps(frozen, indent=2))
            definitions = {'candidate': self._definition(candidate)}
            if baseline:
                definitions['baseline'] = self._definition(baseline)
                previous, revised = definitions['baseline'], definitions['candidate']
                if previous.parameter_schema != revised.parameter_schema:
                    raise ValueError('An improvement comparison must preserve the unchanged baseline parameter domain.')
                prior_checks = {compute_skill_hash(check) for check in previous.outcome_checks}
                new_checks = {compute_skill_hash(check) for check in revised.outcome_checks}
                if (not prior_checks.issubset(new_checks) or
                        any(revised.expected_state.get(key) != value for key, value in previous.expected_state.items())):
                    raise ValueError('An improvement cannot weaken baseline outcome or final-state checks.')
            comparisons, controls = {}, {}
            candidate_bindings = self._bindings(definitions['candidate'])
            # This is deliberately a scoped suite, not an unsupported generic score.
            for definition in definitions.values():
                for binding in candidate_bindings:
                    registry = SkillRegistry(folder/'compile-only.json')
                    plan = registry.compile(PlanDraft(skill_definition=definition, bindings=binding))
                    if not any(s['operation'] == 'mock_prepared_sample' for s in plan['steps']):
                        raise ValueError('Synthetic pH evaluation currently supports prepared-sample skills only.')
            routing = self._routing(folder, definitions['candidate'], candidate_bindings,
                                    definitions['baseline'].retrieval_examples if baseline else ())
            for label, definition in definitions.items():
                rows = []
                for bi, binding in enumerate(candidate_bindings):
                    for case in SUITE['recoverable'] + SUITE['must_remain_unknown']:
                        rows.append(await self._replay(folder/label/f'{bi}-{case["name"]}', definition, binding, case))
                comparisons[label] = rows
            for control in ('consent', 'stop'):
                controls[control] = await self._replay(folder/control, definitions['candidate'],
                                                      candidate_bindings[0], SUITE['recoverable'][0], control=control)
            recoverable = {c['name'] for c in SUITE['recoverable']}
            baseline_rows = comparisons.get('baseline', [])
            candidate_rows = comparisons['candidate']
            score = lambda rows: sum(r['recovered'] for r in rows if r['case'] in recoverable)
            prior_success = {(r['case'], compute_skill_hash(r['bindings'])) for r in baseline_rows if r['recovered']}
            successes = {(r['case'], compute_skill_hash(r['bindings'])) for r in candidate_rows if r['recovered']}
            gates = {'routing': routing,
                     'outcome': prior_success.issubset(successes) and all(
                         r['recovered'] for r in candidate_rows if r['case'] == 'clear'),
                     'unknown': all(not r['recovered'] and (not r['observed'] or r['observed']['status'] == 'unknown')
                                    for r in candidate_rows if r['case'] not in recoverable),
                     'consent': controls['consent']['control_passed'],
                     'stop': controls['stop']['control_passed']}
            metrics = {'cases': comparisons, 'controls': controls, 'scope': SUITE['scope'],
                       'actual_model_used': False, 'baseline_unchanged': baseline is None or
                       compute_skill_hash(self._definition(baseline)) == baseline['version']}
            metrics_path = folder/'comparison.json'
            metrics_path.write_text(json.dumps(metrics, indent=2))
            hashes = [hashlib.sha256((folder/'frozen-inputs.json').read_bytes()).hexdigest(),
                      hashlib.sha256(metrics_path.read_bytes()).hexdigest()]
            gain = score(candidate_rows)-score(baseline_rows)
            reasons = [f'Independent readable outcomes: baseline {score(baseline_rows)}, candidate {score(candidate_rows)}.',
                       f'Recovered-case change: {gain}; unchanged-baseline non-regression required.']
            reasons += [f'Failed {name} gate.' for name, passed in gates.items() if not passed]
            receipt = {'evaluation_id': eid, 'suite_hash': compute_skill_hash(SUITE),
                       'candidate_hash': candidate['version'], 'baseline_hash': baseline['version'] if baseline else None,
                       'artifact_hashes': hashes, 'baseline_recovered': score(baseline_rows),
                       'candidate_recovered': score(candidate_rows), 'regression_gates': gates,
                       'passed': all(gates.values()) and gain > 0, 'reasons': reasons,
                       'metrics': {'artifact': eid+'/comparison.json', 'provenance': 'SYNTHETIC',
                                   'case_count': len(candidate_rows), 'recovered_gain': gain,
                                   'physical_qualification': False}}
            (folder/'receipt.json').write_text(json.dumps(receipt, indent=2))
            return copy.deepcopy(receipt)
