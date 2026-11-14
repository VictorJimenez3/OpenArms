"""Qualitative pH references and evidence-grounded feedback, entirely offline.

Scope: research/victor/laboratory-experiments-and-feasibility.md section 3.
These are classroom expectations, not bench observations or measured pH.
"""
from __future__ import annotations
import copy
import re
import uuid
from .contracts import Observation

EXPERIMENT = {'id': 'red_cabbage_ph', 'title': 'Red-cabbage pH investigation',
              'question': 'How does red-cabbage indicator respond to vinegar, baking-soda solution, and water?',
              'mode': 'MOCK', 'description': 'Qualitative reference outcomes; no physical measurement.'}
EXPERIMENTS = [EXPERIMENT]
CONDITIONS = (
    {'id': 'vinegar', 'title': 'Vinegar', 'color': 'pink', 'classification': 'acidic'},
    {'id': 'baking_soda', 'title': 'Mild baking-soda solution', 'color': 'blue-green', 'classification': 'basic'},
    {'id': 'water', 'title': 'Water control', 'color': 'purple', 'classification': 'near neutral'},
)

def get_experiment(experiment_id):
    if experiment_id != EXPERIMENT['id']:
        raise ValueError('Only the red-cabbage pH experiment is available.')
    return copy.deepcopy(EXPERIMENT)

def condition(condition_id):
    for entry in CONDITIONS:
        if entry['id'] == condition_id:
            return copy.deepcopy(entry)
    raise ValueError('Choose vinegar, baking_soda, or water.')

def reference_observation(request_id, trial_id, condition_id, available=True):
    c = condition(condition_id)
    if not available:
        return Observation(request_id=request_id, trial_id=trial_id, provenance='UNKNOWN',
            text='No readable reference observation is available. The color and acid/base outcome remain UNKNOWN.',
            source='mock reference unavailable', evidence=[]).model_dump()
    return Observation(request_id=request_id, trial_id=trial_id, provenance='MODEL-PREDICTED',
        text=f"MOCK reference: {c['title']} is expected to appear {c['color']} and classify as {c['classification']}. This is not a measured color or pH.",
        source='application-authored qualitative red-cabbage reference v1',
        evidence=['ref-' + uuid.uuid4().hex],
        value={'color': c['color'], 'classification': c['classification'], 'condition_id': condition_id}).model_dump()

def unknown_observation(request_id, trial_id, reason):
    return Observation(request_id=request_id, trial_id=trial_id, provenance='UNKNOWN',
        text='Trial outcome UNKNOWN. ' + reason, source='no independent observation', evidence=[]).model_dump()

def reflection_feedback(text, observations):
    """Quote the saved student reflection, but assert only the stored evidence."""
    latest = observations[-1] if observations else {}
    if latest.get('status') == 'observed':
        feedback = (f"The independent {latest['provenance']} observation was recorded by {latest['source']}. "
                    f"{latest['text']} How does that evidence compare with your prediction?")
    elif latest.get('provenance') == 'MODEL-PREDICTED' and latest.get('value'):
        value = latest['value']
        feedback = (f"The saved MODEL-PREDICTED reference is {value['color']} ({value['classification']}). "
                    'Use that labeled reference to compare with your prediction; this trial provides no measured pH or physical result. '
                    'Which condition would you compare next?')
    else:
        feedback = ('The outcome remains UNKNOWN. Execution completion alone cannot establish a color or acid/base classification. '
                    'What readable observation would you need to test your prediction?')
    return {'feedback': feedback, 'student_reflection': text,
            'provenance': 'EVIDENCE-GROUNDED-GUIDANCE',
            'evidence': [eid for o in observations for eid in o.get('evidence', [])],
            'request_ids': [o['request_id'] for o in observations], 'correct': None}

def science_reply(text, observations):
    norm = text.lower()
    if re.search(r'\b(result|happen|observe|evidence|see|saw)\b', norm) and observations:
        return observations[-1]['text'] + ' The observer and controller report separately.'
    if 'vinegar' in norm:
        return 'Vinegar is acidic; the qualitative cabbage reference is pink. In this mock trial that is an expectation, not a measurement.'
    if 'baking' in norm or 'base' in norm or 'basic' in norm:
        return 'Mild baking-soda solution is basic; the qualitative cabbage reference is blue-green. Actual color depends on preparation, so the mock reference is not a measured pH.'
    if 'water' in norm or 'neutral' in norm:
        return 'Water is the near-neutral control; the qualitative cabbage reference is purple. A control gives us a comparison for the other prepared conditions.'
    return ('Red-cabbage pigments change color with acid/base conditions: pink for an acidic reference, purple near neutral, '
            'and blue-green for this basic reference. These are qualitative expectations. Compare a readable observation with the water control; color alone here does not supply a measured pH.')
