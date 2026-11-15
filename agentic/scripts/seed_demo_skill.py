"""Operator-seeded demo-bench skill: start the app warm for the base A->C pour.

Runs the app's own demo-bench Lab in OPENARMS_DATA_DIR with a fixed operator-authored
skill (no model call), one scripted, exactly confirmed SIMULATED execution, a fresh
independent observation, then the existing setup-scoped evaluator. Only a promoted
skill is kept; a later app on the same data directory routes matching requests to it
with no expert planning call. Re-run after any change to the simulator or lab sources,
because admission is bound to the content-derived execution scope.
"""
import argparse
import asyncio
import copy
import json
import time
from pathlib import Path

from openarms_lab.demo_bench import (CONDITIONS, EXPERIMENT, DemoBenchBackend, DemoBenchSceneService,
                                     DemoBenchSkillEvaluator, execution_scope)
from openarms_lab.runtime import Lab
from openarms_lab.skills import SkillRegistry

DEFINITION = {
    'skill_id': 'demo_bench.base_pour', 'name': 'Base demo pour',
    'intent': 'Pour the prepared beaker at A once into the container at C, return the beaker to A and go HOME.',
    'retrieval_examples': [
        'pour {source} into {into}', 'pour from {source} into {into}', 'pour {source} to {into}',
        'pour the beaker from {source} into {into}', 'pour the beaker at {source} into the container at {into}',
        'pour the beaker from {source} into the container at {into}',
        'pour {source} into {into} and go home', 'pour the beaker from {source} into {into} and go home',
        'pour the beaker from {source} into {into}, return the beaker to {source} and go HOME, then check the result.'],
    'parameter_schema': {'source': {'type': 'string', 'enum': ['A']}, 'into': {'type': 'string', 'enum': ['C']}},
    'preconditions': {'fresh_scene': True, 'labels': ['source', 'receiver']},
    'steps': [{'operation': 'inspect_scene'},
              {'operation': 'add_sample', 'arguments': {'source': '$source', 'into': '$into', 'portions': 1}},
              {'operation': 'observe'}],
    'expected_state': {'at': 'HOME'},
    'outcome_checks': [{'feature': 'donor_appearance', 'expected': 'empty'}],
    'limitations': ['Operator-seeded SIMULATED demo bench skill; no physical, volume or chemistry qualification.'],
}
SEED_REQUEST = 'pour the beaker from A into C'


class OperatorSeed:
    provider, model, reasoning_effort = 'OPERATOR_SEED', 'fixed-demo-bench-skill-v1', 'none'

    def describe(self):
        return {'provider': self.provider, 'model': self.model, 'requested_model': None, 'actual_model': None,
                'reasoning_effort': 'none', 'live_model': False}

    async def run(self, context, *, tool_handler, cancel_event=None, **kwargs):
        planning = context['phase'] in ('planning', 'improvement')
        if planning and context.get('images'):
            await tool_handler('localize_objects', {'evidence_id': context['images'][0]['evidence_id'],
                                                    'labels': ['source', 'receiver']})
        return {'kind': 'plan' if planning else 'complete',
                'summary': 'Operator-seeded demo pour; the host validates it independently.' if planning else 'Seed checkpoint.',
                'payload': {'skill_definition': copy.deepcopy(DEFINITION), 'bindings': {'source': 'A', 'into': 'C'}}
                           if planning else {'continue': True},
                'provider': self.provider, 'model': self.model, 'requested_model': None, 'actual_model': None,
                'model_verified': False, 'reasoning_effort': 'none', 'calls': 0, 'usage': {}, 'elapsed_ms': 0,
                'tool_receipts': []}


async def settled(lab, sid):
    task = lab.snapshot(sid)['tasks'][-1]
    worker = lab.workers.get(task['task_id'])
    if worker:
        await asyncio.wait_for(asyncio.shield(worker), 300)
    return lab.snapshot(sid)


async def seed(data):
    scope = execution_scope()
    scene = DemoBenchSceneService(data/'scene-evidence')
    registry = SkillRegistry(data/f'task-skills-{scope}.json')
    if DEFINITION['skill_id'] in registry.data['active']:
        return {'status': 'already_active', 'execution_scope': scope, 'registry': str(registry.path)}
    lab = Lab(data, expert=OperatorSeed(), perception=scene, registry=registry,
              evaluator=DemoBenchSkillEvaluator(data/'evaluations'), auto_evaluate=False,
              experiment=EXPERIMENT, conditions=CONDITIONS, execution_scope=scope,
              backend_factory=lambda: DemoBenchBackend(scene), expert_timeout=240)
    sid = (await lab.create())['session_id']
    try:
        await lab.converse(sid, SEED_REQUEST, 'operator-seed')
        state = await settled(lab, sid)
        pending = state['pending']
        if not pending:
            raise RuntimeError('Seed request produced no proposal: ' + str(state['tasks'][-1].get('summary')))
        await lab.present(sid, pending['request_id'], pending['proposal_version'])
        await lab.confirm(sid, pending['request_id'], pending['proposal_version'])
        state = await settled(lab, sid)
        task = state['tasks'][-1]
        observation = task['observations'][-1] if task['observations'] else {}
        if task['status'] != 'completed' or observation.get('status') != 'observed' or not all(observation['checks'].values()):
            raise RuntimeError('Seed execution was not independently observed as successful.')
        decision = await lab.evaluate_candidate(sid, task['plan']['skill_id'], task['plan']['skill_version'])
        return {'status': decision['status'], 'reason': decision.get('reason'), 'execution_scope': scope,
                'skill_id': task['plan']['skill_id'], 'skill_version': task['plan']['skill_version'],
                'registry': str(registry.path), 'session_id': sid, 'provenance': 'OPERATOR_SEED + SIMULATED',
                'observation': observation.get('text'), 'seeded_at': time.time()}
    finally:
        await lab.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--data', type=Path, required=True, help='The OPENARMS_DATA_DIR the app will use.')
    args = parser.parse_args()
    args.data.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(seed(args.data.resolve()))
    print(json.dumps(result, indent=2))
    if result['status'] not in ('promoted', 'already_active'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
