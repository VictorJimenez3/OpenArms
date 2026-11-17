# OpenArms: the judging goal

> **Historical (HackPrinceton, November 2026).** This document is no longer maintained and may describe plans, scenes, owners or rules that no longer apply. [HANDOFF.md](../HANDOFF.md) is current. Where they differ, trust the code.

A student directs a real robot arm one supported action at a time through responsive conversation. The target is a visible physical action in the first minute, with honest progress, cancellation and an independently observed result. This timing and the physical demonstration are **targets, not achieved acceptance**. Prediction and reflection are optional.

## Decided experiment and remaining verification

Victor’s presentation plan is one live robot activity and several simulation examples. Aim to carry the same student interaction into an additional validated scene. Label standalone runs and asset previews according to what they show. [Project objective](../PROJECT_OBJECTIVE.md) · [Victor’s implementation handoff](../research/victor/student-and-agent-flow.md)

Use exactly **two active vessels**: a smaller moving donor at A and a stationary, preferably wider clear receiver at C. Pick up A, pour one premeasured portion into C, return the donor to A and finish at HOME. Fixed stations, taught trajectories and a retained supervised fallback are acceptable.

The preferred Smartivity My First Science Kit experiment is prepared magic-tea indicator plus citric-acid solution; fallback is a small contained citric-acid/baking-soda reaction. The kit manual has been reviewed in the [shared physical experiment page](https://app.notion.com/p/41871c9c107e816fab14f3549f6a8fd6); actual packet inventory, the two-vessel adaptation, preparation and visible response still need bench verification. This is a selected direction, not a validated recipe. Water is the calibration/integration medium. Food color is only a motion/visibility test; grape juice is not required. A second physical experiment is optional after this one works.

[Architecture](ARCHITECTURE.md) owns D1–D4 and the connected system; [wet-lab](WET_LAB.md) owns physical checks. MuJoCo is active for development and the two-vessel software slice. Isaac is parked with its useful source/evidence preserved. Simulation is not a compulsory preview or substitute for the physical student experience. Extra vessels or experiments in optional simulations do not change the physical scope.

## Current implementation boundary

The integrated local branch preserves main `4f9c3ec` / PR #25's real Gemini Live conversation repairs, following PR #22's shared runtime. Speech remains Gemini Live; Sol/Astra/Opus or an explicitly bound Fable expert use the existing Codex/Claude boundary independently. Fable has no inferred model binding. Browser/iPhone sessions share exact proposals, STOP, evidence and the notebook. The application still disables physical dispatch.

The current local integration adds a water-only two-vessel MuJoCo backend, fresh per-action camera validation, independent post-action pixels and replay-backed admission for warm skill reuse. Select `OPENARMS_EXECUTION=mujoco OPENARMS_SCENE=two_vessel`; the default `metered_dropper` remains the older indicator-pH regression. This is simulated water motion, not kit chemistry. [The integration ledger](MAIN_INTEGRATION.md) owns branch/commit/evidence status and pending full-suite/live acceptance. Photo-derived vessel models on main are estimates, not caliper measurements or verified fit. The active simulator still uses provisional 70/60 mm vessel heights and older dock geometry, not the latest vessel/CAD assets. Real-camera registration, physical water pour, chemistry, first-minute timing and unplugged-device acceptance remain open.

Start with [the runbook](LAB_RUNBOOK.md), [current tasks](../research/joseph/TODO.md), [interfaces](INTERFACES.md) and [delivery contract](FULL_SYSTEM_DELIVERY.md). Shared intent lives in the [OpenArms Notion hub](https://app.notion.com/p/41771c9c107e81ab8026cdafa6245063).
