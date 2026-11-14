"""Reviewed symbolic pH recipe. This artifact grants no hardware capability.

Qualitative scope follows research/victor/laboratory-experiments-and-feasibility.md,
section 3. Bench qualification remains pending; this is a mock fixture only.
"""
from __future__ import annotations
from pydantic import Field
from .contracts import FrozenModel

class PhSkill(FrozenModel):
    skill_id: str = 'red_cabbage_ph.v1'
    version: str = '1.0.0'
    name: str = 'Prepared red-cabbage indicator trial (MOCK)'
    source: str = 'A'
    destination: str = 'C'
    conditions: tuple[str, ...] = ('vinegar', 'baking_soda', 'water')
    steps: tuple[str, ...] = ('check_prepared_condition', 'mock_dose', 'return_home')
    observation_policy: str = 'separate_qualitative_reference_or_unknown'
    preconditions: tuple[str, ...] = ('HOME', 'empty_gripper', 'fresh_receiver', 'prepared_condition')
    mock_approved: bool = True
    physical_approved: bool = False
    provenance: str = 'APPLICATION-AUTHORED-MOCK'
    evidence: tuple[str, ...] = ('agentic/tests/test_lab_adapter.py', 'agentic/tests/test_ph_runtime.py')
    limitations: str = 'Symbolic execution only; no fluid simulation, sensor, measured pH or physical actuation.'

PH_SKILL = PhSkill()

def install_recipes(registry):
    registry.install_builtin(PH_SKILL.model_dump(mode='json'))
