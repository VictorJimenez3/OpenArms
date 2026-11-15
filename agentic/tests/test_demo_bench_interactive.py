"""Several commands in one demo-bench trial: the bench keeps its state until the student resets it."""
import copy

import pytest

from agentic.openarms_lab.task_loop import student_summary
from agentic.tests.test_demo_bench_runtime import DEFINITION, PourExpert, make_lab, settled


def definition(amount):
    value = copy.deepcopy(DEFINITION)
    value['skill_id'] = f'demo_bench_pour_{amount}'
    value['steps'][1]['arguments']['amount'] = amount
    if amount == 'half':
        value['outcome_checks'] = [{'feature': 'donor_appearance', 'expected': 'liquid_visible'},
                                   {'feature': 'sample_cup_station', 'expected': 'A'}]
    return value


class AmountExpert(PourExpert):
    """Deterministic planner that pours the amount named in the request."""
    async def run(self, context, *, tool_handler, **kwargs):
        self.definition = definition('half' if 'half' in context['request'].lower() else 'all')
        return await super().run(context, tool_handler=tool_handler, **kwargs)


async def command(lab, sid, text):
    handle = await lab.start_task(sid, text)
    await settled(lab, handle)
    state = lab.snapshot(sid)
    pending = state['pending']
    if not pending:
        return state['tasks'][-1], None
    exact = (sid, pending['request_id'], pending['proposal_version'])
    await lab.present(*exact)
    await lab.confirm(*exact)
    await settled(lab, handle)
    return lab.snapshot(sid)['tasks'][-1], pending


@pytest.mark.asyncio
async def test_two_half_pours_then_a_full_pour_without_reset_and_an_empty_beaker_is_refused(tmp_path):
    scene, lab = make_lab(tmp_path, AmountExpert())
    try:
        sid = (await lab.create())['session_id']
        first, pending = await command(lab, sid, 'Pour half of the beaker at A into C, then put it back and go HOME.')
        assert first['status'] == 'completed', first['summary']
        assert 'half of what is in the beaker' in pending['summary']
        assert pending['student_summary'].startswith('The robot will look at the bench, pour half of the liquid')
        assert first['observations'][-1]['features']['donor_appearance'] == 'liquid_visible'
        second, _ = await command(lab, sid, 'Pour half again into C and go HOME.')
        assert second['status'] == 'completed', second['summary']
        third, _ = await command(lab, sid, 'Pour the rest of the beaker from A into C, then return it to A and go HOME.')
        assert third['status'] == 'completed', third['summary']
        assert third['observations'][-1]['features']['donor_appearance'] == 'empty'
        backend = lab.backends[sid]
        assert backend.executions == 3 and backend.state()['pours_done'] == 3
        empty, _ = await command(lab, sid, 'Pour the beaker from A into C, then return it to A and go HOME.')
        assert empty['status'] == 'failed' and 'empty' in (empty['summary'] or '').lower()
        assert backend.executions == 3
        await lab.prepare(sid)
        refilled, _ = await command(lab, sid, 'Pour the beaker from A into C, then return it to A and go HOME.')
        assert refilled['status'] == 'completed', refilled['summary']
        assert backend.state()['pours_done'] == 1
    finally:
        await lab.shutdown()


def test_student_summary_is_plain_and_separate_from_the_exact_summary():
    plan = {'steps': [{'operation': 'inspect_scene', 'arguments': {'view': 'primary'}},
                      {'operation': 'add_sample', 'arguments': {'source': 'A', 'into': 'C', 'portions': 1, 'amount': 'all'}},
                      {'operation': 'observe', 'arguments': {'view': 'primary'}}]}
    text = student_summary(plan)
    assert text == ('The robot will look at the bench, pour all the liquid from the beaker at A into the container at C, '
                    'then put the beaker back and take a picture to check what happened. Nothing moves until you say confirm.')
