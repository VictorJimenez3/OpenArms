"""Persistent registry for approved mock skill versions and their evidence."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import tempfile
from pathlib import Path

from .contracts import (EvaluationReceipt, InspectArguments, LocalizeArguments,
                        MOCK_OPERATIONS, MockCupArguments, MockPourArguments,
                        MockSampleArguments, PlanDraft, SkillDefinition, Step)

PRIMITIVE_SCHEMAS = {
    'inspect_scene': InspectArguments, 'localize_objects': LocalizeArguments,
    'mock_prepared_sample': MockSampleArguments, 'mock_pick_up': MockCupArguments,
    'mock_put_down': MockCupArguments, 'mock_pour': MockPourArguments,
    'observe': InspectArguments,
}
TYPES = {'string': (str,), 'integer': (int,), 'number': (int, float), 'boolean': (bool,)}
TOKEN = re.compile(r'\$([a-z][a-z0-9_]{0,63})\Z')
SLOT = re.compile(r'\{([a-z][a-z0-9_]{0,63})\}')
GATES = {'routing', 'outcome', 'unknown', 'consent', 'stop'}


def compute_skill_hash(skill):
    if hasattr(skill, 'model_dump'):
        skill = skill.model_dump(mode='json')
    return hashlib.sha256(json.dumps(skill, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def _valid_value(spec, value):
    return (type(value) in TYPES[spec.type] and
            (type(value) != float or math.isfinite(value)) and
            (type(value) != str or 0 < len(value) <= 128) and
            (spec.minimum is None or value >= spec.minimum) and
            (spec.maximum is None or value <= spec.maximum))


def _bind(schema, bindings):
    if set(schema) != set(bindings):
        raise ValueError('Each declared parameter needs exactly one binding.')
    for name, value in bindings.items():
        spec = schema[name]
        if not _valid_value(spec, value) or (spec.enum is not None and value not in spec.enum):
            raise ValueError(f'Invalid value for parameter {name}.')
    return bindings


def _substitute(arguments, bindings):
    if isinstance(arguments, dict):
        return {key: _substitute(value, bindings) for key, value in arguments.items()}
    if isinstance(arguments, list):
        return [_substitute(value, bindings) for value in arguments]
    match = TOKEN.fullmatch(arguments) if isinstance(arguments, str) else None
    if match:
        if match[1] not in bindings:
            raise ValueError(f'Undeclared parameter {match[1]}.')
        return bindings[match[1]]
    return arguments


def _normalize(text):
    return re.sub(r'\s+', ' ', text.lower().strip().rstrip('.!'))


class SkillRegistry:
    def __init__(self, path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {
            'versions': {}, 'active': {}, 'validations': {}, 'evaluations': [], 'decisions': []}
        for version, record in self.data['versions'].items():
            if version != compute_skill_hash(SkillDefinition.model_validate(record['definition'])):
                raise ValueError('Persisted skill hash mismatch.')
        for skill_id, version in self.data['active'].items():
            record = self.data['versions'][version]
            if record['definition']['skill_id'] != skill_id or record['status'] != 'active':
                raise ValueError('Persisted active skill index is inconsistent.')

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            try:
                json.dump(self.data, handle, indent=2, allow_nan=False)
                handle.flush()
                temporary.replace(self.path)
            finally:
                temporary.unlink(missing_ok=True)

    def get(self, skill_id, version=None):
        version = version or self.data['active'].get(skill_id)
        entry = self.data['versions'].get(version)
        if not entry or entry['definition']['skill_id'] != skill_id:
            raise KeyError('Unknown skill/version.')
        return copy.deepcopy({**entry['definition'], 'version': version, 'status': entry['status']})

    def list(self):
        return [self.get(skill_id) for skill_id in self.data['active']]

    def match(self, text):
        norm = _normalize(text)
        if re.search(r"\b(?:no|not|never|cancel|stop|except|unless|instead|don't|can’t|can't)\b", norm):
            return None
        matches = {}
        for skill in self.list():
            schema = skill['parameter_schema']
            for template in skill['retrieval_examples']:
                parts = SLOT.split(_normalize(template))
                if set(parts[1::2]) != set(schema):
                    continue
                aliases = {}
                pattern = re.escape(parts[0])
                for slot, literal in zip(parts[1::2], parts[2::2]):
                    spec = schema[slot]
                    if slot in aliases or not spec['enum']:
                        break
                    aliases[slot] = {_normalize(str(v).replace('_', ' ')): v for v in spec['enum']}
                    if len(aliases[slot]) != len(spec['enum']):
                        break
                    pattern += f'(?P<{slot}>' + '|'.join(map(re.escape, aliases[slot])) + ')' + re.escape(literal)
                else:
                    match = re.fullmatch(pattern, norm)
                    if match:
                        bindings = {slot: aliases[slot][value] for slot, value in match.groupdict().items()}
                        matches[(skill['version'], compute_skill_hash(bindings))] = PlanDraft(
                            skill_id=skill['skill_id'], skill_version=skill['version'], bindings=bindings)
        return next(iter(matches.values())) if len(matches) == 1 else None

    @staticmethod
    def _validate_schema(definition):
        for key, spec in definition.parameter_schema.items():
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', key):
                raise ValueError('Invalid skill parameter name.')
            if ((spec.minimum is not None or spec.maximum is not None) and spec.type not in ('integer', 'number') or
                    spec.minimum is not None and spec.maximum is not None and spec.minimum > spec.maximum or
                    spec.enum is not None and any(not _valid_value(spec, value) for value in spec.enum)):
                raise ValueError(f'Invalid parameter schema for {key}.')
        if any(len(example) > 300 for example in definition.retrieval_examples):
            raise ValueError('Retrieval examples must be at most 300 characters.')

    def candidate(self, definition):
        version = compute_skill_hash(definition)
        if version not in self.data['versions']:
            self.data['versions'][version] = {'definition': definition.model_dump(mode='json'),
                                              'status': 'candidate'}
            self._save()
        return version

    def validate_for_task(self, task_id, definition):
        version = self.candidate(definition)
        entry = self.data['versions'][version]
        if entry['status'] in ('rejected', 'retired'):
            raise ValueError('This candidate version cannot be executed.')
        if entry['status'] != 'active':
            entry['status'] = 'task_validated'
            self.data['validations'].setdefault(task_id, {}).setdefault(version, False)
            self._save()
        return version

    def authorize(self, task_id, skill_id, version, *, consume=False):
        status = self.get(skill_id, version)['status']
        if status == 'active':
            return
        versions = self.data['validations'].get(task_id, {})
        if status != 'task_validated' or versions.get(version) is not False:
            raise ValueError('This candidate has no unused validation for this task.')
        if consume:
            versions[version] = True
            self._save()

    def compile(self, draft, *, task_id=None):
        """Flatten pinned skill composition and independently validate supported steps."""
        definition = draft.skill_definition
        if definition and (draft.skill_id or draft.skill_version):
            raise ValueError('Choose an authored or a registered skill definition.')
        if draft.skill_version and not draft.skill_id:
            raise ValueError('Skill version requires a skill ID.')
        if definition or draft.skill_id:
            if draft.steps or draft.preconditions != type(draft.preconditions)() or draft.outcome_checks or draft.expected_state:
                raise ValueError('A skill proposal cannot override its definition.')
            if draft.skill_id:
                skill = self.get(draft.skill_id, draft.skill_version)
                self.authorize(task_id, draft.skill_id, skill['version'])
                definition = SkillDefinition.model_validate({k: v for k, v in skill.items() if k not in ('status', 'version')})
            preconditions = [definition.preconditions]
            checks = list(definition.outcome_checks)
            steps = self._expand(definition, draft.bindings, preconditions, checks, depth=0)
            expected_state = definition.expected_state
        else:
            if draft.bindings:
                raise ValueError('Bindings require a skill definition.')
            steps = [self._primitive(step) for step in draft.steps]
            preconditions, checks, expected_state = [draft.preconditions], draft.outcome_checks, draft.expected_state
        actions = [i for i, step in enumerate(steps) if step.operation in MOCK_OPERATIONS]
        if not 1 <= len(steps) <= 8 or len(actions) > 1:
            raise ValueError('A plan requires 1–8 steps and at most one mock action.')
        if actions:
            if not any(step.operation in ('observe', 'inspect_scene') for step in steps[:actions[0]]):
                raise ValueError('A mock action plan requires an image checkpoint before execution.')
            if steps[-1].operation != 'observe' or not checks:
                raise ValueError('A mock action plan must end with an independent observation and outcome checks.')
        return {
            'skill_id': definition.skill_id if definition else None,
            'skill_version': compute_skill_hash(definition) if definition else None,
            'bindings': draft.bindings,
            'steps': [step.model_dump(mode='json') for step in steps],
            'preconditions': [rule.model_dump(mode='json') for rule in preconditions],
            'expected_state': expected_state,
            'outcome_checks': [check.model_dump(mode='json') for check in checks],
            'limitations': definition.limitations if definition else [],
            'evidence_ids': list(dict.fromkeys(draft.evidence_ids + (definition.evidence_ids if definition else []))),
        }

    @staticmethod
    def _primitive(step):
        if step.operation not in PRIMITIVE_SCHEMAS:
            raise ValueError('Composition requires an enclosing skill definition.')
        args = PRIMITIVE_SCHEMAS[step.operation].model_validate(step.arguments)
        return Step(operation=step.operation, arguments=args.model_dump(mode='json'))

    def _expand(self, definition, bindings, preconditions, checks, *, depth):
        if depth > 2:
            raise ValueError('Skill composition depth exceeded.')
        self._validate_schema(definition)
        _bind(definition.parameter_schema, bindings)
        steps = []
        for step in definition.steps:
            args = _substitute(step.arguments, bindings)
            if step.operation != 'call_skill':
                steps.append(self._primitive(Step(operation=step.operation, arguments=args)))
                continue
            if set(args) != {'skill_id', 'skill_version', 'bindings'} or not isinstance(args['bindings'], dict):
                raise ValueError('Composition requires a pinned skill and explicit bindings.')
            skill = self.get(args['skill_id'], args['skill_version'])
            if skill.pop('status') != 'active':
                raise ValueError('Only active skill versions may be composed.')
            skill.pop('version')
            child = SkillDefinition.model_validate(skill)
            preconditions.append(child.preconditions)
            checks.extend(child.outcome_checks)
            steps.extend(self._expand(child, args['bindings'], preconditions, checks, depth=depth + 1))
            if len(steps) > 8:
                raise ValueError('Expanded skill exceeds the step budget.')
        return steps

    def evaluation_decisions(self, version):
        return [copy.deepcopy(decision) for decision in self.data['decisions']
                if decision['candidate_hash'] == version]

    def record_evaluation(self, skill_id, version, raw_receipt):
        receipt = EvaluationReceipt.model_validate(raw_receipt)
        candidate = self.get(skill_id, version)
        if candidate['status'] not in ('candidate', 'task_validated'):
            raise ValueError('Only a candidate is eligible for evaluation.')
        baseline = self.data['active'].get(skill_id)
        if (receipt.candidate_hash != version or receipt.baseline_hash != baseline or
                any(r['evaluation_id'] == receipt.evaluation_id for r in self.data['evaluations'])):
            raise ValueError('Evaluation must identify the exact candidate and current baseline.')
        if any(not re.fullmatch(r'[0-9a-f]{64}', item) for item in receipt.artifact_hashes):
            raise ValueError('Evaluation artifacts require SHA-256 hashes.')
        approved = (receipt.passed and GATES.issubset(receipt.regression_gates) and
                    all(receipt.regression_gates.values()) and
                    receipt.candidate_recovered > receipt.baseline_recovered)
        decision = {'skill_id': skill_id, 'candidate_hash': version, 'baseline_hash': baseline,
                    'rollback_target': baseline, 'evaluation_id': receipt.evaluation_id,
                    'status': 'promoted' if approved and candidate['status'] == 'task_validated' else 'rejected'}
        if approved and candidate['status'] == 'task_validated':
            self.data['active'][skill_id] = version
            if baseline:
                self.data['versions'][baseline]['status'] = 'retired'
            self.data['versions'][version]['status'] = 'active'
        else:
            self.data['versions'][version]['status'] = 'rejected'
        self.data['evaluations'].append(receipt.model_dump(mode='json'))
        self.data['decisions'].append(decision)
        self._save()
        return copy.deepcopy(decision)
