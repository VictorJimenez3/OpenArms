"""Comprehensive tests for OpenArms persistent versioned skill registry (agentic/openarms_lab/skills.py).

Covers:
- Registry initialization and atomic persistence
- Seed active skill metadata ('known_station_transfer.v1') and team-reported baseline evidence
- Paraphrased known station transfers (mandarin/orange A/C -> B)
- Lesson buoyancy requests ('test sample at A in B', 'test sample at C in B')
- Ambiguity clarification for missing sources/destinations
- Safety rejection for unsupported objects, routes, and parameters
- Cold composition fallback (expert_mode='local_composer', model_calls=0, no pretend model)
- Optional SDK GenAI provider mocking with strict JSON primitive validation
- Candidate testing returning evidence_id bound to content hash
- Promotion safety: refuses untested or modified candidates, grants mock approval only (physical never auto-promoted)
- Warm phrase resolution choosing active composed skill for transfer and observe
- Parent runtime step schema compatibility
"""

import asyncio
import copy
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from agentic.openarms_lab.skills import (
    ALLOWED_PRIMITIVES,
    DEFAULT_EXPERT_MODEL,
    SEED_KNOWN_STATION_TRANSFER,
    SkillRegistry,
    compute_skill_hash,
)


@pytest.fixture
def registry_file(tmp_path: Path) -> Path:
    """Fixture providing a temporary skills catalog JSON file path."""
    return tmp_path / "skills.json"


@pytest.fixture
def registry(registry_file: Path) -> SkillRegistry:
    """Fixture providing an initialized SkillRegistry instance."""
    return SkillRegistry(registry_file)


# ==============================================================================
# 1. Initialization, Persistence, and Seed Skill Integrity
# ==============================================================================


def test_registry_initialization_seeds_known_transfer(registry: SkillRegistry, registry_file: Path) -> None:
    """Verify registry seeds known_station_transfer.v1 with exact required metadata."""
    assert registry_file.exists()

    skills = registry.list()
    assert len(skills) >= 1

    skill_ids = [s["skill_id"] for s in skills]
    assert "known_station_transfer.v1" in skill_ids

    seed = registry.get("known_station_transfer.v1")
    assert seed["status"] == "active"
    assert seed["controller_ref"] == "transfer"
    assert "preconditions" in seed
    assert "expected_outcomes" in seed

    # Verification of approval scopes and team-reported baseline
    assert seed["approval_scopes"]["mock"] == "approved"
    assert seed["approval_scopes"]["physical"] == "team_reported_baseline_only"
    assert "TEAM-REPORTED only" in seed["evidence"]["report"]
    assert "not independently verified" in seed["evidence"]["report"]

    # Parameter definitions check
    params = seed["parameters"]
    assert set(params["source"]["enum"]) == {"A", "C"}
    assert set(params["destination"]["enum"]) == {"B"}
    assert "mandarin" in params["object"]["enum"]
    assert "sample" in params["object"]["enum"]


def test_registry_reloads_persisted_catalog(tmp_path: Path) -> None:
    """Verify registry reloads state from disk across instances and preserves content."""
    catalog_path = tmp_path / "persisted_skills.json"
    reg1 = SkillRegistry(catalog_path)
    assert len(reg1.list()) == 1

    # Add a custom mock candidate directly for persistence testing
    reg1._skills["custom.v1"] = {
        "skill_id": "custom.v1",
        "name": "Custom",
        "status": "candidate",
        "steps": [],
        "approval_scopes": {"mock": "untested", "physical": "unsupported"},
    }
    reg1._save()

    # Reopen in new instance
    reg2 = SkillRegistry(catalog_path)
    assert "custom.v1" in [s["skill_id"] for s in reg2.list()]
    assert reg2.get("custom.v1")["status"] == "candidate"


def test_get_nonexistent_skill_raises_key_error(registry: SkillRegistry) -> None:
    """Verify get() on non-existent skill raises KeyError."""
    with pytest.raises(KeyError, match="not found in registry"):
        registry.get("nonexistent_skill.v99")


# ==============================================================================
# 2. Synchronous Fast-Path Resolution: Paraphrases & Parameters
# ==============================================================================


@pytest.mark.parametrize(
    "phrase,expected_obj,expected_src,expected_dst",
    [
        ("transfer mandarin from A to B", "mandarin", "A", "B"),
        ("move the mandarin from station A to station B", "mandarin", "A", "B"),
        ("transfer orange from A to B", "mandarin", "A", "B"),
        ("move orange from C to B", "mandarin", "C", "B"),
        ("please transfer the orange from station C to station B", "mandarin", "C", "B"),
        ("pick up mandarin at A and place it in B", "mandarin", "A", "B"),
        ("pickup orange from C to destination B", "mandarin", "C", "B"),
        ("move mandarin A -> B", "mandarin", "A", "B"),
        ("mandarin C to B", "mandarin", "C", "B"),
    ],
)
def test_resolve_mandarin_orange_paraphrases(
    registry: SkillRegistry, phrase: str, expected_obj: str, expected_src: str, expected_dst: str
) -> None:
    """Verify diverse paraphrases for mandarin/orange transfers resolve correctly with parameters."""
    res = registry.resolve(phrase)
    assert res["status"] == "resolved"
    assert res["skill_id"] == "known_station_transfer.v1"
    assert res["parameters"] == {
        "object": expected_obj,
        "source": expected_src,
        "destination": expected_dst,
    }
    assert res["metrics"]["model_calls"] == 0
    assert res["metrics"]["tokens"] == 0
    assert isinstance(res["metrics"]["planning_ms"], float)
    assert res["metrics"]["planning_ms"] >= 0.0


@pytest.mark.parametrize(
    "phrase,expected_src,expected_dst",
    [
        ("test sample at A in B", "A", "B"),
        ("test sample at C in B", "C", "B"),
        ("test the sample at station A in station B", "A", "B"),
        ("can we test sample at C in B?", "C", "B"),
        ("transfer sample from A to B", "A", "B"),
        ("move sample from station C to B", "C", "B"),
    ],
)
def test_resolve_buoyancy_lesson_requests(
    registry: SkillRegistry, phrase: str, expected_src: str, expected_dst: str
) -> None:
    """Verify buoyancy science lesson requests resolve with sample object and correct source/destination."""
    res = registry.resolve(phrase)
    assert res["status"] == "resolved"
    assert res["skill_id"] == "known_station_transfer.v1"
    assert res["parameters"] == {
        "object": "sample",
        "source": expected_src,
        "destination": expected_dst,
    }
    assert res["metrics"]["model_calls"] == 0


# ==============================================================================
# 3. Ambiguity & Clarification Handling
# ==============================================================================


@pytest.mark.parametrize(
    "ambiguous_phrase,expected_hint",
    [
        ("transfer the mandarin", "source"),
        ("move orange", "source"),
        ("transfer mandarin to B", "source"),
        ("move orange into station B", "source"),
        ("transfer mandarin from A", "destination"),
        ("move orange from station C", "destination"),
        ("test sample at A", "destination"),
        ("move sample to B", "source"),
    ],
)
def test_resolve_ambiguous_missing_stations_asks_clarification(
    registry: SkillRegistry, ambiguous_phrase: str, expected_hint: str
) -> None:
    """Verify missing source or destination stations trigger clarification without guessing."""
    res = registry.resolve(ambiguous_phrase)
    assert res["status"] == "clarify"
    assert "parameters" not in res
    assert expected_hint in res["message"].lower()
    assert res["metrics"]["model_calls"] == 0


def test_resolve_missing_object_asks_clarification(registry: SkillRegistry) -> None:
    """Verify missing object triggers clarification rather than unsafe assumptions."""
    res = registry.resolve("transfer from station A to station B")
    assert res["status"] == "clarify"
    assert "object" in res["message"].lower()


# ==============================================================================
# 4. Safety Rejection for Unsupported Parameters & Objects
# ==============================================================================


@pytest.mark.parametrize(
    "unsupported_phrase,expected_reason",
    [
        ("move apple from A to B", "apple"),
        ("transfer banana from C to B", "banana"),
        ("move beaker from A to B", "beaker"),
        ("transfer vial from C to B", "vial"),
        ("transfer mandarin from A to C", "destination"),
        ("move orange from A to D", "destination"),
        ("transfer mandarin from B to A", "source"),
        ("move sample from D to B", "source"),
        ("teleport mandarin to the moon", "does not match"),
        ("please play a song on the synthesizer", "does not match"),
    ],
)
def test_resolve_unsupported_requests_rejected(
    registry: SkillRegistry, unsupported_phrase: str, expected_reason: str
) -> None:
    """Verify arbitrary objects, invalid routes, and unsupported parameters are rejected."""
    res = registry.resolve(unsupported_phrase)
    assert res["status"] == "unsupported"
    assert expected_reason.lower() in res["message"].lower()
    assert res["metrics"]["model_calls"] == 0


# ==============================================================================
# 5. Cold Expert Composition & Fallback
# ==============================================================================


def test_compose_deterministic_fallback_without_api_key(registry: SkillRegistry) -> None:
    """Verify compose without API key uses deterministic local_composer with model_calls=0."""
    async def _run() -> None:
        with patch.dict(os.environ, {}, clear=True):
            candidate = await registry.compose("transfer mandarin from A to B and observe placement")

            assert candidate["skill_id"] == "transfer_and_observe.v1"
            assert candidate["status"] == "candidate"
            assert candidate["expert_mode"] == "local_composer"
            assert candidate["model_calls"] == 0
            assert candidate["tokens"] == 0

            # Step validation for parent runtime
            steps = candidate["steps"]
            assert len(steps) == 2
            assert steps[0] == {
                "action": "transfer",
                "args": {"source": "$source", "destination": "$destination", "object": "$object"},
            }
            assert steps[1] == {
                "action": "observe",
                "args": {"station": "$destination"},
            }

            # Candidate is persisted in catalog
            stored = registry.get("transfer_and_observe.v1")
            assert stored["status"] == "candidate"
            assert stored["approval_scopes"]["mock"] == "pending_test"
            assert stored["approval_scopes"]["physical"] == "unsupported"

    asyncio.run(_run())


def test_compose_rejects_forbidden_low_level_code(registry: SkillRegistry) -> None:
    """Verify compose rejects instructions containing raw servo/motor or dangerous commands."""
    async def _run() -> None:
        with pytest.raises(ValueError, match="forbidden token"):
            await registry.compose("set servo angle 180 on motor id 3 with pwm 255")

    asyncio.run(_run())


def test_compose_with_mocked_genai_sdk(registry: SkillRegistry) -> None:
    """Verify compose with configured API key calls GenAI SDK and validates allowed primitives."""
    async def _run() -> None:
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "steps": [
                {"action": "transfer", "args": {"source": "$source", "destination": "$destination", "object": "$object"}},
                {"action": "observe", "args": {"station": "$destination"}},
            ]
        })

        mock_client = MagicMock()
        mock_response.usage_metadata.total_token_count=42
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
        mock_client.aio.aclose = AsyncMock()

        mock_genai_module = MagicMock()
        mock_genai_module.Client.return_value = mock_client
        mock_google = MagicMock()
        mock_google.genai = mock_genai_module

        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key", "OPENARMS_EXPERT_MODEL": "gemini-3.8-flash"}):
            with patch.dict("sys.modules", {"google": mock_google, "google.genai": mock_genai_module}):
                candidate = await registry.compose("transfer orange from C to B and inspect")
                assert candidate["skill_id"] == "transfer_and_observe.v1"
                assert candidate["model_calls"] == 1
                assert candidate["expert_mode"] == "gemini-3.8-flash"
                assert len(candidate["steps"]) == 2

    asyncio.run(_run())


def test_compose_with_mocked_genai_sdk_rejects_unapproved_primitives(registry: SkillRegistry) -> None:
    """Verify compose rejects model responses containing unapproved primitive actions."""
    async def _run() -> None:
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "steps": [
                {"action": "transfer", "args": {"source": "$source", "destination": "$destination", "object": "$object"}},
                {"action": "unapproved_drill_action", "args": {"target": "fixture"}},
            ]
        })
        mock_client = MagicMock()
        mock_response.usage_metadata.total_token_count=42
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
        mock_client.aio.aclose = AsyncMock()
        mock_genai_module = MagicMock()
        mock_genai_module.Client.return_value = mock_client
        mock_google = MagicMock()
        mock_google.genai = mock_genai_module

        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key"}):
            with patch.dict("sys.modules", {"google": mock_google, "google.genai": mock_genai_module}):
                with pytest.raises(ValueError, match="unsupported steps"):
                    await registry.compose("transfer and observe")

    asyncio.run(_run())


# ==============================================================================
# 6. Candidate Testing and Evidence Generation
# ==============================================================================


def test_test_candidate_generates_bound_evidence(registry: SkillRegistry) -> None:
    """Verify test_candidate executes structural/simulation tests and returns evidence_id with hash."""
    async def _run() -> None:
        await registry.compose("transfer and observe")

        evidence = registry.test_candidate("transfer_and_observe.v1")
        assert "evidence_id" in evidence
        assert evidence["evidence_id"].startswith("ev-")
        assert evidence["verdict"] == "passed"
        assert evidence["approval_scopes"]["mock"] == "approved"
        assert evidence["approval_scopes"]["physical"] == "unsupported"
        assert len(evidence["tests_passed"]) >= 4

        # Registry record contains evidence binding
        updated_skill = registry.get("transfer_and_observe.v1")
        assert updated_skill["evidence_id"] == evidence["evidence_id"]
        assert updated_skill["evidence"]["skill_hash"] == evidence["skill_hash"]

    asyncio.run(_run())


def test_test_candidate_nonexistent_skill_raises_key_error(registry: SkillRegistry) -> None:
    """Verify testing a nonexistent skill raises KeyError."""
    with pytest.raises(KeyError):
        registry.test_candidate("missing_skill.v1")


# ==============================================================================
# 7. Promotion Safety & Hash Binding
# ==============================================================================


def test_promote_refuses_untested_candidate(registry: SkillRegistry) -> None:
    """Verify promote refuses candidates that have not been tested."""
    async def _run() -> None:
        await registry.compose("transfer and observe")

        with pytest.raises(ValueError, match="has not been tested"):
            registry.promote("transfer_and_observe.v1", "fake_evidence_id")

    asyncio.run(_run())


def test_promote_refuses_modified_candidate_after_testing(registry: SkillRegistry) -> None:
    """Verify promote refuses candidate if its content hash was modified after testing."""
    async def _run() -> None:
        await registry.compose("transfer and observe")
        evidence = registry.test_candidate("transfer_and_observe.v1")

        # Simulate tampering / modifying candidate steps directly in catalog
        skill = registry._skills["transfer_and_observe.v1"]
        skill["steps"].append({"action": "observe", "args": {"tampered": True}})
        registry._save()

        with pytest.raises(ValueError, match="does not match evidence tested hash"):
            registry.promote("transfer_and_observe.v1", evidence["evidence_id"])

    asyncio.run(_run())


def test_promote_succeeds_with_mock_approval_only(registry: SkillRegistry) -> None:
    """Verify successful promotion activates mock approval only, never auto-promoting physical."""
    async def _run() -> None:
        await registry.compose("transfer and observe")
        evidence = registry.test_candidate("transfer_and_observe.v1")

        promoted = registry.promote("transfer_and_observe.v1", evidence["evidence_id"])

        assert promoted["status"] == "active"
        assert promoted["approval_scopes"]["mock"] == "approved"
        # Physical MUST remain unsupported or non-promoted
        assert promoted["approval_scopes"]["physical"] == "unsupported"
        assert "promoted_at" in promoted

        # Catalog on disk reflects promotion
        reloaded = SkillRegistry(registry.catalog_path).get("transfer_and_observe.v1")
        assert reloaded["status"] == "active"
        assert reloaded["approval_scopes"]["mock"] == "approved"
        assert reloaded["approval_scopes"]["physical"] == "unsupported"

    asyncio.run(_run())


def test_promote_already_active_skill_raises_error(registry: SkillRegistry) -> None:
    """Verify promoting an already active skill raises ValueError."""
    async def _run() -> None:
        await registry.compose("transfer and observe")
        evidence = registry.test_candidate("transfer_and_observe.v1")
        registry.promote("transfer_and_observe.v1", evidence["evidence_id"])

        with pytest.raises(ValueError, match="already active"):
            registry.promote("transfer_and_observe.v1", evidence["evidence_id"])

    asyncio.run(_run())


# ==============================================================================
# 8. Warm Path Resolution of Composed Skill (transfer_and_observe.v1)
# ==============================================================================


def test_resolve_composed_skill_before_and_after_promotion(registry: SkillRegistry) -> None:
    """Verify resolve rejects transfer+observe before promotion, and resolves to it once active."""
    async def _run() -> None:
        phrase = "transfer mandarin from A to B and observe"

        # Before composition: unsupported
        res_before = registry.resolve(phrase)
        assert res_before["status"] == "unsupported"

        # Compose (creates candidate)
        await registry.compose("transfer and observe")

        # While candidate: still unsupported for active execution
        res_candidate = registry.resolve(phrase)
        assert res_candidate["status"] == "unsupported"
        assert "candidate" in res_candidate["message"]

        # Test and Promote
        evidence = registry.test_candidate("transfer_and_observe.v1")
        registry.promote("transfer_and_observe.v1", evidence["evidence_id"])

        # Now active: resolves to transfer_and_observe.v1
        res_active = registry.resolve(phrase)
        assert res_active["status"] == "resolved"
        assert res_active["skill_id"] == "transfer_and_observe.v1"
        assert res_active["parameters"] == {
            "object": "mandarin",
            "source": "A",
            "destination": "B",
        }
        assert res_active["metrics"]["model_calls"] == 0

    asyncio.run(_run())


@pytest.mark.parametrize(
    "phrase,expected_obj,expected_src,expected_dst",
    [
        ("transfer mandarin from A to B and observe", "mandarin", "A", "B"),
        ("move orange from C to B and inspect", "mandarin", "C", "B"),
        ("move sample from A to B and check placement", "sample", "A", "B"),
        ("test sample at C in B and verify placement", "sample", "C", "B"),
        ("transfer orange at A into B and watch outcome", "mandarin", "A", "B"),
    ],
)
def test_resolve_active_composed_skill_paraphrases(
    registry: SkillRegistry, phrase: str, expected_obj: str, expected_src: str, expected_dst: str
) -> None:
    """Verify diverse paraphrases for transfer + observe resolve cleanly to transfer_and_observe.v1."""
    async def _run() -> None:
        await registry.compose("transfer and observe")
        evidence = registry.test_candidate("transfer_and_observe.v1")
        registry.promote("transfer_and_observe.v1", evidence["evidence_id"])

        res = registry.resolve(phrase)
        assert res["status"] == "resolved"
        assert res["skill_id"] == "transfer_and_observe.v1"
        assert res["parameters"] == {
            "object": expected_obj,
            "source": expected_src,
            "destination": expected_dst,
        }
        assert res["metrics"]["model_calls"] == 0

        # Ensure plain transfer without observe still routes to known_station_transfer.v1
        plain_res = registry.resolve(f"transfer {expected_obj} from {expected_src} to {expected_dst}")
        assert plain_res["status"] == "resolved"
        assert plain_res["skill_id"] == "known_station_transfer.v1"

    asyncio.run(_run())


@pytest.mark.parametrize("phrase", [
    "move sample from A to B at 50 mm/s",
    "move sample from A to B slowly",
    "move sample from A to B without observing",
    "move sample from A to B and rotate it",
    "move sample from A to B and move mandarin from C to B",
    "move sample and beaker from A to B",
    "move sample from A to B with water",
    "move two samples from A to B",
    "move samples from A to B",
    "move the red sample from A to B",
    "move sample from A to B twice",
    "move sample from A or C to B",
    "move sample from A to B or C",
    "do not move sample from A to B",
    "don't move sample from A to B",
    "never move sample from A to B",
    "what if we move sample from A to B?",
    "did you move sample from A to B?",
    "should we move sample from A to B?",
    "is it safe to move sample from A to B?",
    "explain how to move sample from A to B",
    "I saw someone move sample from A to B",
    "move sample from Alpha to Bravo",
    "move sample from AB to B",
    "move sample from A to BC",
    "move sample from A to B; reset",
    "move sample from A to B and don't inspect",
    "move sample from A to B and inspect station A",
    "move orange sample from A to B",
    "move from A to B",  # no object inference from context
])
def test_full_request_never_executes_supported_subset(registry, phrase):
    result = registry.resolve(phrase)
    assert result["status"] in {"clarify", "unsupported"}
    assert "skill_id" not in result
    assert "parameters" not in result
    assert result["metrics"]["model_calls"] == 0


@pytest.mark.parametrize("phrase,source,obj", [
    ("Could you move the sample from the source station C into the destination station B?", "C", "sample"),
    ("would you please carry an orange from A to B?", "A", "mandarin"),
    ("please deliver the mandarin at station C into station B.", "C", "mandarin"),
    ("take sample at A and put it on B", "A", "sample"),
    ("pick up the orange from station C and set it at station B", "C", "mandarin"),
    ("I'd like you to transport a sample from C to B, please", "C", "sample"),
    ("move sample C -> B", "C", "sample"),
])
def test_varied_complete_polite_requests(registry, phrase, source, obj):
    result = registry.resolve(phrase)
    assert result["status"] == "resolved", result
    assert result["parameters"] == {"source": source, "destination": "B", "object": obj}


@pytest.mark.parametrize("instruction", [
    "sing a song", "transfer and drill", "observe then transfer", "transfer",
    "do not transfer and observe", "transfer beaker from A to B and observe",
    "transfer sample from A to B and observe twice", "what if we transfer and observe?",
    "transfer sample from A to B and observe station A",
    "transfer sample from A to B and observe and rotate",
])
def test_compose_rejects_unrepresented_intent_before_provider(registry, instruction):
    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
        with patch("builtins.__import__", side_effect=AssertionError("provider import not expected")):
            with pytest.raises(ValueError, match="Unsupported composition intent"):
                asyncio.run(registry.compose(instruction))
    assert len(registry.list()) == 1


def test_duplicate_composition_preserves_tested_artifact(registry):
    with patch.dict(os.environ, {}, clear=True):
        candidate = asyncio.run(registry.compose("transfer and observe"))
        evidence = registry.test_candidate(candidate["skill_id"])
        before = registry.catalog_path.read_bytes()
        with pytest.raises(ValueError, match="already exists"):
            asyncio.run(registry.compose("move sample C to B and inspect"))
        assert registry.catalog_path.read_bytes() == before
        assert registry.get(candidate["skill_id"])["evidence_id"] == evidence["evidence_id"]


def test_candidate_evidence_runs_actual_bindings_via_validator(registry):
    from agentic.openarms_lab.skills import _execute_bound_skill, _mock_state
    with patch.dict(os.environ, {}, clear=True):
        candidate = asyncio.run(registry.compose("transfer and observe"))
    # Directly run a misbound artifact: C is empty. A hardcoded A->B simulator
    # would incorrectly report success even though the artifact requests C.
    candidate["steps"][0]["args"]["source"] = "$destination"
    with pytest.raises(ValueError, match="absent at source"):
        _execute_bound_skill(candidate, {"source": "A", "destination": "B", "object": "sample"},
                             _mock_state("A", "sample"))
    candidate = registry.get(candidate["skill_id"])
    # Reading the wrong station must produce the wrong observation, not hardcoded B.
    candidate["steps"][1]["args"]["station"] = "$source"
    end, observed = _execute_bound_skill(candidate,
        {"source": "C", "destination": "B", "object": "mandarin"}, _mock_state("C", "mandarin"))
    assert end["point_holds"]["B"] == "mandarin"
    assert observed == {"C": None}


def test_candidate_tests_depend_on_independent_validator(registry):
    with patch.dict(os.environ, {}, clear=True):
        candidate = asyncio.run(registry.compose("transfer and observe"))
    with patch("agentic.openarms_agent.validator.validate", return_value={"ok": False, "reason": "injected validator rejection"}) as checked:
        with pytest.raises(ValueError, match="injected validator rejection"):
            registry.test_candidate(candidate["skill_id"])
    checked.assert_called_once()
    assert registry.get(candidate["skill_id"])["evidence_id"] is None


@pytest.mark.parametrize("parameter,values", [
    ("source", ["A", "C", "D"]), ("source", ["A"]),
    ("destination", ["B", "D"]), ("object", ["mandarin", "sample", "beaker"]),
])
def test_candidate_tests_reject_overbroad_or_changed_domains(registry, parameter, values):
    with patch.dict(os.environ, {}, clear=True):
        candidate = asyncio.run(registry.compose("transfer and observe"))
    registry._skills[candidate["skill_id"]]["parameters"][parameter]["enum"] = values
    with pytest.raises(ValueError, match="unsupported domain"):
        registry.test_candidate(candidate["skill_id"])


def test_forged_candidate_embedded_evidence_cannot_promote(registry):
    with patch.dict(os.environ, {}, clear=True):
        candidate = asyncio.run(registry.compose("transfer and observe"))
    skill = registry._skills[candidate["skill_id"]]
    skill["evidence_id"] = "fake-embedded-evidence"
    skill["evidence"] = {"evidence_id": skill["evidence_id"], "skill_id": candidate["skill_id"],
                         "skill_hash": compute_skill_hash(skill), "verdict": "passed"}
    with pytest.raises(ValueError, match="has not been tested"):
        registry.promote(candidate["skill_id"], skill["evidence_id"])


def test_mock_evidence_persists_and_active_definition_stays_bound(registry):
    with patch.dict(os.environ, {}, clear=True):
        candidate = asyncio.run(registry.compose("transfer and observe"))
    evidence = registry.test_candidate(candidate["skill_id"])
    assert evidence["provenance"] == "MOCK"
    assert "symbolic" in evidence["test_method"]
    assert evidence["approval_scopes"]["physical"] == "unsupported"
    reloaded = SkillRegistry(registry.catalog_path)
    promoted = reloaded.promote(candidate["skill_id"], evidence["evidence_id"])
    assert compute_skill_hash(promoted) == evidence["skill_hash"]
    assert reloaded.resolve("move sample A to B then observe")["status"] == "resolved"
    reloaded._skills[candidate["skill_id"]]["steps"][1]["args"]["station"] = "$source"
    assert reloaded.resolve("move sample A to B then observe")["status"] == "unsupported"


def _fake_sdk(payload, usage=73):
    """Real async boundary with a minimal SDK-shaped module, no network or keys."""
    import types
    generate = AsyncMock(return_value=types.SimpleNamespace(
        text=json.dumps(payload), usage_metadata=types.SimpleNamespace(total_token_count=usage)))
    close = AsyncMock()
    client = types.SimpleNamespace(aio=types.SimpleNamespace(
        models=types.SimpleNamespace(generate_content=generate), aclose=close))
    module = types.ModuleType("google.genai")
    module.Client = MagicMock(return_value=client)
    module.types = types.SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs)
    google = types.ModuleType("google")
    google.genai = module
    return {"google": google, "google.genai": module}, generate, close


def _approved_composite_steps():
    return [
        {"action": "transfer", "args": {"source": "$source", "destination": "$destination", "object": "$object"}},
        {"action": "observe", "args": {"station": "$destination"}},
    ]


def test_async_expert_uses_instruction_reports_actual_usage_and_closes(registry):
    modules, generate, close = _fake_sdk({"steps": _approved_composite_steps()}, usage=137)
    phrase = "could you transfer sample from C to B and verify the result?"
    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key", "OPENARMS_EXPERT_MODEL": "test-model"}):
        with patch.dict("sys.modules", modules):
            candidate = asyncio.run(registry.compose(phrase))
    generate.assert_awaited_once()
    close.assert_awaited_once()
    assert phrase in generate.await_args.kwargs["contents"]
    assert generate.await_args.kwargs["model"] == "test-model"
    assert candidate["model_calls"] == 1
    assert candidate["tokens"] == 137
    assert candidate["planning_ms"] >= 0
    assert candidate["expert_mode"] == "test-model"


@pytest.mark.parametrize("payload", [
    {"steps": []}, {"steps": None}, [],
    {"steps": _approved_composite_steps(), "speed": "fast"},
    {"steps": [{"action": "observe", "args": {"station": "$destination"}}]},
    {"steps": list(reversed(_approved_composite_steps()))},
    {"steps": [
        {"action": "transfer", "args": {"source": "$destination", "destination": "$source", "object": "$object"}},
        {"action": "observe", "args": {"station": "$destination"}},
    ]},
    {"steps": [
        {"action": "transfer", "args": {"source": "$source", "destination": "$destination", "object": "$object", "speed": 5}},
        {"action": "observe", "args": {"station": "$destination"}},
    ]},
])
def test_invalid_expert_output_never_falls_back_or_persists(registry, payload):
    modules, generate, close = _fake_sdk(payload)
    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
        with patch.dict("sys.modules", modules):
            with pytest.raises(ValueError):
                asyncio.run(registry.compose("transfer sample from A to B and observe"))
    generate.assert_awaited_once()
    close.assert_awaited_once()
    assert len(registry.list()) == 1


def test_unknown_usage_is_not_replaced_with_estimate(registry):
    modules, _, _ = _fake_sdk({"steps": _approved_composite_steps()}, usage=None)
    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
        with patch.dict("sys.modules", modules):
            candidate = asyncio.run(registry.compose("transfer and observe"))
    assert candidate["model_calls"] == 1
    assert candidate["tokens"] is None


def test_active_baseline_can_receive_supplemental_mock_evidence_without_physical_promotion(registry):
    baseline = registry.get("known_station_transfer.v1")
    evidence = registry.test_candidate(baseline["skill_id"])
    assert evidence["verdict"] == "passed"
    assert evidence["provenance"] == "MOCK"
    assert evidence["approval_scopes"]["physical"] == "unsupported"
    tested = registry.get(baseline["skill_id"])
    assert tested["status"] == "active"
    assert tested["approval_scopes"] == baseline["approval_scopes"]
    assert tested["evidence"] == baseline["evidence"]
    assert registry.resolve("move mandarin A to B")["status"] == "resolved"


def test_compose_observe_destination_demo_phrase(registry):
    with patch.dict(os.environ, {}, clear=True):
        candidate = asyncio.run(registry.compose("transfer sample from A to B and observe the destination"))
    evidence = registry.test_candidate(candidate["skill_id"])
    registry.promote(candidate["skill_id"], evidence["evidence_id"])
    assert registry.resolve("transfer sample from A to B and observe the destination")["status"] == "resolved"
