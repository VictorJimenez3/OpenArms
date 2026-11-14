from openarms_sim import example_plan, preview
from openarms_sim.config import load_bench, load_poses
from openarms_sim.two_vessel import VARIANTS, capture, observe


def test_liquid_setup_pours_one_portion_and_returns_the_donor():
    bench = load_bench('liquid')
    assert bench.sources == ['A'] and bench.receivers == ['C'] and not bench.objects
    result = preview(example_plan(setup='liquid'), setup='liquid', render=False)
    assert result['ok'] and result['returned_to_dock'] and result['home_reached']
    assert result['transfer'] == [{'source': 'A', 'into': 'C', 'added': {'water': 1}}]
    assert result['predicted'][0]['provenance'] == 'MODELED'
    assert result['inventory'] == {'A': {}, 'C': {'water': 1}}
    assert result['physical_execution'] is False and result['provenance'] == 'SIMULATED'


def test_cannot_report_a_modeled_outcome_for_spill_empty_or_overflow():
    plan = example_plan(setup='liquid')
    poses = load_poses('liquid')
    for name in ('ABOVE_C', 'TIP_C'):
        poses[name]['shoulder_pan'] -= 18
    spill = preview(plan, setup='liquid', poses=poses, render=False)
    assert not spill['ok'] and any(i['code'] == 'spill' for i in spill['issues'])
    overflow = preview(plan, setup='liquid', contents={'C': {'water': 4}}, render=False)
    assert not overflow['ok'] and any(i['code'] == 'overflow' for i in overflow['issues'])
    empty = preview(plan, setup='liquid', contents={'A': {}}, render=False)
    for result in (spill, overflow, empty):
        assert result['transfer'] == result['predicted'] == []


def test_actual_overviews_classify_faults_and_a_fresh_generation(tmp_path):
    frames = {name: capture(tmp_path / f'{name}.png', variant=name, generation=1, timestamp_s=100)
              for name in VARIANTS}
    reference = frames['nominal']
    cases = {name: observe(frame, reference, now_s=100, generation=1) for name, frame in frames.items()}
    assert cases['nominal']['ready']
    assert cases['camera_shift']['camera_registration'] == 'shifted'
    assert cases['swapped']['stations']['A']['status'] == 'unexpected_vessel'
    assert cases['missing']['stations']['A']['status'] == cases['occluded']['stations']['A']['status'] == 'unreadable'
    assert all(not cases[name]['ready'] for name in VARIANTS if name != 'nominal')
    assert not observe(reference, reference, now_s=107, generation=1)['ready']
    assert not observe(reference, reference, now_s=100, generation=2)['ready']
    reset = capture(tmp_path / 'reset.png', generation=2, timestamp_s=107)
    assert reset['evidence_id'] != reference['evidence_id']
    assert observe(reset, reference, now_s=107, generation=2)['ready']
    assert not observe({**reset, 'sha256': 'wrong'}, reference, now_s=107, generation=2)['ready']

    frame_path = tmp_path / 'after.png'
    result = preview(example_plan(setup='liquid'), setup='liquid', render=False, overview_path=frame_path)
    assert result['ok']
    after = observe(frame_path, reference)
    assert after['receiver_appearance']['state'] == 'water_appearance'
    assert cases['nominal']['receiver_appearance']['state'] == 'dark_base_visible'
