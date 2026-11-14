import copy
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agentic.openarms_lab.simulation_evaluation import SimulationSkillEvaluator, simulation_scope
from agentic.tests.test_task_loop import DEFINITION


def test_admission_scope_changes_when_apparatus_code_changes_without_a_version_label(monkeypatch):
    original = simulation_scope()
    read_bytes = Path.read_bytes

    def changed(path):
        data = read_bytes(path)
        return data + b'\n# changed apparatus implementation' if path.as_posix().endswith('lab_demos/ph/run.py') else data

    monkeypatch.setattr(Path, 'read_bytes', changed)
    assert simulation_scope() != original


@pytest.mark.asyncio
async def test_failed_simulation_binding_blocks_otherwise_passing_synthetic_admission(tmp_path):
    evaluator = SimulationSkillEvaluator(tmp_path)
    fixture = {'evaluation_id': 'case', 'passed': True, 'suite_hash': 'fixture',
               'regression_gates': {}, 'metrics': {}, 'reasons': [], 'artifact_hashes': []}
    evaluator.fixture.evaluate_candidate = AsyncMock(return_value=fixture)
    evaluated = []

    async def case(folder, definition, bindings):
        evaluated.append(bindings)
        return {'passed': bindings['condition'] != 'water', 'bindings': bindings}

    evaluator._case = case
    candidate = copy.deepcopy(DEFINITION)
    receipt = await evaluator.evaluate_candidate('session', candidate, None)
    assert evaluated == [{'condition': 'vinegar'}, {'condition': 'water'}]
    assert receipt['passed'] is False
    assert receipt['regression_gates']['mujoco_parameters'] is False
    assert fixture['passed'] is True
    assert receipt['artifact_hashes']
