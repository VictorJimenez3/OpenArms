"""Rehearse evidence-driven expert decisions on the synthetic lab fixture.

This is a text/student harness for the canonical ``openarms_lab`` runtime. It
uses the configured expert and the bounded synthetic executor, then changes the
camera evidence after the one approved action. It never enables physical
execution and it does not qualify chemistry, contact physics, or a new scene.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from openarms_lab.expert_profiles import add_expert_arguments, expert_from_arguments
from openarms_lab.runtime import Lab
from openarms_lab.scene import SceneService
from openarms_lab.simulated_backend import SceneBackend


REQUEST = 'Please test the prepared vinegar sample and check the indicator color.'
SCOPE = 'synthetic-indicator-v1'
TERMINAL = {'completed', 'failed', 'cancelled', 'needs_clarification'}
ACTION_OPERATIONS = {'mock_prepared_sample', 'mock_pick_up', 'mock_put_down', 'mock_pour'}


class OccludingBackend(SceneBackend):
    """Hide the primary camera only after the approved action returns."""

    def __init__(self, scene_service, **kwargs):
        super().__init__(scene_service, **kwargs)
        self.occluded_after_action = False

    async def execute_step(self, request_id, arguments, progress, *, operation='mock_prepared_sample'):
        result = await super().execute_step(request_id, arguments, progress, operation=operation)
        if result.get('status') == 'completed':
            self.scene_service.world(self.session_id).occluded_primary = True
            self.occluded_after_action = True
        return result


class AdaptiveScene(SceneService):
    """Make the first post-action observation genuinely unreadable.

    Both views are obscured for the complete observer call, including any
    approved ``fallback_view`` attempt. Only after that call returns is the
    secondary view restored. Thus the recorded failure keeps accurate view and
    attempt metadata, and a later expert revision can request fresh secondary
    evidence without changing the already-approved plan.
    """

    def __init__(self, artifact_dir):
        super().__init__(artifact_dir)
        self._first_observation = set()

    def arm_after_action(self, sid):
        self._first_observation.add(sid)

    async def observe(self, sid, execution_receipt):
        if sid in self._first_observation:
            self._first_observation.remove(sid)
            world = self.world(sid)
            world.occluded_primary = True
            world.occluded_secondary = True
            try:
                result = await super().observe(sid, execution_receipt)
                requested = execution_receipt.get('view', 'primary')
                fallback = execution_receipt.get('fallback_view')
                result['attempt_views'] = [requested] + ([fallback] if result.get('attempts') and fallback else [])
                return result
            finally:
                # The primary remains unavailable; only a fresh secondary
                # observation after the failed checkpoint may recover.
                world.occluded_primary = True
                world.occluded_secondary = False
        result = await super().observe(sid, execution_receipt)
        requested = execution_receipt.get('view', 'primary')
        fallback = execution_receipt.get('fallback_view')
        result['attempt_views'] = [requested] + ([fallback] if result.get('attempts') and fallback else [])
        return result


class AdaptiveBackend(OccludingBackend):
    async def execute_step(self, request_id, arguments, progress, *, operation='mock_prepared_sample'):
        result = await super().execute_step(request_id, arguments, progress, operation=operation)
        if result.get('status') == 'completed':
            self.scene_service.arm_after_action(self.session_id)
        return result


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def _tool_names(task: dict) -> list[str]:
    names = []
    for run in task.get('expert_runs', []):
        for receipt in run.get('tool_receipts', []):
            name = receipt.get('name') or receipt.get('tool_name')
            if name:
                names.append(name)
    return names


def _action_receipts(task: dict) -> list[dict]:
    """Return completed controller-equivalent action receipts only."""
    return [receipt for receipt in task.get('execution', [])
            if receipt.get('operation') in ACTION_OPERATIONS and receipt.get('status') == 'completed']


def _approval_trace(state: dict) -> list[dict]:
    """Project requests into an auditable proposal/presentation/consent ledger."""
    trace = []
    for request in state.get('requests', []):
        trace.append({
            'request_id': request.get('request_id'),
            'task_id': request.get('task_id'),
            'proposal_version': request.get('proposal_version'),
            'plan_hash': request.get('plan_hash'),
            'status': request.get('status'),
            'presented': request.get('presented'),
            'presentation': request.get('presentation'),
            'student_confirmed': request.get('student_confirmed'),
            'confirmed_at': request.get('confirmed_at'),
            'result_status': (request.get('result') or {}).get('status'),
        })
    return trace


def _outcome_checks_preserved(state: dict) -> bool:
    """Check every revision retains the first approved outcome contract."""
    plans = [request.get('plan') or {} for request in state.get('requests', [])]
    if not plans:
        return True
    baseline = {json.dumps(check, sort_keys=True) for check in plans[0].get('outcome_checks', [])}
    return all(baseline.issubset({json.dumps(check, sort_keys=True)
                                  for check in plan.get('outcome_checks', [])})
               for plan in plans[1:])


def _has_secondary_decision(task: dict) -> bool:
    for run in task.get('expert_runs', []):
        for receipt in run.get('tool_receipts', []):
            arguments = receipt.get('arguments') or {}
            if arguments.get('view') == 'secondary' or arguments.get('fallback_view') == 'secondary':
                return True
            plan = arguments.get('plan') or {}
            for step in plan.get('steps', []):
                step_arguments = step.get('arguments') or {}
                if step_arguments.get('view') == 'secondary' or step_arguments.get('fallback_view') == 'secondary':
                    return True
    for step in (task.get('plan') or {}).get('steps', []):
        arguments = step.get('arguments') or {}
        if arguments.get('view') == 'secondary' or arguments.get('fallback_view') == 'secondary':
            return True
    return False


def _has_secondary_revision(task: dict) -> bool:
    """Detect a secondary-view choice made after the first proposal.

    The initial plan may already include an automatic fallback. That is not an
    adaptive decision, so only a bounded replan and its final plan count here.
    """
    if task.get('replans', 0) < 1:
        return False
    for run in task.get('expert_runs', [])[1:]:
        for receipt in run.get('tool_receipts', []):
            arguments = receipt.get('arguments') or {}
            if arguments.get('view') == 'secondary' or arguments.get('fallback_view') == 'secondary':
                return True
            plan = arguments.get('plan') or {}
            for step in plan.get('steps', []):
                step_arguments = step.get('arguments') or {}
                if step_arguments.get('view') == 'secondary' or step_arguments.get('fallback_view') == 'secondary':
                    return True
    return any((step.get('arguments') or {}).get('view') == 'secondary' or
               (step.get('arguments') or {}).get('fallback_view') == 'secondary'
               for step in (task.get('plan') or {}).get('steps', []))


async def settle(lab: Lab, sid: str, *, out: Path, label: str, timeout: float) -> dict:
    """Present and confirm every exact proposal, including bounded revisions."""
    proposals = []
    statuses = []
    presented = set()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = lab.snapshot(sid)
        if not state['tasks']:
            await asyncio.sleep(.05)
            continue
        task = state['tasks'][-1]
        status_key = (task['status'], len(task.get('expert_runs', [])), task.get('replans', 0))
        if status_key not in statuses:
            statuses.append(status_key)
        pending = state.get('pending')
        if pending:
            key = (pending['request_id'], pending['proposal_version'])
            if key not in presented:
                presented.add(key)
                proposals.append({
                    'request_id': pending['request_id'],
                    'proposal_version': pending['proposal_version'],
                    'plan_hash': pending['plan_hash'],
                    'summary': pending['summary'],
                    'task_id': pending['task_id'],
                })
                await lab.present(sid, pending['request_id'], pending['proposal_version'])
                await lab.confirm(sid, pending['request_id'], pending['proposal_version'])
        elif task['status'] in TERMINAL:
            break
        await asyncio.sleep(.05)
    else:
        raise TimeoutError(f'{label} did not settle within {timeout:g}s')

    state = lab.snapshot(sid)
    task = state['tasks'][-1]
    if task['status'] not in TERMINAL:
        raise RuntimeError(f'{label} ended in nonterminal status {task["status"]!r}')
    artifact = {
        'label': label,
        'session_id': sid,
        'execution_scope': state.get('execution_scope'),
        'status_history': [list(item) for item in statuses],
        'proposals': proposals,
        'approval_trace': _approval_trace(state),
        'approved_outcome_checks_preserved': _outcome_checks_preserved(state),
        'task': task,
        'controller_receipts': task.get('execution', []),
        'observations': task.get('observations', []),
        'tool_names': _tool_names(task),
        'expert_runs': task.get('expert_runs', []),
    }
    _write(out / f'{label}.json', artifact)
    return state


async def run_case(root: Path, args, *, adaptive: bool) -> dict:
    folder = root / ('adaptive' if adaptive else 'clear')
    folder.mkdir(parents=True, exist_ok=False)
    scene = AdaptiveScene(folder / 'scene') if adaptive else SceneService(folder / 'scene')
    expert = expert_from_arguments(args, folder / 'expert', artifact_roots=[scene.artifact_dir])
    if adaptive:
        backend_factory = lambda: AdaptiveBackend(scene, delay=.02)
    else:
        backend_factory = lambda: SceneBackend(scene, delay=.02)
    lab = Lab(folder / 'sessions', expert=expert, perception=scene,
              backend_factory=backend_factory, execution_scope=SCOPE,
              expert_timeout=args.expert_timeout)
    started = time.perf_counter()
    created = await lab.create()
    sid = created['session_id']
    try:
        await lab.converse(sid, REQUEST, f'{"adaptive" if adaptive else "clear"}-request')
        await asyncio.sleep(.05)
        # This is a student follow-up, not a second task. The runtime should
        # answer it from state while the expert is working.
        await lab.converse(sid, 'What are you doing?', f'{"adaptive" if adaptive else "clear"}-status')
        state = await settle(lab, sid, out=folder, label='trace', timeout=args.timeout)
        task = state['tasks'][-1]
        action_receipts = _action_receipts(task)
        if len(action_receipts) > 1:
            raise AssertionError(f'{"adaptive" if adaptive else "clear"} dispatched more than one action.')
        if adaptive:
            backend = lab.backends[sid]
            if action_receipts and not backend.occluded_after_action:
                raise AssertionError('Adaptive backend did not arm post-action occlusion.')
            observation = task.get('observations', [])[-1] if task.get('observations') else None
            secondary = _has_secondary_decision(task)
            secondary_revision = _has_secondary_revision(task)
            if len(action_receipts) != 1:
                adaptive_result = 'no_action_dispatched'
            elif observation and observation.get('status') == 'observed' and secondary_revision:
                adaptive_result = 'secondary_recovery'
            elif observation and observation.get('status') == 'unknown':
                adaptive_result = 'unknown_after_primary_occlusion'
            else:
                adaptive_result = 'declined_or_failed'
            state['_rehearsal'] = {'adaptive_result': adaptive_result,
                                   'secondary_decision': secondary,
                                   'secondary_revision': secondary_revision}
        _write(folder / 'state.json', state)
        return {
            'label': 'adaptive' if adaptive else 'clear',
            'status': state['tasks'][-1]['status'],
            'route': state['tasks'][-1].get('route'),
            'replans': state['tasks'][-1].get('replans', 0),
            'proposal_count': len(state.get('requests', [])),
            'approved_outcome_checks_preserved': _outcome_checks_preserved(state),
            'observation_status': (state['tasks'][-1].get('observations') or [{}])[-1].get('status'),
            'observation_provenance': (state['tasks'][-1].get('observations') or [{}])[-1].get('provenance'),
            'action_dispatch_count': len(action_receipts),
            'single_action_dispatch': len(action_receipts) == 1,
            'tool_names': _tool_names(state['tasks'][-1]),
            'expert_runs': len(state['tasks'][-1].get('expert_runs', [])),
            'model_identities': [
                {'requested': run.get('requested_model'), 'actual': run.get('actual_model'),
                 'verified': run.get('model_verified')}
                for run in state['tasks'][-1].get('expert_runs', [])
            ],
            'expert_timings_ms': [
                {'adapter': run.get('elapsed_ms'), 'host': run.get('host_elapsed_ms')}
                for run in state['tasks'][-1].get('expert_runs', [])
            ],
            'expert_configuration': expert.describe(),
            'elapsed_seconds': time.perf_counter() - started,
            **state.get('_rehearsal', {}),
        }
    finally:
        await lab.shutdown()


async def run_both_obscured_control(root: Path) -> dict:
    folder = root / 'both-obscured-control'
    folder.mkdir(parents=True, exist_ok=False)
    scene = SceneService(folder / 'scene')
    sid = 'both-obscured-control'
    world = scene.world(sid)
    world.occluded_primary = True
    world.occluded_secondary = True
    observation = await scene.observe(sid, {'view': 'primary', 'fallback_view': 'secondary'})
    result = {'provenance': observation.get('provenance'), 'status': observation.get('status'),
              'features': observation.get('features'), 'attempts': observation.get('attempts', []),
              'attempt_views': observation.get('attempt_views', ['primary', 'secondary']),
              'evidence_ids': [image['evidence_id'] for image in observation.get('images', [])]}
    _write(folder / 'observation.json', result)
    if result['status'] != 'unknown':
        raise AssertionError('Both-obscured control must remain UNKNOWN.')
    return result


async def main(args) -> int:
    args.out.mkdir(parents=True, exist_ok=False)
    clear = await run_case(args.out, args, adaptive=False)
    adaptive = await run_case(args.out, args, adaptive=True)
    control = await run_both_obscured_control(args.out)
    summary = {
        'request': REQUEST,
        'execution_scope': SCOPE,
        'provenance': 'SYNTHETIC',
        'physical_execution': False,
        'clear': clear,
        'adaptive': adaptive,
        'both_obscured_control': control,
        'expert_configuration': clear['expert_configuration'],
        'limitations': [
            'Synthetic image and qualitative indicator fixture only.',
            'This rehearsal does not qualify physical actuation or chemistry.',
            'The actual model field remains null when the adapter cannot verify CLI telemetry.',
        ],
    }
    _write(args.out / 'summary.json', summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--expert-timeout', type=float, default=240)
    add_expert_arguments(parser)
    return parser.parse_args()


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main(parse_args())))
