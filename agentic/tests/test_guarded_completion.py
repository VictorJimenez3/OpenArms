"""Skip only the clean post-observation expert call on the demo bench; anything unclear still escalates."""
import pytest

from agentic.openarms_lab.task_loop import TaskLoop
from agentic.tests.test_demo_bench_runtime import PourExpert, make_lab, settled


async def pour(lab, sid, text='Pour the beaker from A into C, then return it to A and go HOME.'):
    handle = await lab.start_task(sid, text)
    await settled(lab, handle)
    pending = lab.snapshot(sid)['pending']
    exact = (sid, pending['request_id'], pending['proposal_version'])
    await lab.present(*exact)
    await lab.confirm(*exact)
    await settled(lab, handle)
    return lab.snapshot(sid)['tasks'][-1]


def feedback_calls(expert):
    return [c for c in expert.contexts if c['phase'] == 'execution_feedback']


def test_guarded_completion_is_opt_in():
    assert TaskLoop.guarded_demo_bench_completion is False


@pytest.mark.asyncio
@pytest.mark.parametrize('checkpoint,completion,expected', [(False, False, 2), (True, False, 1), (False, True, 1), (True, True, 0)])
async def test_clean_demo_pour_skips_only_the_guarded_calls(tmp_path, checkpoint, completion, expected):
    expert = PourExpert()
    scene, lab = make_lab(tmp_path, expert)
    lab.guarded_demo_bench_checkpoint, lab.guarded_demo_bench_completion = checkpoint, completion
    try:
        sid = (await lab.create())['session_id']
        task = await pour(lab, sid)
        assert task['status'] == 'completed', task['summary']
        assert len(feedback_calls(expert)) == expected
        assert lab.backends[sid].executions == 1
        assert task['summary'] == task['observations'][-1]['text']
        marked = [f for f in task['feedback'] if f['type'] == 'deterministic_completion']
        assert len(marked) == (1 if completion else 0)
        if completion:
            assert marked[0]['evidence_id'] in task['observations'][-1]['evidence']
    finally:
        await lab.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize('pixels', [{'ready': False, 'camera_registration': 'unknown', 'reason': 'Occluded.'},
                                    {'ready': True, 'camera_registration': 'registered', 'donor': 'liquid_visible',
                                     'receiver': 'red_liquid', 'held': False}])
async def test_unclear_or_failed_outcome_still_reaches_the_expert(tmp_path, pixels):
    expert = PourExpert()
    scene, lab = make_lab(tmp_path, expert)
    lab.guarded_demo_bench_checkpoint = lab.guarded_demo_bench_completion = True
    observe = scene.observe

    async def faulty(sid, receipt):
        scene._observe_pixels = lambda *_: dict(pixels)
        return await observe(sid, receipt)

    scene.observe = faulty
    try:
        sid = (await lab.create())['session_id']
        task = await pour(lab, sid)
        assert feedback_calls(expert), 'An unknown or failed observation must be escalated.'
        assert not any(f['type'] == 'deterministic_completion' for f in task['feedback'])
        assert lab.backends[sid].executions == 1
    finally:
        await lab.shutdown()


@pytest.mark.parametrize('setting,expected', [(None, True), ('0', False)])
def test_demo_bench_app_enables_the_guarded_fast_path_unless_disabled(tmp_path, monkeypatch, setting, expected):
    from fastapi.testclient import TestClient
    from agentic.openarms_lab.app import create_app
    monkeypatch.setenv('OPENARMS_EXECUTION', 'mujoco')
    monkeypatch.setenv('OPENARMS_SCENE', 'demo_bench')
    monkeypatch.setenv('OPENARMS_DATA_DIR', str(tmp_path/'application'))
    monkeypatch.delenv('OPENARMS_DEMO_TOKEN', raising=False)
    if setting is None:
        monkeypatch.delenv('OPENARMS_DEMO_FAST_PATH', raising=False)
    else:
        monkeypatch.setenv('OPENARMS_DEMO_FAST_PATH', setting)
    app = create_app()
    with TestClient(app):
        assert app.state.lab.guarded_demo_bench_checkpoint is expected
        assert app.state.lab.guarded_demo_bench_completion is expected
        assert app.state.lab.fast_planning_context is expected
    assert TaskLoop.guarded_demo_bench_checkpoint is False and TaskLoop.guarded_demo_bench_completion is False
