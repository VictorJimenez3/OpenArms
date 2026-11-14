"""Historical dilution content and current mock dose safety boundaries.

Verifies:
1. EXPERIMENT definition, metadata, controlled variables, and lesson concepts (H2O 18.015 g/mol).
2. Receiver vessel B mock addition caveats and station C wet lab mapping distinction.
3. Analytical model_observation with MODEL-PREDICTED provenance and 0.50 vs 0.25 values.
4. Sensor honesty: no faked RGB or optical sensor readings in text/assumptions.
5. make_quiz progression: multiple-choice dye conservation on trial 1, free response on trial 2+.
6. Inconclusive/unknown observation handling enforcing physical verification without faking.
7. evaluate_answer deterministic rubric for MC and free response.
8. Compatibility with direct calls and dispatcher signatures.
9. Verification of educational citations in module documentation.
"""
from __future__ import annotations

import pytest
from agentic.openarms_lab import dilution


def test_experiment_structure_and_controls():
    """Verify EXPERIMENT schema, independent and controlled variables, and samples."""
    exp = dilution.EXPERIMENT
    assert exp["id"] == "color_dilution"
    assert "Color Dilution" in exp["title"]
    assert exp["independent_variable"] == "added water volume"
    assert len(exp["controlled_variables"]) >= 4

    # Receiver vessel B mock addition checks
    assert exp["receiver"]["station"] == "B"
    assert exp["receiver"]["initial_volume_ml"] == 5.0
    assert exp["receiver"]["initial_relative_concentration"] == 1.0
    assert "MOCK" in exp["receiver"]["note"]
    assert "receiver C" in exp["receiver"]["note"]

    # Samples A and C
    samples = exp["samples"]
    assert "A" in samples and "C" in samples

    assert samples["A"]["volume_ml"] == 5.0
    assert samples["A"]["expected_final_volume_ml"] == 10.0
    assert samples["A"]["expected_relative_concentration"] == 0.5
    assert "lighter" in samples["A"]["qualitative_appearance"]

    assert samples["C"]["volume_ml"] == 15.0
    assert samples["C"]["expected_final_volume_ml"] == 20.0
    assert samples["C"]["expected_relative_concentration"] == 0.25
    assert "lighter" in samples["C"]["qualitative_appearance"]

    # Lesson concepts (water molar mass constant, not measured)
    concepts = exp["lesson_concepts"]
    assert concepts["molar_mass_water_g_mol"] == 18.015
    assert "C7732185" in concepts["source"]
    assert "not an experimental measurement" in concepts["note"].lower()


def test_model_observation_sample_a_and_c():
    """Verify analytical model predictions for Source A and Source C."""
    # Test Source A (5 mL water added to 5 mL stock)
    obs_a = dilution.model_observation({"sample": "A"})
    assert obs_a["provenance"] == "MODEL-PREDICTED"
    assert obs_a["value"] == 0.5
    assert obs_a["units"] == "relative concentration"
    assert "0.50" in obs_a["text"]
    assert "No measured color or RGB value is available" in obs_a["text"]
    assert any("Conservation of solute moles" in a for a in obs_a["assumptions"])
    assert any("NEVER fake" in a for a in obs_a["assumptions"])
    assert "OpenStax" in obs_a["source"]
    assert "educational-simulation.md" in obs_a["source"]
    assert "WET_LAB.md" in obs_a["source"]

    # Test Source C (15 mL water added to 5 mL stock)
    obs_c = dilution.model_observation({"source": "C"})
    assert obs_c["provenance"] == "MODEL-PREDICTED"
    assert obs_c["value"] == 0.25
    assert "0.25" in obs_c["text"]
    assert "noticeably lighter" in obs_c["text"]


def test_model_observation_custom_and_dispatcher():
    """Verify model_observation handles custom volumes and dispatcher signatures."""
    # Custom volume
    obs_custom = dilution.model_observation(water_volume=10.0, stock_volume=5.0)
    assert obs_custom["value"] == pytest.approx(0.3333, abs=0.001)

    # Dispatcher call: ("color_dilution", {"sample": "A"})
    obs_disp = dilution.model_observation("color_dilution", {"sample": "A"})
    assert obs_disp["value"] == 0.5

    # Negative volume error
    with pytest.raises(ValueError):
        dilution.model_observation(water_volume=-5.0)


def test_make_quiz_progression():
    """Verify trial 1 produces MC on dye conservation; trial 2 produces free response."""
    # Trial 1: Multiple choice
    quiz_t1 = dilution.make_quiz(trial_count=1)
    assert quiz_t1["id"] == "quiz_dilution_mc_conservation"
    assert quiz_t1["type"] == "multiple_choice"
    assert isinstance(quiz_t1["options"], list)
    assert len(quiz_t1["options"]) == 4
    assert any("conserved" in opt for opt in quiz_t1["options"])

    # Trial 2: Free response comparative synthesis
    quiz_t2 = dilution.make_quiz(trial_count=2)
    assert quiz_t2["id"] == "quiz_dilution_fr_variable_volume"
    assert quiz_t2["type"] == "free_response"
    assert quiz_t2["options"] is None
    assert "C_stock * V_stock" in quiz_t2["prompt"]

    # Dispatcher call: ("color_dilution", [], 1)
    quiz_disp = dilution.make_quiz("color_dilution", [], 1)
    assert quiz_disp["type"] == "multiple_choice"


def test_make_quiz_unknown_outcome():
    """Verify inconclusive trial produces evidence verification question without faking."""
    unknown_obs = [{"status": "unknown", "text": "Liquid meniscus level unverified"}]
    quiz = dilution.make_quiz(unknown_obs, trial_count=2)
    assert quiz["id"] == "quiz_dilution_fr_unknown_evidence"
    assert quiz["type"] == "free_response"
    assert "NEVER fake" in quiz["prompt"]


def test_evaluate_answer_multiple_choice():
    """Verify evaluation rubric for trial 1 MC question."""
    quiz = dilution.make_quiz(trial_count=1)

    # Correct response (Option A or key terms)
    res_a = dilution.evaluate_answer(quiz, "A")
    assert res_a["correct"] is True
    assert res_a["provenance"] == "RULE-BASED-RUBRIC"
    assert "conserved" in res_a["feedback"].lower()

    res_text = dilution.evaluate_answer(quiz, "Dye molecules are conserved, relative concentration decreases to 0.50")
    assert res_text["correct"] is True

    # Incorrect response
    res_b = dilution.evaluate_answer(quiz, "B")
    assert res_b["correct"] is False
    assert "Incorrect" in res_b["feedback"]


def test_evaluate_answer_free_response_comparative():
    """Verify evaluation rubric for trial 2 comparative synthesis."""
    quiz = dilution.make_quiz(trial_count=2)

    # Comprehensive answer: mentions 0.5 vs 0.25, lighter color, and conserved solute
    good_answer = (
        "Adding 5 mL water gives final concentration 0.50, while 15 mL water gives 0.25 by C1V1=C2V2. "
        "The 15 mL solution looks noticeably lighter. Total solute moles remain conserved throughout."
    )
    res_good = dilution.evaluate_answer(quiz, good_answer)
    assert res_good["correct"] is True
    assert "0.50 vs 0.25" in res_good["feedback"]

    # Incomplete answer: only mentions color without values or conservation
    poor_answer = "It just becomes a little bit light blue."
    res_poor = dilution.evaluate_answer(quiz, poor_answer)
    assert res_poor["correct"] is False
    assert "Partially complete" in res_poor["feedback"]


def test_evaluate_answer_free_response_unknown_evidence():
    """Verify rubric for unknown outcome requires physical verification and forbids faking."""
    unknown_quiz = {"id": "quiz_dilution_fr_unknown_evidence", "type": "free_response"}

    good_ans = (
        "We need physical optical sensors or camera verification of the meniscus level. "
        "Controller logs only report motor commands and must never be used to fake sensor readings."
    )
    res_good = dilution.evaluate_answer(unknown_quiz, good_ans)
    assert res_good["correct"] is True
    assert "Strong scientific reasoning" in res_good["feedback"]

    bad_ans = "The arm finished its motion so we can just assume it worked and print RGB values."
    res_bad = dilution.evaluate_answer(unknown_quiz, bad_ans)
    assert res_bad["correct"] is False


def test_citations_in_module_docstring():
    """Verify primary educational sources and links in module docstring."""
    doc = dilution.__doc__ or ""
    assert "https://assets.openstax.org/oscms-prodcms/media/documents/Chemistry-LR.pdf" in doc
    assert "https://webbook.nist.gov/cgi/cbook.cgi?ID=C7732185" in doc
    assert "research/victor/educational-simulation.md" in doc
    assert "docs/WET_LAB.md" in doc
    assert "MOCK portion addition" in doc
    assert "receiver C" in doc


@pytest.mark.parametrize(('initial', 'station', 'portions', 'missing_observation', 'reason'), [
    ('held', 'C', 2, False, 'invalid_task'),
    ('held', 'B', 1, False, 'invalid_task'),
    ('held', 'C', 1, True, 'independent observation'),
    ('full_receiver', 'C', 1, False, 'empty receiver'),
    ('unheld', 'C', 1, False, 'held full cup'),
])
async def test_mock_pour_rejects_invalid_dose_route_state_or_missing_observation(
        tmp_path, initial, station, portions, missing_observation, reason):
    import asyncio

    from agentic.openarms_lab.backends import MockBackend
    from agentic.openarms_lab.runtime import Lab
    from agentic.tests.test_task_loop import TestPerception, decision

    class ProposedPour:
        async def run(self, context, **kwargs):
            steps = [{'operation': 'inspect_scene'},
                     {'operation': 'mock_pour', 'arguments': {
                         'fixture': 'sample_cup', 'station': station, 'portions': portions}}]
            if not missing_observation:
                steps.append({'operation': 'observe'})
            return decision(payload={'steps': steps,
                                     'outcome_checks': [{'feature': 'readable', 'expected': True}]})

    class PreparedMock(MockBackend):
        def prepare(self):
            super().prepare()
            if initial != 'unheld':
                self._state.update(holding='sample_cup', cup_station=None)
            if initial == 'full_receiver':
                self._state.update(receiver_portions=1)

    backend = PreparedMock(delay=0)
    lab = Lab(tmp_path, expert=ProposedPour(), perception=TestPerception(unknown=False),
              backend_factory=lambda: backend)
    try:
        sid = (await lab.create())['session_id']
        before = backend.state()
        handle = await lab.start_task(sid, 'Pour the held mock cup into the receiver.')
        await asyncio.wait_for(asyncio.shield(lab.workers[handle['task_id']]), 2)
        snap = lab.snapshot(sid)
        assert snap['tasks'][0]['status'] == 'failed'
        assert reason in snap['tasks'][0]['summary']
        assert snap['pending'] is None and snap['requests'] == [] and snap['observations'] == []
        assert backend.state() == before and backend.executions == 0
    finally:
        await lab.shutdown()
