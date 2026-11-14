"""Admit a reusable skill only after fixture regression and actual MuJoCo runs.

Robustness improvements are measured in the frozen synthetic camera suite.
MuJoCo clear-view runs additionally check every declared parameter combination.
These are separate evidence environments, neither a physical qualification.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import time
from pathlib import Path

from .evaluation import SyntheticSkillEvaluator, _PinnedPlanner
from .runtime import Lab
from .skills import compute_skill_hash


def simulation_scope():
    import cv2
    import mujoco
    import numpy
    from .mujoco_scene import CAMERA_SETUP, METHOD, SCENE
    root = Path(__file__).resolve().parents[2]
    # Version labels alone cannot carry admission across changed implementation.
    sources = ['simulation/lab_demos/ph/run.py', 'simulation/lab_demos/ph/__init__.py',
               'simulation/lab_demos/titration/run.py',
               'agentic/openarms_lab/mujoco_scene.py', 'agentic/openarms_lab/mujoco_worker.py',
               'agentic/openarms_lab/mujoco_backend.py',
               'agentic/openarms_lab/skills.py', 'agentic/openarms_lab/evaluation.py',
               'agentic/openarms_lab/simulation_evaluation.py', 'agentic/openarms_lab/contracts.py',
               'simulation/config/setups/block/poses.json']
    sources += [str(path.relative_to(root)) for path in sorted((root / 'simulation/models/so101').rglob('*'))
                if path.is_file() and path.suffix.lower() in {'.xml', '.stl', '.obj', '.mtl', '.png', '.jpg'}]
    identity = {'scene': SCENE, 'camera': CAMERA_SETUP, 'observer': METHOD,
                'versions': {'mujoco': mujoco.__version__, 'numpy': numpy.__version__, 'opencv': cv2.__version__},
                'sources': {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in sources}}
    return 'mujoco-' + compute_skill_hash(identity)[:16]


class SimulationSkillEvaluator:
    def __init__(self, artifact_dir):
        self.artifact_dir = Path(artifact_dir)
        self.fixture = SyntheticSkillEvaluator(self.artifact_dir / 'fixture')
        self._lock = asyncio.Lock()

    async def _case(self, folder, definition, bindings):
        from .mujoco_backend import MujocoBackend
        from .mujoco_scene import MujocoSceneService
        scene = MujocoSceneService(folder / 'images')
        lab = Lab(folder, perception=scene,
                  expert=_PinnedPlanner(definition.model_dump(mode='json'), bindings),
                  backend_factory=lambda: MujocoBackend(scene), execution_timeout=90)
        started = time.perf_counter()
        sid = (await lab.create())['session_id']
        try:
            task = await lab.start_task(sid, 'Replay the pinned prepared-sample skill for MuJoCo admission.')
            await asyncio.wait_for(asyncio.shield(lab.workers[task['task_id']]), 120)
            state = lab.snapshot(sid)
            if state['pending']:
                proposal = state['pending']
                await lab.present(sid, proposal['request_id'], proposal['proposal_version'])
                await lab.confirm(sid, proposal['request_id'], proposal['proposal_version'])
                await asyncio.wait_for(asyncio.shield(lab.workers[task['task_id']]), 120)
            state = lab.snapshot(sid)
            task = state['tasks'][-1]
            observed = task['observations'][-1] if task['observations'] else None
            passed = bool(task['status'] == 'completed' and observed and
                          observed['status'] == 'observed' and observed['provenance'] == 'SIMULATED' and
                          observed['checks'] and all(observed['checks'].values()))
            receipt = {'passed': passed, 'bindings': bindings, 'backend': 'mujoco',
                       'provenance': 'SIMULATED', 'real_model_used': False,
                       'task_status': task['status'], 'reason': task.get('summary'),
                       'observation': observed, 'elapsed_ms': (time.perf_counter()-started)*1000}
            (folder / 'state.json').write_text(json.dumps(state, indent=2))
            (folder / 'receipt.json').write_text(json.dumps(receipt, indent=2))
            return receipt
        finally:
            await lab.shutdown()

    async def evaluate_candidate(self, sid, candidate, baseline):
        async with self._lock:
            receipt = await self.fixture.evaluate_candidate(sid, candidate, baseline)
            result = copy.deepcopy(receipt)
            folder = self.artifact_dir / receipt['evaluation_id']
            folder.mkdir(parents=True, exist_ok=False)
            definitions = {'candidate': self.fixture._definition(candidate)}
            if baseline:
                definitions['baseline'] = self.fixture._definition(baseline)
            comparisons = {}
            # A candidate that already failed deterministic admission is never
            # run merely to create attractive simulation evidence.
            if receipt['passed']:
                for label, definition in definitions.items():
                    comparisons[label] = []
                    for index, bindings in enumerate(self.fixture._bindings(definition)):
                        comparisons[label].append(await self._case(folder / label / str(index), definition, bindings))
            accepted = bool(comparisons.get('candidate')) and all(row['passed'] for row in comparisons['candidate'])
            result['regression_gates']['mujoco_parameters'] = accepted
            result['passed'] = result['passed'] and accepted
            result['suite_hash'] = compute_skill_hash({'version': 'fixture-and-mujoco-admission-v1',
                                                       'simulation_scope': simulation_scope(),
                                                       'fixture_suite_hash': receipt['suite_hash']})
            result['metrics'].update(environment='Synthetic robustness and MuJoCo clear-view admission',
                                     improvement_environment='SYNTHETIC', mujoco_cases=comparisons)
            result['reasons'].append('Every declared parameter combination passed the real MuJoCo renderer.' if accepted
                                     else 'MuJoCo admission did not pass; the existing active skill is unchanged.')
            artifact = folder / 'comparison.json'
            artifact.write_text(json.dumps({'candidate': candidate, 'unchanged_baseline': baseline,
                                            'fixture_receipt': receipt, 'mujoco': comparisons}, indent=2))
            result['artifact_hashes'].append(hashlib.sha256(artifact.read_bytes()).hexdigest())
            (folder / 'receipt.json').write_text(json.dumps(result, indent=2))
            return result
