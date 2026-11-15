"""Joseph's Smartivity experiments on Duc/Stefanie's demo bench: same arm, frame, poses, camera and observer."""
import pytest

from agentic.openarms_lab import two_vessel_scene
from agentic.openarms_lab.demo_bench import anchors, execution_scope, read_pixels
from agentic.openarms_lab.demo_bench_worker import experiment_contents, experiment_name, run_worker
from agentic.tests.test_demo_bench_runtime import PourExpert, make_lab, settled

EXPECTED = {'volcano': ('red_liquid', 'red_liquid'), 'potions': ('blue_liquid', 'pink_liquid', 'purple_liquid'),
            'lava_lamp': ('red_liquid', 'red_liquid')}


def test_unknown_experiment_is_refused(monkeypatch):
    monkeypatch.setenv('OPENARMS_DEMO_EXPERIMENT', 'not-a-kit')
    with pytest.raises(ValueError, match='Unknown demo bench experiment'):
        experiment_name()


def test_volcano_keeps_the_bench_contents_and_each_experiment_has_its_own_scope(monkeypatch):
    monkeypatch.delenv('OPENARMS_DEMO_EXPERIMENT', raising=False)
    assert experiment_contents() is None
    scopes = set()
    for name in EXPECTED:
        monkeypatch.setenv('OPENARMS_DEMO_EXPERIMENT', name)
        scopes.add(execution_scope())
    assert len(scopes) == len(EXPECTED)


@pytest.mark.asyncio
@pytest.mark.parametrize('name', sorted(EXPECTED))
async def test_each_experiment_reads_on_the_shared_observer_and_faults_fail_closed(tmp_path, monkeypatch, name):
    monkeypatch.setenv('OPENARMS_DEMO_EXPERIMENT', name)
    frames = {}
    for variant in ('nominal', 'camera_shift', 'missing', 'swapped', 'occluded'):
        result = await run_worker(tmp_path, {'kind': 'capture', 'variant': variant, 'generation': 0})
        frames[variant] = two_vessel_scene.fixture._pixels(result['raw_frame'])
    anchor = anchors(frames['nominal'])
    nominal = read_pixels(frames['nominal'], anchor)
    assert nominal['ready'] and nominal['donor'] == 'liquid_visible'
    assert nominal['receiver'] == (EXPECTED[name][1] if name == 'potions' else EXPECTED[name][0])
    for variant in ('camera_shift', 'missing', 'swapped', 'occluded'):
        assert read_pixels(frames[variant], anchor)['ready'] is False, variant


@pytest.mark.asyncio
async def test_magic_potions_pour_turns_the_flask_purple_through_the_consented_loop(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENARMS_DEMO_EXPERIMENT', 'potions')
    scene, lab = make_lab(tmp_path, PourExpert())
    try:
        sid = (await lab.create())['session_id']
        handle = await lab.start_task(sid, 'Pour the cup at A into the flask at C, then return it to A and go HOME.')
        await settled(lab, handle)
        pending = lab.snapshot(sid)['pending']
        exact = (sid, pending['request_id'], pending['proposal_version'])
        await lab.present(*exact)
        await lab.confirm(*exact)
        await settled(lab, handle)
        task = lab.snapshot(sid)['tasks'][-1]
        assert task['status'] == 'completed', task['summary']
        outcome = task['observations'][-1]
        assert outcome['features']['donor_appearance'] == 'empty'
        assert outcome['features']['receiver_appearance'] == 'purple_liquid'
        assert 'purple liquid' in outcome['text']
        assert lab.backends[sid].executions == 1
    finally:
        await lab.shutdown()
