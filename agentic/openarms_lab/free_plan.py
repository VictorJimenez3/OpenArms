"""Free-form commands built from the saved positions. Turned on with OPENARMS_FREE_PLANS=1.

The skill registry knows one motion (transfer A or C to B). This adds plans the student
composes from what the pose file actually holds:

    move the mandarin from B to A
    go to above B, then return home
    go above A, open the gripper, go down to A, close the gripper, go up, return home

A command becomes plan actions from the existing agent catalog (move_block, go_to,
gripper, wait). The existing validator checks them against the bench state; the same
steps are simulated when a preview is configured, and executed through the firmware's
PoseArm only after the student's "execute" and, on the real arm, the bench operator's
approval in the terminal. Text is parsed with fixed patterns: no model call, and a
command that is not fully understood is not turned into a partial plan.
"""
from __future__ import annotations
import asyncio
import os
import re
from pathlib import Path

from agentic.openarms_agent.validator import validate
from .contracts import ExecutionResult, Observation

ROOT = Path(__file__).resolve().parents[2]
SKILL = 'free_plan.v1'
GRIPPER = 'gripper.pos'
HOME_TOL = 5.0  # degrees; the same start tolerance as the transfer runner

_SPLIT = re.compile(r'\s*(?:[,;]|\.(?:\s|$)|\band then\b|\bafter that\b|\bthen\b|\band\b)\s*')
_ST = r'(?:station\s+|point\s+|position\s+|mark\s+)?([a-z])\b'
_MOVE = re.compile(r'\b(?:move|transfer|bring|take|carry|put|place|shift|return)\b.*\bfrom\s+' + _ST + r'.*?\b(?:back\s+)?(?:in)?to\s+' + _ST)
_POSE = re.compile(r'\b(above|over|grasp|tip)\s+' + _ST)
_DOWN = re.compile(r'\b(?:down|lower|descend)\b.*?\b(?:to|at|on|onto)\s+' + _ST)
_GOTO = re.compile(r'\b(?:go|move|head|come|travel|reach)\s+(?:back\s+|over\s+)?to\s+' + _ST)
_HOME = re.compile(r'\bhome\b|\brest position\b')
_UP = re.compile(r'\b(?:go|move|come|lift|raise)\s+(?:back\s+)?up\b|\blift\b|\braise\b')
_OPEN = re.compile(r'\b(?:open|release|let go|drop)\b')
_CLOSE = re.compile(r'\b(?:close|grab|grip|grasp|hold|clamp)\b')
_WAIT = re.compile(r'\b(?:wait|pause|hold on)\b.*?(\d+(?:\.\d+)?)')
_NEGATED = re.compile(r"\b(?:don't|dont|do not|without|no need to|never)\b")
_AGAIN = re.compile(r"^(?:(?:please\s+)?(?:do|run|try|execute|repeat)\s+)?(?:(?:it|that|this|the same(?: thing| command)?|the (?:previous|last) (?:command|one|action|request))\s*)?(?:again|once more|one more time)?$")


def from_env():
    if os.getenv('OPENARMS_FREE_PLANS', '').strip().lower() in ('', '0', 'off', 'false', 'no'):
        return None
    return FreePlans()


def repeat_requested(text):
    """True for "again", "do it again", "repeat the previous command"..."""
    t = re.sub(r'[^a-z ]', '', text.lower()).strip()
    return bool(t) and bool(_AGAIN.fullmatch(t)) and bool(re.search(r'again|once more|one more time|repeat|previous|last|same', t))


class PlanProblem(ValueError):
    """The command was understood but cannot be done; the message is for the student."""


class FreePlans:
    def __init__(self, poses_path=None, seconds=None, ask=input):
        self.poses_path = poses_path
        self.seconds = seconds
        self.ask = ask
        self._poses = None
        self._arm = None
        self._stop = False
        self._prompt = None

    # ---- bench description ---------------------------------------------------------

    def poses(self, backend=None):
        runner = getattr(backend, 'runner', None)
        if runner is not None and hasattr(runner, 'poses'):
            return runner.poses  # the connected arm's own pose file
        if self._poses is None:
            from firmware.openarms_executor.poses import load_poses
            self._poses = load_poses(Path(self.poses_path or os.environ.get('OPENARMS_POSES', ROOT/'firmware/openarms_executor/poses.json')))
        return self._poses

    def move_seconds(self, backend=None):
        if self.seconds is not None:
            return float(self.seconds)
        if os.getenv('OPENARMS_SECONDS'):
            return float(os.environ['OPENARMS_SECONDS'])
        return float(getattr(getattr(backend, 'runner', None), 'seconds', 1.5))

    def stations(self, backend, holds=None):
        """Every station with both a hover and a grasp position recorded is a point."""
        names = self.poses(backend)['poses']
        held = holds if holds is not None else (backend.state().get('point_holds') or {})
        return {n[len('GRASP_'):]: {'kind': 'point', 'holds': held.get(n[len('GRASP_'):])}
                for n in sorted(names) if n.startswith('GRASP_') and f"ABOVE_{n[len('GRASP_'):]}" in names}

    def state(self, backend):
        base = backend.state()
        stations = self.stations(backend)
        return {'at': base.get('at', 'HOME'), 'holding': base.get('holding'), 'armed': base.get('armed', True),
                'portions_left': {}, 'receiver_load': {},
                'point_holds': {k: v['holds'] for k, v in stations.items()},
                'poses': sorted(self.poses(backend)['poses']), 'gripper': base.get('gripper')}

    # ---- text -> plan actions ----------------------------------------------------------

    def parse(self, text, backend):
        """Plan actions for a command, None if it is not one of ours. Raises PlanProblem."""
        stations = self.stations(backend)
        known = self.poses(backend)['poses']
        steps, at = [], 'HOME'

        def station(letter):
            name = letter.upper()
            if name not in stations:
                raise PlanProblem(f"There is no saved station {name}. The saved stations are {', '.join(stations) or 'none'}.")
            return name

        def go(pose):
            nonlocal at
            if pose not in known:
                raise PlanProblem(f"There is no saved position {pose}. The saved positions are {', '.join(sorted(known))}.")
            steps.append({'action': 'go_to', 'args': {'pose': pose}})
            at = pose

        clauses = [c.strip() for c in _SPLIT.split(text.lower().replace('_', ' ')) if c.strip()]
        for clause in clauses:
            if _NEGATED.search(clause):
                continue  # "don't grasp it": the student is saying what to leave out
            if m := _MOVE.search(clause):
                steps.append({'action': 'move_block', 'args': {'from': station(m[1]), 'to': station(m[2])}})
                at = 'HOME'
            elif m := _WAIT.search(clause):
                steps.append({'action': 'wait', 'args': {'seconds': float(m[1]) if '.' in m[1] else int(m[1])}})
            elif m := _POSE.search(clause):
                go({'above': 'ABOVE_', 'over': 'ABOVE_', 'grasp': 'GRASP_', 'tip': 'TIP_'}[m[1]] + station(m[2]))
            elif m := _DOWN.search(clause):
                go('GRASP_' + station(m[1]))
            elif re.search(r'\b(?:go|move|come)\s+(?:back\s+)?down\b|\blower\b|\bdescend\b', clause) and at.startswith('ABOVE_'):
                go('GRASP_' + at[len('ABOVE_'):])
            elif _HOME.search(clause):
                go('HOME')
            elif m := _GOTO.search(clause):
                go('ABOVE_' + station(m[1]))
            elif _UP.search(clause) and at.startswith('GRASP_'):
                go('ABOVE_' + at[len('GRASP_'):])
            elif _OPEN.search(clause):
                steps.append({'action': 'gripper', 'args': {'state': 'open'}})
            elif _CLOSE.search(clause):
                steps.append({'action': 'gripper', 'args': {'state': 'close'}})
            else:
                return None  # one clause we do not understand: no partial plan
        return steps or None

    def summary(self, steps, obj):
        said = []
        for s in steps:
            a, args = s['action'], s['args']
            if a == 'move_block':
                said.append(f"move the {obj} from {args['from']} to {args['to']}")
            elif a == 'go_to':
                said.append('return to HOME' if args['pose'] == 'HOME' else f"go to {args['pose']}")
            elif a == 'gripper':
                said.append(f"{args['state']} the gripper")
            else:
                said.append(f"wait {args['seconds']} s")
        text = '; then '.join(said)
        return text[:1].upper() + text[1:]

    def validate(self, backend, steps):
        """The agent validator's verdict for these steps on the bench as it stands."""
        plan = {'plan_id': 'free', 'student_instruction': 'free plan', 'steps': steps}
        v = validate(plan, self.state(backend), self.stations(backend))
        if not v['ok']:
            raise PlanProblem(v['reason'])
        return v

    def estimate_seconds(self, backend, steps):
        return sum(t if isinstance(t, (int, float)) else self.move_seconds(backend) for t in self.sim_request(backend, steps, 'object')['script'])

    # ---- simulation ------------------------------------------------------------------

    def sim_request(self, backend, steps, obj):
        """The exact targets PoseArm would send for these steps, for openarms_sim.script."""
        from firmware.openarms_executor.motion import FakeRobot
        from firmware.openarms_executor.pose_arm import PoseArm
        poses = self.poses(backend)
        v = self.validate(backend, steps)
        stations = self.stations(backend)
        scratch = PoseArm(FakeRobot(poses['poses']['HOME']), poses, stations)
        script, labels = [], []
        for step in v['expanded']:
            targets, _ = scratch._script(step['action'], step['args'])
            name = step['args'].get('station') or step['args'].get('pose') or step['args'].get('state') or ''
            script += targets
            labels += [f"{step['action']}({name})"] * len(targets)
        start = {k: h for k, h in self.state(backend)['point_holds'].items() if h}
        end = {k: h for k, h in v['end_state']['point_holds'].items() if h}
        thing = next(iter(start.values()), None)
        return {
            'script': script, 'labels': labels, 'seconds': self.move_seconds(backend),
            'home': {**poses['poses']['HOME'], GRIPPER: poses['gripper']['open']},
            'marks': {s: poses['poses'][f'GRASP_{s}'] for s in stations},
            'object': thing or obj,
            'object_at': next((k for k, h in start.items() if h == thing), None),
            'expect_at': next((k for k, h in end.items() if h == thing), None),
            'source': '', 'destination': '', 'strict_grasp': False,
            'trusted': list(poses['poses'].values()),
        }

    # ---- execution -------------------------------------------------------------------

    def _plan(self, r):
        return {'plan_id': r['request_id'], 'student_instruction': r.get('summary', ''), 'steps': r['parameters']['steps']}

    def _physical_arm(self, backend):
        if self._arm is None:
            from firmware.openarms_executor.pose_arm import PoseArm
            holds = backend.state().get('point_holds') or {}
            self._arm = PoseArm(backend.runner.robot, self.poses(backend), self.stations(backend, holds),
                                seconds=self.move_seconds(backend))
        return self._arm

    def _off_home(self, backend):
        home = self.poses(backend)['poses']['HOME']
        obs = backend.runner.robot.get_observation()
        return sorted(k for k, v in home.items() if abs(float(obs[k]) - v) > HOME_TOL)

    async def authorize(self, backend, r):
        """Bench operator approval in the server terminal. Returns (approved, reason)."""
        if self._prompt is not None and not self._prompt.done():
            return False, 'An earlier operator prompt is still open in the terminal. Answer it first.'
        if not backend.state().get('armed', True) or (self._arm is not None and not self._arm.state()['armed']):
            return False, 'The arm is disarmed after a fault or stop. Check the bench and restart the server.'
        off = await asyncio.to_thread(self._off_home, backend)
        if off:
            return False, f"The arm is not at HOME (off: {', '.join(j.removesuffix('.pos') for j in off)}). Move it to HOME and ask again."
        q = (f"\nPlan {r['request_id'][:8]}: {r['summary']}.\n"
             f"Arm at HOME, bench clear, objects where the app shows them? y/n> ")
        self._prompt = asyncio.ensure_future(asyncio.to_thread(self.ask, q))
        ok = (await asyncio.shield(self._prompt)).strip().lower() in ('y', 'yes')
        return ok, None if ok else 'The bench operator declined this plan.'

    async def execute(self, backend, r, progress):
        if backend.mode == 'physical':
            return await self._execute_physical(backend, r, progress)
        return await self._execute_mock(backend, r, progress)

    async def _execute_mock(self, backend, r, progress):
        v = self.validate(backend, r['parameters']['steps'])
        stopped = getattr(backend, '_stopped', None)
        if stopped is not None:
            stopped.clear()
        for step in v['expanded']:
            await progress(step['action'])
            await asyncio.sleep(getattr(backend, 'delay', 0.05))
            if stopped is not None and stopped.is_set():
                backend._state['armed'] = False
                return ExecutionResult(request_id=r['request_id'], backend=backend.mode, status='stopped', reason='STOP requested.')
        end = v['end_state']
        backend._state.update(at=end['at'], holding=end['holding'], gripper=end.get('gripper'))
        backend._state['point_holds'].update(end['point_holds'])
        return ExecutionResult(request_id=r['request_id'], backend=backend.mode, status='completed', controller_completed=True,
                               observation=Observation(provenance='MOCK', text='Mock controller reports ' + self._where(end) + '.',
                                                       source='mock state inspection', value=end['point_holds']))

    async def _execute_physical(self, backend, r, progress):
        from agentic.openarms_agent.runner import run
        arm = self._physical_arm(backend)
        self._stop = False
        await progress('controller_running')
        backend._executing = True
        try:
            done = await asyncio.to_thread(run, self._plan(r), arm, lambda: self._stop)
        finally:
            backend._executing = False
        state = arm.state()
        # The app's view of the bench follows what the arm did, step by completed step.
        backend._state['point_holds'].update(state.get('point_holds') or {})
        backend._state.update(at=state['at'], holding=state['holding'], armed=state['armed'])
        status = {'executed': 'completed', 'stopped': 'stopped'}.get(done['status'], 'failed')
        if status == 'completed':
            text = 'Controller finished; independent physical placement evidence is not available.'
        else:
            text = 'Physical outcome is unknown; the operator must check the bench.'
        return ExecutionResult(request_id=r['request_id'], backend='physical', status=status, operator_authorized=True,
                               controller_completed=status == 'completed', physical_success=None,
                               observation=Observation(provenance='UNKNOWN', text=text, source='controller report'),
                               reason=None if status == 'completed' else f"{done.get('failed_step') or 'run'}: {done.get('reason')}")

    def stop(self):
        self._stop = True
        if self._arm is not None:
            self._arm.stop()

    @staticmethod
    def _where(state):
        held = [f"the {h} at {k}" for k, h in state['point_holds'].items() if h]
        return (', '.join(held) if held else 'nothing on the marks') + f"; arm at {state['at']}"
