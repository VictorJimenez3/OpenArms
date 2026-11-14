"""Fixed mandarin demo. Authoritative local state; no hardware transport."""
import asyncio
import time
from pathlib import Path
import tempfile
from dialogue import Reply
from runner import MockRunner

class MandarinDialogue:
    def __init__(self, submit=None, runner=None):
        self.runner = runner or MockRunner()
        self.event = lambda name, **fields: None
        self.pending = None
        self.placement = 'A'
        self.executions = []
        self.closed = False
        self.scratch = tempfile.TemporaryDirectory(prefix='openarms-plan-')
        if submit is None:
            from agy_bridge import submit
        self.submit = submit

    def set_event_sink(self, sink):
        self.event = sink

    async def respond(self, context, student_text):
        if self.closed:
            raise RuntimeError('Dialogue closed')
        if student_text is None:
            return Reply('Mandarin transfer demo. Tell me what you want moved between A and B. I will propose a plan before anything runs.', 'instruction')
        text = student_text.strip().lower().rstrip('.!?').strip()
        if text in {'cancel', 'stop', 'cancel simulation', 'cancel transfer', 'cancel the transfer'}:
            if not self.pending:
                return Reply(f'No pending transfer to cancel. Last reported placement: {self.placement}.', 'reflection')
            plan_id = self.pending['plan_id']
            self.pending = None
            await self.runner.stop()
            self.event('plan_cancelled', plan_id=plan_id, placement=self.placement)
            return Reply(f'Transfer cancelled. Plan {plan_id}. Last reported placement: {self.placement}. No execution was requested for this plan.', 'reflection')
        if text in {'confirm', 'i confirm'} or text.startswith('confirm '):
            if not self.pending:
                return Reply('There is no pending preview. Request the mandarin transfer first.', 'confirmation')
            plan = self.pending
            if text not in {'confirm', 'i confirm', 'confirm ' + plan['plan_id'].lower()}:
                return Reply(f'Confirmation does not match pending plan {plan["plan_id"]}. Say confirm or cancel.', 'confirmation')
            # Consume before producing the result; no retries or duplicate runs.
            self.pending = None
            self.event('plan_confirmed', plan_id=plan['plan_id'])
            started = time.monotonic()
            mode = getattr(self.runner, 'mode', None)
            if mode not in {'mock', 'physical'}:
                raise ValueError('Runner must declare mock or physical mode')
            if mode == 'physical' and (await self.runner.authorize(plan)) is not True:
                self.event('operator_rejected', plan_id=plan['plan_id'])
                return Reply('The bench operator did not authorize this transfer. No execution was requested.', 'reflection')
            try:
                result = await self.runner.execute(plan)
            except BaseException:
                self.event('execution_failed', plan_id=plan['plan_id'])
                await self.runner.stop()
                raise
            if result.plan_id != plan['plan_id'] or result.mode != mode or result.status not in {'completed','failed','stopped','unknown'}:
                raise ValueError('Runner result does not match approved plan')
            if result.mode == 'physical' and result.operator_authorized is not True:
                raise ValueError('Physical runner must obtain bench operator authorization')
            self.event('execution_result', plan_id=result.plan_id, mode=result.mode,
                       status=result.status, placement=result.placement,
                       operator_authorized=result.operator_authorized,
                       duration_ms=round((time.monotonic()-started)*1000))
            self.executions.append(plan['plan_id'])
            self.placement = result.placement or 'unknown'
            if result.mode == 'mock':
                return Reply(f'Simulated result for plan {result.plan_id}: the mandarin is at {self.placement}. No hardware moved.', 'result')
            placement = f'Reported placement: {result.placement}.' if result.placement else 'Final placement has not been observed.'
            return Reply(f'Physical runner reports {result.status} for plan {result.plan_id}. {placement}', 'result')
        # Every revised instruction revokes the previous preview first.
        if self.pending:
            self.event('plan_invalidated', plan_id=self.pending['plan_id'], reason='new_instruction')
        self.pending = None
        if self.placement != 'A':
            return Reply('This transfer is complete. Reset the mandarin at A and start a new session for another trial.', 'reflection')
        state_dir = Path(self.scratch.name) / context.turn_id
        state_dir.mkdir(mode=0o700)
        started = time.monotonic()
        self.event('planning_started')
        plan = await self.submit(student_text, state_dir)
        self.event('planning_finished', duration_ms=round((time.monotonic()-started)*1000), status=plan.get('status') if isinstance(plan,dict) else 'invalid')
        if self.closed:
            raise asyncio.CancelledError
        if isinstance(plan, dict) and plan.get('status') == 'no_plan':
            return Reply('No transfer plan was submitted. You can ask me to move the mandarin from A to B, or cancel.', 'instruction')
        if (not isinstance(plan, dict) or plan.get('status') != 'preview_ready'
            or plan.get('object') != 'mandarin' or plan.get('source') != 'A'
            or plan.get('destination') != 'B' or not isinstance(plan.get('plan_id'), str)
            or not plan['plan_id'].startswith('plan-')):
            raise ValueError('Agent did not submit a valid fixed transfer through MCP')
        self.pending = plan
        self.event('preview_ready', plan_id=plan['plan_id'], object='mandarin', source='A', destination='B', preview='placeholder')
        return Reply(f'Proposed transfer, plan {plan["plan_id"]}: move the mandarin from A to B. Simulator deferred. Say confirm to submit to the runner, or cancel. Physical movement additionally requires bench operator authorization.', 'preview')

    async def close(self):
        self.closed = True
        self.pending = None
        try:
            await self.runner.stop()
        finally:
            self.scratch.cleanup()
