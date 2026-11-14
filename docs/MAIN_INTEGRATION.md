# Consolidation into one stable main

Integrator: this overhaul lane. Tracking: [#19](https://github.com/VictorJimenez3/OpenArms/issues/19), [#10](https://github.com/VictorJimenez3/OpenArms/issues/10), [#9](https://github.com/VictorJimenez3/OpenArms/issues/9), device acceptance [#4](https://github.com/VictorJimenez3/OpenArms/issues/4).

## Baseline and merge policy

Remote main was `171a21a393a12e37a2ad5e3e075ce5949b262bd4` when this consolidation began. Keep it as the rollback point. `codex/ph-agent-overhaul` is the sole integration branch; the app continues to use one session service and Codex gpt-6.1-sol medium for the expert. Joseph has withdrawn Gemini; default voice is disabled pending replacement. The chosen application simulator is the newer MuJoCo metered-dropper pH apparatus. Isaac and the other laboratory videos remain separate research/demonstration tools. Only pH is exposed as a student experiment.

Merge useful work, reconcile overlapping implementations, and record superseded branches rather than restore old dispatchers or lesson defaults. Git ancestry and patch-equivalence checks distinguish already incorporated worker changes from genuinely missing work. Keep active worktrees intact; remove branches only after their disposition is verified on main. No force-push or blanket branch deletion.

Every merge below is local until independent review and the combined checks pass. A merge into this integration branch is not a claim that main was updated or that physical/device acceptance passed.

## Integration order and branch disposition

| Lane / PR / pinned head | Disposition and dependency | Acceptance / remaining gap |
| --- | --- | --- |
| Current overhaul, `f2fc7ad` at audit start | Integration base; R1–R6, D2–D4 software. Existing browser/native/runtime worker commits are incorporated by reviewed cherry-picks. | Full loop passes on the new MuJoCo apparatus; final repairs, audible rehearsal, and current-build evidence still required. |
| Four MuJoCo labs, #16, `16a975e`; `visual/accessible-lab`, `codex/four-mujoco-labs`, four experiment branches | Merge full parent branch. Exact `simulation/lab_demos` sources were already imported; retain research gallery/assets and ancestry. The app uses its pH adapter, not four additional student experiments. | Run simulation and experiment suites; preserve analytical-model/geometric-action limitations and action-disabled controls. |
| Isaac, #17, `783725b`; kinematics branch | Merge isolated simulation/research tools and evidence; no app backend switch. D3 reusable simulation research. | Check pure interfaces/evaluator tests and archived execution receipts. No fresh GPU or physical result claimed. |
| Cup fixture, #21, `3919181` | Merge static mechanical artifact. No hardware activation. | Validate retained mesh receipt and exports; physical fit/reach remain unverified. |
| Product/workflow docs, #20 `cc6cff5`, #14 `9c49f77`, #1 `c1c0db4`, #6 `6cb44cf` | Reconcile history into one current architecture and ownership contract. Preserve D1–D4 physical product objective and R1–R6 software delivery, optional prediction/reflection, one runtime. | Documentation must distinguish target, implemented, demonstrated, and blocked. Remove old mandarin student-demo/default and obsolete relay instructions from current entrypoints. |
| iPhone prototype, #5 `2709976`, voice-ios/voice-relay branches | Preserve useful research and history; retain current shared-session app and newer relay files on overlapping paths. | Current Swift checks/build and common session acceptance. Actual unplugged phone remains a separate unmet gate. |
| Bench capture/models/skills, `87c9476`, `f5ed1f6`, `e3cb425` | All unique commits verified patch-equivalent in integration; record ancestry after verification. Bench vision already ancestor of main. | Existing perception/evidence tests; no new physical claim. |
| Old skill harness `6d3fbc7` | Inspect useful unique work; reconcile or mark explicitly superseded by the sole current task/registry/evaluator path. Do not introduce a second active dispatcher. | Independent audit maps any retained gaps before disposition is final. |
| Old free-plans `c305f27` | Preserve useful generic simulation preview changes after review; supersede app regex dispatcher with camera-aware expert and deterministic validation. | Regression checks for affected preview behavior; no unvalidated direct motion path. |
| `duc` `bc33e99` | Merge-only history with empty three-dot content diff from main; no application changes to restore. | Verify ancestry/content. |
| Voice repair worker, `57b0a6a` | Completed and integrated. R1/R4 consent and feedback. Provider-independent controls are retained; Gemini transport is disabled pending replacement. | Historical provider tests cannot qualify replacement voice. |
| Task/evidence repair worker, `0aa2741` | Completed and integrated. R2–R6. | Immutable baseline, preflight, cancellation of promotion, registry routing, frame identity/freshness checked. |
| User-owned design chat, `76bf691` | Paused with clean worktree and no additional design commit. Existing simplified browser/native UI is already integrated. R1/R3/R4/R5 presentation. | Browser checks, screenshots, portable Swift tests and signed Simulator build passed. Actual phone remains unverified. |
| Other remote/local branches already ancestors of main or reviewed integration commits | Account for them in the final generated ref ledger. Archive only finished owned worktrees after main verification. | No unique patch may be silently dropped. |

## Release sequence

1. Finish this inventory, integrate isolated assets/research, reconcile shared documentation, and retain branch-specific merge receipts.
2. Integrate voice/task fixes and design handoff. Fix review findings; rerun relevant checks on their combined result.
3. Run the complete natural request → real expert/image tools → exact proposal/confirmation → new MuJoCo execution → independent pixel observation → spoken result → registration/reuse → evaluated improvement. Preserve failed attempts and actual provider/scene hashes.
4. Review the final combined diff against R1–R6 and D1–D4. Record scope, dependencies, evidence, and gaps in the integration PR before any push.
5. Move main through one reviewed integration PR, verify the remote commit and a clean checkout, then close/resolve the old PRs and archive finished branches/worktrees. Keep the rollback commit and an evidence index.

## Current release blockers

- Gemini was explicitly withdrawn. Its default application path is disabled even if old credentials remain. Replacement voice is not implemented/qualified; no OpenAI voice API key is configured. Preserve the Codex expert and common session instead of introducing another runtime.
- Joseph explicitly removed the device/voice rehearsal merge gate on November 14: merge the reviewed software baseline now and finish those checks later. The unplugged physical iPhone remains unavailable, and replacement voice remains unfinished. This authorization permits consolidation; it does not establish voice or device acceptance.
- Remote main advanced from `171a21a` to `19a37ae`. Its added `0b90e36` Claude fallback has been independently reviewed and reconciled into integration history. The current expert covers its useful planning behaviors; the older physical/free-plan dispatcher is superseded, not reactivated.
- No physical pH actuation or physical reset is enabled or newly verified. The broader product's D1 milestone remains open.

## Current evidence

Before the provider withdrawal guard, the combined suite passed 464 tests; desktop/mobile browser checks passed 36, audio checks passed 5, and portable native checks passed 17. A signed iOS Simulator build and fresh screenshots passed. The guard plus leading-decimal routing correction passed 13 focused tests, then 466 combined tests. The initial combined attempt found an unavailable-status protocol mismatch; the guard now emits the clients’ existing unavailable status, and the unchanged integration test passes. These are software evidence, not actual-phone acceptance.

The actual Codex expert completed an updated-apparatus cold/warm simulation run (7 cold calls, 0 warm). A later actual-provider voice run reached observed simulated output; the extended registration/reuse voice rehearsal was interrupted at Joseph's instruction to stop Gemini and is not a completed acceptance trace. The latest actual-Codex improvement retained an unchanged baseline and promoted a secondary-view recovery change: 9 to 12 recovered outcomes across 24 frozen SYNTHETIC cases, with all routing/observation/consent/STOP gates passing. No physical qualification is claimed.

The [software evidence index](../research/joseph/software-consolidation-2026-11-14/README.md) retains measured receipts and limitations.

This document is an execution ledger; statuses are updated as merges and verification complete.

### Phone prototype reconciliation

The original phone/relay branch paths are retained in their newer form. Its one absent file, `ios/Checks/CoreChecks.swift`, targets the obsolete `/voice` state protocol and is superseded by the current streaming XCTest suite invoked by `Checks/check.sh`. It is retained in Git history, not restored as an invalid current test. This history merge does not replace the shared-session client.

### Independent branch audit

A separate Account 2 audit reviewed pinned MuJoCo, Isaac, fixture, legacy harness and free-plan branches. The audit verified 12 MuJoCo demo tests, 42 Isaac checks (two optional OpenUSD modules could not import), 47 historical harness tests, the Isaac archive/video hashes and raw simulated force receipts, and four fixture meshes. It found two generic-preview input regressions to repair before inclusion. It rejected activating the old independent skill harness, whose own registry/promotion path does not meet the current contract. Its source will remain inspectable as an archived patch and merged Git history. No new GPU, provider or physical run was performed by that audit.

### Generic preview reconciliation

The `stefanie/free-plans` branch contributes numeric holds, labels, explicit expected endpoints and cache identity to the reusable simulation preview. Integration rejects non-finite, negative, boolean or greater-than-60-second holds and preserves the original first-target gripper fallback. The fixed-pattern application dispatcher, old physical wiring and its tests are superseded; their original source remains in merged Git history. Labeled previews need an explicit expected endpoint to establish simulated delivery.

### Complete ref accounting

The [branch ledger](MAIN_BRANCH_LEDGER.md) accounts for every known local and remote head. Eleven earlier worker/merge branches had no unique patches by `git cherry` and were joined without changing the current tree. The kinematics branch’s unmatched duplicate teardown commit was reviewed directly: its cleanup file is identical and the newer smoke code preserves the diagnostic while adding mass conditions and gravity. Its history is now included too. All eight previously listed PR heads are ancestors of the integration branch. No active worktree or remote branch has been removed.
