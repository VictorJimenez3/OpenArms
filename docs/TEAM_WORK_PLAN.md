# OpenArms team work plan

Joseph's current focus is MuJoCo simulation, camera-aware agent updates, integration, documentation and coordination. Victor and Duc continue physical bring-up and their existing subsystem responsibilities. Stefanie's existing simulation work remains coordinated with her; this reconciliation does not reassign her files. [AGENTS](../AGENTS.md#ownership) owns edit boundaries and [current TODO](../research/joseph/TODO.md) owns task status.

The physical target is exactly two vessels: A donor → C receiver → donor A → HOME, using water for calibration and the selected Smartivity chemistry only after verification. The student directs individual actions, with optional prediction/reflection. First-minute physical action remains an acceptance target.

## Current working baseline

The local integration preserves main `4f9c3ec`, the shared task loop/registry and PR #25's actual Gemini Live conversation repairs. Speech stays Gemini Live, independently of Codex/Claude expert profiles. The water-only carried-donor backend, fresh camera dispatch checks and replay-backed admission are now locally integrated. The default `metered_dropper` retains the fixed-dispenser regression. Verified [reconciliation evidence](../research/joseph/reconciliation-2026-11-14/README.md) covers actual Gemini Live generated-audio water dialogue, real-Codex cold/admitted-warm reuse (7/0 calls) and independent simulated checks. The combined software run had 564 passes plus one rendering-poll timeout under concurrent load; the unchanged isolated case and 58 follow-up checks passed. [MAIN_INTEGRATION](MAIN_INTEGRATION.md) owns the detailed evidence boundaries. Physical dispatch and real-device acceptance remain separate.

## Handoffs and active writers

| Owner / lane | Current responsibility | Handoff |
| --- | --- | --- |
| **Victor** · D1–D3 / R2,R4,R5 · [#10](https://github.com/VictorJimenez3/OpenArms/issues/10), [#19](https://github.com/VictorJimenez3/OpenArms/issues/19) | Existing agentic owner and team integrator; coordinate his student-loop and physical work before changing shared runtime files. | Agreed request/event/observation contract; preserved working fallback and current branch context. |
| **Duc + physical team** · D1 / [#12](https://github.com/VictorJimenez3/OpenArms/issues/12) | Existing firmware, controls, calibration and physical bring-up. Their bench files and saved poses stay protected. | Actual vessel dimensions, fixture/setup identity, taught trajectory, dry/water evidence, spills/interventions, camera identities, chemistry verification and reset readiness. |
| **Joseph + authorized reconciliation coordinator** · D1–D4 / R1–R6 | Simulation/camera integration, provider/session preservation, documentation and cross-lane review. Explicitly authorized to integrate/push this reconciliation in coordination with existing owners. | A reviewed connected software slice, requirement/evidence ledger, matching repo/Notion tasks and remaining physical blockers. |
| **Stefanie** | Preserve her current simulation assets/calibration branch and coordinate any overlap with Joseph's simulation work. Existing unique changes need review, not silent merge or deletion. | Scene/source revision, assumptions and measured-versus-provisional geometry. |
| **Model two-vessel base plate** | Active owner of `firmware/fixtures/cup_dock/` and agreed measured-vessel assets. Reuse existing parametric CAD and produce two seats plus fiducial geometry/configuration. | Fixture `4b2e3df` is locally integrated and independently digitally rebuilt/reviewed, including ArUco decoding. Print fit and robot registration remain unverified. Simulator owner must consume its geometry next; no duplicate fixture writer. |
| **Build Smartivity volcano simulation** | Active simulation implementation owner. MuJoCo is active; optional simulation may contain more than two vessels. | Supported actions, deterministic reset, cameras, configuration/source identities, model limitations and run evidence. Physical scope remains two vessels. |
| **Improve harness self-improvement** | Independent evaluator/revision trials using the existing runtime seam. | Unchanged baseline, real limitation, candidate, same-case comparison, failures, retain/reject and rollback. Initial evaluator capability is not D4 completion. |

Joseph retains browser/iPhone ownership; coordinate scoped client changes. Current tasks belong in existing issues, not new parallel project specifications. See [#9](https://github.com/VictorJimenez3/OpenArms/issues/9) for shared interfaces and [#4](https://github.com/VictorJimenez3/OpenArms/issues/4) for actual iPhone acceptance.

## Integration order

1. Keep physical bring-up and independent software moving in parallel. Software uses versioned provisional vessel/fixture inputs until the physical team supplies measured replacements. Preserve the actual Gemini Live connection.
2. Verify the locally integrated two-vessel/camera slice; retain PR #25's newer speech fixes and preserve the original prototype's dirty files. Run student command → fresh scene → supported skill validation → MuJoCo execution → independent result → equivalent warm reuse. Record which backend and scene actually ran. The simulator owner must next replace provisional 70/60 mm vessels and old docks with the reviewed vessel/fixture geometry; do not create a competing scene writer.
3. Verify changed/missing/swapped/stale scene cases, exact proposal/consent, STOP during active work, delayed tool results and reconnect. Unreadable results remain UNKNOWN. Do not add mandatory simulator or expert round trips to the known-skill motor path.
4. Feed actual bench handoffs into the same semantic A→C skill and scene contract. Supervised physical action, chemistry, first-minute timing and unplugged-device evidence remain explicit acceptance gates. Software integration may proceed without claiming them.
