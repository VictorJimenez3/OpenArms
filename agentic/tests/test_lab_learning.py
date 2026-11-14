"""Tests for OpenArms educational lesson, inquiry guidance, and quiz support.

Verifies:
1. Seeded experiments structure, required keys, and variable controls.
2. Controlled buoyancy comparative trial against MOCK backend (Sample A 0.8 g/mL,
   Sample C 1.2 g/mL, external volume 20 mL, water density 1.0 g/mL).
3. Mandarin transfer robotic baseline with no invented science effect.
4. Analytical model observation with explicit MODEL-PREDICTED provenance (separate
   from mock motion and physical observations; not a real simulator).
5. Mandarin transfer returning None for model_observation.
6. make_quiz progression: multiple choice on trial 1, free response on later trials,
   and evidence verification prompt when outcomes are unknown.
7. evaluate_answer deterministic rubric: transparent assessment of density,
   displacement/buoyancy principles, and grounding in empirical observation list.
8. Unknown outcome rubric enforcing independent verification and forbidding controller inference.
9. No fabrication of real results; clear separation between model and observation.
10. Optional async tutoring function fallback.
"""
from __future__ import annotations

import asyncio
import pytest

from agentic.openarms_lab.learning import (
    EXPERIMENTS,
    get_experiment,
    model_observation,
    make_quiz,
    evaluate_answer,
    tutor_reflection_async,
)


# ==============================================================================
# 1. Experiments Registry & Curriculum Tests
# ==============================================================================

def test_experiments_structure():
    """Verify EXPERIMENTS registry has required keys and types for every entry."""
    assert isinstance(EXPERIMENTS, list)
    assert len(EXPERIMENTS) >= 2

    required_keys = {
        "id", "title", "question", "instructions",
        "independent_variable", "controlled_variables", "samples"
    }

    for exp in EXPERIMENTS:
        assert isinstance(exp, dict)
        missing = required_keys - set(exp.keys())
        assert not missing, f"Experiment {exp.get('id')} missing keys: {missing}"
        assert isinstance(exp["id"], str) and exp["id"]
        assert isinstance(exp["title"], str) and exp["title"]
        assert isinstance(exp["question"], str) and exp["question"]
        assert isinstance(exp["instructions"], str) and exp["instructions"]
        assert isinstance(exp["independent_variable"], str) and exp["independent_variable"]
        assert isinstance(exp["controlled_variables"], list) and len(exp["controlled_variables"]) >= 2
        assert isinstance(exp["samples"], dict) and len(exp["samples"]) >= 1


def test_buoyancy_trial_seeded_values():
    """Verify buoyancy trial is seeded with exact parameters required by research."""
    exp = get_experiment("buoyancy_trial")

    assert exp["id"] == "buoyancy_trial"
    assert exp["independent_variable"] == "sample density"
    assert "sample volume" in exp["controlled_variables"]
    assert "fluid density" in exp["controlled_variables"]
    assert "release method" in exp["controlled_variables"]

    # Check fluid definition
    assert exp["fluid"]["substance"] == "water"
    assert exp["fluid"]["density"] == 1.0

    # Check Sample A
    sample_a = exp["samples"]["A"]
    assert sample_a["station"] == "A"
    assert sample_a["density"] == 0.8
    assert sample_a["volume"] == 20.0
    assert sample_a["mass"] == 16.0
    assert sample_a["expected_model_state"] == "floats"

    # Check Sample C
    sample_c = exp["samples"]["C"]
    assert sample_c["station"] == "C"
    assert sample_c["density"] == 1.2
    assert sample_c["volume"] == 20.0
    assert sample_c["mass"] == 24.0
    assert sample_c["expected_model_state"] == "sinks"

    # Same external volume
    assert sample_a["volume"] == sample_c["volume"] == 20.0


def test_mandarin_transfer_seeded_values():
    """Verify mandarin transfer lesson acts as a physical baseline with no science effect."""
    exp = get_experiment("mandarin_transfer")

    assert exp["id"] == "mandarin_transfer"
    assert "baseline" in exp["instructions"].lower()
    assert "no physical or scientific model effect" in exp["instructions"].lower()
    assert "mandarin" in exp["samples"]
    assert exp["samples"]["mandarin"]["source"] == "A"
    assert exp["samples"]["mandarin"]["destination"] == "B"


def test_get_experiment():
    """Test get_experiment retrieval, alias support, and error handling."""
    # Direct IDs
    b = get_experiment("buoyancy_trial")
    assert b["id"] == "buoyancy_trial"

    m = get_experiment("mandarin_transfer")
    assert m["id"] == "mandarin_transfer"

    # Aliases
    b_alias = get_experiment("buoyancy")
    assert b_alias["id"] == "buoyancy_trial"

    m_alias = get_experiment("mandarin")
    assert m_alias["id"] == "mandarin_transfer"

    # Deep copy verification (mutation must not alter global)
    b["title"] = "MUTATED TITLE"
    assert get_experiment("buoyancy_trial")["title"] != "MUTATED TITLE"

    # Unknown experiment raises ValueError
    with pytest.raises(ValueError) as excinfo:
        get_experiment("nuclear_fusion_101")
    assert "not found" in str(excinfo.value)


# ==============================================================================
# 2. Analytical Model Observation & Provenance Tests
# ==============================================================================

def test_model_observation_buoyancy_sample_a():
    """Verify Sample A returns correct MODEL-PREDICTED floating prediction."""
    obs = model_observation("buoyancy_trial", {"sample": "A"})
    assert obs is not None
    assert obs["provenance"] == "MODEL-PREDICTED"
    assert obs["value"] == "floats"
    assert "0.80 g/mL" in obs["text"]
    assert "80.0%" in obs["text"]
    assert obs["units"] == "categorical"
    assert isinstance(obs["assumptions"], list)
    assert any("Archimedes" in a for a in obs["assumptions"])
    assert "OpenStax" in obs["source"] or "Archimedes" in obs["source"]


def test_model_observation_buoyancy_sample_c():
    """Verify Sample C returns correct MODEL-PREDICTED sinking prediction."""
    obs = model_observation("buoyancy_trial", {"sample_id": "C"})
    assert obs is not None
    assert obs["provenance"] == "MODEL-PREDICTED"
    assert obs["value"] == "sinks"
    assert "1.20 g/mL" in obs["text"]
    assert "exceeds" in obs["text"] or "downward" in obs["text"]


def test_model_observation_buoyancy_custom_parameters():
    """Verify model_observation accepts arbitrary density or mass and volume."""
    # Explicit density < 1.0 -> floats
    obs_light = model_observation("buoyancy_trial", {"density": 0.5})
    assert obs_light["value"] == "floats"

    # Explicit density > 1.0 -> sinks
    obs_dense = model_observation("buoyancy_trial", {"density": 1.5})
    assert obs_dense["value"] == "sinks"

    # Mass and volume provided: 30g / 20mL = 1.5 g/mL -> sinks
    obs_mass_vol = model_observation("buoyancy_trial", {"mass": 30.0, "volume": 20.0})
    assert obs_mass_vol["value"] == "sinks"

    # Fluid density changed to 1.3 g/mL: Sample C (1.2 g/mL) now floats!
    obs_saline = model_observation("buoyancy_trial", {"sample": "C", "fluid_density": 1.3})
    assert obs_saline["value"] == "floats"

    # Neutral buoyancy
    obs_neutral = model_observation("buoyancy_trial", {"density": 1.0, "fluid_density": 1.0})
    assert obs_neutral["value"] == "neutral"


def test_model_observation_mandarin_transfer_returns_none():
    """Verify mandarin transfer returns None: no science effect invented."""
    obs = model_observation("mandarin_transfer", {"destination": "B"})
    assert obs is None


def test_model_observation_provenance_strictly_labeled():
    """Ensure analytical output is explicitly labeled MODEL-PREDICTED, not real observation."""
    obs = model_observation("buoyancy_trial", {"sample": "A"})
    assert obs["provenance"] == "MODEL-PREDICTED"
    assert obs["provenance"] != "MOCK-OBSERVATION"
    assert obs["provenance"] != "PHYSICAL-OBSERVATION"


def test_model_observation_invalid_inputs():
    """Test error handling on invalid parameters."""
    with pytest.raises(ValueError):
        model_observation("unknown_exp_id")

    with pytest.raises(ValueError):
        model_observation("buoyancy_trial", {"density": -0.5})

    with pytest.raises(ValueError):
        model_observation("buoyancy_trial", {"mass": 10.0, "volume": 0.0})


# ==============================================================================
# 3. Quiz Generation (make_quiz) Tests
# ==============================================================================

def test_make_quiz_trial_1_multiple_choice():
    """Verify trial 1 produces a multiple-choice quiz for buoyancy."""
    quiz = make_quiz("buoyancy_trial", observations=[], trial_count=1)
    assert quiz["type"] == "multiple_choice"
    assert isinstance(quiz["prompt"], str)
    assert isinstance(quiz["options"], list)
    assert len(quiz["options"]) == 4
    # Option A should be the correct density explanation
    assert any("0.8 g/mL" in opt for opt in quiz["options"])


def test_make_quiz_trial_0_multiple_choice():
    """Verify trial 0 (pre-lab) also produces a multiple-choice quiz."""
    quiz = make_quiz("buoyancy_trial", trial_count=0)
    assert quiz["type"] == "multiple_choice"
    assert quiz["options"] is not None


def test_make_quiz_trial_2_free_response_comparative():
    """Verify trial 2 with normal observations produces a free-response comparison quiz."""
    observations = [
        {"sample": "A", "result": "floated", "provenance": "MOCK-OBSERVATION"},
        {"sample": "C", "result": "sank", "provenance": "MOCK-OBSERVATION"},
    ]
    quiz = make_quiz("buoyancy_trial", observations=observations, trial_count=2)
    assert quiz["type"] == "free_response"
    assert quiz["options"] is None
    assert "compare" in quiz["prompt"].lower()
    assert "archimedes" in quiz["prompt"].lower() or "density" in quiz["prompt"].lower()


def test_make_quiz_unknown_outcome_asks_for_evidence():
    """Verify when an observation has an unknown outcome, quiz asks what evidence is needed."""
    observations = [
        {"sample": "A", "result": "floated", "provenance": "MOCK-OBSERVATION"},
        {"sample": "C", "result": "unknown", "status": "failed", "provenance": "MOCK-OBSERVATION"},
    ]
    quiz = make_quiz("buoyancy_trial", observations=observations, trial_count=2)
    assert quiz["type"] == "free_response"
    assert quiz["options"] is None
    assert "unknown" in quiz["prompt"].lower() or "inconclusive" in quiz["prompt"].lower()
    assert "controller" in quiz["prompt"].lower()
    assert "evidence" in quiz["prompt"].lower()


def test_make_quiz_mandarin_transfer():
    """Verify quiz generation for mandarin transfer baseline."""
    # Trial 1: Multiple choice baseline
    quiz_t1 = make_quiz("mandarin_transfer", trial_count=1)
    assert quiz_t1["type"] == "multiple_choice"
    assert any("independent" in opt.lower() for opt in quiz_t1["options"])

    # Trial 2: Free response reflection
    quiz_t2 = make_quiz("mandarin_transfer", trial_count=2)
    assert quiz_t2["type"] == "free_response"
    assert "independent" in quiz_t2["prompt"].lower()


# ==============================================================================
# 4. Answer Evaluation (evaluate_answer) Tests
# ==============================================================================

def test_evaluate_mc_buoyancy_correct():
    """Test evaluation of correct multiple choice prediction for buoyancy."""
    quiz = make_quiz("buoyancy_trial", trial_count=1)

    # Various student input forms
    for ans in ["A", "a", "Option A", "A) Sample A will float because its density (0.8 g/mL) is less than water's density (1.0 g/mL)."]:
        res = evaluate_answer("buoyancy_trial", quiz, ans)
        assert res["correct"] is True
        assert res["provenance"] == "RULE-BASED-RUBRIC"
        assert "[✓ Correct]" in res["feedback"]
        assert "0.8" in res["feedback"]
        assert "Archimedes" in res["feedback"]
        assert res["follow_up"]


def test_evaluate_mc_buoyancy_incorrect():
    """Test evaluation of incorrect multiple choice prediction for buoyancy."""
    quiz = make_quiz("buoyancy_trial", trial_count=1)

    for ans in ["B", "C", "D", "Sample A will sink because solid objects always sink"]:
        res = evaluate_answer("buoyancy_trial", quiz, ans)
        assert res["correct"] is False
        assert "[✗ Incorrect]" in res["feedback"]
        assert "Review the density formula" in res["follow_up"] or "density" in res["follow_up"]


def test_evaluate_mc_mandarin_correct_and_incorrect():
    """Test evaluation of mandarin transfer multiple choice baseline."""
    quiz = make_quiz("mandarin_transfer", trial_count=1)

    res_correct = evaluate_answer("mandarin_transfer", quiz, "A")
    assert res_correct["correct"] is True
    assert "[✓ Correct]" in res_correct["feedback"]

    res_incorrect = evaluate_answer("mandarin_transfer", quiz, "B")
    assert res_incorrect["correct"] is False
    assert "[✗ Incorrect]" in res_incorrect["feedback"]
    assert "controller" in res_incorrect["feedback"].lower()


def test_evaluate_fr_buoyancy_complete_scientifically_credible():
    """Test free-response evaluation when student provides a complete scientific explanation."""
    observations = [
        {"sample": "A", "result": "floated", "provenance": "MOCK-OBSERVATION"},
        {"sample": "C", "result": "sank", "provenance": "MOCK-OBSERVATION"},
    ]
    quiz = make_quiz("buoyancy_trial", observations=observations, trial_count=2)

    student_answer = (
        "In our recorded trials, Sample A was observed to float and Sample C was observed to sink. "
        "Sample A floated because its density of 0.8 g/mL is less than water's density of 1.0 g/mL. "
        "According to Archimedes' principle, the upward buoyant force from displaced water equals the weight "
        "of the displaced liquid. For Sample A, buoyant force balances gravity when 80% submerged. "
        "In contrast, Sample C has a density of 1.2 g/mL, which exceeds water's density; the maximum buoyant force "
        "cannot support its gravitational weight, so Sample C sinks to the bottom."
    )

    res = evaluate_answer("buoyancy_trial", quiz, student_answer, observations)
    assert res["correct"] is True
    assert res["provenance"] == "RULE-BASED-RUBRIC"
    assert "[✓ Satisfactory Explanation]" in res["feedback"]
    assert "[✓ Met]" in res["feedback"]
    assert "Trial 1 (A): floated [provenance: MOCK-OBSERVATION]" in res["feedback"]
    assert "Trial 2 (C): sank [provenance: MOCK-OBSERVATION]" in res["feedback"]
    assert "Advanced Inquiry Extension" in res["follow_up"]


def test_evaluate_fr_buoyancy_missing_displacement():
    """Test free-response evaluation when student mentions density but omits displacement/buoyancy principles."""
    observations = [
        {"sample": "A", "result": "floated", "provenance": "MOCK-OBSERVATION"},
        {"sample": "C", "result": "sank", "provenance": "MOCK-OBSERVATION"},
    ]
    quiz = make_quiz("buoyancy_trial", observations=observations, trial_count=2)

    student_answer = (
        "Sample A floated and Sample C sank in our trial. "
        "Sample A has a density of 0.8 g/mL and Sample C has a density of 1.2 g/mL. "
        "One is less dense than water and the other is more dense."
    )

    res = evaluate_answer("buoyancy_trial", quiz, student_answer, observations)
    assert res["correct"] is False
    assert "[✗ Incomplete Explanation]" in res["feedback"]
    assert "Missing explanation of Archimedes' principle" in res["feedback"]
    assert "Archimedes' principle and buoyant force" in res["follow_up"]


def test_evaluate_fr_buoyancy_missing_density():
    """Test free-response evaluation when student mentions displacement but omits density."""
    observations = [
        {"sample": "A", "result": "floated", "provenance": "MOCK-OBSERVATION"},
        {"sample": "C", "result": "sank", "provenance": "MOCK-OBSERVATION"},
    ]
    quiz = make_quiz("buoyancy_trial", observations=observations, trial_count=2)

    student_answer = (
        "In our trial, Sample A was floating and Sample C was sinking. "
        "This is because of Archimedes' principle and the buoyant force pushing upward "
        "from the displaced water."
    )

    res = evaluate_answer("buoyancy_trial", quiz, student_answer, observations)
    assert res["correct"] is False
    assert "[✗ Incomplete Explanation]" in res["feedback"]
    assert "Missing explicit analysis of sample density" in res["feedback"]
    assert "sample density" in res["follow_up"]


def test_evaluate_fr_buoyancy_missing_observation_grounding():
    """Test free-response evaluation when student gives textbook theory without referencing trials."""
    observations = [
        {"sample": "A", "result": "floated", "provenance": "MOCK-OBSERVATION"},
        {"sample": "C", "result": "sank", "provenance": "MOCK-OBSERVATION"},
    ]
    quiz = make_quiz("buoyancy_trial", observations=observations, trial_count=2)

    student_answer = (
        "Density is mass divided by volume. Archimedes' displacement principle says that "
        "buoyant force equals the weight of displaced fluid. If density is 0.8, it floats; "
        "if 1.2, it sinks."
    )

    # Omits direct reference to Sample A or Sample C or the trials
    res = evaluate_answer("buoyancy_trial", quiz, student_answer, observations)
    assert res["correct"] is False
    assert "Must explicitly reference the observed outcomes" in res["feedback"]


def test_evaluate_fr_unknown_outcome_satisfactory():
    """Test evaluation of student answer for unknown trial outcome."""
    observations = [
        {"sample": "A", "result": "floated", "provenance": "MOCK-OBSERVATION"},
        {"sample": "C", "result": "unknown", "status": "failed", "provenance": "MOCK-OBSERVATION"},
    ]
    quiz = make_quiz("buoyancy_trial", observations=observations, trial_count=2)

    student_answer = (
        "We need an independent visual inspection using the camera or a teacher check "
        "to see whether the sample is floating or resting at the bottom. We must never infer "
        "or assume the outcome from the controller logs because motor steps can succeed even if "
        "the gripper dropped the object early or failed to release it."
    )

    res = evaluate_answer("buoyancy_trial", quiz, student_answer, observations)
    assert res["correct"] is True
    assert "[✓ Satisfactory]" in res["feedback"]
    assert "[✓ Met]" in res["feedback"]


def test_evaluate_fr_unknown_outcome_violating_controller_rule():
    """Test rejection when student attempts to infer physical state from controller logs."""
    observations = [
        {"sample": "C", "result": "unknown", "provenance": "MOCK-OBSERVATION"},
    ]
    quiz = make_quiz("buoyancy_trial", observations=observations, trial_count=2)

    # Violates core rule: assumes outcome from controller
    student_answer = "The controller reported success, so the sample definitely sank to the bottom."

    res = evaluate_answer("buoyancy_trial", quiz, student_answer, observations)
    assert res["correct"] is False
    assert "[✗ Incomplete]" in res["feedback"]
    assert "Must explicitly state that controller execution logs do not prove physical outcome" in res["feedback"]


# ==============================================================================
# 5. No Fabrication of Real Results & Grounding Tests
# ==============================================================================

def test_grounding_with_empty_observations():
    """Ensure evaluation does not fabricate observations when observations list is empty."""
    quiz = make_quiz("buoyancy_trial", observations=[], trial_count=1)
    res = evaluate_answer("buoyancy_trial", quiz, "A", observations=[])

    assert "No empirical observations recorded yet in this session." in res["feedback"]
    # Model predictions should not be claimed as empirical observations
    assert "MODEL-PREDICTED" not in res["feedback"] or "theoretical" in res["feedback"] or "prediction" in res["feedback"]


def test_multiple_trials_accurate_synthesis():
    """Verify that multi-trial observations are summarized accurately and completely."""
    observations = [
        {"sample": "A", "result": "floated", "provenance": "MOCK-OBSERVATION"},
        {"sample": "C", "result": "sank", "provenance": "MOCK-OBSERVATION"},
        {"sample": "custom_salt_water", "result": "floated", "provenance": "PHYSICAL-OBSERVATION"},
    ]

    quiz = make_quiz("buoyancy_trial", observations=observations, trial_count=3)
    student_answer = (
        "Across our three trials, Sample A and the custom sample floated, while Sample C sank. "
        "Sample A's density (0.8 g/mL) was lower than water (1.0 g/mL), so Archimedes' buoyant force "
        "from displaced fluid balanced gravity at partial submersion. Sample C was denser (1.2 g/mL), "
        "so the buoyant force was insufficient and it sank."
    )

    res = evaluate_answer("buoyancy_trial", quiz, student_answer, observations)
    assert res["correct"] is True
    assert "Trial 1 (A): floated [provenance: MOCK-OBSERVATION]" in res["feedback"]
    assert "Trial 2 (C): sank [provenance: MOCK-OBSERVATION]" in res["feedback"]
    assert "Trial 3 (custom_salt_water): floated [provenance: PHYSICAL-OBSERVATION]" in res["feedback"]


# ==============================================================================
# 6. Optional Async Tutoring Function Test
# ==============================================================================

def test_tutor_reflection_async():
    """Verify tutor_reflection_async executes asynchronously and falls back to rubric cleanly."""
    quiz = make_quiz("buoyancy_trial", trial_count=1)

    async def _run():
        return await tutor_reflection_async("buoyancy_trial", quiz, "A", observations=[])

    res = asyncio.run(_run())
    assert isinstance(res, dict)
    assert res["correct"] is True
    assert res["provenance"] == "RULE-BASED-RUBRIC"
    assert "[✓ Correct]" in res["feedback"]
