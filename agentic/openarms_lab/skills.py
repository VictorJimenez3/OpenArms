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


def compute_skill_hash(skill_data: Dict[str, Any]) -> str:
    """Compute deterministic SHA256 of skill definition excluding volatile runtime fields."""
    volatile = {"evidence", "evidence_id", "promoted_at", "updated_at", "status"}
    frozen = {k: v for k, v in skill_data.items() if k not in volatile}
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
        self._load_or_initialize()

    def _load_or_initialize(self) -> None:
        """Load catalog from disk or seed with active known station transfer skill."""
        if self.catalog_path.exists():
            try:
                with open(self.catalog_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "skills" in data and isinstance(data["skills"], dict):
                    self._skills = data["skills"]
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
        """Synchronously resolve a natural language instruction against active skills.

        Returns:
            dict with {
                'status': 'resolved' | 'clarify' | 'unsupported',
                'skill_id': str (optional),
                'parameters': dict (optional),
                'message': str,
                'metrics': {
                    'model_calls': int,
                    'tokens': int,
                    'planning_ms': float
                }
            }
        """
        start_time = time.perf_counter()
        normalized_text = text.strip()
        lowered = normalized_text.lower()

        # Check for explicitly unsupported action verbs
        for verb in UNSUPPORTED_ACTION_VERBS:
            if re.search(rf"\b{verb}\b", lowered):
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return {
                    "status": "unsupported",
                    "message": (
                        f"Instruction contains unsupported action '{verb}' and does not match any recognized "
                        "lab action. OpenArms only supports calibrated station transfers and buoyancy sample tests."
                    ),
                    "metrics": {
                        "model_calls": 0,
                        "tokens": 0,
                        "planning_ms": round(elapsed_ms, 3),
                    },
                }

        # Check for observation intent
        observe_match = re.search(
            r"\b(observe|inspect|inspection|check\s+placement|verify\s+placement|watch)\b",
            lowered,
        )
        wants_observe = bool(observe_match)

        # 1. Detect Object
        obj: Optional[str] = None
        # Check known supported objects
        if re.search(r"\b(mandarin|mandarins|orange|oranges)\b", lowered):
            obj = "mandarin"
        elif re.search(r"\b(sample|samples)\b", lowered):
            obj = "sample"
        else:
            # Check for known unsupported objects
            for unsupp in KNOWN_UNSUPPORTED_OBJECTS:
                if re.search(rf"\b{unsupp}\b", lowered):
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    return {
                        "status": "unsupported",
                        "message": (
                            f"Unsupported object '{unsupp}'. OpenArms currently only supports "
                            "'mandarin' (or 'orange') and 'sample'."
                        ),
                        "metrics": {
                            "model_calls": 0,
                            "tokens": 0,
                            "planning_ms": round(elapsed_ms, 3),
                        },
                    }

        # 2. Extract Stations
        source: Optional[str] = None
        destination: Optional[str] = None

        # Pattern A: Lesson buoyancy request syntax: "test sample at A in B" or "test sample at C in B"
        buoyancy_pattern = re.search(
            r"\btest\s+(?:the\s+)?sample\s+at\s+(?:the\s+)?(?:station\s+)?([A-Za-z0-9]+)\s+in\s+(?:the\s+)?(?:station\s+)?([A-Za-z0-9]+)\b",
            lowered,
        )
        if buoyancy_pattern:
            source = buoyancy_pattern.group(1).upper()
            destination = buoyancy_pattern.group(2).upper()
            if not obj:
                obj = "sample"
        else:
            # Pattern B: Explicit source: "from [the] [source] [station] X" / "pickup from X"
            from_match = re.search(
                r"\b(?:from|source|pickup\s+from|pick\s+up\s+from)\s+(?:the\s+)?(?:source\s+)?(?:station\s+)?([A-Za-z0-9]+)\b",
                lowered,
            )
            if from_match:
                source = from_match.group(1).upper()
            else:
                # "at [the] [station] X" when followed later by "to" or "in"
                at_match = re.search(
                    r"\bat\s+(?:the\s+)?(?:station\s+)?([A-Za-z0-9]+)\b(?=.*?\b(?:to|into|in)\b)",
                    lowered,
                )
                if at_match:
                    source = at_match.group(1).upper()

            # Pattern C: Explicit destination: "to [the] [destination] [station] Y" / "into Y" / "in Y"
            to_match = re.search(
                r"\b(?:to|into|in|destination)\s+(?:the\s+)?(?:destination\s+)?(?:station\s+)?([A-Za-z0-9]+)\b",
                lowered,
            )
            if to_match:
                destination = to_match.group(1).upper()

            # Pattern D: Arrow / transition syntax "A -> B" or "A to B"
            if not source or not destination:
                arrow_match = re.search(
                    r"\b(?:station\s+)?([A-Za-z0-9])\s*(?:->|to)\s*(?:station\s+)?([A-Za-z0-9])\b",
                    lowered,
                )
                if arrow_match:
                    if not source:
                        source = arrow_match.group(1).upper()
                    if not destination:
                        destination = arrow_match.group(2).upper()

        # 3. Check for explicitly unsupported stations first (before checking for missing stations)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        if source and source not in ALLOWED_SOURCES:
            return {
                "status": "unsupported",
                "message": (
                    f"Unsupported source station '{source}'. OpenArms calibrated pickup is only "
                    f"supported from stations {sorted(list(ALLOWED_SOURCES))}."
                ),
                "metrics": {
                    "model_calls": 0,
                    "tokens": 0,
                    "planning_ms": round(elapsed_ms, 3),
                },
            }

        if destination and destination not in ALLOWED_DESTINATIONS:
            return {
                "status": "unsupported",
                "message": (
                    f"Unsupported destination station '{destination}'. OpenArms calibrated placement "
                    f"is only supported to station {sorted(list(ALLOWED_DESTINATIONS))}."
                ),
                "metrics": {
                    "model_calls": 0,
                    "tokens": 0,
                    "planning_ms": round(elapsed_ms, 3),
                },
            }

        # 4. Handle Ambiguities (Missing Parameters)
        if not obj and (not source or not destination):
            return {
                "status": "unsupported",
                "message": (
                    f"Instruction '{normalized_text}' does not match any recognized lab action. "
                    "Expected station transfer or buoyancy sample test."
                ),
                "metrics": {
                    "model_calls": 0,
                    "tokens": 0,
                    "planning_ms": round(elapsed_ms, 3),
                },
            }

        if not obj:
            return {
                "status": "clarify",
                "message": "Missing object to transfer. Please specify whether to move a 'mandarin' or 'sample'.",
                "metrics": {
                    "model_calls": 0,
                    "tokens": 0,
                    "planning_ms": round(elapsed_ms, 3),
                },
            }

        if not source and not destination:
            return {
                "status": "clarify",
                "message": (
                    "Missing pickup and placement stations. Please specify source (A or C) "
                    "and destination (B)."
                ),
                "metrics": {
                    "model_calls": 0,
                    "tokens": 0,
                    "planning_ms": round(elapsed_ms, 3),
                },
            }

        if not source:
            return {
                "status": "clarify",
                "message": (
                    f"Ambiguous request: missing source station for {obj}. "
                    "Please specify whether to pick from station A or station C."
                ),
                "metrics": {
                    "model_calls": 0,
                    "tokens": 0,
                    "planning_ms": round(elapsed_ms, 3),
                },
            }

        if not destination:
            return {
                "status": "clarify",
                "message": (
                    f"Ambiguous request: missing destination station for {obj}. "
                    "Please specify placement destination station B."
                ),
                "metrics": {
                    "model_calls": 0,
                    "tokens": 0,
                    "planning_ms": round(elapsed_ms, 3),
                },
            }

        # 5. Route to Active Skill
        selected_skill_id = "known_station_transfer.v1"
        if wants_observe:
            # Check if transfer_and_observe.v1 exists and is active
            if "transfer_and_observe.v1" in self._skills:
                candidate_skill = self._skills["transfer_and_observe.v1"]
                if candidate_skill.get("status") == "active":
                    selected_skill_id = "transfer_and_observe.v1"
                else:
                    return {
                        "status": "unsupported",
                        "message": (
                            "Skill 'transfer_and_observe.v1' is currently a candidate and not yet active. "
                            "It must be tested and promoted before dispatch."
                        ),
                        "metrics": {
                            "model_calls": 0,
                            "tokens": 0,
                            "planning_ms": round(elapsed_ms, 3),
                        },
                    }
            else:
                return {
                    "status": "unsupported",
                    "message": (
                        "Observation composite skill 'transfer_and_observe.v1' is not registered. "
                        "Compose and promote the skill before dispatch."
                    ),
                    "metrics": {
                        "model_calls": 0,
                        "tokens": 0,
                        "planning_ms": round(elapsed_ms, 3),
                    },
                }
        else:
            if selected_skill_id not in self._skills or self._skills[selected_skill_id].get("status") != "active":
                return {
                    "status": "unsupported",
                    "message": f"Skill '{selected_skill_id}' is not active in the registry.",
                    "metrics": {
                        "model_calls": 0,
                        "tokens": 0,
                        "planning_ms": round(elapsed_ms, 3),
                    },
                }

        parameters = {
            "object": obj,
            "source": source,
            "destination": destination,
        }

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return {
            "status": "resolved",
            "skill_id": selected_skill_id,
            "parameters": parameters,
            "message": f"Resolved instruction to active skill '{selected_skill_id}' ({source} -> {destination}).",
            "metrics": {
                "model_calls": 0,
                "tokens": 0,
                "planning_ms": round(elapsed_ms, 3),
            },
        }

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

        expert_model = os.environ.get("OPENARMS_EXPERT_MODEL", DEFAULT_EXPERT_MODEL)
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

        steps: List[Dict[str, Any]] = []
        expert_mode = "local_composer"
        model_calls = 0
        tokens = 0

        if api_key:
            # Attempt to use Google GenAI SDK if available
            called_sdk = False
            try:
                # Try new google.genai SDK
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=api_key)
                prompt = (
                    f"You are the OpenArms expert robotics composer. Allowed primitive actions are: "
                    f"{list(ALLOWED_PRIMITIVES)}. Allowed parameters are $source, $destination, $object.\n"
                    f"Instruction: {instruction}\n"
                    f"Respond ONLY with a valid JSON object matching this schema:\n"
                    f'{{"steps": [{{"action": "transfer", "args": {{"source": "$source", "destination": "$destination", "object": "$object"}}}}, {{"action": "observe", "args": {{"station": "$destination"}}}}]}}'
                )
                response = client.models.generate_content(
                    model=expert_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                model_calls = 1
                expert_mode = expert_model
                raw_text = str(response.text) if response.text else "{}"
                parsed = json.loads(raw_text)
                if "steps" in parsed and isinstance(parsed["steps"], list):
                    for step in parsed["steps"]:
                        if step.get("action") not in ALLOWED_PRIMITIVES:
                            raise ValueError(f"SDK returned unapproved primitive action: {step.get('action')}")
                        steps.append(step)
                called_sdk = True
            except ImportError:
                # Try legacy google.generativeai SDK
                try:
                    import google.generativeai as genai_legacy

                    genai_legacy.configure(api_key=api_key)
                    model = genai_legacy.GenerativeModel(expert_model)
                    prompt = (
                        f"Allowed primitives: {list(ALLOWED_PRIMITIVES)}. "
                        f"Instruction: {instruction}. Output JSON with 'steps' array containing primitive actions."
                    )
                    res = model.generate_content(prompt)
                    model_calls = 1
                    expert_mode = expert_model
                    parsed = json.loads(res.text)
                    if "steps" in parsed and isinstance(parsed["steps"], list):
                        for step in parsed["steps"]:
                            if step.get("action") not in ALLOWED_PRIMITIVES:
                                raise ValueError(f"SDK returned unapproved primitive action: {step.get('action')}")
                            steps.append(step)
                    called_sdk = True
                except ImportError:
                    pass

            if not called_sdk and not steps:
                # API key was provided but neither SDK is installed; fall back to local compiler
                expert_mode = "local_composer"
                model_calls = 0

        # Fallback deterministic compiler: expert_mode='local_composer', model_calls=0
        if not steps:
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

        # Validate steps against whitelist
        for step in steps:
            action = step.get("action")
            if action not in ALLOWED_PRIMITIVES:
                raise ValueError(f"Invalid primitive '{action}' in composed candidate. Allowed: {ALLOWED_PRIMITIVES}")

        candidate_id = "transfer_and_observe.v1"
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
            action = step.get("action")
            if action not in ALLOWED_PRIMITIVES:
                raise ValueError(f"Candidate step {i} uses forbidden primitive '{action}'. Allowed: {ALLOWED_PRIMITIVES}")
            args = step.get("args", {})
            if not isinstance(args, dict):
                raise ValueError(f"Candidate step {i} has invalid args: must be a dict.")
        tests_passed.append("primitives_whitelist_check")

        # 3. Parameter Bindings Check
        params = skill.get("parameters", {})
        for i, step in enumerate(steps):
            for k, val in step.get("args", {}).items():
                if isinstance(val, str) and val.startswith("$"):
                    param_name = val[1:]
                    if param_name not in params:
                        raise ValueError(f"Candidate step {i} references undeclared parameter '{param_name}'.")
        tests_passed.append("parameter_bindings_check")

        # 4. Mock Execution Simulation
        # Simulate route A -> B
        state: Dict[str, Any] = {"A": "sample", "B": None, "C": None, "observed": None}
        for step in steps:
            action = step["action"]
            if action == "transfer":
                if state["A"] is None or state["B"] is not None:
                    raise ValueError("Mock simulation failed: transfer precondition violated.")
                state["B"] = state["A"]
                state["A"] = None
            elif action == "observe":
                state["observed"] = state["B"]
        if state["B"] != "sample" or state["A"] is not None or state["observed"] != "sample":
            raise ValueError("Mock simulation A->B outcome mismatch.")
        tests_passed.append("mock_simulation_A_to_B")

        # Simulate route C -> B
        state = {"A": None, "B": None, "C": "mandarin", "observed": None}
        for step in steps:
            action = step["action"]
            if action == "transfer":
                if state["C"] is None or state["B"] is not None:
                    raise ValueError("Mock simulation failed: transfer precondition violated.")
                state["B"] = state["C"]
                state["C"] = None
            elif action == "observe":
                state["observed"] = state["B"]
        if state["B"] != "mandarin" or state["C"] is not None or state["observed"] != "mandarin":
            raise ValueError("Mock simulation C->B outcome mismatch.")
        tests_passed.append("mock_simulation_C_to_B")

        # Boundary rejection check: invalid route B -> A
        if params.get("source", {}).get("enum") and "B" in params["source"]["enum"]:
            raise ValueError("Boundary check failed: source allows invalid station 'B'.")
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
            "tests_passed": tests_passed,
            "approval_scopes": {
                "mock": "approved",
                "physical": "unsupported",
            },
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        # Bind evidence to candidate in registry
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
        evidence = skill.get("evidence")
        if not evidence or skill.get("evidence_id") != evidence_id:
            raise ValueError(
                f"Refusing promotion: skill '{skill_id}' has not been tested with evidence '{evidence_id}'."
            )

        if evidence.get("verdict") != "passed":
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
