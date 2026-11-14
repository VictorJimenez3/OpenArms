"""Persistent versioned reusable skill registry for OpenArms robot lab tasks.

Provides two-speed skill resolution:
- Warm fast path: Synchronous deterministic slot-filling and validation with zero model calls.
- Cold expert path: Composes validated multi-step composite skills (e.g. transfer + observe)
  using GenAI SDK when configured, or a deterministic compiler fallback.
Candidate skills require independent test evidence before promotion to active mock status.
Physical motor execution is never auto-promoted.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union

# Configuration defaults
DEFAULT_EXPERT_MODEL = "gemini-3.8-flash"
ALLOWED_PRIMITIVES = {"transfer", "observe"}
ALLOWED_OBJECTS = {"mandarin", "orange", "sample"}
ALLOWED_SOURCES = {"A", "C"}
ALLOWED_DESTINATIONS = {"B"}

# Known unsupported objects to reject explicitly with helpful feedback
KNOWN_UNSUPPORTED_OBJECTS = {
    "apple", "banana", "beaker", "vial", "cup", "water", "liquid", "acid",
    "cube", "block", "rock", "stone", "flask", "tube", "pellet", "tablet",
    "ball", "box", "gripper", "wire", "reagent", "petri",
}

# Known unsupported action verbs
UNSUPPORTED_ACTION_VERBS = {
    "teleport", "fly", "clean", "throw", "destroy", "eat", "cook", "sing",
    "play", "synthesize", "pour", "spill", "drop", "stir", "shake", "cut",
    "burn", "dance",
}

# Active seed skill
SEED_KNOWN_STATION_TRANSFER: Dict[str, Any] = {
    "skill_id": "known_station_transfer.v1",
    "name": "Known Station Transfer",
    "version": "1.0.0",
    "status": "active",
    "controller_ref": "transfer",
    "description": (
        "Transfer an orange/mandarin or sample from station A or C to station B "
        "using calibrated SO-101 arm trajectory."
    ),
    "steps": [
        {
            "action": "transfer",
            "args": {
                "source": "$source",
                "destination": "$destination",
                "object": "$object",
            },
        }
    ],
    "parameters": {
        "object": {
            "type": "string",
            "enum": ["mandarin", "orange", "sample"],
            "description": "Item to be transferred (normalized to 'mandarin' or 'sample')",
        },
        "source": {
            "type": "string",
            "enum": ["A", "C"],
            "description": "Pickup station",
        },
        "destination": {
            "type": "string",
            "enum": ["B"],
            "description": "Placement station",
        },
    },
    "preconditions": {
        "source_station_occupied": True,
        "destination_station_empty": True,
        "gripper_calibrated": True,
    },
    "expected_outcomes": {
        "source_station_vacated": True,
        "destination_station_occupied": True,
    },
    "approval_scopes": {
        "mock": "approved",
        "physical": "team_reported_baseline_only",
    },
    "evidence": {
        "type": "baseline",
        "report": (
            "Physical baseline TEAM-REPORTED only; not independently verified in current "
            "connected evidence harness."
        ),
        "source": "Notion snapshot 2026-11-14",
    },
    "limitations": (
        "Calibrated station geometry only (A->B, C->B). No uncalibrated spatial generalization. "
        "Physical runner requires supervisor bench stop."
    ),
    "versions": ["1.0.0"],
}


# The grammar deliberately consumes the whole request. Broad substring extraction
# would silently discard quantities, new objects, extra actions, or motion settings.
_TRANSFER = {"action": "transfer", "args": {
    "source": "$source", "destination": "$destination", "object": "$object"}}
_TRANSFER_OBSERVE = [_TRANSFER, {"action": "observe", "args": {"station": "$destination"}}]
_VERB = r"(?:transfer|move|carry|take|bring|put|place|transport|deliver|relocate|send|shift|pickup|pick up|test)"
_OBJECT = r"(?:the |an? )?(?P<object>[a-z][a-z-]*)"
_SOURCE = r"(?:the )?(?:source )?(?:station )?(?P<source>[a-z0-9])"
_DESTINATION = r"(?:the )?(?:destination )?(?:station )?(?P<destination>[a-z0-9])"
_OBSERVE = (r"(?:observe|inspect|watch|check|verify)"
            r"(?: (?:the )?(?:placement|outcome|result|it|destination))?"
            r"(?: (?:at |in )?(?:the )?(?:destination )?station (?P<observed>[a-z0-9]))?")


def _parse_request(text: str, abstract: bool = False) -> Dict[str, Any]:
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        return {"status": "clarify", "message": "Please give one transfer request."}
    cleaned = re.sub(r"\s+", " ", text.strip().lower())
    polite = re.match(r"^(?:(?:can|could|would|will) you |(?:can|could) we |i(?:'d| would) like you to |i want you to )", cleaned)
    if polite:
        cleaned = cleaned[polite.end():]
    elif cleaned.endswith("?"):
        return {"status": "clarify", "message": "Please give an affirmative request, rather than a question."}
    cleaned = re.sub(r"[.!?]$", "", cleaned).strip()
    cleaned = re.sub(r"^please ", "", cleaned)
    cleaned = re.sub(r",? please$", "", cleaned)
    for verb in sorted(UNSUPPORTED_ACTION_VERBS):
        if re.search(rf"\b{verb}\b", cleaned):
            return {"status": "unsupported", "message": f"Unsupported action '{verb}'; request does not match a supported skill."}
    observe = False
    observed = None
    observation = re.fullmatch(r"(?P<transfer>.+?)(?:,? and (?:then )?|,? then |,? followed by )" + _OBSERVE, cleaned)
    if observation:
        observe = True
        observed = observation.group("observed")
        cleaned = observation.group("transfer")
    # An abstract skill request is allowed only for composition, never execution.
    if abstract and observe and cleaned in ("transfer", "move", "transfer an object", "move an object"):
        return {"status": "parsed", "parameters": {"object": None, "source": None, "destination": None}, "observe": True}

    patterns = [
        _VERB + r"(?: from " + _SOURCE + r")?(?: (?:to|into|in) " + _DESTINATION + r")?",
        # Transfer phrasing, including partial requests that need missing-slot clarification.
        _VERB + r" " + _OBJECT + r"(?: (?:from|at) " + _SOURCE + r")?(?: (?:to|into|in) " + _DESTINATION + r")?",
        _VERB + r" " + _OBJECT + r" (?:to|into|in) " + _DESTINATION + r" from " + _SOURCE,
        _VERB + r" " + _OBJECT + r" " + _SOURCE + r" (?:to|->) " + _DESTINATION,
        _OBJECT + r" " + _SOURCE + r" (?:to|->) " + _DESTINATION,
        # Pickup/place describes the same single transfer, not a second independent action.
        r"(?:pick up|pickup|take) " + _OBJECT + r" (?:from|at) " + _SOURCE +
        r" and (?:place|put|set|release) it (?:to|at|in|into|on) " + _DESTINATION,
    ]
    match = next((m for pattern in patterns if (m := re.fullmatch(pattern, cleaned))), None)
    if match is None:
        return {"status": "clarify", "message": "Request is ambiguous or contains unsupported details. Specify one object and one source/destination; extra actions, quantities and motion settings need separate validated skills."}
    slots = match.groupdict()
    obj = slots.get("object")
    if obj == "orange":
        obj = "mandarin"
    if obj and obj not in {"mandarin", "sample"}:
        return {"status": "unsupported", "message": f"Unsupported object '{obj}'. Only mandarin (orange) and sample are supported."}
    source = slots.get("source")
    destination = slots.get("destination")
    source = source.upper() if source else None
    destination = destination.upper() if destination else None
    if source and source not in ALLOWED_SOURCES:
        return {"status": "unsupported", "message": f"Unsupported source station '{source}'; use A or C."}
    if destination and destination not in ALLOWED_DESTINATIONS:
        return {"status": "unsupported", "message": f"Unsupported destination station '{destination}'; use B."}
    if observed and (not destination or observed.upper() != destination):
        return {"status": "unsupported", "message": "Observation must target the transfer destination B."}
    return {"status": "parsed", "parameters": {"object": obj, "source": source, "destination": destination}, "observe": observe}


def _mock_state(source: str, obj: str) -> Dict[str, Any]:
    return {"at": "HOME", "holding": None, "armed": True, "gripper": "open",
            "portions_left": {}, "receiver_load": {},
            "point_holds": {"A": None, "C": None, "B": None, source: obj},
            "observation_sensor_ready": True}


def _execute_bound_skill(skill: Dict[str, Any], parameters: Dict[str, Any],
                         state: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Symbolically execute bound steps with the same independent validator as runtime."""
    from .contracts import Parameters
    from agentic.openarms_agent.validator import validate
    bound_parameters = Parameters.model_validate(parameters).model_dump()
    state = copy.deepcopy(state)
    observations = {}
    for step in skill["steps"]:
        args = {}
        for name, value in step["args"].items():
            if not isinstance(value, str) or not value.startswith("$") or value[1:] not in bound_parameters:
                raise ValueError("Unsupported primitive binding.")
            args[name] = bound_parameters[value[1:]]
        if step["action"] == "transfer":
            if set(args) != {"source", "destination", "object"}:
                raise ValueError("Transfer arguments must be source, destination, and object.")
            if state["point_holds"].get(args["source"]) != args["object"]:
                raise ValueError("Requested object is absent at source.")
            plan = {"plan_id": "candidate-mock-test", "student_instruction": "Bound artifact test",
                    "steps": [{"action": "move_block", "args": {"from": args["source"], "to": args["destination"]}}]}
            stations = {name: {"kind": "point", "holds": item}
                        for name, item in state["point_holds"].items()}
            checked = validate(plan, state, stations)
            if not checked["ok"]:
                raise ValueError(checked["reason"])
            state = checked["end_state"]
        elif step["action"] == "observe":
            if not state.get("observation_sensor_ready"):
                raise ValueError("Mock observation sensor is unavailable.")
            if set(args) != {"station"} or args["station"] not in state["point_holds"]:
                raise ValueError("Observation arguments require a known station.")
            observations[args["station"]] = state["point_holds"][args["station"]]
        else:
            raise ValueError("Unsupported primitive.")
    return state, observations


def compute_skill_hash(skill_data: Dict[str, Any]) -> str:
    """Hash definition, including physical scope, excluding evidence and mock lifecycle."""
    volatile = {"evidence", "evidence_id", "promoted_at", "updated_at", "status", "content_hash"}
    frozen = copy.deepcopy({k: v for k, v in skill_data.items() if k not in volatile})
    if isinstance(frozen.get("approval_scopes"), dict):
        frozen["approval_scopes"].pop("mock", None)
    payload = json.dumps(frozen, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SkillRegistry:
    """Persistent JSON versioned reusable skill registry for OpenArms."""

    def __init__(self, path: Union[Path, str]):
        target_path = Path(path)
        if target_path.is_dir() or (not target_path.exists() and not target_path.suffix):
            self.catalog_path = target_path / "skills.json"
        else:
            self.catalog_path = target_path

        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self._skills: Dict[str, Dict[str, Any]] = {}
        self._evidence: Dict[str, Dict[str, Any]] = {}
        self._load_or_initialize()

    def _load_or_initialize(self) -> None:
        """Load catalog from disk or seed with active known station transfer skill."""
        if self.catalog_path.exists():
            try:
                with open(self.catalog_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "skills" in data and isinstance(data["skills"], dict):
                    self._skills = data["skills"]
                    self._evidence = data.get("test_evidence", {})
                elif isinstance(data, dict):
                    self._skills = data
                else:
                    self._skills = {}
            except (json.JSONDecodeError, OSError) as e:
                raise ValueError(f"Failed to load corrupted skill registry from {self.catalog_path}: {e}")

        if not self._skills:
            seed = copy.deepcopy(SEED_KNOWN_STATION_TRANSFER)
            seed["content_hash"] = compute_skill_hash(seed)
            self._skills[seed["skill_id"]] = seed
            self._save()

    def _save(self) -> None:
        """Persist catalog atomically to protect artifact edits."""
        data = {
            "schema_version": "1.0.0",
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "skills": self._skills,
            "test_evidence": self._evidence,
        }
        tmp_path = self.catalog_path.with_name(f"{self.catalog_path.name}.tmp.{os.getpid()}")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.catalog_path)
        except Exception:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

    def list(self) -> List[Dict[str, Any]]:
        """Return list of all registered skills in the catalog."""
        return [copy.deepcopy(skill) for skill in self._skills.values()]

    def get(self, skill_id: str) -> Dict[str, Any]:
        """Return skill dictionary by id. Raises KeyError if not found."""
        if skill_id not in self._skills:
            raise KeyError(f"Skill '{skill_id}' not found in registry.")
        return copy.deepcopy(self._skills[skill_id])

    def resolve(self, text: str) -> Dict[str, Any]:
        """Resolve an entire affirmative request; never discard extra instructions."""
        started = time.perf_counter()

        def result(status, message, **fields):
            return {"status": status, "message": message, **fields, "metrics": {
                "model_calls": 0, "tokens": 0,
                "planning_ms": (time.perf_counter() - started) * 1000,
            }}

        parsed = _parse_request(text)
        if parsed.get("status") != "parsed":
            return result(parsed["status"], parsed["message"])
        parameters = parsed["parameters"]
        missing = [key for key, value in parameters.items() if value is None]
        if missing:
            return result("clarify", "Please specify " + ", ".join(missing) +
                          ". Use one mandarin or sample, source A or C, and destination B.")
        skill_id = "transfer_and_observe.v1" if parsed["observe"] else "known_station_transfer.v1"
        skill = self._skills.get(skill_id)
        if not skill or skill.get("status") != "active":
            state = "candidate; test and promote it first" if skill else "not registered"
            return result("unsupported", f"Skill '{skill_id}' is {state}.")
        if skill_id == "transfer_and_observe.v1":
            evidence = self._evidence.get(skill.get("evidence_id"))
            if (not evidence or evidence.get("skill_id") != skill_id or
                    evidence.get("skill_hash") != compute_skill_hash(skill)):
                return result("unsupported", "Active composite no longer matches its tested artifact.")
        if skill.get("steps") != (_TRANSFER_OBSERVE if parsed["observe"] else [_TRANSFER]):
            return result("unsupported", "Skill definition has unsupported steps or parameter bindings.")
        return result("resolved", f"Resolved instruction to active skill '{skill_id}'.",
                      skill_id=skill_id, parameters=parameters)

    async def compose(self, instruction: str) -> Dict[str, Any]:
        """Compose a reusable candidate skill from natural language instruction.

        Uses OPENARMS_EXPERT_MODEL and GEMINI_API_KEY/GOOGLE_API_KEY if present with SDK.
        If no key is configured, uses deterministic compiler fallback expert_mode='local_composer'
        with model_calls=0 and no pretend model.
        """
        # Safety filter: reject instructions attempting low-level motor or unsafe code
        forbidden = re.search(r"\b(pwm|servo|baud|hex|motor\s+id|raw\s+bus|eval|exec)\b", instruction, re.I)
        if forbidden:
            raise ValueError(
                f"Composition rejected: instruction contains low-level hardware or forbidden token '{forbidden.group(1)}'."
            )

        parsed_request = _parse_request(instruction, abstract=True)
        if parsed_request.get("status") != "parsed" or not parsed_request.get("observe"):
            raise ValueError("Unsupported composition intent: request one transfer followed by destination observation.")
        candidate_id = "transfer_and_observe.v1"
        if candidate_id in self._skills:
            raise ValueError("This version already exists. Reuse its artifact; a new version requires explicit review.")

        expert_model = os.environ.get("OPENARMS_EXPERT_MODEL", DEFAULT_EXPERT_MODEL)
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

        steps: List[Dict[str, Any]] = []
        expert_mode = "local_composer"
        model_calls = 0
        tokens = 0

        planning_started=time.perf_counter()
        if api_key:
            from google import genai
            from google.genai import types
            client=genai.Client(api_key=api_key)
            try:
                response=await client.aio.models.generate_content(model=expert_model,contents=(
                    "Compose a reusable OpenArms skill for: "+instruction+
                    '. Allowed steps are exactly [{"action":"transfer","args":{"source":"$source","destination":"$destination","object":"$object"}},'
                    '{"action":"observe","args":{"station":"$destination"}}]. Return JSON {"steps":[...]}. '
                    'Compose only the requested intent using these existing primitives. No motor code, new parameters or extra actions.'),
                    config=types.GenerateContentConfig(response_mime_type='application/json'))
                model_calls=1
                expert_mode=expert_model
                parsed=json.loads(response.text)
                if not isinstance(parsed, dict) or set(parsed) != {"steps"}:
                    raise ValueError("Expert candidate must contain only steps.")
                steps=parsed["steps"]
                tokens=getattr(getattr(response, 'usage_metadata', None), 'total_token_count', None)
                if type(tokens) is not int or tokens < 0:
                    tokens = None
            finally:
                await client.aio.aclose()

        # Fallback deterministic compiler: expert_mode='local_composer', model_calls=0
        if not api_key:
            expert_mode = "local_composer"
            model_calls = 0
            tokens = 0
            # Construct standard transfer_and_observe steps
            steps = [
                {
                    "action": "transfer",
                    "args": {
                        "source": "$source",
                        "destination": "$destination",
                        "object": "$object",
                    },
                },
                {
                    "action": "observe",
                    "args": {
                        "station": "$destination",
                    },
                },
            ]

        if steps != _TRANSFER_OBSERVE:
            raise ValueError('Expert candidate has unsupported steps, order or parameter bindings.')

        candidate_skill: Dict[str, Any] = {
            "skill_id": candidate_id,
            "name": "Transfer and Observe",
            "version": "1.0.0",
            "status": "candidate",
            "controller_ref": "composite",
            "description": (
                "Composed skill: transfer an object from source (A or C) to destination B, "
                "followed by visual/sensor observation of the destination fixture."
            ),
            "steps": steps,
            "parameters": {
                "object": {
                    "type": "string",
                    "enum": ["mandarin", "orange", "sample"],
                    "description": "Item to transfer and observe",
                },
                "source": {
                    "type": "string",
                    "enum": ["A", "C"],
                    "description": "Pickup station",
                },
                "destination": {
                    "type": "string",
                    "enum": ["B"],
                    "description": "Placement and observation station",
                },
            },
            "preconditions": {
                "source_occupied": True,
                "destination_empty": True,
                "observation_sensor_ready": True,
            },
            "expected_outcomes": {
                "object_at_destination": True,
                "source_vacated": True,
                "destination_observed": True,
            },
            "approval_scopes": {
                "mock": "pending_test",
                "physical": "unsupported",
            },
            "limitations": (
                "Candidate composition only. Mock approval pending test; "
                "physical execution strictly blocked until independently authorized."
            ),
            "evidence": None,
            "evidence_id": None,
            "expert_mode": expert_mode,
            "model_calls": model_calls,
            "tokens": tokens,
            "planning_ms":(time.perf_counter()-planning_started)*1000,
            "versions": ["1.0.0"],
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        candidate_skill["content_hash"] = compute_skill_hash(candidate_skill)
        self._skills[candidate_id] = candidate_skill
        self._save()
        return copy.deepcopy(candidate_skill)

    def test_candidate(self, skill_id: str) -> Dict[str, Any]:
        """Run independent mocked structural and parameter tests on a candidate skill.

        Returns an evidence record with hash binding version.
        """
        if skill_id not in self._skills:
            raise KeyError(f"Skill '{skill_id}' not found in registry.")

        skill = self._skills[skill_id]
        if not isinstance(skill, dict) or skill.get("skill_id") != skill_id:
            raise ValueError("Skill artifact identity does not match the registry key.")
        tests_passed: List[str] = []

        # 1. Structural Checks
        required_fields = ["skill_id", "steps", "parameters", "preconditions", "expected_outcomes", "approval_scopes"]
        for field in required_fields:
            if field not in skill:
                raise ValueError(f"Candidate structural test failed: missing field '{field}'.")
        tests_passed.append("structural_fields_check")

        # 2. Primitives Whitelist Check
        steps = skill.get("steps", [])
        if not steps or not isinstance(steps, list):
            raise ValueError("Candidate structural test failed: steps must be a non-empty list.")

        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                raise ValueError(f"Candidate step {i} must be a dictionary.")
            action = step.get("action")
            if action not in ALLOWED_PRIMITIVES:
                raise ValueError(f"Candidate step {i} uses forbidden primitive '{action}'. Allowed: {ALLOWED_PRIMITIVES}")
            args = step.get("args", {})
            if not isinstance(args, dict):
                raise ValueError(f"Candidate step {i} has invalid args: must be a dict.")
        tests_passed.append("primitives_whitelist_check")

        # 3. Parameter Bindings Check
        params = skill.get("parameters", {})
        if not isinstance(params, dict):
            raise ValueError("Candidate parameters must be a dictionary.")
        for i, step in enumerate(steps):
            for k, val in step.get("args", {}).items():
                if isinstance(val, str) and val.startswith("$"):
                    param_name = val[1:]
                    if param_name not in params:
                        raise ValueError(f"Candidate step {i} references undeclared parameter '{param_name}'.")
        tests_passed.append("parameter_bindings_check")

        if steps not in ([_TRANSFER], _TRANSFER_OBSERVE):
            raise ValueError("Skill must bind one transfer, optionally followed by destination observation.")
        has_observation = steps == _TRANSFER_OBSERVE
        # Execute the actual bound artifact through the independent legacy validator.
        # This is a symbolic mock check of occupancy/gripper invariants, not physics.
        expected_parameters = {"object": {"mandarin", "orange", "sample"},
                               "source": {"A", "C"}, "destination": {"B"}}
        if set(params) != set(expected_parameters):
            raise ValueError("Candidate parameters must be exactly object, source and destination.")
        for key, values in expected_parameters.items():
            definition = params[key]
            if (not isinstance(definition, dict) or definition.get("type") != "string" or
                    not isinstance(definition.get("enum"), list) or
                    not all(isinstance(value, str) for value in definition["enum"]) or
                    set(definition["enum"]) != values):
                raise ValueError(f"Candidate parameter '{key}' has an unsupported domain.")
        scopes = skill.get("approval_scopes", {})
        is_baseline = (skill_id == "known_station_transfer.v1" and steps == [_TRANSFER] and
                       scopes.get("physical") == "team_reported_baseline_only")
        if skill.get("status") not in ("candidate", "active") or (
                scopes.get("physical") != "unsupported" and not is_baseline):
            raise ValueError("Mock tests cannot approve a new physical authorization scope.")
        for source in ("A", "C"):
            for obj in ("sample", "mandarin"):
                bound = {"source": source, "destination": "B", "object": obj}
                state = _mock_state(source, obj)
                end, observed = _execute_bound_skill(skill, bound, state)
                if (end["point_holds"][source] is not None or
                        end["point_holds"]["B"] != obj or observed != ({"B": obj} if has_observation else {})):
                    raise ValueError("Bound mock execution outcome mismatch.")
                tests_passed.append(f"mock_{source}_to_B_{obj}")
                failures = [
                    ("occupied_destination", {"point_holds": {source: obj, "B": "obstruction"}}),
                    ("empty_source", {"point_holds": {source: None, "B": None}}),
                    ("held_object", {"holding": "other"}),
                    ("disarmed", {"armed": False}),
                ]
                if has_observation:
                    failures.append(("sensor_unavailable", {"observation_sensor_ready": False}))
                for case, changed in failures:
                    invalid = copy.deepcopy(state)
                    invalid.update(changed)
                    try:
                        _execute_bound_skill(skill, bound, invalid)
                    except ValueError:
                        tests_passed.append(f"reject_{case}_{source}_{obj}")
                    else:
                        raise ValueError(f"Mock boundary test failed to reject {case}.")
        for invalid in ({"source": "B", "destination": "A", "object": "sample"},
                        {"source": "A", "destination": "B", "object": "beaker"}):
            try:
                _execute_bound_skill(skill, invalid, _mock_state("A", "sample"))
            except ValueError:
                continue
            raise ValueError("Mock boundary test accepted unsupported parameters.")
        tests_passed.append("boundary_rejection_check")

        # Generate Evidence Binding
        content_hash = compute_skill_hash(skill)
        evidence_hash_seed = f"{skill_id}:{content_hash}:{time.time()}"
        evidence_id = f"ev-{hashlib.sha256(evidence_hash_seed.encode('utf-8')).hexdigest()[:12]}"

        evidence: Dict[str, Any] = {
            "evidence_id": evidence_id,
            "skill_id": skill_id,
            "skill_hash": content_hash,
            "verdict": "passed",
            "provenance": "MOCK",
            "test_method": "bound artifact through legacy validator; symbolic state only",
            "tests_passed": tests_passed,
            "approval_scopes": {
                "mock": "approved",
                "physical": "unsupported",
            },
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        # Bind evidence to candidate in registry
        self._evidence[evidence_id] = copy.deepcopy(evidence)
        if not is_baseline:
            skill["evidence"] = evidence
        skill["evidence_id"] = evidence_id
        self._save()
        return copy.deepcopy(evidence)

    def promote(self, skill_id: str, evidence_id: str) -> Dict[str, Any]:
        """Promote a tested candidate skill to active status.

        Refuses untested or changed candidates.
        Persists active mock approval only; physical motion is NEVER auto-promoted.
        """
        if skill_id not in self._skills:
            raise KeyError(f"Skill '{skill_id}' not found in registry.")

        skill = self._skills[skill_id]

        if skill.get("status") == "active":
            raise ValueError(f"Skill '{skill_id}' is already active.")

        # Check evidence presence and matching ID
        evidence = self._evidence.get(evidence_id)
        if (not evidence or skill.get("evidence_id") != evidence_id or
                evidence.get("skill_id") != skill_id or evidence.get("evidence_id") != evidence_id):
            raise ValueError(
                f"Refusing promotion: skill '{skill_id}' has not been tested with evidence '{evidence_id}'."
            )

        if skill.get("status") != "candidate":
            raise ValueError("Only candidates can be promoted.")
        if evidence.get("verdict") != "passed" or evidence.get("provenance") != "MOCK":
            raise ValueError(f"Refusing promotion: evidence '{evidence_id}' has non-passing verdict.")

        # Check hash binding: verify candidate has not been modified since test
        current_hash = compute_skill_hash(skill)
        tested_hash = evidence.get("skill_hash")
        if current_hash != tested_hash:
            raise ValueError(
                f"Refusing promotion: skill '{skill_id}' content hash ({current_hash}) does not match "
                f"evidence tested hash ({tested_hash}). Candidate was modified after testing."
            )

        # Update lifecycle: mock approved only, physical NEVER auto-promoted
        skill["status"] = "active"
        skill["approval_scopes"] = {
            "mock": "approved",
            "physical": "unsupported",
        }
        skill["promoted_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._save()
        return copy.deepcopy(skill)
