"""Selected expert task rehearsal against synthetic or MuJoCo images; no physical actuation.

The harness acts as a test student and explicitly presents/confirms simulated plans.
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


def timing(state, started_at, acknowledged_at):
    task = state['tasks'][-1]
    controller, = task['execution']
    approved = next(r for r in state['requests'] if r['request_id'] == controller['request_id'])
    events = [e for e in state['notebook'] if e['request_id'] == approved['request_id']]
    proposed = next(e['time'] for e in events if e['kind'] == 'request_proposed')
    first_progress = next(e['time'] for e in events
                          if e['kind'] == 'execution_progress' and e['data'].get('phase'))
    finished = next(e['time'] for e in events if e['kind'] == 'execution_result')
    outcome = task['observations'][-1]
    observed = next(e['time'] for e in state['notebook'] if e['kind'] == 'observation'
                    and e['data']['observation']['observation_id'] == outcome['observation_id'])
    confirmed = approved['confirmed_at']
    assert controller['plan_hash'] == approved['plan_hash']
    assert controller['task_id'] == approved['task_id'] == outcome['task_id'] == task['task_id']
    assert controller['trial_id'] == approved['trial_id'] == outcome['trial_id'] == task['trial_id']
    assert started_at <= proposed <= confirmed <= first_progress <= finished <= observed
    return {
        'request_acknowledgment_ms': (acknowledged_at-started_at)*1000,
        'request_to_proposal_ms': (proposed-started_at)*1000,
        'proposal_to_confirmation_ms': (confirmed-proposed)*1000,
        'confirmation_to_controller_progress_ms': (first_progress-confirmed)*1000,
        'controller_elapsed_ms': controller['elapsed_ms'],
        'simulated_motion_seconds': (controller.get('simulation') or {}).get('motion_seconds'),
        'controller_receipt_to_observation_ms': (observed-finished)*1000,
        'request_to_observation_ms': (observed-started_at)*1000,
        'planning_metrics': approved['metrics'],
    }


async def demo_bench_negatives(lab, sid, admitted_request):
    """STOP revokes a presented proposal; an unsupported route never becomes the A-to-C pour."""
    backend = lab.backends[sid]
    before = backend.executions
    await lab.converse(sid, 'Prepare a new trial', 'prepare-stop-check')
    await lab.converse(sid, admitted_request, 'stop-check-request')
    pending = (await settle(lab, sid))['pending']
    await lab.present(sid, pending['request_id'], pending['proposal_version'])
    await lab.stop(sid)
    try:
        await lab.confirm(sid, pending['request_id'], pending['proposal_version'])
        confirm_after_stop = 'accepted'
    except Exception as exc:
        confirm_after_stop = f'rejected: {exc}'
    stop = {'pending_after_stop': lab.snapshot(sid)['pending'], 'confirm_after_stop': confirm_after_stop,
            'dispatches': backend.executions - before}
    await lab.converse(sid, 'Prepare a new trial', 'prepare-unsupported-check')
    started = time.time()
    await lab.converse(sid, 'Pour the beaker from C into A.', 'unsupported-request')
    state = await settle(lab, sid)
    task = state['tasks'][-1]
    unsupported = {'request': 'Pour the beaker from C into A.', 'status': task['status'], 'summary': task.get('summary'),
                   'pending': state['pending'], 'dispatches': backend.executions - before,
                   'model_calls': sum(run['calls'] for run in task['expert_runs']), 'wall_ms': (time.time()-started)*1000}
    assert stop['pending_after_stop'] is None and stop['confirm_after_stop'].startswith('rejected') and stop['dispatches'] == 0
    assert unsupported['pending'] is None and unsupported['dispatches'] == 0
    print(json.dumps({'stop_check': stop, 'unsupported_check': unsupported}), flush=True)
    return {'stop': stop, 'unsupported': unsupported}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--execution', choices=['mock', 'mujoco'], default='mock')
    parser.add_argument('--scene', choices=['metered_dropper', 'two_vessel', 'demo_bench'], default='metered_dropper')
    add_expert_arguments(parser)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    scene = SceneService(args.out/'scene')
    expert = expert_from_arguments(args, args.out/'expert', artifact_roots=[scene.artifact_dir])
    evaluator = SyntheticSkillEvaluator(args.out/'evaluations')
    factory = lambda: SceneBackend(scene, delay=.02)
    options = {'execution_scope': 'mock'}
    request_text = 'Please test the prepared vinegar sample and check the indicator color.'
    if args.scene == 'demo_bench':
        if args.execution != 'mujoco':
            parser.error('--scene demo_bench requires --execution mujoco')
        from openarms_lab.demo_bench import (CONDITIONS, EXPERIMENT, DemoBenchBackend, DemoBenchSceneService,
                                             DemoBenchSkillEvaluator, execution_scope)
        scene = DemoBenchSceneService(args.out/'scene')
        expert = expert_from_arguments(args, args.out/'expert', artifact_roots=[scene.artifact_dir])
        evaluator = DemoBenchSkillEvaluator(args.out/'evaluations')
        factory = lambda: DemoBenchBackend(scene)
        options = {'experiment': EXPERIMENT, 'conditions': CONDITIONS, 'execution_scope': execution_scope()}
        request_text = 'Please pour the beaker from A into C, return the beaker to A and go HOME, then check the result.'
    elif args.scene == 'two_vessel':
        if args.execution != 'mujoco':
            parser.error('--scene two_vessel requires --execution mujoco')
        from openarms_lab.two_vessel_scene import TwoVesselSceneService
        from openarms_lab.two_vessel_backend import TwoVesselBackend
        from openarms_lab.two_vessel_evaluation import TwoVesselSkillEvaluator
        from openarms_lab.two_vessel_configuration import EXPERIMENT, CONDITIONS, execution_scope
        scene = TwoVesselSceneService(args.out/'scene')
        expert = expert_from_arguments(args, args.out/'expert', artifact_roots=[scene.artifact_dir])
        evaluator = TwoVesselSkillEvaluator(args.out/'evaluations')
        factory = lambda: TwoVesselBackend(scene)
        options = {'experiment': EXPERIMENT, 'conditions': CONDITIONS, 'execution_scope': execution_scope()}
        request_text = ('Please pour one premeasured portion of water from A into C, '
                        'return the donor to A and go HOME, then check the result.')
    elif args.execution == 'mujoco':
        from openarms_lab.mujoco_scene import MujocoSceneService
        from openarms_lab.mujoco_backend import MujocoBackend
        from openarms_lab.simulation_evaluation import SimulationSkillEvaluator, simulation_scope
        scene = MujocoSceneService(args.out/'scene')
        expert = expert_from_arguments(args, args.out/'expert', artifact_roots=[scene.artifact_dir])
        evaluator = SimulationSkillEvaluator(args.out/'evaluations')
        factory = lambda: MujocoBackend(scene)
        options['execution_scope'] = simulation_scope()
    lab = Lab(args.out/'sessions', expert=expert, perception=scene, evaluator=evaluator,
              backend_factory=factory, expert_timeout=240, **options)
    sid = (await lab.create())['session_id']
    try:
        began = time.perf_counter()
        cold_started = time.time()
        queued = await lab.converse(sid, request_text, 'cold-request')
        cold_ack = time.time()
        progress = await lab.converse(sid, 'What are you doing?', 'cold-follow-up')
        assert [t['task_id'] for t in progress['tasks']] == [queued['tasks'][-1]['task_id']]
        cold = await settle(lab, sid, approve=True)
        (args.out/'cold.json').write_text(json.dumps(cold, indent=2))
        task = cold['tasks'][-1]
        assert task['status'] == 'completed', task.get('summary')
        assert task['observations'] and task['observations'][-1]['status'] == 'observed'
        answered = await lab.converse(sid, 'What happened?', 'cold-result-question')
        assert answered['messages'][-1]['text'] == task['observations'][-1]['text']
        assert len(answered['tasks']) == len(cold['tasks'])
        (args.out/'student-follow-ups.json').write_text(json.dumps({
            'in_progress': progress['messages'][-2:], 'result': answered['messages'][-2:],
        }, indent=2))
        plan = task['plan']
        assert plan['skill_id'], 'Expert did not author a reusable candidate'
        decision = await lab.evaluate_candidate(sid, plan['skill_id'], plan['skill_version'])
        print(json.dumps({'evaluation': decision}), flush=True)
        assert decision['status'] == 'promoted', decision
        skill = lab.registry.get(plan['skill_id'])
        request = skill['retrieval_examples'][-1]
        for key, value in plan['bindings'].items():
            request = request.replace('{'+key+'}', str(value).replace('_', ' '))
        prepared = await lab.converse(sid, 'Prepare a new trial', 'prepare-repeat')
        assert prepared['trial']['trial_id'] != cold['trial']['trial_id']
        warm_started = time.time()
        await lab.converse(sid, request, 'warm-request')
        warm_ack = time.time()
        warm = await settle(lab, sid, approve=True)
        (args.out/'warm.json').write_text(json.dumps(warm, indent=2))
        task2 = warm['tasks'][-1]
        assert task2['status'] == 'completed' and task2['route'] == 'active_skill'
        assert task2['plan']['skill_version'] == skill['version'], 'Warm request changed the admitted version'
        assert not task2['expert_runs'], 'Warm successful skill invoked the expert'
        assert task2['plan']['bindings'] == plan['bindings']
        assert warm['pending'] is None and task2['observations'][-1]['status'] == 'observed'
        negatives = await demo_bench_negatives(lab, sid, request) if args.scene == 'demo_bench' else None
        if args.scene == 'two_vessel':
            observed = task2['observations'][-1]
            assert observed['status'] == 'observed' and observed['provenance'] == 'SIMULATED'
            assert observed['features']['receiver_appearance'] == 'water_appearance'
            assert all(observed['checks'].values()), observed
        summary = {'expert_configuration': expert.describe(), 'expert_runs': task['expert_runs'],
                   'provider': task['expert_runs'][0]['provider'], 'model': task['expert_runs'][0]['model'],
                   'requested_model': task['expert_runs'][0].get('requested_model'),
                   'actual_model': task['expert_runs'][0].get('actual_model'),
                   'reasoning_effort': task['expert_runs'][0]['reasoning_effort'],
                   'provenance': 'SIMULATED' if args.execution == 'mujoco' else 'SYNTHETIC',
                   'execution_backend': args.execution, 'execution_scope': options['execution_scope'],
                   'scene': args.scene,
                   'actual_expert': True, 'audible_voice_verified': False,
                   'cold_model_calls': sum(run['calls'] for run in task['expert_runs']),
                   'warm_model_calls': 0, 'warm_request': request, 'promotion': decision,
                   'cold_timing': timing(cold, cold_started, cold_ack),
                   'warm_timing': timing(warm, warm_started, warm_ack), 'negative_checks': negatives,
                   'elapsed_seconds': time.perf_counter()-began}
        (args.out/'summary.json').write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2), flush=True)
    finally:
        (args.out/'final-state.json').write_text(json.dumps(lab.snapshot(sid), indent=2))
        await lab.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
