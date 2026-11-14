"""Execution boundary for a confirmed transfer; default implementation is mock."""
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class ExecutionResult:
    plan_id: str
    mode: str
    status: str
    placement: str | None = None
    operator_authorized: bool = False

class TransferRunner(Protocol):
    mode: str
    async def authorize(self, plan: dict) -> bool: ...
    async def execute(self, plan: dict) -> ExecutionResult: ...
    async def stop(self) -> None: ...

class MockRunner:
    mode = 'mock'
    def __init__(self):
        self.executions = []
        self.placement = 'A'
    async def execute(self, plan):
        plan_id = plan['plan_id']
        if (plan.get('object'), plan.get('source'), plan.get('destination')) != ('mandarin','A','B'):
            raise ValueError('Unsupported transfer')
        if plan_id in self.executions or self.placement != 'A':
            raise ValueError('Transfer already consumed; reset the mock session')
        self.executions.append(plan_id)
        self.placement = 'B'
        return ExecutionResult(plan_id,'mock','completed','B')
    async def stop(self):
        pass
