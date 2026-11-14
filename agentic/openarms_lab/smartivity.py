"""Simulation-only Smartivity connection to the OpenArms expert and skill compiler."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from functools import partial
import gzip
import hashlib
import io
import json
from pathlib import Path
import time
import uuid

from PIL import Image
import numpy as np

from .codex_expert import ExpertUnavailable
from .contracts import PlanDraft, SkillDefinition
from .expert_profiles import add_expert_arguments, expert_from_arguments
from .skills import SkillRegistry

CAMERAS = ('overview', 'side')
CAPTURE_HZ = 4
RECORD_HZ = 30
MAX_FRAME_AGE = 1
OBJECTIVE = 'Erupting Volcano · pour the prepared beaker into the flask and return the beaker to its dock.'
MANIFEST = {
    'source': 'Smartivity My First Science Kit, Erupting Volcano, pp. 26–27',
    'A': 'Prepared beaker in donor dock. 15 mL water, 4 kit spoons citric acid, 6 drops liquid soap. Stirred 32 times.',
    'C': 'Fixed flask in tray. 30 mL water, 4 kit spoons baking soda, 4 drops red colour. Stirred 32 times.',
    'preparation': 'All preparation is preloaded. Robot picks the beaker, pours promptly, returns it to A, and retracts.',
    'fill_variation': 'Amounts above are the nominal booklet recipe. Nonzero seeds perturb simulated water fills by up to 5%.',
}
POTIONS_OBJECTIVE = ('Magic Potion-1 and Magic Potion-2 · combine the prepared green tea in A with the pink '
                     'tea in C, then observe the result and return the cup.')
POTIONS_MANIFEST = {
    'source': 'Smartivity My First Science Kit, Magic Potion-1 and Magic Potion-2, pp. 30–33',
    'preparation': 'A Magic Tea Bag steeped in 50 mL water for 10 minutes. It was removed and the blue tea was split equally.',
    'A': 'Cup with the reserved 25 mL blue tea, prepared with 1 kit spoon of baking soda and stirred. Green.',
    'C': 'Fixed flask in tray with 25 mL blue tea, prepared with 1 kit spoon of citric acid and stirred. Pink.',
    'sequence': 'All preparation is virtual setup. The robot pours the prepared green cup into the pink flask.',
}
EXPERIMENTS = {'volcano': (OBJECTIVE, MANIFEST), 'potions': (POTIONS_OBJECTIVE, POTIONS_MANIFEST)}
SKILLS = {
    'pick': ('mock_pick_up', 'A', 'Pick and lift the beaker from dock A', 'beaker_lifted'),
    'pour': ('mock_pour', 'C', 'Tilt the held beaker into flask C, then move clear', 'reaction_visible'),
    'return_cup': ('mock_put_down', 'A', 'Set the beaker upright in dock A', 'beaker_docked'),
}
SEQUENCE = tuple(SKILLS) + ('home',)
MOTION_FOR_OPERATION = {skill[0]: action for action, skill in SKILLS.items()}
TOOLS = [{
    'name': 'execute_skill',
    'description': 'Validate and execute one simulated motion, then return fresh images. Bind the latest attached overview ID.',
    'input_schema': {'type': 'object', 'additionalProperties': False, 'required': ['action', 'evidence_id'],
                     'properties': {'action': {'enum': list(SEQUENCE)}, 'evidence_id': {'type': 'string'}}},
}, {
    'name': 'inspect_scene', 'description': 'Read fresh overview and side pixels and current joint readings.',
    'input_schema': {'type': 'object', 'additionalProperties': False},
}]
REGISTER_TOOL = {
    'name': 'register_layout',
    'description': 'Before moving a vessel, estimate both station locations from a fresh overhead image.',
    'input_schema': {'type': 'object', 'additionalProperties': False, 'required': ['evidence_id'],
                     'properties': {'evidence_id': {'type': 'string'}}},
}


@dataclass(frozen=True)
class Frame:
    metadata: dict
    jpeg: bytes
    rgb: np.ndarray
    monotonic: float


def _default_world(seed, scenario='volcano', position_variation_m=None):
    from openarms_sim.smartivity_world import World
    return World(seed=seed, scenario=scenario, position_variation_m=position_variation_m)


def _skill_definition(action, scenario):
    operation, station, name, feature = SKILLS[action]
    if scenario == 'potions':
        name = name.replace('beaker', 'cup')
    return SkillDefinition.model_validate({
        'skill_id': f'smartivity_{scenario}.{action}.v1',
        'name': name, 'intent': name,
        'preconditions': {'fresh_scene': True, 'labels': [station]},
        'steps': [{'operation': 'inspect_scene'}, {'operation': operation, 'arguments': {
            'fixture': 'sample_cup', 'station': station}}, {'operation': 'observe'}],
        'outcome_checks': [{'feature': feature, 'expected': True}],
        'limitations': ['Simulated fixture only.'],
    })


class SmartivityRun:
    """One world, one task. All world operations run on the render-context thread."""

    def __init__(self, folder, expert, *, scenario='volcano', world_factory=None, register_layout=False):
        self.folder = Path(folder)
        self.expert = expert
        self.scenario = scenario
        self.objective, self.manifest = EXPERIMENTS[scenario]
        self.require_registration = register_layout
        self.world_factory = world_factory or partial(_default_world, scenario=scenario)
        self.world = None
        self.frames = {}
        self.generation = 0
        self.seed = 0
        self.status = 'idle'
        self.action = None
        self.outcome = None
        self.recovery = None
        self.evidence = []
        self.timing = {}
        self.reset_ms = None
        self._lock = asyncio.Lock()
        self._task = None
        self._stop_event = None
        self.recorded_frames = None

    @property
    def running(self):
        return self._task is not None and not self._task.done()

    def snapshot(self):
        return dict(status=self.status, objective=self.objective, scenario=self.scenario, evidence=list(self.evidence),
                    action=self.action, outcome=self.outcome, recovery=self.recovery,
                    seed=self.seed, generation=self.generation, timing=dict(self.timing),
                    reset_ms=self.reset_ms,
                    phase=self.world.phase if self.world else 'ready',
                    frames={key: frame.metadata for key, frame in self.frames.items()})

    async def _reset(self, seed, *, record=False):
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2_147_483_647:
            raise ValueError('Enter a seed from 0 to 2147483647.')
        if self.world is not None:
            self.world.close()
            self.world = None
        self.generation += 1
        self.seed = seed
        self.status = 'idle'
        self.action = self.outcome = self.recovery = None
        self.evidence.clear()
        self.timing = {}
        self.frames.clear()
        self._capture_count = 0
        self._steps = 0
        self.recorded_frames = None
        self.recorded_preparation = []
        self._phase_index = 0
        self._actions = []
        self._events = []
        self._rejections = 0
        self._seen = {}
        self._observed_change = False
        self._observed_pour = False
        self._layout_registration = None
        self._camera_evidence = {}
        self._preparation = []
        self._actual_result = None
        self._started = self._clock()
        self._sim_started = None
        self._stop_event = asyncio.Event()
        self.episode_id = uuid.uuid4().hex
        self.episode = self.folder / self.episode_id
        self.episode.mkdir(parents=True)
        # MJCF compilation and IK can take seconds. The renderer is created on
        # this event-loop thread only when we capture the first frame below.
        self.world = await asyncio.to_thread(self.world_factory, seed)
        self._sim_started = self.world.sim_time
        try:
            self._capture()
            if self.scenario == 'potions':
                phases = ((None, 'Blue tea steeped and divided between cup and flask.'),
                          ('acidify_flask', 'Prepared the pink flask with the booklet’s citric acid dose.'),
                          ('basify_cup', 'Prepared the green cup with the booklet’s baking soda dose.'))
                for preparation, note in phases:
                    if preparation:
                        self.world.prepare(preparation)
                        self._capture()
                    if record:
                        self.recorded_preparation.append((self.world.preparation_stage, self.world.visual_state()))
                    pictures = self._save_frames()
                    self._preparation.append({'phase': self.world.preparation_stage, 'summary': note,
                                              'evidence_ids': [frame['frame_id'] for frame in pictures]})
                    self.evidence.append(note)
        except Exception:
            self.world.close()
            self.world = None
            raise
        self._baseline_effect = self._effect_pixels(self.frames['overview'].rgb)
        self._peak_effect_pixels = 0
        self._call_starts = {}
        self._call_timings = []
        self.reset_ms = round((self._clock() - self._started) * 1000, 2)

    async def reset(self, seed=0):
        async with self._lock:
            await self._stop()
            await self._reset(seed)
            self.evidence.append('Prepared apparatus visible in the reset cameras.')
            return self.snapshot()

    async def start(self, seed=0, *, diagnostic=False, checkpoint=False, record=False):
        async with self._lock:
            if self.running:
                raise ValueError('Stop or finish the current simulation before starting another.')
            await self._reset(seed, record=record)
            self.status = 'running'
            self._limit = 1 if checkpoint else len(SEQUENCE)
            self._mode = 'scripted_diagnostic' if diagnostic else 'openarms_policy'
            self._task = asyncio.create_task(self._run(diagnostic, checkpoint, record))
            return self.snapshot()

    async def wait(self):
        if self._task is not None:
            await asyncio.shield(self._task)
        return self._actual_result

    async def _stop(self):
        if self.running:
            self._stop_event.set()
            self.world.halt()
            await self.wait()

    async def stop(self):
        async with self._lock:
            await self._stop()
            return self.snapshot()

    async def close(self):
        async with self._lock:
            await self._stop()
            if self.world is not None:
                self.world.close()
                self.world = None

    @staticmethod
    def _clock():
        return time.monotonic()

    def _capture(self):
        capture_group = self._capture_count + 1
        new = {}
        for camera in CAMERAS:
            rgb = self.world.rgb(camera)
            clock, wall = self._clock(), time.time()
            buffer = io.BytesIO()
            Image.fromarray(rgb).save(buffer, format='JPEG', quality=92, subsampling=0)
            jpeg = buffer.getvalue()
            dimensions = {'width_px': rgb.shape[1], 'height_px': rgb.shape[0]}
            frame_id = f'{self.episode_id}-{capture_group:05d}-{camera}'
            new[camera] = Frame({
                'frame_id': frame_id, 'evidence_id': frame_id, 'camera_id': camera,
                'generation': self.generation, 'calibration_id': f'{self.scenario}-{camera}.v1-seed{self.seed}',
                'coordinate_frame': f'{camera}_image_top_left', 'units': 'px',
                'orientation': 'top-left RGB', 'captured_at': wall, 'clock': 'unix_seconds',
                'physics_time_s': self.world.sim_time, 'sha256': hashlib.sha256(jpeg).hexdigest(),
                'provenance': 'SIMULATED', **dimensions,
            }, jpeg, rgb, clock)
        self.frames = new
        self._capture_count = capture_group

    async def _drive(self, stop_driving):
        clock = self._clock
        wall_zero, model_zero = clock(), self.world.sim_time
        next_camera = wall_zero
        frames = self.recorded_frames
        if frames is not None:
            frames.append((model_zero, None, self.world.visual_state()))
        while not stop_driving.is_set():
            now = clock()
            model_target = now - wall_zero + model_zero
            # A bound yields to cancellation/inference even when rendering runs late.
            for _ in range(64):
                if self.world.sim_time + self.world.timestep > model_target:
                    break
                action = (SEQUENCE[self._phase_index] if frames is not None and self.world.busy else None)
                self.world.tick()
                self._steps += 1
                if frames is not None and self.world.sim_time >= model_zero + len(frames) / RECORD_HZ:
                    frames.append((self.world.sim_time, action, self.world.visual_state()))
            if now >= next_camera:
                self._capture()
                if self._phase_index == 1 and self.world.busy:
                    self._measure_effect()
                next_camera = clock() + 1 / CAPTURE_HZ
            self.timing = self._rates(clock() - wall_zero)
            await asyncio.sleep(0.005)

    def _rates(self, elapsed):
        elapsed = max(elapsed, 1e-6)
        simulated = self.world.sim_time - self._sim_started
        return {'wall_s': round(elapsed, 3), 'sim_s': round(simulated, 3),
                'sim_seconds_per_wall_second': round(simulated / elapsed, 3),
                'control_hz': round(self._steps / elapsed, 2),
                'captures_per_camera_hz': round(self._capture_count / elapsed, 2),
                'recorded_states_hz': round(len(self.recorded_frames or ()) / elapsed, 2)}

    def _save_frames(self):
        images = []
        for frame in self.frames.values():
            metadata = frame.metadata
            path = self.episode / (metadata['frame_id'] + '.jpg')
            if not path.exists():
                path.write_bytes(frame.jpeg)
            self._camera_evidence[metadata['frame_id']] = metadata
            images.append({'path': str(path.resolve()), **metadata})
        return images

    def _observe(self):
        if not self.frames or any(self._clock() - frame.monotonic > MAX_FRAME_AGE
                                  for frame in self.frames.values()):
            self._capture()
        images = self._save_frames()
        overview = self.frames['overview']
        self._seen = {overview.metadata['evidence_id']: (self.generation, self._phase_index, overview)}
        proprioception = self.world.proprioception()
        registered = not self.require_registration or (
            self._layout_registration is not None and self._layout_registration['status'] == 'registered')
        return {'images': images, 'proprioception': proprioception,
                'completed_actions': list(SEQUENCE[:self._phase_index]),
                'available_skills': [SEQUENCE[self._phase_index]]
                if self._phase_index < self._limit and registered and not proprioception.get('fault') else [],
                'provenance': 'SIMULATED'}

    @staticmethod
    def _pixel_change(before, after):
        return float(np.abs(before.astype(np.int16) - after).mean())

    def _effect_pixels(self, rgb):
        red, green, blue = np.moveaxis(rgb, -1, 0).astype(np.int16)
        if self.scenario == 'potions':
            effect = (red >= 200) & (blue >= 231) & (blue - red >= 5) & (blue - green >= 32)
        else:
            effect = (red > 190) & (green > 65) & (blue > 80) & (red - green > 35) & (blue - green > 8)
        return int(effect.sum())

    def _measure_effect(self):
        frame = self.frames['overview']
        growth = self._effect_pixels(frame.rgb) - self._baseline_effect
        if growth > self._peak_effect_pixels:
            self._peak_effect_pixels = growth
            self._peak_effect_frame = frame.metadata
            (self.episode / 'visible-effect.jpg').write_bytes(frame.jpeg)

    def _refuse(self, reason):
        self._rejections += 1
        self.recovery = reason
        return {'error': reason, **self._observe()}

    async def _register_layout(self, arguments):
        from openarms_sim.smartivity_registration import locate_layout

        if not self.require_registration or self._phase_index or self.world.busy:
            return self._refuse('Registration is available before motion in the layout experiment.')
        if self._layout_registration and self._layout_registration['status'] == 'registered':
            return self._refuse('The current setup is already registered.')
        evidence_id = arguments.get('evidence_id')
        observed = self._seen.get(evidence_id) if isinstance(evidence_id, str) else None
        if set(arguments) != {'evidence_id'} or observed is None or observed[0] != self.generation:
            return self._refuse('Inspect the current scene before requesting registration.')
        rgb = self.world.registration_image()
        calibration = self.world.registration_calibration()
        frame_id = f'{self.episode_id}-layout-{uuid.uuid4().hex[:8]}'
        path = self.episode / (frame_id + '.png')
        Image.fromarray(rgb).save(path)
        frame = {'frame_id': frame_id, 'evidence_id': frame_id, 'camera_id': 'layout_overhead',
                 'captured_at': time.time(), 'calibration_id': 'layout-overhead.v1',
                 'coordinate_frame': 'layout_overhead_image_top_left', 'generation': self.generation,
                 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'provenance': 'SIMULATED'}
        self._camera_evidence[frame_id] = frame
        self._layout_registration = {'evidence_id': frame_id, 'calibration': calibration}
        try:
            estimate = locate_layout(rgb, calibration)
            await asyncio.to_thread(self.world.register_layout, estimate['dock_xy'], estimate['receiver_xy'])
            if self._stop_event.is_set():
                raise asyncio.CancelledError
            self._layout_registration.update(estimate, status='registered')
        except (RuntimeError, ValueError) as exc:
            self._layout_registration.update(status='rejected', reason=str(exc))
            self.recovery = 'The fixture markers could not be registered.'
        response = self._observe()
        response['images'].append({'path': str(path.resolve()), **frame})
        response['layout_registration'] = self._layout_registration
        return response

    async def _tool(self, name, arguments):
        if self._stop_event.is_set():
            raise asyncio.CancelledError
        if name == 'inspect_scene' and not arguments:
            return self._observe()
        if name == 'register_layout':
            return await self._register_layout(arguments)
        if self.require_registration and not (
            self._layout_registration and self._layout_registration['status'] == 'registered'):
            return self._refuse('Register the two fixture markers before moving the arm.')
        if name != 'execute_skill' or set(arguments) != {'action', 'evidence_id'}:
            return self._refuse('Inspect the scene or submit one supported skill with an overview evidence ID.')
        action, evidence_id = arguments['action'], arguments['evidence_id']
        if self._phase_index >= self._limit or action != SEQUENCE[self._phase_index]:
            return self._refuse('That motion is unavailable in the current phase. Inspect the latest cameras.')
        seen = self._seen.get(evidence_id) if isinstance(evidence_id, str) else None
        if seen is None or seen[:2] != (self.generation, self._phase_index):
            return self._refuse('The observation was invalidated. Inspect the current scene.')
        decision_frame = seen[2]
        self._capture()  # Revalidate scene immediately before dispatch, after model latency.
        dispatch = self.frames['overview']
        if (dispatch.metadata['calibration_id'] != decision_frame.metadata['calibration_id'] or
                self._pixel_change(decision_frame.rgb, dispatch.rgb) > 3.0):
            return self._refuse('The camera scene changed during inference. Replan from the latest frame.')
        skill_version = None
        motion, label = action, 'Retract to HOME'
        if action in SKILLS:
            definition = _skill_definition(action, self.scenario)
            compiled = self._registry.compile(PlanDraft(skill_definition=definition, evidence_ids=[evidence_id]))
            skill_version = compiled['skill_version']
            motion = MOTION_FOR_OPERATION[compiled['steps'][1]['operation']]
            label = definition.name
        started = self._clock()
        try:
            self.world.start(motion)
        except ValueError as exc:
            return self._refuse(str(exc))
        self.action = label
        while self.world.busy:
            if self._stop_event.is_set():
                raise asyncio.CancelledError
            await asyncio.sleep(0.02)
        if self._stop_event.is_set():
            raise asyncio.CancelledError
        fault = self.world.proprioception().get('fault')
        if not fault:
            self._phase_index += 1
        self._capture()
        observation = self._observe()
        changed = self._pixel_change(dispatch.rgb, self.frames['overview'].rgb)
        self._observed_change |= changed >= 0.5
        if action == 'pour':
            self._measure_effect()
            self._observed_pour = self._peak_effect_pixels >= 35
        self.evidence.append(f'{self.action}. New camera frames captured.')
        if action == 'pour':
            effect = 'Pink foam' if self.scenario == 'volcano' else 'A lavender color change'
            self.evidence.append(f'{effect} became visible in the overview.' if self._observed_pour else
                                 'The overview did not detect the expected new color region.')
        self.recovery = 'Motion stopped. Reset the scene before continuing.' if fault else None
        action_receipt = {
            'action': action, 'skill_version': skill_version, 'decision_evidence_id': evidence_id,
            'dispatch_evidence_id': dispatch.metadata['evidence_id'],
            'after_evidence_ids': [frame['evidence_id'] for frame in observation['images']],
            'decision_frame_age_at_dispatch_ms': round((started - decision_frame.monotonic) * 1000, 2),
            'dispatch_frame_age_ms': round((started - dispatch.monotonic) * 1000, 2),
            'execution_ms': round((self._clock() - started) * 1000, 2),
            'overview_mean_rgb_delta': round(changed, 4), 'controller_fault': fault,
        }
        # Retain the immediately revalidated frame even after the latest buffer advances.
        self._camera_evidence[dispatch.metadata['frame_id']] = dispatch.metadata
        (self.episode / (dispatch.metadata['frame_id'] + '.jpg')).write_bytes(dispatch.jpeg)
        self._actions.append(action_receipt)
        return {**observation, 'action_receipt': action_receipt, 'recovery': self.recovery,
                'controller_completed': fault is None, 'use_images_to_judge_outcome': True}

    async def _run(self, diagnostic, checkpoint, record):
        self._registry = SkillRegistry(self.episode / 'skills.json')
        self._peak_effect_frame = None
        stop_driving = asyncio.Event()
        driver = None
        error = None
        expert_result = None
        final_evaluation = None
        try:
            if record:
                self.recorded_frames = []
            driver = asyncio.create_task(self._drive(stop_driving))
            policy = asyncio.create_task(self._policy(diagnostic, checkpoint))
            try:
                done, _ = await asyncio.wait((driver, policy), return_when=asyncio.FIRST_COMPLETED)
                if driver in done:
                    await driver
                    raise RuntimeError('Simulation clock stopped unexpectedly.')
                expert_result = await policy
            finally:
                if not policy.done():
                    policy.cancel()
                    await asyncio.gather(policy, return_exceptions=True)

            final_evaluation = self.world.evaluate()
            final_observation = (expert_result or {}).get('payload', {})
            recent_id = self.frames['overview'].metadata['evidence_id']
            inspected = next(iter(self._seen), '')
            cited = final_observation.get('evidence_id')
            report = final_observation.get('observed_outcome')
            expert_observed = (expert_result and expert_result['kind'] == 'complete' and
                               cited in (recent_id, inspected) and bool(inspected) and
                               isinstance(report, str) and bool(report.strip()))
            completion = (self._phase_index == len(SEQUENCE) and final_evaluation.get('success')
                          and self._observed_pour and (diagnostic or expert_observed))
            first_loop = bool(self._phase_index >= 1 and self._observed_change)
            self.status = 'success' if (first_loop if checkpoint else completion) else 'failed'
            self.outcome = ('Camera → policy → motion → changed camera checkpoint passed.' if checkpoint and first_loop
                            else 'Transfer, donor placement and outcome observation verified.' if completion
                            else 'The trial did not meet the outcome checks.')
            if self.status == 'failed':
                self.recovery = 'Inspect the final images and reset for another trial.'
        except asyncio.CancelledError:
            self.status = 'stopped'
            self.outcome = 'Simulation STOP accepted.'
            self.recovery = 'Reset the scene before starting another trial.'
        except (ExpertUnavailable, RuntimeError, ValueError, OSError) as exc:
            self.status = 'failed'
            error = getattr(exc, 'code', type(exc).__name__)
            self.outcome = str(exc)
            self.recovery = 'Resolve the reported blocker, then reset.'
        finally:
            stop_driving.set()
            if self.world.busy:
                self.world.halt()
            if driver:
                await asyncio.gather(driver, return_exceptions=True)
            final_evaluation = final_evaluation or self.world.evaluate()
            self._actual_result = {
                'episode_id': self.episode_id, 'seed': self.seed, 'generation': self.generation,
                'manifest': self.manifest, 'scenario': self.scenario, 'status': self.status, 'outcome': self.outcome,
                'mode': self._mode,
                'checkpoint_only': checkpoint, 'error': error, 'evaluation': final_evaluation,
                'actions': self._actions, 'expert_events': self._events, 'expert_result': expert_result,
                'camera_evidence': self._camera_evidence, 'policy_call_timings': self._call_timings,
                'effect_pixel_gain': self._peak_effect_pixels,
                'effect_frame': self._peak_effect_frame, 'reset_ms': self.reset_ms,
                'preparation_steps': self._preparation,
                'layout_registration': self._layout_registration,
                'position_variation_m': getattr(self.world, 'position_variation_m', None),
                'policy_calls': sum(event['type'] == 'expert_call_started' for event in self._events),
                'tool_rejections': self._rejections, 'interventions': int(self.status == 'stopped'),
                'resets': self.generation - 1, 'timing': self.timing,
            }
            (self.episode / 'receipt.json').write_text(json.dumps(self._actual_result, indent=2) + '\n')

    async def _policy(self, diagnostic, checkpoint):
        observation = self._observe()
        if diagnostic:
            if self.require_registration:
                observation = await self._register_layout({'evidence_id': observation['images'][0]['evidence_id']})
                if self._layout_registration['status'] != 'registered':
                    raise ValueError(self._layout_registration['reason'])
            for action in SEQUENCE[:1] if checkpoint else SEQUENCE:
                observation = await self._tool('execute_skill', {
                    'action': action, 'evidence_id': observation['images'][0]['evidence_id']})
                if observation.get('error') or observation.get('recovery'):
                    raise ValueError(observation.get('error') or observation['recovery'])
            return None

        async def emit(event):
            now = self._clock()
            self._events.append({**event, 'monotonic_s': now - self._started})
            if event['type'] == 'expert_call_started':
                self._call_starts[event['call']] = now
            elif event['type'] == 'expert_call_completed':
                self._call_timings.append({
                    'call': event['call'],
                    'inference_ms': round((now - self._call_starts[event['call']]) * 1000, 2),
                })

        objective = ('Verify the first pick and lift only. Stop after observing the changed pose.'
                     if checkpoint else self.objective)
        if self.require_registration:
            # The expert transport repeats startup context on every model call.
            # Keep it visibly distinct from the live state returned by tools.
            images = observation.pop('images')
            observation = {'images': images, 'initial_snapshot': observation}
        context = {
            'task_id': self.episode_id, 'request': objective, 'phase': 'confirmed_simulation',
            'manifest': self.manifest,
            'tools': [*TOOLS, REGISTER_TOOL] if self.require_registration else TOOLS, **observation,
            'capability_limits': {'physical_actuation': False, 'station_set': ['A', 'C'],
                                  'skill_order': list(SEQUENCE[:self._limit])},
            'instructions': (
                'The student explicitly started this simulation. Inspect the supplied scene pixels before each action. '
                'If the expected vessel, fixture or grasp is unclear, inspect again or stop with uncertainty. '
                'On a controller fault, report the recovery status and request a reset. '
                'Use execute_skill with the current overview evidence_id and one available skill. '
                'The host returns updated frames after each skill. ' +
                ('Before the first motion, call register_layout with the current overview evidence ID. '
                 'After any tool call, use the latest host tool receipt for current joints, available skills, '
                 'completed actions, and evidence. The initial_snapshot is historical. Each action receipt '
                 'already includes a new scene inspection. Call inspect_scene again only if evidence is unclear. '
                 if self.require_registration else '') +
                'After the requested sequence, use kind=complete with payload '
                '{evidence_id: latest overview ID, observed_outcome: string}; cite what you actually see. '
                'The ledger and exact object poses are evaluator-only. Never infer material identity from pixels.'),
        }
        generation, task_id, stop = self.generation, self.episode_id, self._stop_event

        async def current_tool(name, arguments):
            if generation != self.generation or stop.is_set():
                raise asyncio.CancelledError
            return await self._tool(name, arguments)

        try:
            return await self.expert.run(context, tool_handler=current_tool, emit=emit, cancel_event=stop)
        finally:
            self.expert.release(task_id)


async def _cli(args):
    folder = args.out.resolve()
    expert = expert_from_arguments(args, folder / 'expert', artifact_roots=[folder],
                                   max_calls=10, task_timeout=360)
    world_factory = partial(_default_world, scenario=args.scenario,
                            position_variation_m=(args.layout_spread_mm / 1000
                                                  if args.layout_spread_mm else None))
    run = SmartivityRun(folder, expert, scenario=args.scenario, world_factory=world_factory,
                        register_layout=args.register_layout)
    try:
        await run.start(args.seed, diagnostic=args.diagnostic, checkpoint=args.checkpoint, record=True)
        result = await run.wait()
        frames = run.recorded_frames or []
        if frames:
            if args.capture_only:
                with gzip.open(run.episode / 'motion.json.gz', 'wt', encoding='utf-8') as target:
                    json.dump([(t, action, asdict(state)) for t, action, state in frames], target,
                              separators=(',', ':'), allow_nan=False)
                if run.recorded_preparation:
                    with gzip.open(run.episode / 'preparation.json.gz', 'wt', encoding='utf-8') as target:
                        json.dump([(phase, asdict(state)) for phase, state in run.recorded_preparation], target,
                                  separators=(',', ':'), allow_nan=False)
            else:
                from openarms_sim.smartivity_video import render_movie
                title = 'Erupting Volcano' if args.scenario == 'volcano' else 'Magic Potions 1 & 2'
                result['video'] = render_movie(run.world, frames, run.episode / 'overview.mp4',
                                               title=title, mode=result['mode'], episode_id=run.episode_id,
                                               preparation=run.recorded_preparation)
                (run.episode / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({'receipt': str(run.episode / 'receipt.json'), 'status': result['status'],
                          'mode': result['mode'], 'evaluation': result['evaluation'],
                          'timing': result['timing']}, indent=2))
        return result['status'] == 'success'
    finally:
        await run.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--scenario', choices=EXPERIMENTS, default='volcano')
    parser.add_argument('--diagnostic', action='store_true', help='Scripted simulator-only control.')
    parser.add_argument('--checkpoint', action='store_true', help='Test the first camera-to-policy action only.')
    parser.add_argument('--capture-only', action='store_true',
                        help='Save 30 Hz render states for separate rendering on another host.')
    parser.add_argument('--layout-spread-mm', type=float, help='Opt into experimentally randomized fixtures (up to 18 mm per axis).')
    parser.add_argument('--register-layout', action='store_true', help='Use the overhead camera to register the randomized fixtures.')
    add_expert_arguments(parser)
    args = parser.parse_args()
    if args.layout_spread_mm is not None and not 0 < args.layout_spread_mm <= 18:
        parser.error('--layout-spread-mm must be greater than zero and at most 18.')
    if args.register_layout and (not args.layout_spread_mm or args.scenario != 'volcano'):
        parser.error('--register-layout requires an explicit volcano layout spread.')
    raise SystemExit(0 if asyncio.run(_cli(args)) else 1)


if __name__ == '__main__':
    main()
