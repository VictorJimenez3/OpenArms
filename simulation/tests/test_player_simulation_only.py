"""A simulation-only experiment may use non-real_bench substances as a note; hazards always block."""
from openarms_sim.config import load_chemistry_config
from openarms_sim.player import Player


def reasons(allow, mixture):
    player = Player.__new__(Player)
    player.chem_cfg, player.allow_simulation_only, player.issues, player.step = load_chemistry_config(), allow, [], None
    player._seen = set()
    return player._unsafe_reasons(mixture), [(i.severity, i.code) for i in player.issues]


def test_default_blocks_simulation_only_substances():
    blocking, notes = reasons(False, {'magic_tea': 1, 'citric_acid': 1})
    assert blocking and notes == []


def test_simulation_only_experiment_turns_them_into_notes_but_keeps_hazards():
    blocking, notes = reasons(True, {'magic_tea': 1, 'citric_acid': 1})
    assert blocking == [] and notes == [('note', 'simulation_only')]
    blocking, _ = reasons(True, {'bleach': 1, 'vinegar': 1})
    assert blocking
