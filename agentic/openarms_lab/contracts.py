"""Canonical, controller-independent request and evidence shapes."""
from __future__ import annotations
from typing import Any, Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field

Provenance = Literal['REAL', 'SIMULATED', 'MOCK', 'MODEL-PREDICTED', 'UNKNOWN']

class Parameters(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    object: Literal['mandarin', 'sample']
    source: Literal['A', 'C']
    destination: Literal['B']

class SkillRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    request_id: str
    session_id: str
    skill_id: str
    parameters: Parameters

class Observation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    provenance: Provenance
    text: str
    source: str
    value: Any = None
    evidence: list[str] = Field(default_factory=list)

class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str
    backend: Literal['mock', 'physical', 'simulated']
    status: Literal['completed', 'failed', 'stopped', 'unknown']
    operator_authorized: bool = False
    controller_completed: bool = False
    physical_success: bool | None = None
    observation: Observation | None = None
    reason: str | None = None

class ExecutionBackend(Protocol):
    mode: str
    def capabilities(self) -> dict: ...
    def state(self) -> dict: ...
    async def authorize(self, request: SkillRequest) -> bool: ...
    async def execute(self, request: SkillRequest, progress) -> ExecutionResult: ...
    async def stop(self) -> None: ...
