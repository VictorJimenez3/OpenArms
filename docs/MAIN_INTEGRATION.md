# Main and remaining work

The consolidation is **merged**: [PR #22](https://github.com/VictorJimenez3/OpenArms/pull/22), main commit `0ab58195781893594a8e8c2421f41facd713e962`. The earlier baseline `171a21a` remains in history. The old integration/worker branches are no longer the place to start work: branch from current main for a bounded task, review, integrate, then archive its worktree.

## Current direction

Joseph selected the Smartivity My First Science Kit and deferred activity selection. [Architecture](ARCHITECTURE.md#kit-scope-and-bench-handoff) owns the inventory and Victor's outstanding physical handoff. Simulation is an optional Devpost/presentation extra, outside the core architecture and acceptance requirements. The app still has one shared session, task loop, registry and deterministic execution boundary. Physical actuation is disabled; Gemini is withdrawn and replacement voice remains open.

Tracking: [#19](https://github.com/VictorJimenez3/OpenArms/issues/19) full system, [#9](https://github.com/VictorJimenez3/OpenArms/issues/9) interfaces, [#10](https://github.com/VictorJimenez3/OpenArms/issues/10) connected loop, [#4](https://github.com/VictorJimenez3/OpenArms/issues/4) actual iPhone acceptance. The user waived audible/device rehearsals as a merge gate; they remain unmet product acceptance checks.

## Branch and worktree disposition

[The historical ref ledger](MAIN_BRANCH_LEDGER.md) records the heads incorporated by PR #22. The cleanup verifies each local worktree against main, preserves ignored evidence in local checksum-verified archives, and removes completed clean checkouts. Main's local bench environment, credentials and rehearsal records are preserved. Shared branch deletion is restricted to unchanged, fully merged heads; no force-push or unique work deletion.

Two remote branches advanced after consolidation and are deliberately retained:

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

The kit/terminology cleanup passed 493 Python tests, 36 browser checks, and 17 portable Swift tests; a subsequent wording-only change passed the seven focused learning tests. No new test files were added. Account 2 independently reviewed the full rename diff, session-history guards and scope hashing. Its three documentation findings were resolved: the mandatory pH delivery tail was replaced, the old demo plan became current design notes, and the native guide now awaits replacement voice. This is software verification, not kit, hardware or live-voice acceptance.

Finished worktree contents were verified against merged main; ignored run evidence was archived locally and reopened for checksum comparison before removal. The main bench environment and local rehearsal records remain intact. New application setup uses `.venv-lab` so it does not overwrite the existing bench `.venv`.
