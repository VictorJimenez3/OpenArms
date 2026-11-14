"""Record an actual synthetic failure, ask the selected expert to revise, compare pinned versions."""
import argparse
import asyncio
import copy
import json
import shutil
from pathlib import Path

from openarms_lab.expert_profiles import add_expert_arguments, expert_from_arguments
from openarms_lab.evaluation import SyntheticSkillEvaluator
from openarms_lab.runtime import Lab
from openarms_lab.scene import SceneService
from openarms_lab.simulated_backend import SceneBackend
from full_loop_rehearsal import settle


class ObscuredAfterAction(SceneBackend):
    async def execute_step(self, *args, **kwargs):
        result = await super().execute_step(*args, **kwargs)
        self.scene_service.world(self.session_id).occluded_primary = True
        return result


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    add_expert_arguments(parser)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    data = args.out/'sessions'
    data.mkdir()
    shutil.copyfile(args.baseline/'sessions/task-skills.json', data/'task-skills.json')
    scene = SceneService(args.out/'scene')
    expert = expert_from_arguments(args, args.out/'expert', artifact_roots=[scene.artifact_dir])
    evaluator = SyntheticSkillEvaluator(args.out/'evaluations')
    lab = Lab(data, expert=expert, perception=scene, evaluator=evaluator,
              backend_factory=lambda: ObscuredAfterAction(scene, delay=.02), expert_timeout=240)
    sid = (await lab.create())['session_id']
    baseline = copy.deepcopy(lab.registry.list()[0])
    (args.out/'unchanged-baseline.json').write_text(json.dumps(baseline, indent=2))
    try:
        request = baseline['retrieval_examples'][0]
        for parameter, spec in baseline['parameter_schema'].items():
            request = request.replace('{'+parameter+'}', str(spec['enum'][0]).replace('_', ' '))
        await lab.converse(sid, request, 'recorded-limitation')
        failed = await settle(lab, sid, approve=True)
        (args.out/'limitation.json').write_text(json.dumps(failed, indent=2))
        task = failed['tasks'][-1]
        assert any(o['status'] == 'unknown' for o in task['observations']), 'No independently observed limitation recorded'
        await lab.prepare(sid)
        scene.world(sid).occluded_primary = False
        await lab.start_improvement(sid, task['task_id'],
            'The primary camera became obscured during the result check. Improve this same reusable skill using '
            'the recorded failure and supported observation tools. Preserve its skill ID, parameter domains, '
            'sample operation, and clear-view behavior. Propose a substantive bounded recovery; do not just rename it.')
        revised = await settle(lab, sid, approve=True)
        (args.out/'revision.json').write_text(json.dumps(revised, indent=2))
        revision = revised['tasks'][-1]
        assert revision['status'] == 'completed', revision.get('summary')
        plan = revision['plan']
        assert plan['skill_id'] == baseline['skill_id'] and plan['skill_version'] != baseline['version']
        candidate = lab.registry.get(plan['skill_id'], plan['skill_version'])
        assert candidate['steps'] != baseline['steps'], 'A new label is not an improvement'
        decision = await lab.evaluate_candidate(sid, plan['skill_id'], plan['skill_version'])
        receipt = lab.registry.data['evaluations'][-1]
        assert decision['baseline_hash'] == baseline['version']
        summary = {'actual_expert': True, 'expert_configuration': expert.describe(),
                   'expert_runs': revision['expert_runs'],
                   'provider': revision['expert_runs'][0]['provider'], 'model': revision['expert_runs'][0]['model'],
                   'reasoning_effort': revision['expert_runs'][0]['reasoning_effort'], 'provenance': 'SYNTHETIC',
                   'limitation_task': task['task_id'], 'decision': decision, 'receipt': receipt,
                   'baseline_steps': baseline['steps'], 'candidate_steps': candidate['steps'],
                   'physical_hardware_used': False}
        (args.out/'summary.json').write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2), flush=True)
    finally:
        (args.out/'final-state.json').write_text(json.dumps(lab.snapshot(sid), indent=2))
        await lab.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
