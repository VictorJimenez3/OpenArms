"""Fewer cold planning turns: identical duplicated fields are not an override; the host localizes up front."""
import copy

import pytest

from agentic.openarms_lab.contracts import PlanDraft
from agentic.openarms_lab.skills import SkillRegistry
from agentic.openarms_lab.task_loop import TaskLoop
from agentic.tests.test_demo_bench_runtime import DEFINITION, make_lab, settled


def plan(**top):
    return PlanDraft.model_validate({'skill_definition': DEFINITION, 'bindings': {'source': 'A', 'into': 'C'}, **top})


def test_identical_duplicates_compile_like_the_plain_definition(tmp_path):
    registry = SkillRegistry(tmp_path / 'skills.json')
    plain = registry.compile(plan())
    duplicated = registry.compile(plan(preconditions=DEFINITION['preconditions'], expected_state=DEFINITION['expected_state'],
                                       outcome_checks=DEFINITION['outcome_checks']))
    assert duplicated == plain


@pytest.mark.parametrize('top', [{'expected_state': {'at': 'A'}},
                                 {'outcome_checks': [{'feature': 'donor_appearance', 'expected': 'liquid_visible'}]},
                                 {'preconditions': {'fresh_scene': True, 'labels': ['source']}},
                                 {'steps': [{'operation': 'inspect_scene'}]}])
def test_conflicting_or_extra_top_level_fields_still_cannot_override(tmp_path, top):
    with pytest.raises(ValueError, match='override'):
        SkillRegistry(tmp_path / 'skills.json').compile(plan(**top))


class CountingExpert:
    def __init__(self):
        self.contexts, self.tools = [], []

    async def run(self, context, *, tool_handler, **_):
        self.contexts.append(copy.deepcopy(context))
        if context['phase'] != 'planning':
            return {'kind': 'complete', 'summary': 'ok', 'payload': {'continue': True}}
        if not context.get('host_localization'):
            self.tools.append('localize_objects')
            await tool_handler('localize_objects', {'evidence_id': context['images'][0]['evidence_id'],
                                                    'labels': ['source', 'receiver']})
        return {'kind': 'plan', 'summary': 'Pour A into C.',
                'payload': {'skill_definition': DEFINITION, 'bindings': {'source': 'A', 'into': 'C'}}}


def test_fast_planning_context_is_opt_in():
    assert TaskLoop.fast_planning_context is False


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
async def test_host_localization_reaches_the_planner_and_saves_its_tool_turn(tmp_path, enabled):
    expert = CountingExpert()
    scene, lab = make_lab(tmp_path, expert)
    lab.fast_planning_context = enabled
    try:
        sid = (await lab.create())['session_id']
        handle = await lab.start_task(sid, 'Pour the beaker from A into C, then return it to A and go HOME.')
        await settled(lab, handle)
        state = lab.snapshot(sid)
        assert state['tasks'][-1]['status'] == 'awaiting_confirmation', state['tasks'][-1]['summary']
        planning = expert.contexts[0]
        if enabled:
            receipt = planning['host_localization']
            assert receipt['evidence_id'] == planning['images'][0]['evidence_id']
            assert set(receipt['verified_labels']) >= {'source', 'receiver'}
            assert expert.tools == []
        else:
            assert 'host_localization' not in planning and expert.tools == ['localize_objects']
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_failed_host_localization_is_not_injected(tmp_path):
    expert = CountingExpert()
    scene, lab = make_lab(tmp_path, expert)
    lab.fast_planning_context = True

    async def unavailable(*_, **__):
        raise RuntimeError('camera busy')

    scene.localize_objects = unavailable
    try:
        sid = (await lab.create())['session_id']
        handle = await lab.start_task(sid, 'Pour the beaker from A into C, then return it to A and go HOME.')
        await settled(lab, handle)
        assert 'host_localization' not in expert.contexts[0]
    finally:
        await lab.shutdown()


def test_registered_skill_with_repeated_fields_gets_an_actionable_error(tmp_path):
    registry = SkillRegistry(tmp_path / 'skills.json')
    with pytest.raises(ValueError, match='only skill_id, skill_version and bindings'):
        registry.compile(PlanDraft.model_validate({'skill_id': 'x', 'skill_version': 'y', 'bindings': {},
                                                   'expected_state': {'at': 'HOME'}}))


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
async def test_fast_planning_tells_the_planner_to_return_the_plan_directly(tmp_path, enabled):
    expert = CountingExpert()
    scene, lab = make_lab(tmp_path, expert)
    lab.fast_planning_context = enabled
    try:
        sid = (await lab.create())['session_id']
        handle = await lab.start_task(sid, 'Pour the beaker from A into C, then return it to A and go HOME.')
        await settled(lab, handle)
        text = expert.contexts[0]['instructions']
        assert ('validates the returned plan itself' in text) is enabled
        assert ('only skill_id, skill_version and bindings' in text) is enabled
    finally:
        await lab.shutdown()
