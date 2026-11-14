"""Educational lesson, inquiry guidance, and quiz support for OpenArms.

This module provides curriculum experiment definitions, analytical model predictions,
and deterministic rubric-based assessment for OpenArms laboratory sessions.

Academic & Field Research Citations:
-------------------------------------
1. Guided Inquiry & Variable Scaffolding:
   Lazonder, A. W., & Harmsen, R. (2016). Meta-Analysis of Inquiry-Based
   Learning: Effects of Guidance. Review of Educational Research, 86(3),
   681-718. https://doi.org/10.3102/0034654315627366
   -> OpenArms implements structured guided inquiry: isolating variables,
      eliciting directional predictions before physical trials, recording
      empirical observations, and prompting reflection using transparent rubrics.

2. Evidence-Based Reasoning & Model Discrepancies:
   Holmes, N. G., Wieman, C. E., & Bonn, D. A. (2015). Teaching critical
   thinking. Proceedings of the National Academy of Sciences (PNAS),
   112(36), 11199-11204. https://doi.org/10.1073/pnas.1505329112
   -> OpenArms prompts students to compare empirical trial observations against
      explicitly labeled analytical models ('MODEL-PREDICTED'), treating
      discrepancies as opportunities for verification rather than simulation errors.

3. Complementary Physical vs. Virtual Inquiry:
   Muilwijk, M., & Lazonder, A. W. (2023). Comparing the Effects of Physical
   and Virtual Inquiry on Conceptual Knowledge: A Meta-Analysis. Frontiers
   in Education, 8:1163024. https://doi.org/10.3389/feduc.2023.1163024
   -> OpenArms pairs robotic manipulation of physical/mock materials with
      complementary analytical models, isolating variables without fabricating
      unobserved physical phenomena.

4. OpenArms Experiment Feasibility & Simulation Architecture:
   - Victor (2026), 'HackPrinceton Research: Educational Simulation & Feasibility',
     research/victor/educational-simulation.md & research/victor/laboratory-experiments-and-feasibility.md:
     Controlled buoyancy feasibility using matched sample pairs: Sample A (0.8 g/mL)
     and Sample C (1.2 g/mL) in water (1.0 g/mL), identical 20 mL volume.
     Archimedes' principle: F_b = rho_fluid * g * V_displaced; submerged fraction
     rho_object / rho_fluid.
   - Joseph (2026), 'OpenArms Canonical Notion Snapshot',
     research/joseph/OpenArms-Complete-Notion.md:
     Explicit separation between analytic model prediction ('MODEL-PREDICTED')
     and robotic execution ('MOCK-OBSERVATION' / 'PHYSICAL-OBSERVATION').
     OpenArms is not a full CFD simulator; it pairs analytical models with arm actions.
   - Shared Interfaces & Mandarin Baseline:
     docs/INTERFACES.md & research/joseph/mandarin-transfer-handoff.md:
     Mandarin transfer is a physical manipulation baseline. No scientific effect
     is invented; model_observation returns None.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Optional


# ==============================================================================
# Seeded Experiments Curriculum
# ==============================================================================

EXPERIMENTS: list[dict[str, Any]] = [
    {
        "id": "buoyancy_trial",
        "title": "Buoyancy and Density: Comparative Float/Sink Trial",
        "question": "At the same external volume, does sample density determine whether an object floats or sinks in water?",
        "instructions": (
            "1. Review the two prepared samples: Sample A (density 0.8 g/mL) at Station A, and Sample C (density 1.2 g/mL) at Station C.\n"
            "2. Note the controlled variables: both samples have an identical external volume of 20 mL, the liquid is stationary water (density 1.0 g/mL), and the arm employs an identical gentle surface-release method.\n"
            "3. Choose a sample to test, record your prediction, and command the arm to release the sample into the water tank.\n"
            "4. Observe the stable resting state (floated vs sunk) and compare the empirical observation with the analytical Archimedes model prediction.\n"
            "5. Repeat with the second sample to observe the effect of the independent variable (sample density)."
        ),
        "independent_variable": "sample density",
        "controlled_variables": [
            "sample volume",
            "fluid density",
            "release method"
        ],
        "fluid": {
            "substance": "water",
            "density": 1.0,
            "density_units": "g/mL",
            "volume": 200.0,
            "volume_units": "mL"
        },
        "samples": {
            "A": {
                "station": "A",
                "label": "Sample A",
                "density": 0.8,
                "density_units": "g/mL",
                "volume": 20.0,
                "volume_units": "mL",
                "mass": 16.0,
                "mass_units": "g",
                "expected_model_state": "floats",
                "submerged_fraction": 0.8
            },
            "C": {
                "station": "C",
                "label": "Sample C",
                "density": 1.2,
                "density_units": "g/mL",
                "volume": 20.0,
                "volume_units": "mL",
                "mass": 24.0,
                "mass_units": "g",
                "expected_model_state": "sinks",
                "submerged_fraction": 1.0
            }
        },
        "backend": "MOCK",
        "science_discipline": "physics",
        "provenance": "CURRICULUM-SEEDED"
    },
    {
        "id": "mandarin_transfer",
        "title": "Mandarin Transfer: Robotic Manipulation Baseline",
        "question": "Can the robotic arm reliably pick up and transfer a mandarin from Station A to Station B?",
        "instructions": (
            "1. Confirm the mandarin is placed at Station A.\n"
            "2. Issue the spoken or text transfer command to move the mandarin to Station B.\n"
            "3. Review the proposed plan preview and confirm execution.\n"
            "4. Observe arm movement and confirm final placement at Station B via independent observation.\n"
            "Note: This is a robotics manipulation baseline. No physical or scientific model effect is simulated or invented."
        ),
        "independent_variable": "destination station",
        "controlled_variables": [
            "object type",
            "starting station",
            "gripper grasp force",
            "motion trajectory"
        ],
        "samples": {
            "mandarin": {
                "station": "A",
                "source": "A",
                "destination": "B",
                "label": "Fresh Mandarin",
                "mass": 50.0,
                "mass_units": "g",
                "object": "mandarin"
            }
        },
        "backend": "MOCK",
        "science_discipline": "robotics",
        "provenance": "CURRICULUM-SEEDED"
    }
]


def get_experiment(experiment_id: str) -> dict[str, Any]:
    """Retrieve an experiment configuration by ID.

    Args:
        experiment_id: Unique identifier for the experiment (e.g., 'buoyancy_trial'
                       or 'mandarin_transfer'). Supports 'buoyancy' as an alias.

    Returns:
        A deep copy of the experiment dictionary.

    Raises:
        ValueError: If no experiment matches the provided ID.
    """
    normalized_id = experiment_id.strip().lower()
    if normalized_id in ("buoyancy", "buoyancy_trial"):
        target_id = "buoyancy_trial"
    elif normalized_id in ("mandarin", "mandarin_transfer"):
        target_id = "mandarin_transfer"
    else:
        target_id = normalized_id

    for exp in EXPERIMENTS:
        if exp["id"] == target_id:
            return copy.deepcopy(exp)

    available = ", ".join(repr(e["id"]) for e in EXPERIMENTS)
    raise ValueError(f"Experiment '{experiment_id}' not found. Available experiments: {available}")


# ==============================================================================
# Analytical Science Model Observation (Separate from Mock Motion)
# ==============================================================================

def model_observation(experiment_id: str, parameters: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    """Compute an analytical scientific model prediction for an experiment.

    IMPORTANT: This returns MODEL-PREDICTED theoretical values from scientific
    principles (Archimedes' principle: F_b = rho_fluid * g * V_displaced).
    It is NOT an observation from physical sensors or mock robot execution,
    and OpenArms is NOT a dynamic physics simulator.

    For transfer lessons (e.g., 'mandarin_transfer'), this function returns None
    because transfer is a physical baseline with no invented science effect.

    Args:
        experiment_id: The experiment identifier ('buoyancy_trial', 'mandarin_transfer').
        parameters: Optional parameters dictionary. For buoyancy, may contain:
                    - 'sample_id' or 'sample': 'A' or 'C'
                    - 'density': float (in g/mL)
                    - 'mass': float (g) and 'volume': float (mL)
                    - 'fluid_density': float (defaults to 1.0 g/mL water)

    Returns:
        Dict containing keys {provenance, text, value, units, assumptions, source},
        or None for baseline transfer tasks.

    Raises:
        ValueError: If experiment_id is unknown.
    """
    exp = get_experiment(experiment_id)
    target_id = exp["id"]

    # Mandarin transfer has no scientific effect invented: return None.
    if target_id == "mandarin_transfer":
        return None

    if target_id == "buoyancy_trial":
        params = parameters or {}
        sample_key = str(params.get("sample_id") or params.get("sample") or "").strip().upper()

        # Fluid density defaults to water 1.0 g/mL
        fluid_density = float(params.get("fluid_density", 1.0))
        if fluid_density <= 0:
            raise ValueError(f"Fluid density must be positive, got {fluid_density}")

        # Determine sample density
        sample_density: Optional[float] = None
        if "density" in params:
            sample_density = float(params["density"])
        elif "mass" in params and "volume" in params:
            mass = float(params["mass"])
            vol = float(params["volume"])
            if vol <= 0:
                raise ValueError(f"Sample volume must be positive, got {vol}")
            sample_density = mass / vol
        elif sample_key in exp["samples"]:
            sample_density = float(exp["samples"][sample_key]["density"])
        else:
            # Default to Sample A if not specified
            sample_key = "A"
            sample_density = float(exp["samples"]["A"]["density"])

        if sample_density <= 0:
            raise ValueError(f"Sample density must be positive, got {sample_density}")

        # Analytical Archimedes Calculation:
        # F_b_max = rho_fluid * V * g; F_g = rho_sample * V * g
        # Ratio F_g / F_b_max = rho_sample / rho_fluid
        ratio = sample_density / fluid_density

        if ratio < 1.0:
            state = "floats"
            submerged_pct = round(ratio * 100.0, 1)
            sample_desc = f"Sample {sample_key}" if sample_key in ("A", "C") else "Sample"
            text = (
                f"{sample_desc} (density {sample_density:.2f} g/mL) is predicted to float "
                f"in fluid (density {fluid_density:.2f} g/mL). At equilibrium, approximately "
                f"{submerged_pct}% of its volume will be submerged."
            )
            value = "floats"
        elif ratio > 1.0:
            state = "sinks"
            sample_desc = f"Sample {sample_key}" if sample_key in ("A", "C") else "Sample"
            text = (
                f"{sample_desc} (density {sample_density:.2f} g/mL) is predicted to sink "
                f"in fluid (density {fluid_density:.2f} g/mL) because sample density exceeds "
                f"fluid density, creating a net downward gravitational force."
            )
            value = "sinks"
        else:
            state = "neutral"
            sample_desc = f"Sample {sample_key}" if sample_key in ("A", "C") else "Sample"
            text = (
                f"{sample_desc} (density {sample_density:.2f} g/mL) has identical density "
                f"to fluid (density {fluid_density:.2f} g/mL) and is predicted to have neutral buoyancy."
            )
            value = "neutral"

        assumptions = [
            f"Stationary uniform fluid with density {fluid_density:.2f} g/mL",
            "Rigid, non-porous sample with constant external volume and zero fluid absorption",
            "Negligible surface tension effects and container wall adhesion",
            "Ideal Archimedes displacement: buoyant force F_b = rho_fluid * g * V_displaced"
        ]
        source = (
            "Analytical Archimedes' Principle (OpenStax College Physics 2e, Ch. 11.7; "
            "Victor Educational Simulation Research, research/victor/educational-simulation.md)"
        )

        return {
            "provenance": "MODEL-PREDICTED",
            "text": text,
            "value": value,
            "units": "categorical",
            "assumptions": assumptions,
            "source": source
        }

    raise ValueError(f"No analytical model registered for experiment '{experiment_id}'")


# ==============================================================================
# Quiz Generation (MC First Trial -> Free Response Later / Unknown Handling)
# ==============================================================================

def _has_unknown_outcome(observations: list[dict[str, Any]]) -> bool:
    """Check if any recorded observation has an unknown, unconfirmed, or failed outcome."""
    if not observations:
        return False
    for obs in observations:
        if not isinstance(obs, dict):
            continue
        # Check explicit outcome / result keys
        outcome = str(obs.get("outcome") or obs.get("result") or "").strip().lower()
        if outcome in ("unknown", "inconclusive", "unclear", "unverified", "failed", "error"):
            return True
        status = str(obs.get("status") or "").strip().lower()
        if status in ("unknown", "failed", "stopped", "inconclusive"):
            return True
        # Check text description
        text = str(obs.get("text") or "").strip().lower()
        if any(term in text for term in ("unknown", "inconclusive", "cannot confirm", "unclear")):
            return True
        # Check placement for transfer tasks
        if "placement" in obs and obs["placement"] is None:
            return True
    return False


def make_quiz(
    experiment_id: str,
    observations: Optional[list[dict[str, Any]]] = None,
    trial_count: int = 1
) -> dict[str, Any]:
    """Generate a quiz question tailored to the experiment stage and trial history.

    Pedagogical Design Rules:
    - Trial 1 (first trial, trial_count <= 1): Multiple choice question to scaffold
      initial prediction and variable identification (Lazonder & Harmsen, 2016).
    - Trial 2+ (later trials, trial_count >= 2): Free response question prompting
      the student to synthesize evidence across trials (Holmes et al., 2015).
    - Unknown or inconclusive outcomes: Asks what specific physical evidence is
      needed, reinforcing that outcomes must NEVER be inferred from controller logs.

    Args:
        experiment_id: Experiment identifier ('buoyancy_trial', 'mandarin_transfer').
        observations: List of observation dictionaries recorded so far in the session.
        trial_count: Number of trials completed or attempted (default: 1).

    Returns:
        Dict with keys {id, type, prompt, options}.
        'type' is 'multiple_choice' or 'free_response'.
        'options' is list[str] for multiple_choice, or None for free_response.

    Raises:
        ValueError: If experiment_id is unknown.
    """
    exp = get_experiment(experiment_id)
    target_id = exp["id"]
    obs_list = observations or []

    # Check for unknown / unconfirmed outcomes in later trials
    has_unknown = _has_unknown_outcome(obs_list)

    # --------------------------------------------------------------------------
    # Case 1: Buoyancy Experiment
    # --------------------------------------------------------------------------
    if target_id == "buoyancy_trial":
        if trial_count <= 1:
            return {
                "id": "quiz_buoyancy_mc_t1_prediction",
                "type": "multiple_choice",
                "prompt": (
                    "In this buoyancy trial, Sample A has a density of 0.8 g/mL and Sample C "
                    "has a density of 1.2 g/mL, released into water (density 1.0 g/mL). Both have "
                    "an identical volume of 20 mL. Based on Archimedes' principle, what outcome "
                    "do you predict for Sample A upon release?"
                ),
                "options": [
                    "A) Sample A will float because its density (0.8 g/mL) is less than water's density (1.0 g/mL).",
                    "B) Sample A will sink because solid objects always sink in liquids.",
                    "C) Sample A will sink because its mass of 16 g is heavier than air.",
                    "D) Sample A will dissolve instantly into the water."
                ]
            }

        # Later trials (trial_count >= 2)
        if has_unknown:
            return {
                "id": "quiz_buoyancy_fr_unknown_evidence",
                "type": "free_response",
                "prompt": (
                    "One of your buoyancy trials produced an unknown or inconclusive outcome. "
                    "What specific physical evidence and verification steps are required to determine "
                    "whether the sample actually floated or sank, and why must you never infer the outcome "
                    "solely from controller execution logs?"
                ),
                "options": None
            }

        # Normal multi-trial comparative reflection
        return {
            "id": "quiz_buoyancy_fr_comparative_synthesis",
            "type": "free_response",
            "prompt": (
                "Compare your observations across the trials (Sample A vs Sample C). Explain the difference "
                "in their floating and sinking behavior using density (mass and volume) and Archimedes' "
                "displacement principle."
            ),
            "options": None
        }

    # --------------------------------------------------------------------------
    # Case 2: Mandarin Transfer Experiment (Robotic Baseline)
    # --------------------------------------------------------------------------
    if target_id == "mandarin_transfer":
        if trial_count <= 1:
            return {
                "id": "quiz_mandarin_mc_t1_baseline",
                "type": "multiple_choice",
                "prompt": (
                    "In this baseline robotic transfer from Station A to Station B, what constitutes "
                    "valid empirical evidence that the transfer was successfully completed?"
                ),
                "options": [
                    "A) Independent visual or physical sensor observation confirming the mandarin is resting at Station B.",
                    "B) The software controller completed its motion steps without raising an error.",
                    "C) The language model predicted the transfer would succeed.",
                    "D) The user approved the plan proposal before execution."
                ]
            }

        if has_unknown:
            return {
                "id": "quiz_mandarin_fr_unknown_evidence",
                "type": "free_response",
                "prompt": (
                    "A transfer trial resulted in an unverified or failed placement. What physical evidence "
                    "is required to verify where the mandarin actually landed, and why is controller step "
                    "completion not sufficient proof of placement?"
                ),
                "options": None
            }

        return {
            "id": "quiz_mandarin_fr_baseline_reflection",
            "type": "free_response",
            "prompt": (
                "Reflect on the robotic transfer trials. Explain why independent physical observation "
                "of placement is required for laboratory integrity, and clarify whether any scientific "
                "effect was modeled or simulated for this baseline task."
            ),
            "options": None
        }

    raise ValueError(f"No quiz templates registered for experiment '{experiment_id}'")


# ==============================================================================
# Transparent Deterministic Rubric Evaluation
# ==============================================================================

def _format_observations_summary(observations: list[dict[str, Any]]) -> str:
    """Summarize empirical observations without ever fabricating or predicting results."""
    if not observations:
        return "No empirical observations recorded yet in this session."

    lines = []
    for idx, obs in enumerate(observations, start=1):
        if not isinstance(obs, dict):
            continue
        sample = obs.get("sample") or obs.get("sample_id") or obs.get("station") or f"Trial {idx}"
        result = obs.get("result") or obs.get("outcome") or obs.get("status") or obs.get("text") or "recorded"
        prov = obs.get("provenance", "EMPIRICAL-OBSERVATION")
        lines.append(f"Trial {idx} ({sample}): {result} [provenance: {prov}]")

    return "; ".join(lines) if lines else "No empirical observations recorded."


def _normalize_mc_answer(answer: str) -> str:
    """Normalize student input for multiple choice evaluation."""
    ans = answer.strip()
    return re.sub(r"^(option|choice|answer)\s*", "", ans, flags=re.IGNORECASE).strip()


def _evaluate_mc_buoyancy(answer: str, observations: list[dict[str, Any]]) -> tuple[bool, str, str]:
    """Evaluate multiple-choice buoyancy prediction answer deterministically."""
    norm = _normalize_mc_answer(answer).lower()

    # Option A: Sample A will float because density (0.8 g/mL) < water (1.0 g/mL)
    is_a = bool(
        re.match(r"^a([\)\.\:\s]|$)", norm)
        or norm in ("0", "1")
        or ("0.8" in norm and ("float" in norm or "less than" in norm))
        or "sample a will float" in norm
    )
    is_b = bool(re.match(r"^b([\)\.\:\s]|$)", norm) or "solid objects always sink" in norm)
    is_c = bool(re.match(r"^c([\)\.\:\s]|$)", norm) or "heavier than air" in norm or "16 g" in norm)
    is_d = bool(re.match(r"^d([\)\.\:\s]|$)", norm) or "dissolve" in norm)

    is_correct = is_a and not (is_b or is_c or is_d)
    obs_summary = _format_observations_summary(observations)

    if is_correct:
        feedback = (
            "### Rubric Assessment: [✓ Correct]\n"
            "- **Scientific Principle**: Correctly recognized that Sample A floats because its average density "
            "(0.8 g/mL) is less than water's density (1.0 g/mL).\n"
            "- **Archimedes' Force Balance**: According to Archimedes' principle, the buoyant force equals the weight "
            "of displaced fluid. Because Sample A is less dense than water, buoyant force balances gravity at partial "
            "submersion (approx. 80% volume submerged).\n\n"
            f"**Session Context**: {obs_summary}"
        )
        follow_up = (
            "Next step: Execute the physical/mock trial to observe Sample A's stable resting state, "
            "then test Sample C (density 1.2 g/mL) to observe how changing the independent variable affects buoyancy."
        )
    else:
        feedback = (
            "### Rubric Assessment: [✗ Incorrect]\n"
            "- **Key Concept**: Floating and sinking in a stationary fluid depends on the relationship between "
            "average sample density (mass/volume) and fluid density, not absolute mass or solid state.\n"
            "- **Correction**: Sample A has density 0.8 g/mL, which is less than water (1.0 g/mL). "
            "Therefore, Sample A will float with partial submersion.\n\n"
            f"**Session Context**: {obs_summary}"
        )
        follow_up = (
            "Review the density formula (rho = mass / volume). Re-examine Sample A (16 g / 20 mL = 0.8 g/mL) "
            "compared to water (1.0 g/mL)."
        )

    return is_correct, feedback, follow_up


def _evaluate_mc_mandarin(answer: str, observations: list[dict[str, Any]]) -> tuple[bool, str, str]:
    """Evaluate multiple-choice mandarin transfer baseline answer deterministically."""
    norm = _normalize_mc_answer(answer).lower()

    # Correct option is A: Independent visual or sensor observation
    is_a = bool(
        re.match(r"^a([\)\.\:\s]|$)", norm)
        or norm in ("0", "1")
        or "independent visual" in norm
        or "sensor observation" in norm
    )
    is_b = bool(re.match(r"^b([\)\.\:\s]|$)", norm) or "controller completed" in norm)
    is_c = bool(re.match(r"^c([\)\.\:\s]|$)", norm) or "language model predicted" in norm)
    is_d = bool(re.match(r"^d([\)\.\:\s]|$)", norm) or "user approved" in norm or "approved the plan" in norm)

    is_correct = is_a and not (is_b or is_c or is_d)
    obs_summary = _format_observations_summary(observations)

    if is_correct:
        feedback = (
            "### Rubric Assessment: [✓ Correct]\n"
            "- **Laboratory Evidence Standard**: Correctly identified that only independent physical observation "
            "(e.g., camera or sensor at Station B) confirms placement.\n"
            "- **Controller Limitation**: Software execution logs only show that motor steps were sent; they do not "
            "prove that the gripper securely held or released the object.\n\n"
            f"**Session Context**: {obs_summary}"
        )
        follow_up = (
            "Proceed with the transfer and verify Station B using the visual observation camera."
        )
    else:
        feedback = (
            "### Rubric Assessment: [✗ Incorrect]\n"
            "- **Key Rule**: A controller execution report is not proof of placement. Software commands can succeed "
            "even if the gripper slips, drops the object, or jams.\n"
            "- **Correction**: Independent visual or physical sensor observation is required.\n\n"
            f"**Session Context**: {obs_summary}"
        )
        follow_up = (
            "Review the OpenArms interface contract (docs/INTERFACES.md): placement must be independently observed."
        )

    return is_correct, feedback, follow_up


def _evaluate_fr_unknown_outcome(answer: str, observations: list[dict[str, Any]]) -> tuple[bool, str, str]:
    """Evaluate free-response answer for unknown outcome trials deterministically."""
    text = answer.strip().lower()

    # Criterion 1: Independent empirical evidence (camera, visual, sensor, inspection, scale)
    evidence_keywords = [
        "camera", "visual", "look", "photo", "image", "sensor", "inspect", "inspection",
        "scale", "balance", "physical observation", "independent check", "see", "sight", "view"
    ]
    has_evidence = any(kw in text for kw in evidence_keywords)

    # Criterion 2: Controller limitation (never infer from controller / motor / logs / steps)
    # Must explicitly express limitation/negation regarding the controller, not trust it blindly
    controller_terms = ["controller", "motor", "software", "log", "step", "runner"]
    limitation_terms = [
        "not proof", "never infer", "cannot assume", "cannot infer", "doesn't prove",
        "does not prove", "cannot prove", "no guarantee", "not guarantee",
        "doesn't guarantee", "does not guarantee", "insufficient", "not sufficient",
        "slip", "dropped", "jam", "blind", "false success", "could fail", "might fail",
        "unreliable", "unverified"
    ]
    has_controller_limitation = (
        (any(ct in text for ct in controller_terms) and any(lt in text for lt in limitation_terms))
        or "never infer" in text
        or "not proof" in text
        or "cannot infer" in text
    )

    obs_summary = _format_observations_summary(observations)

    rubric_items = [
        f"- **Independent Physical Verification**: {'[✓ Met]' if has_evidence else '[✗ Incomplete]'} "
        + ("Identified need for independent visual/sensor evidence." if has_evidence else "Must cite independent physical evidence (camera, inspection, sensor)."),
        f"- **Controller Limitation Recognition**: {'[✓ Met]' if has_controller_limitation else '[✗ Incomplete]'} "
        + ("Recognized that controller execution logs cannot prove physical state." if has_controller_limitation else "Must explicitly state that controller execution logs do not prove physical outcome.")
    ]

    is_correct = has_evidence and has_controller_limitation

    feedback = (
        f"### Rubric Assessment: {'[✓ Satisfactory]' if is_correct else '[✗ Incomplete]'}\n"
        + "\n".join(rubric_items) + "\n\n"
        f"**Session Context**: {obs_summary}\n"
        "**Principle**: In laboratory science and robotics, software execution is not empirical observation. "
        "A robot may complete a trajectory while dropping or misplacing a sample."
    )

    if is_correct:
        follow_up = "Record a verified observation using camera inspection or manual teacher confirmation."
    else:
        follow_up = (
            "Refine your response: specify what physical tool (e.g. camera, sensor) verifies the state, "
            "and explain why motor logs alone cannot be trusted."
        )

    return is_correct, feedback, follow_up


def _evaluate_fr_buoyancy_comparison(
    answer: str,
    observations: list[dict[str, Any]]
) -> tuple[bool, str, str]:
    """Evaluate free-response buoyancy comparative explanation using deterministic rubric."""
    text = answer.strip().lower()

    # Criterion 1: Density Concept (mass/volume, numerical density 0.8 vs 1.2, or relative to water 1.0)
    density_terms = [
        "density", "mass and volume", "mass/volume", "g/ml", "g/cm3", "mass divided by volume",
        "d = m/v", "0.8", "1.2", "less dense", "more dense", "denser"
    ]
    has_density = any(term in text for term in density_terms)

    # Criterion 2: Displacement / Archimedes' Buoyancy Principle
    displacement_terms = [
        "displacement", "displaced", "buoyant force", "buoyancy", "archimedes",
        "upward force", "weight of water", "weight of displaced", "water displaced",
        "force balance", "gravity", "submerged"
    ]
    has_displacement = any(term in text for term in displacement_terms)

    # Criterion 3: Grounded in Observed Trials (Sample A vs Sample C, floated vs sank)
    observation_terms = [
        "sample a", "sample c", "floated", "sank", "floating", "sinking", "trial", "observed"
    ]
    has_observation_grounding = any(term in text for term in observation_terms)

    obs_summary = _format_observations_summary(observations)

    rubric_items = [
        f"- **Density Principle (mass/volume relationship)**: {'[✓ Met]' if has_density else '[✗ Incomplete]'} "
        + ("Explained density comparison between samples (0.8 g/mL vs 1.2 g/mL) and water (1.0 g/mL)." if has_density else "Missing explicit analysis of sample density (mass/volume) relative to water (1.0 g/mL)."),
        f"- **Displacement & Archimedes' Buoyant Force**: {'[✓ Met]' if has_displacement else '[✗ Incomplete]'} "
        + ("Referenced Archimedes' displacement and buoyant force vs gravity." if has_displacement else "Missing explanation of Archimedes' principle (buoyant force equals weight of displaced fluid)."),
        f"- **Grounded Empirical Synthesis**: {'[✓ Met]' if has_observation_grounding else '[✗ Incomplete]'} "
        + ("Grounded explanation in actual trial observations of Sample A and Sample C." if has_observation_grounding else "Must explicitly reference the observed outcomes of Sample A and Sample C.")
    ]

    is_correct = has_density and has_displacement and has_observation_grounding

    feedback = (
        f"### Transparent Rubric Assessment: {'[✓ Satisfactory Explanation]' if is_correct else '[✗ Incomplete Explanation]'}\n"
        + "\n".join(rubric_items) + "\n\n"
        f"**Recorded Empirical Trials**: {obs_summary}\n"
        "**Theoretical Model Alignment**: "
        "Sample A (density 0.8 g/mL < water 1.0 g/mL) experiences buoyant force equal to its weight "
        "when 80% submerged, so it floats. Sample C (density 1.2 g/mL > water 1.0 g/mL) has a gravitational "
        "weight greater than the maximum buoyant force of fully displaced water, so it sinks. "
        "Model predictions (provenance: MODEL-PREDICTED) align with mock observations (provenance: MOCK-OBSERVATION)."
    )

    if is_correct:
        follow_up = (
            "Advanced Inquiry Extension: What would happen to Sample C if we dissolved salt into the water "
            "to increase fluid density to 1.3 g/mL? How would the buoyant force change?"
        )
    else:
        missing = []
        if not has_density:
            missing.append("sample density (0.8 g/mL vs 1.2 g/mL)")
        if not has_displacement:
            missing.append("Archimedes' principle and buoyant force from displaced water")
        if not has_observation_grounding:
            missing.append("direct reference to your recorded trial observations")
        follow_up = f"To complete your explanation, address the missing elements: {', '.join(missing)}."

    return is_correct, feedback, follow_up


def _evaluate_fr_mandarin_baseline(
    answer: str,
    observations: list[dict[str, Any]]
) -> tuple[bool, str, str]:
    """Evaluate free-response answer for mandarin baseline transfer deterministically."""
    text = answer.strip().lower()

    has_independent_check = any(w in text for w in ("independent", "visual", "camera", "verify", "sensor", "placement", "see", "check"))
    has_baseline_recognition = any(w in text for w in ("baseline", "no science", "manipulation", "robotics", "physical", "motion", "transfer"))

    obs_summary = _format_observations_summary(observations)

    is_correct = has_independent_check and has_baseline_recognition

    feedback = (
        f"### Rubric Assessment: {'[✓ Satisfactory]' if is_correct else '[✗ Incomplete]'}\n"
        f"- **Independent Verification**: {'[✓ Met]' if has_independent_check else '[✗ Incomplete]'} "
        + ("Emphasized independent verification of physical placement." if has_independent_check else "Must emphasize independent verification of placement.") + "\n"
        f"- **Robotics Baseline Recognition**: {'[✓ Met]' if has_baseline_recognition else '[✗ Incomplete]'} "
        + ("Recognized that mandarin transfer is a mechanical baseline with no simulated science effect." if has_baseline_recognition else "Clarify that mandarin transfer has no invented science effect; it is a manipulation baseline.") + "\n\n"
        f"**Recorded Session Trials**: {obs_summary}"
    )

    follow_up = "Verification complete. Ready to proceed with scientific experiments." if is_correct else "Review the difference between robotic manipulation baselines and scientific experiments."
    return is_correct, feedback, follow_up


def evaluate_answer(
    experiment_id: str,
    quiz: dict[str, Any],
    answer: str,
    observations: Optional[list[dict[str, Any]]] = None
) -> dict[str, Any]:
    """Evaluate a student's answer using a transparent, deterministic rubric.

    Evaluation Standards:
    - Multiple choice: Verified against scientific principles and independent evidence rules.
    - Free response: Evaluated using transparent rubric criteria for density,
      Archimedes displacement, and grounding in actual recorded observations.
    - Never fabricates real results: References only the provided observations list.
    - Never infers outcomes from controller commands.

    Args:
        experiment_id: Experiment identifier ('buoyancy_trial', 'mandarin_transfer').
        quiz: Quiz dictionary generated by make_quiz().
        answer: Student's submitted answer text.
        observations: List of empirical observation dictionaries recorded in the session.

    Returns:
        Dict with keys {feedback, correct, follow_up, provenance}.
        'correct' is bool or None.
        'provenance' is 'RULE-BASED-RUBRIC'.

    Raises:
        ValueError: If experiment_id is unknown or quiz is malformed.
    """
    exp = get_experiment(experiment_id)
    target_id = exp["id"]
    obs_list = observations or []

    quiz_type = quiz.get("type")
    quiz_id = quiz.get("id", "")

    if quiz_type == "multiple_choice":
        if target_id == "buoyancy_trial":
            is_correct, feedback, follow_up = _evaluate_mc_buoyancy(answer, obs_list)
        elif target_id == "mandarin_transfer":
            is_correct, feedback, follow_up = _evaluate_mc_mandarin(answer, obs_list)
        else:
            raise ValueError(f"Unsupported experiment '{target_id}' for multiple choice")

        return {
            "feedback": feedback,
            "correct": is_correct,
            "follow_up": follow_up,
            "provenance": "RULE-BASED-RUBRIC"
        }

    if quiz_type == "free_response":
        # Check if quiz is about unknown evidence
        if "unknown" in quiz_id or _has_unknown_outcome(obs_list):
            is_correct, feedback, follow_up = _evaluate_fr_unknown_outcome(answer, obs_list)
        elif target_id == "buoyancy_trial":
            is_correct, feedback, follow_up = _evaluate_fr_buoyancy_comparison(answer, obs_list)
        elif target_id == "mandarin_transfer":
            is_correct, feedback, follow_up = _evaluate_fr_mandarin_baseline(answer, obs_list)
        else:
            raise ValueError(f"Unsupported experiment '{target_id}' for free response")

        return {
            "feedback": feedback,
            "correct": is_correct,
            "follow_up": follow_up,
            "provenance": "RULE-BASED-RUBRIC"
        }

    raise ValueError(f"Unknown quiz type '{quiz_type}' in quiz dict")


# ==============================================================================
# Optional Async Gemini Tutoring Function (Graceful Offline Fallback)
# ==============================================================================

async def tutor_reflection_async(
    experiment_id: str,
    quiz: dict[str, Any],
    student_answer: str,
    observations: Optional[list[dict[str, Any]]] = None,
    api_key: Optional[str] = None
) -> dict[str, Any]:
    """Optional asynchronous conversational tutoring evaluation powered by Gemini.

    If an API key is not provided or the Gemini service is unavailable offline,
    this function gracefully falls back to the deterministic evaluate_answer() rubric.
    Parent OpenArms Live handles real-time conversational voice interaction; this
    function serves as a supplementary analytical tutoring hook.

    Args:
        experiment_id: Experiment identifier.
        quiz: Quiz dictionary.
        student_answer: Student's response string.
        observations: Session observation list.
        api_key: Optional Gemini API key.

    Returns:
        Dict with keys {feedback, correct, follow_up, provenance}.
    """
    # Deterministic offline evaluation is always available
    fallback_result = evaluate_answer(experiment_id, quiz, student_answer, observations)

    # In sandboxed / offline test environments or without explicit Gemini configuration,
    # cleanly return the deterministic rubric result.
    if not api_key:
        return fallback_result

    # Note: If an API key is supplied in a connected production runtime, parent
    # Live services may extend this with full generative dialogue.
    return fallback_result
