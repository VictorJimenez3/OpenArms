import copy

import pytest

from agentic.openarms_lab.runtime import Lab
from agentic.tests.test_demo_bench_runtime import make_lab, settled


class QuestionExpert:
    def __init__(self, question='Do you mean pour the contents into the other container?'):
        self.question = question
        self.contexts = []

    async def run(self, context, **kwargs):
        self.contexts.append(copy.deepcopy(context))
        return {'kind': 'clarification', 'summary': 'Sample selection remains unspecified.',
                'payload': {'question': self.question}, 'provider': 'TEST_FAKE', 'model': 'question-fixture',
                'calls': 1, 'usage': {}, 'elapsed_ms': 1, 'tool_receipts': []}


@pytest.mark.asyncio
async def test_actual_question_is_visible_and_retained_for_followup(tmp_path):
    expert = QuestionExpert()
    lab = Lab(tmp_path, expert=expert)
    try:
        sid = (await lab.create())['session_id']
        handle = await lab.start_task(sid, 'put one cup into the other')
        await settled(lab, handle)
        snapshot = lab.snapshot(sid)
        assert snapshot['tasks'][-1]['status'] == 'needs_clarification'
        assert snapshot['tasks'][-1]['summary'] == expert.question
        assert snapshot['messages'][-1]['text'] == expert.question
        assert snapshot['pending'] is None
        handle = await lab.start_task(sid, 'Yes, pour the contents.')
        await settled(lab, handle)
        assert expert.contexts[-1]['clarification']['question'] == expert.question
        assert lab.backends[sid].executions == 0
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize('question', [None, '', '  ', {}, 'x' * 4001])
async def test_invalid_question_keeps_the_bounded_summary(tmp_path, question):
    lab = Lab(tmp_path, expert=QuestionExpert(question))
    try:
        sid = (await lab.create())['session_id']
        await settled(lab, await lab.start_task(sid, 'Which action?'))
        assert lab.snapshot(sid)['messages'][-1]['text'] == 'Sample selection remains unspecified.'
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_fixed_demo_does_not_require_an_unbound_sample_choice(tmp_path):
    expert = QuestionExpert()
    _, lab = make_lab(tmp_path, expert)
    try:
        sid = (await lab.create())['session_id']
        await settled(lab, await lab.start_task(sid, 'go from a to c please'))
        context = expert.contexts[0]
        assert 'add_sample' in context['capability_limits']['supported_operations']
        assert 'Ask which sample when neither is specified.' not in context['instructions']
        assert 'Do not require a separate sample selection' in context['instructions']
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
async def test_selectable_sample_operation_keeps_its_selection_requirement(tmp_path):
    expert = QuestionExpert()
    lab = Lab(tmp_path, expert=expert)
    try:
        sid = (await lab.create())['session_id']
        await settled(lab, await lab.start_task(sid, 'Test the sample'))
        assert 'Ask which sample when neither is specified.' in expert.contexts[0]['instructions']
    finally:
        await lab.shutdown()
