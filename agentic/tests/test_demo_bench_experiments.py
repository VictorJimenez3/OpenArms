"""Smartivity experiments on the shared demo bench and independent observer."""
import numpy as np
import pytest

from agentic.openarms_lab import two_vessel_scene
from agentic.openarms_lab.demo_bench import _coloured, _masks, anchors, execution_scope, read_pixels
from agentic.openarms_lab.demo_bench_worker import experiment_contents, experiment_name, run_worker
from agentic.openarms_lab.live import system_prompt
from agentic.tests.test_demo_bench_runtime import PourExpert, make_lab, settled

EXPECTED = {'volcano': ('red_liquid', 'red_liquid'), 'potions': ('blue_liquid', 'pink_liquid', 'purple_liquid'),
            'lava_lamp': ('red_liquid', 'red_liquid')}


def test_unknown_experiment_is_refused(monkeypatch):
    monkeypatch.setenv('OPENARMS_DEMO_EXPERIMENT', 'not-a-kit')
    with pytest.raises(ValueError, match='Unknown demo bench experiment'):
        experiment_name()


def test_voice_uses_the_selected_demo_bench_experiment():
    prompt = system_prompt(lambda: {'experiment': {'id': 'demo_bench_pour', 'title': 'Lava Lamp'}})
    assert 'Name the selected experiment from experiment.title' in prompt
    assert 'wait for student confirmation' in prompt
    assert 'current lab is a simulated indicator activity' not in prompt


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

    altered = frames['nominal'].copy()
    cx, cy = np.rint(anchor['C']).astype(int)
    area = np.s_[cy-30:cy+20, cx-45:cx+45]
    mask = _coloured(altered[area]) & ~_masks(altered)['marker_c'][area]
    altered[area][mask] = [132, 240, 240]
    result = read_pixels(altered, anchor)
    assert result['ready'] is False and 'known simulated colour' in result['reason']
    altered[area][mask] = [210, 210, 210]
    with pytest.raises(ValueError, match='readable receiver'):
        anchors(altered)


@pytest.mark.asyncio
@pytest.mark.parametrize(('name', 'color'), [('potions', 'purple'), ('lava_lamp', 'red')])
async def test_opt_in_experiment_pour_uses_the_consented_loop(tmp_path, monkeypatch, name, color):
    monkeypatch.setenv('OPENARMS_DEMO_EXPERIMENT', name)
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
        assert outcome['features']['receiver_appearance'] == f'{color}_liquid'
        assert f'{color} liquid' in outcome['text']
        assert lab.backends[sid].executions == 1
    finally:
        await lab.shutdown()
