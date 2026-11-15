"""Do it once, then fast: confirmed, observed successes teach the registry the student's own wording."""
import pytest

from agentic.openarms_lab.contracts import SkillDefinition
from agentic.openarms_lab.skills import SkillRegistry
from agentic.tests.test_demo_bench_runtime import DEFINITION as DEMO, PourExpert, make_lab, settled
from agentic.tests.test_task_loop import DEFINITION, TestEvaluator as FakeEvaluator

WORDING = 'Pour the beaker at A into the container at C once, put the beaker back at A and go home.'


async def active_demo(tmp_path):
    registry = SkillRegistry(tmp_path / 'skills.json')
    version = registry.validate_for_task('t', SkillDefinition.model_validate(DEMO))
    result = await FakeEvaluator().evaluate_candidate('s', registry.get(DEMO['skill_id'], version), None)
    assert registry.record_evaluation(DEMO['skill_id'], version, result)['status'] == 'promoted'
    return registry, version


@pytest.mark.asyncio
async def test_learned_wording_routes_only_to_the_exact_active_version_and_bindings(tmp_path):
    registry, version = await active_demo(tmp_path)
    assert registry.match(WORDING) is None
    route = registry.learn_route(WORDING, DEMO['skill_id'], version, {'source': 'A', 'into': 'C'})
    assert route['template'] == 'pour the beaker at {source} into the container at {into} once put the beaker back at {source} and go home'
    match = registry.match(WORDING)
    assert (match.skill_id, match.skill_version, match.bindings) == (DEMO['skill_id'], version, {'source': 'A', 'into': 'C'})
    assert registry.match('Please ' + WORDING.lower()) is not None
    assert registry.match('Do not ' + WORDING) is None
    assert registry.match(WORDING.replace('once', 'twice')) is None
    restored = SkillRegistry(tmp_path / 'skills.json')
    assert restored.match(WORDING).skill_version == version


@pytest.mark.asyncio
async def test_unsafe_or_ambiguous_wording_is_not_learned(tmp_path):
    registry, version = await active_demo(tmp_path)
    bind = {'source': 'A', 'into': 'C'}
    assert registry.learn_route('Pour the beaker into the container and go home.', DEMO['skill_id'], version, bind) is None
    assert registry.learn_route("Don't pour A into C.", DEMO['skill_id'], version, bind) is None
    assert registry.learn_route('Pour A into C.', DEMO['skill_id'], 'f' * 64, bind) is None
    assert registry.learn_route('Pour A into C.', DEMO['skill_id'], version, {'source': 'A', 'into': 'A'}) is None
    assert registry.data['routes'] == []


@pytest.mark.asyncio
async def test_learned_route_stops_applying_when_the_active_version_changes(tmp_path):
    registry = SkillRegistry(tmp_path / 'skills.json')
    old = registry.validate_for_task('first', SkillDefinition.model_validate(DEFINITION))
    result = await FakeEvaluator().evaluate_candidate('s', registry.get('sample_color', old), None)
    registry.record_evaluation('sample_color', old, result)
    assert registry.learn_route('Could you check the vinegar sample for me', 'sample_color', old, {'condition': 'vinegar'})
    assert registry.match('could you check the water sample for me').bindings == {'condition': 'water'}
    registry.data['active'].pop('sample_color')
    assert registry.match('Could you check the vinegar sample for me') is None


@pytest.mark.asyncio
async def test_second_request_in_new_wording_and_do_it_again_skip_the_expert(tmp_path):
    expert = PourExpert()
    scene, lab = make_lab(tmp_path, expert)
    lab.evaluator, lab.auto_evaluate = FakeEvaluator(), True
    try:
        sid = (await lab.create())['session_id']

        async def run(text):
            if lab.snapshot(sid)['tasks']:
                await lab.prepare(sid)
            handle = await lab.start_task(sid, text)
            await settled(lab, handle)
            state = lab.snapshot(sid)
            pending = state['pending']
            assert pending, state['tasks'][-1]['summary']
            exact = (sid, pending['request_id'], pending['proposal_version'])
            await lab.present(*exact)
            await lab.confirm(*exact)
            await settled(lab, handle)
            task = lab.snapshot(sid)['tasks'][-1]
            assert task['status'] == 'completed', task['summary']
            return task

        first = await run(WORDING)
        assert first['route'] == 'expert'
        planning_calls = len([c for c in expert.contexts if c['phase'] == 'planning'])
        second = await run(WORDING)
        assert second['route'] == 'active_skill' and second['expert_runs'] == []
        again = await run('Do it again')
        assert again['route'] == 'active_skill' and again['expert_runs'] == []
        assert again['plan']['skill_version'] == first['plan']['skill_version']
        assert len([c for c in expert.contexts if c['phase'] == 'planning']) == planning_calls
        assert lab.backends[sid].executions == 3
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_do_it_again_without_a_prior_success_does_not_invent_an_action(tmp_path):
    scene, lab = make_lab(tmp_path)
    try:
        sid = (await lab.create())['session_id']
        handle = await lab.start_task(sid, 'Do it again')
        await settled(lab, handle)
        task = lab.snapshot(sid)['tasks'][-1]
        assert task['route'] == 'expert'
    finally:
        await lab.shutdown()
