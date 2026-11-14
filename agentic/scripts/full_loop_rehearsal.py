"""Selected expert task rehearsal against synthetic images; no physical actuation.

The harness acts as a test student and explicitly presents/confirms mock plans.
It retains actual model/tool/image/task receipts. It is not an audible rehearsal.
"""
import argparse
import asyncio
import json
import time
from pathlib import Path

from openarms_lab.expert_profiles import add_expert_arguments, expert_from_arguments
from openarms_lab.evaluation import SyntheticSkillEvaluator
from openarms_lab.runtime import Lab
from openarms_lab.scene import SceneService
from openarms_lab.simulated_backend import SceneBackend


async def settle(lab, sid, *, approve=False):
    seen = set()
    async with asyncio.timeout(600):
        while True:
            state = lab.snapshot(sid)
            task = state['tasks'][-1]
            signature = (task['status'], len(task['expert_runs']), task['replans'])
            if signature not in seen:
                seen.add(signature)
                print(json.dumps({'status': task['status'], 'summary': task.get('summary'),
                                  'expert_runs': len(task['expert_runs']), 'replans': task['replans']}), flush=True)
            if task['status'] == 'awaiting_confirmation':
                if not approve:
                    return state
                proposal = state['pending']
                print(json.dumps({'test_student_reviewed_and_confirmed': proposal['summary'],
                                  'plan_hash': proposal['plan_hash']}), flush=True)
                await lab.present(sid, proposal['request_id'], proposal['proposal_version'])
                await lab.confirm(sid, proposal['request_id'], proposal['proposal_version'])
            elif task['status'] in ('completed', 'failed', 'cancelled', 'needs_clarification'):
                return state
            await asyncio.sleep(.1)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--execution', choices=['mock', 'mujoco'], default='mock')
    add_expert_arguments(parser)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    scene = SceneService(args.out/'scene')
    expert = expert_from_arguments(args, args.out/'expert', artifact_roots=[scene.artifact_dir])
    evaluator = SyntheticSkillEvaluator(args.out/'evaluations')
    factory = lambda: SceneBackend(scene, delay=.02)
    scope = 'mock'
    if args.execution == 'mujoco':
        from openarms_lab.mujoco_scene import MujocoSceneService
        from openarms_lab.mujoco_backend import MujocoBackend
        from openarms_lab.simulation_evaluation import SimulationSkillEvaluator, simulation_scope
        scene = MujocoSceneService(args.out/'scene')
        expert = expert_from_arguments(args, args.out/'expert', artifact_roots=[scene.artifact_dir])
        evaluator = SimulationSkillEvaluator(args.out/'evaluations')
        factory = lambda: MujocoBackend(scene)
        scope = simulation_scope()
    lab = Lab(args.out/'sessions', expert=expert, perception=scene, evaluator=evaluator,
              backend_factory=factory, execution_scope=scope, expert_timeout=240)
    sid = (await lab.create())['session_id']
    try:
        began = time.perf_counter()
        await lab.converse(sid, 'Please test the prepared vinegar sample and check the indicator color.', 'cold-request')
        cold = await settle(lab, sid, approve=True)
        (args.out/'cold.json').write_text(json.dumps(cold, indent=2))
        task = cold['tasks'][-1]
        assert task['status'] == 'completed', task.get('summary')
        assert task['observations'] and task['observations'][-1]['status'] == 'observed'
        plan = task['plan']
        assert plan['skill_id'], 'Expert did not author a reusable candidate'
        decision = await lab.evaluate_candidate(sid, plan['skill_id'], plan['skill_version'])
        print(json.dumps({'evaluation': decision}), flush=True)
        assert decision['status'] == 'promoted', decision
        skill = lab.registry.get(plan['skill_id'])
        request = skill['retrieval_examples'][-1]
        for key, value in plan['bindings'].items():
            request = request.replace('{'+key+'}', str(value).replace('_', ' '))
        await lab.prepare(sid)
        await lab.converse(sid, request, 'warm-request')
        warm = await settle(lab, sid, approve=True)
        (args.out/'warm.json').write_text(json.dumps(warm, indent=2))
        task2 = warm['tasks'][-1]
        assert task2['status'] == 'completed' and task2['route'] == 'active_skill'
        assert not task2['expert_runs'], 'Warm successful skill invoked the expert'
        assert task2['plan']['skill_version'] == plan['skill_version']
        assert task2['plan']['bindings'] == plan['bindings']
        assert warm['pending'] is None and task2['observations'][-1]['status'] == 'observed'
        summary = {'expert_configuration': expert.describe(), 'expert_runs': task['expert_runs'],
                   'provider': task['expert_runs'][0]['provider'], 'model': task['expert_runs'][0]['model'],
                   'requested_model': task['expert_runs'][0].get('requested_model'),
                   'actual_model': task['expert_runs'][0].get('actual_model'),
                   'reasoning_effort': task['expert_runs'][0]['reasoning_effort'],
                   'provenance': 'SIMULATED' if args.execution == 'mujoco' else 'SYNTHETIC',
                   'execution_backend': args.execution, 'execution_scope': scope,
                   'actual_expert': True, 'audible_voice_verified': False,
                   'cold_model_calls': sum(run['calls'] for run in task['expert_runs']),
                   'warm_model_calls': 0, 'warm_request': request, 'promotion': decision,
                   'elapsed_seconds': time.perf_counter()-began}
        (args.out/'summary.json').write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2), flush=True)
    finally:
        (args.out/'final-state.json').write_text(json.dumps(lab.snapshot(sid), indent=2))
        await lab.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
