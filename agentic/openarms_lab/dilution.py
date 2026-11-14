"""Color-dilution lesson with student-controlled added water volume.

Primary Official Educational & Field Research Sources:
- Dilution equation (C1*V1 = C2*V2): OpenStax Chemistry 2e, Section 3.3
  https://assets.openstax.org/oscms-prodcms/media/documents/Chemistry-LR.pdf
- Water standard data (H2O 18.015 g/mol): NIST Chemistry WebBook SRD 69, ID C7732185
  https://webbook.nist.gov/cgi/cbook.cgi?ID=C7732185 (lesson concept only; not measured)
- Educational simulation & guided inquiry: research/victor/educational-simulation.md
- Wet lab bounds & physical mapping: docs/WET_LAB.md
  (Motion is MOCK portion addition; physical pouring skills need hardware validation.
   Existing wet lab maps receiver C; do not imply physical mapping B is valid.)
"""
from __future__ import annotations
import re
from typing import Any, Optional

EXPERIMENT: dict[str, Any] = {
    "id": "color_dilution",
    "title": "Color Dilution: Variable Water Volume Inquiry",
    "question": "How does increasing added water volume affect the final relative concentration and color intensity of stock dye?",
    "instructions": (
        "1. Fixed stock dye (5 mL at relative concentration 1.0) is in receiver vessel B.\n"
        "2. Choose premeasured water source: Station A (5 mL) or Station C (15 mL).\n"
        "3. Predict final concentration: C_final = C_stock * V_stock / (V_stock + V_water).\n"
        "4. Command mock portion transfer; observe qualitatively lighter appearance without faking sensors.\n"
        "5. Compare analytical model prediction (0.50 vs 0.25) with empirical observations."
    ),
    "independent_variable": "added water volume",
    "controlled_variables": [
        "stock dye initial volume (5 mL)",
        "stock dye initial concentration (1.0 relative)",
        "receiver vessel geometry (Vessel B)",
        "optical path length and illumination",
        "solvent (pure water, H2O)",
    ],
    "receiver": {
        "station": "B",
        "initial_substance": "stock dye",
        "initial_volume_ml": 5.0,
        "initial_relative_concentration": 1.0,
        "note": "Motion remains MOCK portion addition; existing wet lab maps receiver C, do not imply physical mapping B valid.",
    },
    "samples": {
        "A": {
            "station": "A",
            "substance": "water",
            "volume_ml": 5.0,
            "stock_volume_ml": 5.0,
            "stock_concentration": 1.0,
            "expected_final_volume_ml": 10.0,
            "expected_relative_concentration": 0.5,
            "qualitative_appearance": "lighter than stock dye",
        },
        "C": {
            "station": "C",
            "substance": "water",
            "volume_ml": 15.0,
            "stock_volume_ml": 5.0,
            "stock_concentration": 1.0,
            "expected_final_volume_ml": 20.0,
            "expected_relative_concentration": 0.25,
            "qualitative_appearance": "noticeably lighter than Source A and stock dye",
        },
    },
    "lesson_concepts": {
        "molar_mass_water_g_mol": 18.015,
        "source": "NIST Chemistry WebBook SRD 69, ID C7732185 (https://webbook.nist.gov/cgi/cbook.cgi?ID=C7732185)",
        "note": "Optional lesson concept only (H2O 18.015 g/mol); not an experimental measurement.",
        "conservation_law": "Solute mass/moles remain constant during dilution; concentration drops as volume increases.",
    },
}


def model_observation(parameters: Optional[dict[str, Any] | str] = None, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Compute analytical model prediction. Never fakes RGB or real optical sensor readings."""
    params: dict[str, Any] = {}
    if isinstance(parameters, dict):
        params.update(parameters)
    elif isinstance(parameters, str) and args and isinstance(args[0], dict):
        params.update(args[0])
    params.update(kwargs)

    sample_key = str(params.get("sample") or params.get("sample_id") or params.get("source") or "A").strip().upper()
    v_stock = float(params.get("v_stock", params.get("stock_volume", 5.0)))
    c_stock = float(params.get("c_stock", params.get("stock_concentration", 1.0)))

    if "water_volume" in params or "v_water" in params:
        v_water = float(params.get("water_volume", params.get("v_water", 5.0)))
    elif sample_key in EXPERIMENT["samples"]:
        v_water = float(EXPERIMENT["samples"][sample_key]["volume_ml"])
    else:
        sample_key = "A"
        v_water = float(EXPERIMENT["samples"]["A"]["volume_ml"])

    if v_water < 0 or v_stock <= 0 or c_stock <= 0:
        raise ValueError("Volumes and initial concentration must be positive.")

    v_total = v_stock + v_water
    c_final = round((c_stock * v_stock) / v_total, 4)
    qualitative = "noticeably lighter than 5 mL dilution and much lighter than stock dye" if (sample_key == "C" or v_water >= 15.0) else "lighter than stock dye"

    text = (
        f"Model predicts adding {v_water:.1f} mL water to {v_stock:.1f} mL stock dye (rel. conc. {c_stock:.1f}) yields "
        f"{v_total:.1f} mL solution at relative concentration {c_final:.2f} (qualitatively {qualitative} under controlled "
        f"path/lighting). NEVER fake measured RGB or real optical sensor readings."
    )
    assumptions = [
        "Conservation of solute moles: C_stock * V_stock = C_final * V_total (OpenStax Chemistry 2e, Sec 3.3)",
        "Ideal volume additivity: V_total = V_stock + V_water with negligible excess volume of mixing",
        "Instantaneous complete mixing across receiver vessel B",
        "Constant optical path length and uniform illumination (Beer-Lambert proportionality)",
        "Sensor honesty: NEVER fake measured RGB or real optical sensor readings; qualitative model only",
    ]
    source = (
        "Analytical Dilution Model (OpenStax Chemistry 2e, Sec 3.3, "
        "https://assets.openstax.org/oscms-prodcms/media/documents/Chemistry-LR.pdf; "
        "research/victor/educational-simulation.md; docs/WET_LAB.md)"
    )
    return {
        "provenance": "MODEL-PREDICTED",
        "text": text,
        "value": c_final,
        "units": "relative concentration",
        "assumptions": assumptions,
        "source": source,
    }


def _has_unknown(observations: Optional[list[dict[str, Any]]]) -> bool:
    if not observations:
        return False
    for obs in observations:
        if isinstance(obs, dict):
            status = str(obs.get("status") or obs.get("outcome") or obs.get("result") or "").lower()
            text = str(obs.get("text") or "").lower()
            if any(term in status or term in text for term in ("unknown", "inconclusive", "failed", "unverified")):
                return True
    return False


def make_quiz(observations: Optional[list[dict[str, Any]] | str] = None, trial_count: int = 1, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Generate quiz: MC on trial 1 (solute conservation), free response on later trials."""
    if isinstance(observations, str):
        obs_val = args[0] if args and isinstance(args[0], list) else kwargs.get("observations")
        tc_val = args[1] if len(args) > 1 and isinstance(args[1], int) else kwargs.get("trial_count", 1)
        observations, trial_count = obs_val, tc_val

    obs_list = observations if isinstance(observations, list) else []

    if trial_count <= 1:
        return {
            "id": "quiz_dilution_mc_conservation",
            "type": "multiple_choice",
            "prompt": (
                "When 5 mL of premeasured water (Station A) is added to 5 mL of stock dye (relative concentration 1.0) "
                "in receiver vessel B, what happens to the total number of dye molecules (solute) and the solution concentration?"
            ),
            "options": [
                "A) Dye molecules remain unchanged (conserved), but relative concentration decreases to 0.50 because total volume doubled.",
                "B) The number of dye molecules doubles because liquid volume doubled from 5 mL to 10 mL.",
                "C) The concentration remains 1.0 because dye molecules cannot be diluted.",
                "D) Both dye molecules and concentration decrease to zero upon mixing.",
            ],
        }

    if _has_unknown(obs_list):
        return {
            "id": "quiz_dilution_fr_unknown_evidence",
            "type": "free_response",
            "prompt": (
                "A dilution trial produced an unverified or inconclusive outcome. What physical evidence is required "
                "to confirm liquid transfer and mixing, and why must the system NEVER fake measured RGB values or "
                "infer physical state solely from mock robot commands?"
            ),
            "options": None,
        }

    return {
        "id": "quiz_dilution_fr_variable_volume",
        "type": "free_response",
        "prompt": (
            "Compare the outcomes when adding 5 mL water (Source A) versus 15 mL water (Source C) to 5 mL of stock dye. "
            "Using C_stock * V_stock = C_final * V_final, explain how varying water volume affects the final concentration "
            "(0.50 vs 0.25), qualitative color appearance, and solute conservation."
        ),
        "options": None,
    }


def evaluate_answer(
    quiz: dict[str, Any] | str,
    answer: str | dict[str, Any],
    observations: Optional[list[dict[str, Any]]] = None,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Evaluate student quiz answer using deterministic rubric."""
    if isinstance(quiz, str):
        quiz_dict = answer if isinstance(answer, dict) else (args[0] if args and isinstance(args[0], dict) else {})
        ans_val = observations if isinstance(observations, str) else (args[1] if len(args) > 1 and isinstance(args[1], str) else kwargs.get("answer", ""))
        obs_val = kwargs.get("observations") if observations == ans_val else observations
        quiz, answer, observations = quiz_dict, str(ans_val), (obs_val if isinstance(obs_val, list) else None)

    quiz_type = quiz.get("type", "") if isinstance(quiz, dict) else ""
    quiz_id = quiz.get("id", "") if isinstance(quiz, dict) else ""
    norm = str(answer or "").strip()
    obs_list = observations or []

    if quiz_type == "multiple_choice":
        clean = re.sub(r"^(option|choice|answer)\s*", "", norm, flags=re.I).strip()
        is_bad = bool(re.match(r"^[bcd]([\)\.\:\s]|$)", clean, flags=re.I))
        is_good = bool(re.match(r"^a([\)\.\:\s]|$)", clean, flags=re.I)) or any(k in clean.lower() for k in ("conserv", "unchanged", "0.5"))
        is_correct = is_good and not is_bad
        feedback = (
            "Correct! Solute moles are conserved during dilution (n = C * V). Doubling total volume from 5 mL to 10 mL halves relative concentration to 0.50."
            if is_correct else
            "Incorrect. Dilution conserves the total amount of solute (dye molecules) while increasing solvent volume, which lowers relative concentration."
        )
        follow_up = "Ready for trial 2: test Source C (15 mL water)." if is_correct else "Review the principle of conservation of solute in C1*V1 = C2*V2."
        return {"feedback": feedback, "correct": is_correct, "follow_up": follow_up, "provenance": "RULE-BASED-RUBRIC"}

    if quiz_type == "free_response":
        lower = norm.lower()
        if "unknown" in quiz_id or _has_unknown(obs_list):
            has_ev = any(w in lower for w in ("sensor", "camera", "visual", "optical", "physical", "meniscus", "liquid level", "mass", "scale"))
            has_no_fake = any(w in lower for w in ("fake", "fabricat", "controller", "mock", "log", "infer", "blind", "unverified"))
            is_correct = has_ev and has_no_fake
            feedback = (
                "Strong scientific reasoning. You identified that physical/optical confirmation is essential and that controller logs must never fake sensor readings."
                if is_correct else
                "Incomplete evaluation. Science requires physical evidence; controller completion cannot prove liquid transfer and optical/RGB readings must never be faked."
            )
            follow_up = "Verification standards confirmed." if is_correct else "Reflect on why robot logs do not guarantee physical fluid displacement."
            return {"feedback": feedback, "correct": is_correct, "follow_up": follow_up, "provenance": "RULE-BASED-RUBRIC"}

        has_calc = any(w in lower for w in ("0.5", "0.25", "half", "quarter", "equation", "c1*v1", "c1v1", "inverse", "doubl", "quadrupl"))
        has_color = any(w in lower for w in ("light", "color", "intensity", "absorb", "dilut", "pale"))
        has_solute = any(w in lower for w in ("conserv", "moles", "molecules", "solute", "amount of dye", "unchanged", "constant"))
        is_correct = sum([has_calc, has_color, has_solute]) >= 2
        feedback = (
            "Excellent synthesis! You connected added water volume to final concentration (0.50 vs 0.25), noted qualitative color lightening, and recognized solute conservation."
            if is_correct else
            "Partially complete explanation. Be sure to address concentration values (0.50 vs 0.25), qualitative color lightening, and solute conservation."
        )
        follow_up = "Inquiry complete. You have demonstrated rigorous dilution principles." if is_correct else "Review C_final = C_stock * V_stock / (V_stock + V_water)."
        return {"feedback": feedback, "correct": is_correct, "follow_up": follow_up, "provenance": "RULE-BASED-RUBRIC"}

    return {"feedback": "Unrecognized quiz format.", "correct": None, "follow_up": "Check quiz type.", "provenance": "RULE-BASED-RUBRIC"}
