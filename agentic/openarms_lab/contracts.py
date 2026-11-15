"""Strict, immutable bindings for the server-owned mock pH trial."""
from __future__ import annotations
from typing import Any, Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field

ConditionId = Literal['vinegar', 'baking_soda', 'water']
Provenance = Literal['REAL', 'SIMULATED', 'MOCK', 'MODEL-PREDICTED', 'UNKNOWN']
UUID_PATTERN = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'

class FrozenModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)

class Parameters(FrozenModel):
    condition_id: ConditionId
    source: Literal['A'] = 'A'
    destination: Literal['C'] = 'C'
    preparation: Literal['prepared_sample_with_ph_indicator'] = 'prepared_sample_with_ph_indicator'

class SkillRequest(FrozenModel):
    request_id: str = Field(pattern=UUID_PATTERN)
    session_id: str = Field(pattern=UUID_PATTERN)
    trial_id: str = Field(pattern=UUID_PATTERN)
    proposal_version: int = Field(ge=1)
    generation: int = Field(ge=0)
    skill_id: Literal['indicator_ph.v1']
    skill_version: Literal['1.0.0']
    skill_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    prediction: str = Field(min_length=1, max_length=4000)
    parameters: Parameters

class Observation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: str = Field(pattern=UUID_PATTERN)
    trial_id: str = Field(pattern=UUID_PATTERN)
    provenance: Literal['MODEL-PREDICTED', 'UNKNOWN']
    text: str
    source: str
    evidence: list[str] = Field(default_factory=list)
    value: Any = None

class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: str = Field(pattern=UUID_PATTERN)
    trial_id: str = Field(pattern=UUID_PATTERN)
    backend: Literal['mock'] = 'mock'
    status: Literal['completed', 'failed', 'stopped', 'unknown']
    operator_authorized: Literal[False] = False
    controller_completed: bool = False
    physical_success: None = None
    evidence_id: str
    reason: str | None = None
    # Execution receipt deliberately has no observation field.

class ExecutionBackend(Protocol):
    mode: str
    def capabilities(self) -> dict: ...
    def state(self) -> dict: ...
    def prepare(self) -> None: ...
    async def execute(self, request: SkillRequest, progress) -> ExecutionResult: ...
    async def stop(self) -> None: ...


class LabExecutor(Protocol):
    mode: str
    def capabilities(self) -> dict: ...
    def state(self) -> dict: ...
    def prepare(self) -> None: ...
    def check_step(self, operation: str, arguments: dict) -> Any: ...
    async def execute_step(self, request_id: str, arguments: dict, progress, *, operation: str) -> dict: ...
    async def stop(self) -> None: ...
    async def wait_idle(self) -> None: ...


# These operations are bounded mock actions and read-only observations.
PreparedCondition = Literal['vinegar', 'baking_soda', 'water']
MockOperation = Literal['mock_prepared_sample', 'mock_pick_up', 'mock_put_down', 'mock_pour']
MOCK_OPERATIONS = ('mock_prepared_sample', 'mock_pick_up', 'mock_put_down', 'mock_pour')
# Simulator-typed actions, named as the simulator's own plan action (openarms_sim add_sample).
SimOperation = Literal['add_sample']
ACTION_OPERATIONS = (*MOCK_OPERATIONS, 'add_sample')
PLAN_PRIMITIVES = ('inspect_scene', 'localize_objects', *ACTION_OPERATIONS, 'observe')
SceneView = Literal['primary', 'secondary']


class SkillParameter(FrozenModel):
    type: Literal['string', 'integer', 'number', 'boolean']
    enum: list[str | int | float | bool] | None = Field(default=None, min_length=1, max_length=20)
    minimum: int | float | None = None
    maximum: int | float | None = None


class Step(FrozenModel):
    operation: Literal['inspect_scene', 'localize_objects', 'observe', 'call_skill'] | MockOperation | SimOperation
    arguments: dict[str, Any] = Field(default_factory=dict)


class Preconditions(FrozenModel):
    fresh_scene: bool = False
    labels: list[str] = Field(default_factory=list, max_length=12)


class OutcomeCheck(FrozenModel):
    feature: str = Field(pattern=r'^[a-z][a-z0-9_]{0,63}$')
    expected: str | int | float | bool


class SkillDefinition(FrozenModel):
    skill_id: str = Field(pattern=r'^[a-z][a-z0-9_.-]{0,79}$')
    name: str = Field(min_length=1, max_length=120)
    intent: str = Field(min_length=1, max_length=500)
    retrieval_examples: list[str] = Field(default_factory=list, max_length=20)
    parameter_schema: dict[str, SkillParameter] = Field(default_factory=dict)
    preconditions: Preconditions = Field(default_factory=Preconditions)
    steps: list[Step] = Field(min_length=1, max_length=8)
    expected_state: dict[str, str | int | float | bool] = Field(default_factory=dict)
    outcome_checks: list[OutcomeCheck] = Field(min_length=1, max_length=12)
    limitations: list[str] = Field(min_length=1, max_length=12)
    evidence_ids: list[str] = Field(default_factory=list, max_length=30)


class PlanDraft(FrozenModel):
    skill_definition: SkillDefinition | None = None
    skill_id: str | None = None
    skill_version: str | None = None
    bindings: dict[str, str | int | float | bool] = Field(default_factory=dict)
    steps: list[Step] = Field(default_factory=list, max_length=8)
    preconditions: Preconditions = Field(default_factory=Preconditions)
    expected_state: dict[str, str | int | float | bool] = Field(default_factory=dict)
    outcome_checks: list[OutcomeCheck] = Field(default_factory=list, max_length=12)
    evidence_ids: list[str] = Field(default_factory=list, max_length=30)


class InspectArguments(FrozenModel):
    view: SceneView = 'primary'


class ObserveArguments(InspectArguments):
    fallback_view: SceneView | None = None


class LocalizeArguments(FrozenModel):
    evidence_id: str = Field(min_length=1, max_length=128)
    labels: list[str] = Field(min_length=1, max_length=12)


class MockSampleArguments(FrozenModel):
    condition_id: PreparedCondition
    source: Literal['A'] = 'A'
    destination: Literal['C'] = 'C'


class MockCupArguments(FrozenModel):
    fixture: Literal['sample_cup']
    station: Literal['A', 'B']


class MockPourArguments(FrozenModel):
    fixture: Literal['sample_cup']
    station: Literal['C']
    portions: int = Field(default=1, ge=1, le=1)


class AddSampleArguments(FrozenModel):
    source: Literal['A'] = 'A'
    into: Literal['C'] = 'C'
    portions: int = Field(default=1, ge=1, le=1)


PRIMITIVE_SCHEMAS = {
    'inspect_scene': InspectArguments,
    'localize_objects': LocalizeArguments,
    'observe': ObserveArguments,
    'mock_prepared_sample': MockSampleArguments,
    'mock_pick_up': MockCupArguments,
    'mock_put_down': MockCupArguments,
    'mock_pour': MockPourArguments,
    'add_sample': AddSampleArguments,
}


class ImageReference(FrozenModel):
    path: str = Field(min_length=1, max_length=4096)
    evidence_id: str = Field(min_length=1, max_length=128)
    captured_at: str | int | float
    provenance: str = Field(min_length=1, max_length=80)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class EvaluationReceipt(FrozenModel):
    evaluation_id: str = Field(min_length=1, max_length=128)
    suite_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    candidate_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    baseline_hash: str | None
    artifact_hashes: list[str] = Field(min_length=1, max_length=50)
    baseline_recovered: int = Field(ge=0)
    candidate_recovered: int = Field(ge=0)
    regression_gates: dict[str, bool]
    passed: bool
    reasons: list[str] = Field(min_length=1, max_length=30)
    metrics: dict[str, Any] = Field(default_factory=dict)


class PerceptionService(Protocol):
    async def inspect_scene(self, sid: str, view: str = 'primary') -> dict: ...
    async def localize_objects(self, sid: str, evidence_id: str, labels: list[str]) -> dict: ...
    async def observe(self, sid: str, execution_receipt: dict) -> dict: ...


class Evaluator(Protocol):
    async def evaluate_candidate(self, sid: str, candidate: dict, baseline: dict | None) -> dict: ...
