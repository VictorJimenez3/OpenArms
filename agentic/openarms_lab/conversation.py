"""Interpret read-only turns and exact notebook choices before dispatch."""
from __future__ import annotations

import re
import time

from .learning import science_reply

STOP_PHRASES = {'stop', 'stop now', 'stop please', 'please stop', 'emergency stop',
                'please stop now', 'stop now please'}


def stop_input(text):
    return bool(re.fullmatch(r'[a-zA-Z ,.!]+', text.strip()) and words(text) in STOP_PHRASES)

RESET_REQUESTS = {'new trial', 'next trial', 'prepare next trial', 'prepare a new trial',
                  'prepare the next trial', 'start a new trial', 'start over', 'try again'}
SOCIAL_REPLIES = {
    'hello': 'Hi. What would you like to try?',
    'hi': 'Hi. What would you like to try?',
    'thanks': 'You’re welcome.',
    'thank you': 'You’re welcome.',
    'okay': 'Okay.',
    'ok': 'Okay.',
    'great': 'Okay.',
    'got it': 'Okay.',
    'that makes sense': 'Okay.',
}

REPEAT = re.compile(r'^(?:(?:can|could|would|will) you |please )?'
                    r'(?:repeat|say (?:that|it) again|tell me more|go over (?:that|it) again)\b')
REQUEST = re.compile(r'^(?:(?:can|could|would|will) you |please )'
                     r'(?:please )?(?:test|run|pour|pick up|put down|set down|inspect|use|try|'
                     r'prepare|start|move|heat|mix|measure|perform|do (?:the|a))\b')
QUESTION = re.compile(
    r"^(?:(?:what|which|why|where|when|who|how)\b|"
    r"(?:explain|tell me (?:about|why|what|which|where|when|how))\b|"
    r"(?:can|could|would|will) you (?:explain|tell me|describe)\b|"
    r"(?:is|are|did|does|was|were|has|have|will) (?:it|this|that|the|my|our|there|we|you)\b)"
)
STATUS = re.compile(
    r"\b(?:status|progress|how long|(?:how is|hows) it going|waiting|still|"
    r"what (?:are you|is it|s it) (?:doing|checking)|what(?: is|s) happening|"
    r"what(?:s| is) (?:next|taking so long)|what happened|"
    r"stopp?ed|finished|done|ready|running|queued|working|cancelled|canceled)\b"
)
RESULT = re.compile(r'\b(?:result|outcome|evidence|observed|saw|happened|readout)\b')
SCIENCE = re.compile(
    r'\b(?:ph|indicator|acid|acidic|basic|base|alkaline|control|neutral|vinegar|'
    r'baking soda|water|color|colour|purple|pink|blue|green)\b'
)


def words(text):
    # Apostrophes are often omitted by ASR.
    return ' '.join(re.sub(r"[^a-z0-9 ]", '', text.lower()).split())


def condition_input(text):
    """Recognize a complete choice or correction, never a fragment of a question."""
    text = re.sub(r'^((?:actually|instead|no)[, ]+)(?:please )?(?:test|run) (?:the )?(?:prepared )?',
                  r'\1', text.lower().strip())
    aliases = {'vinegar': 'vinegar', 'baking soda': 'baking_soda', 'baking-soda': 'baking_soda',
               'baking_soda': 'baking_soda', 'water': 'water', 'water control': 'water'}
    pattern = (r'(?:actually[, ]*|instead[, ]*|no[, ]*)?'
               r'(?:(?:i (?:choose|pick|want|would like|prefer)|choose|pick|select|use|try|switch to|change to|'
               r'make that|let[’\']s (?:use|try))\s+)?'
               r'(?:the\s+)?(?P<condition>vinegar|baking[-_ ]soda|water(?: control)?)(?: solution)?'
               r'(?: (?:one|sample))?(?:[, ]+(?:please|instead))?')
    match = re.fullmatch(pattern, text.lower().strip().rstrip('.!'))
    return aliases[match['condition']] if match else None


def reset_input(text):
    norm = words(text)
    norm = re.sub(r'^(?:please |(?:can|could|would) you )', '', norm)
    return norm.removesuffix(' please') in RESET_REQUESTS


def prediction_input(text):
    norm = words(text)
    return (norm.startswith('i predict ') or
            re.fullmatch(r'(?:it (?:will|might|should) (?:be|turn) )?(?:pink|purple|blue|green|'
                         r'blue green|acidic|basic|neutral|near neutral)', norm) is not None)


def read_only_turn(text):
    norm = words(text)
    if norm in SOCIAL_REPLIES or REPEAT.match(norm):
        return True
    if re.match(r'^(?:can|could|would|will) you\b', norm) and re.search(
            r'\b(?:after this|after that|later|next time|in the future)\b', norm):
        return True
    # Modal imperatives are common in speech, including “Will you pick up cup A?”
    if REQUEST.match(norm) or re.match(r'^how about (?:we |trying |testing |using |pouring |picking |setting )', norm):
        return False
    if QUESTION.match(norm):
        return True
    if re.match(r'^(?:can|could|would|will) you\b', norm):
        return bool(re.match(r'^(?:can|could|would|will) you (?:see|hear|know|remember|still)\b', norm))
    return re.match(r'^(?:(?:is|are|was|were|does|did|has|have)\b|do (?:i|we|you|they)\b)', norm) is not None


def explicit_action(text):
    """Recognize direct requests, leaving open-ended interpretation to the guide."""
    norm = re.sub(r'^(?:actually|instead|no) +', '', words(text))
    if reset_input(norm) or read_only_turn(norm):
        return False
    return bool(REQUEST.match(norm) or re.match(
        r'^(?:test|run|pour|pick up|put down|set down|inspect|move|mix|measure)\b', norm))


def controller_state(state, task):
    """A pre-action camera checkpoint can set an active task status."""
    request_id = task.get('request_id')
    if not request_id:
        return None
    for event in reversed(state.get('notebook', [])):
        if event.get('request_id') != request_id:
            continue
        data = event.get('data') or {}
        if event['kind'] == 'execution_result' and data.get('receipt'):
            return data['receipt'].get('status')
        if event['kind'] == 'execution_progress' and data.get('phase'):
            return 'in_progress'
    return None


def status_reply(state):
    trial = state['trial']
    task = next((t for t in reversed(state['tasks']) if t['trial_id'] == trial['trial_id']), {})
    status = task.get('status')
    if status == 'queued':
        return 'Your request is queued. I’ll let you know when there’s a proposal or a question.'
    if status == 'running':
        return 'I’m checking the scene and working out a supported plan. No action has started.'
    if status == 'awaiting_confirmation' and state.get('pending'):
        pending = state['pending']
        return f"I’m waiting for your confirmation. {pending['summary']}"
    if status == 'needs_clarification' and task.get('summary'):
        return task['summary']
    if status in ('executing', 'observing'):
        controller = controller_state(state, task)
        if controller == 'in_progress':
            return 'The simulation is carrying out the approved action. I’ll report what the observer can see.'
        if controller == 'completed':
            return 'The simulation controller finished. The observer is checking the result.'
        if controller == 'failed':
            return 'The simulation controller reported a failure. I’m checking the available evidence.'
        return 'I’m checking the scene for the approved plan. The action hasn’t started.'
    if trial['state'] == 'stopped' or status == 'cancelled':
        return 'The task stopped.' if trial['state'] == 'stopped' else 'The task was cancelled.'
    if status in ('failed', 'completed') and task.get('summary'):
        return task['summary']
    return 'The lab is ready. What would you like to try?'


def conversation_reply(text, state):
    """Reply to read-only text from runtime evidence, without starting a task."""
    norm = words(text)
    water_only = (state.get('experiment') or {}).get('id') == 'two_vessel_water'
    if norm in SOCIAL_REPLIES:
        return SOCIAL_REPLIES[norm]
    if REPEAT.match(norm):
        if state.get('pending'):
            return state['pending']['summary']
        previous = next((m['text'] for m in reversed(state['messages'])
                         if m['role'] == 'assistant' and m.get('final')), None)
        return previous or status_reply(state)
    observations = [o for o in state['observations'] if o.get('trial_id') == state['trial']['trial_id']]
    if re.search(r'\b(?:what can you see|what do you see|which cup|where is|whats in front)\b', norm):
        scene = state.get('scene') or {}
        frame_id = scene.get('frame_id')
        expires_at = scene.get('expires_at') or (scene.get('captured_at', 0) + 180)
        if not scene.get('fresh') or expires_at <= time.time():
            return 'I don’t have a fresh verified view of those objects in this trial.'
        for event in reversed(state['notebook']):
            if event.get('kind') != 'perception_result':
                continue
            data = event.get('data') or {}
            receipt = data.get('receipt') or {}
            if data.get('operation') == 'localize_objects' and receipt.get('evidence_id') == frame_id:
                labels = receipt.get('verified_labels') or []
                if labels and receipt.get('provenance') in ('SYNTHETIC', 'SIMULATED'):
                    if 'which cup' in norm and {'source', 'receiver'}.issubset(labels):
                        return 'Do you mean the source at A or the receiver at C in the simulation?'
                    return 'In the simulation, the latest scene shows ' + ', '.join(labels) + '.'
        return 'I don’t have a verified view of those objects in this trial.'
    if RESULT.search(norm):
        if observations:
            return observations[-1]['text']
        if not STATUS.search(norm):
            return 'There’s no independent observation recorded for this trial yet.'
    if STATUS.search(norm):
        return status_reply(state)
    if re.search(r'\b(?:what can (?:you|we|i) do|which actions|what are my options|capabilities|supported)\b', norm):
        action = (state.get('capabilities') or {}).get('action_description')
        if action:
            return f'I can {action} in the simulation after you review the proposed steps.'
        return ('I can plan the supported two-cup simulation and discuss its results. '
                'Tell me the action you want to try, and I’ll show any proposed steps for review.')
    if water_only:
        if SCIENCE.search(norm):
            return 'This is a water-only simulation. There’s no indicator in the setup; we check how much water reaches the receiver.'
        return 'I can answer questions about the current pour or what the simulation observer found.'
    if SCIENCE.search(norm):
        return science_reply(text, [])
    return 'I can answer questions about the current trial, what the observer found, or how the indicator works.'
