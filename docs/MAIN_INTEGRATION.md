# Consolidation into one stable main

Integrator: this overhaul lane. Tracking: [#19](https://github.com/VictorJimenez3/OpenArms/issues/19), [#10](https://github.com/VictorJimenez3/OpenArms/issues/10), [#9](https://github.com/VictorJimenez3/OpenArms/issues/9), device acceptance [#4](https://github.com/VictorJimenez3/OpenArms/issues/4).

## Baseline and merge policy

Remote main was `171a21a393a12e37a2ad5e3e075ce5949b262bd4` when this consolidation began. Keep it as the rollback point. `codex/ph-agent-overhaul` is the sole integration branch; the app continues to use one session service, Gemini Live for conversation, and Codex gpt-6.1-sol medium for the expert. The chosen application simulator is the newer MuJoCo metered-dropper pH apparatus. Isaac and the other laboratory videos remain separate research/demonstration tools. Only pH is exposed as a student experiment.

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
| Voice repair worker | Sole owner of live bridge/voice controls and targeted tests; integrate after handoff. R1/R4 consent and feedback. | Resume/progress/outcome delivery, one mutation per student turn, interrupted playback rejection. |
| Task/evidence repair worker | Sole owner of task loop, skill validation and new evidence tests; integrate after handoff. R2–R6. | Immutable improvement baseline, final-plan preflight, frame identity/freshness. |
| User-owned design chat | Sole owner of browser/native design; integrate final committed handoff. R1/R3/R4/R5 presentation. | Computer-use screenshots, browser tests, Swift build; preserve audio/session/STOP. |
| Other remote/local branches already ancestors of main or reviewed integration commits | Account for them in the final generated ref ledger. Archive only finished owned worktrees after main verification. | No unique patch may be silently dropped. |

## Release sequence

1. Finish this inventory, integrate isolated assets/research, reconcile shared documentation, and retain branch-specific merge receipts.
2. Integrate voice/task fixes and design handoff. Fix review findings; rerun relevant checks on their combined result.
3. Run the complete natural request → real expert/image tools → exact proposal/confirmation → new MuJoCo execution → independent pixel observation → Gemini result → registration/reuse → evaluated improvement. Preserve failed attempts and actual provider/scene hashes.
4. Review the final combined diff against R1–R6 and D1–D4. Record scope, dependencies, evidence, and gaps in the integration PR before any push.
5. Move main through one reviewed integration PR, verify the remote commit and a clean checkout, then close/resolve the old PRs and archive finished branches/worktrees. Keep the rollback commit and an evidence index.

## Current release blockers

- Voice/task review repairs and user-directed design handoff are still active.
- The newest apparatus has a successful actual-Codex cold/warm software run; the final combined build still needs its audible Gemini rehearsal and evaluated improvement receipts.
- The physical iPhone is unavailable to this Mac. Simulator builds and generated audible desktop speech do not satisfy the previously requested actual unplugged iPhone acceptance. This gate must be fulfilled or explicitly changed before declaring that acceptance complete.
- No physical pH actuation or physical reset is enabled or newly verified by this software consolidation. The broader product's D1 physical milestone remains open.

This document is an execution ledger; statuses are updated as merges and verification complete.

### Phone prototype reconciliation

The original phone/relay branch paths are retained in their newer form. Its one absent file, `ios/Checks/CoreChecks.swift`, targets the obsolete `/voice` state protocol and is superseded by the current streaming XCTest suite invoked by `Checks/check.sh`. It is retained in Git history, not restored as an invalid current test. This history merge does not replace the shared-session client.

### Independent branch audit

A separate Account 2 audit reviewed pinned MuJoCo, Isaac, fixture, legacy harness and free-plan branches. The audit verified 12 MuJoCo demo tests, 42 Isaac checks (two optional OpenUSD modules could not import), 47 historical harness tests, the Isaac archive/video hashes and raw simulated force receipts, and four fixture meshes. It found two generic-preview input regressions to repair before inclusion. It rejected activating the old independent skill harness, whose own registry/promotion path does not meet the current contract. Its source will remain inspectable as an archived patch and merged Git history. No new GPU, provider or physical run was performed by that audit.
