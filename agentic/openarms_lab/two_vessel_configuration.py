"""Host-owned water-only scene identity, separate from indicator skill admission."""
from pathlib import Path
import hashlib
from .skills import compute_skill_hash

EXPERIMENT = {'id': 'two_vessel_water', 'title': 'Two-vessel water pour — simulation',
              'question': 'Can one premeasured water portion move from donor A into receiver C?',
              'mode': 'SIMULATED',
              'description': 'Water-only MuJoCo development rehearsal. No indicator, kit recipe or physical result.'}
CONDITIONS = [{'id': 'water', 'title': 'Premeasured water'}]


def execution_scope():
    import mujoco
    import numpy
    import cv2
    import PIL
    import scipy
    import yaml
    import imageio
    import pydantic
    root = Path(__file__).resolve().parents[2]
    sources = [Path(__file__).resolve(), root/'bench_vision/perception.py']
    sources += [root/'agentic/openarms_lab'/name for name in (
        'two_vessel_backend.py', 'two_vessel_scene.py', 'two_vessel_worker.py', 'two_vessel_evaluation.py',
        'mujoco_backend.py', 'mujoco_scene.py', 'mujoco_process.py', 'scene.py',
        'contracts.py', 'skills.py', 'task_loop.py', 'runtime.py', 'evaluation.py', 'store.py')]
    sources += sorted((root/'simulation/openarms_sim').glob('*.py'))
    sources += [root/'simulation/config'/name for name in (
        'setups/liquid/bench.yaml', 'setups/liquid/poses.json', 'joint_map.yaml', 'chemistry.yaml')]
    sources += [p for p in sorted((root/'simulation/models/so101').rglob('*'))
                if p.is_file() and p.suffix.lower() in ('.xml', '.stl', '.obj', '.mtl', '.png', '.jpg')]
    identity = {'experiment': EXPERIMENT, 'conditions': CONDITIONS,
                'versions': {'mujoco': mujoco.__version__, 'numpy': numpy.__version__, 'opencv': cv2.__version__,
                             'pillow': PIL.__version__, 'scipy': scipy.__version__, 'yaml': yaml.__version__,
                             'imageio': imageio.__version__, 'pydantic': pydantic.__version__},
                'sources': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    return 'two-vessel-' + compute_skill_hash(identity)[:16]
