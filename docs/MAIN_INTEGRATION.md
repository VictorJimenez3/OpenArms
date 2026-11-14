# Main and remaining work

The consolidation is **merged**: [PR #22](https://github.com/VictorJimenez3/OpenArms/pull/22), main commit `0ab58195781893594a8e8c2421f41facd713e962`. The earlier baseline `171a21a` remains in history. The old integration/worker branches are no longer the place to start work: branch from current main for a bounded task, review, integrate, then archive its worktree.

## Current direction and audited baseline

Current reviewed main is **`4f9c3ec`**, [PR #25](https://github.com/VictorJimenez3/OpenArms/pull/25), following PR #22 and photo-derived vessel models in PR #23 and v2 refinement in PR #24 (`e3ede414`). The active physical target is the **two-vessel A→C pour**, donor return and HOME, with preferred Smartivity indicator chemistry and fallback fizz pending actual preparation/outcome verification. MuJoCo is active development; Isaac is parked. First-minute physical action remains a target. [PROJECT](PROJECT.md) owns scope and [current TODO](../research/joseph/TODO.md) owns next work.

Gemini Live speech is preserved; Joseph withdrew only Gemini thinking. Expert profiles remain independent, with Fable requiring an explicit actual-model binding. The application preserves one shared session/task loop/registry and disables physical dispatch. The user waived audible/device rehearsals as a software merge gate; those remain unmet product acceptance checks.

| State at reconciliation audit | Evidence / limitation |
| --- | --- |
| Merged and software-tested: PR #25 conversation | 529 Python, 36 browser and 5 audio checks; actual Gemini Live generated-speech cold/warm, correction, exact consent, mock STOP and barge-in receipts. Mac human audibility and unplugged iPhone remain unverified. |
| Merged: PR #23 / PR #24 vessel models | Original photo-derived donor/receiver v2 geometry. Estimates, not manufacturer identification, caliper measurement, printed fit or physical qualification. |
| Main regression backend | `indicator_ph` fixed-dispenser scene; supports synthetic/MuJoCo software evidence, not the selected carried-donor physical kit workflow. |
| Separate unmerged prototype | `codex/openarms-conversation-integration` at `f1cf4fd` contains two-vessel/camera/runtime work. Review/port only the needed slice onto current main; preserve newer PR #25 voice fixes and dirty documentation. |
| Separate evaluator lane | `codex/openarms-harness-improvement` at `3f47ada` adds initial capability. It does not establish D4 or a measured improvement without completed comparative trials. |
| Active independent lanes | Model two-vessel base plate owns fixture/assets; Build Smartivity volcano simulation owns its scene; Improve harness self-improvement owns its trials. Coordinate them instead of creating duplicate writers. |
| Physical acceptance | Actual fixture fit/registration, repeated water pour, chemistry adaptation/outcome, first-minute action and real-camera/device qualification remain open. |

This is an audit snapshot, not a claim that separate work has since merged. Update this table with the resulting commits and reviewed checks when integration lands. Preserve original receipts and their provenance.

Tracking: [#19](https://github.com/VictorJimenez3/OpenArms/issues/19) full system, [#9](https://github.com/VictorJimenez3/OpenArms/issues/9) interfaces, [#10](https://github.com/VictorJimenez3/OpenArms/issues/10) connected loop, [#12](https://github.com/VictorJimenez3/OpenArms/issues/12) physical work, [#4](https://github.com/VictorJimenez3/OpenArms/issues/4) actual iPhone acceptance. Joseph authorized the existing coordinator to review, integrate and push this reconciliation; coordinate Victor's existing integration ownership and preserve teammate changes.

## Historical PR #22 branch and worktree disposition

[The historical ref ledger](MAIN_BRANCH_LEDGER.md) records the heads incorporated by PR #22. The cleanup verifies each local worktree against main, preserves ignored evidence in local checksum-verified archives, and removes completed clean checkouts. Main's local bench environment, credentials and rehearsal records are preserved. Shared branch deletion is restricted to unchanged, fully merged heads; no force-push or unique work deletion.

At the earlier consolidation audit, two remote branches had advanced and were retained. Re-fetch and inspect their current state before using or changing them:

| Branch / audited head | Disposition |
| --- | --- |
| `duc` / `21cf9fa` | Two new merge commits; their complete trees equal already incorporated main commits. No unique source changes. Preserve the teammate's current branch. |
| `stefanie/joint-map` / `dc3fd3e` | Unique calibration and kit-preview work across 11 files. Not integrated or deleted. It expands a physical-policy allowlist and marks a partial joint fit as measured; review those semantics before integration. No activity or hardware approval is implied by the kit choice. |

## Evidence

The [committed evidence index](../research/joseph/software-consolidation-2026-11-14/README.md) retains original receipts and source revisions. The reviewed consolidation passed 493 Python tests, 36 browser checks, 5 audio checks, 17 portable Swift tests and a signed iOS Simulator build. The actual Sol image/tool smoke passed, but CLI telemetry did not independently verify the model identity. Live Claude/Fable qualification remains open.

Historical optional-simulation evidence includes a Codex cold/warm run with 7/0 expert calls, and an unchanged-baseline synthetic improvement recovering 9/24 to 12/24 outcomes. Those are bounded software results, not kit or physical qualification. The extended historical voice rehearsal was interrupted at Joseph's instruction to stop Gemini; it is not completed acceptance.

The cleanup changes active indicator names and identifiers without rewriting historical exports, raw research or evaluation receipts. Earlier sessions remain read-only; changed simulator scope requires fresh skill admission if that optional tool is used. The kit is not implemented by renaming an old experiment. Current acceptance gaps are in the architecture and [R1–R6 contract](FULL_SYSTEM_DELIVERY.md).

## Before the next push

Record D1–D4 / R1–R6 requirements, changed files, dependencies, evidence, remaining gaps and an independent reviewer for substantial work. Preserve exact proposal/confirmation, STOP and independent observation. Passing component tests does not establish a working voice, kit or physical demo. Re-fetch main and merge reviewed changes without overwriting teammate work.

## Cleanup review

The kit/terminology cleanup passed 493 Python tests, 36 browser checks, and 17 portable Swift tests; a subsequent wording-only change passed the seven focused learning tests. No new test files were added. Account 2 independently reviewed the full rename diff, session-history guards and scope hashing. Its three documentation findings were resolved: the mandatory pH delivery tail was replaced, the old demo plan became current design notes, and the native guide then awaited a provider decision. The later Gemini Live correction and PR #25 supersede that historical voice state. This is software verification, not kit, hardware or live-voice acceptance.

Finished worktree contents were verified against merged main; ignored run evidence was archived locally and reopened for checksum comparison before removal. The main bench environment and local rehearsal records remain intact. New application setup uses `.venv-lab` so it does not overwrite the existing bench `.venv`.


## Gemini Live conversation repair

Joseph retained Gemini Live speech and explicitly requested this reviewed conversation merge after coordination with Victor on issue #10. The [November 14 voice receipt](../research/joseph/gemini-conversation-2026-11-14/README.md) records real-provider cold/warm conversations, corrections, exact consent, observation, active mock STOP and barge-in;529 Python,36 browser and5 audio tests passed. Failed attempts and independent review are retained. This delivery does not merge the separate two-vessel/camera/evaluator work or qualify physical/device operation.
