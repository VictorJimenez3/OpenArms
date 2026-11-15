# Harness Improvement Loop: Live Progress

Updated: 2026-11-15, checkpoint 1. This is an interim result, not product or physical acceptance.

## Best Measured Combination

**Requested Sol medium + opt-in guarded pre-action checkpoint**, on the simulated demo bench.

| Live cold end-to-end case | Baseline medium | Medium + guard | Repetitions per arm |
| --- | ---: | ---: | ---: |
| Familiar request: confirmation to controller progress | 16.12 s | 1.68 s | 2 |
| Familiar request: request to independent observation | 73.18 s | 53.26 s | 2 |
| Familiar request: request to student-facing answer | 80.98 s | 65.08 s | 2 |
| Unseen wording: confirmation to controller progress | 12.89 s | 1.69 s | 2 |
| Unseen wording: request to independent observation | 73.07 s | 57.30 s | 2 |
| Unseen wording: request to student-facing answer | 80.82 s | 66.54 s | 2 |

All four live candidate actions passed exact-consent checks, dispatched once, produced a fresh independently observed result, and retained post-action expert feedback. The guarded checkpoint actually activated once per action.

These are measured wall-clock medians, not projected service-tier speedups. The student approval is scripted, not a measured human approval delay. Requested model is `gpt-6.1-sol`; actual model identity is not reported/verified by the provider.

## Current Goal And Bottleneck

Victor's next target: **about 30 s request-to-answer with high success**, without weakening exact consent, STOP, single dispatch or independent verification.

The target is **not achieved**. On unseen wording, the guarded candidate still spends about 48.22 s median reaching a proposal, 57.30 s reaching independent observation, and 66.54 s reaching the answer. Cold planning and remaining model turns are now the main opportunity; removing the already-small 1.69 s pre-motion interval alone cannot reach 30 s.

Next bounded measurements: try low effort combined with the guard, then choose a planning-turn/model candidate from actual traces. **Low + guard has not yet been measured and is not the best-proven combination.** Any projected gain stays separate from measured results.

## Other Attempts And Checks

- Medium versus low effort, unchanged runtime/prompt/scene, two proposal-only requests repeated twice: both 4/4 correct; low improved the aggregate by only 1.09x and made unfamiliar supported wording about 16% slower. **Do not change the global default on that evidence.**
- Deterministic expert plus real simulator: development **76/76 baseline and 76/76 candidate**; four optimizer-held-out cases **32/32 each**. Zero correctness regressions. Deterministic timings do not establish a live-model speedup.
- Existing setup-scoped evaluator admitted the same frozen seed separately in baseline and guarded policy scopes. Warm tests copy that seed outside timed requests; this does not claim every live cold-authored skill was admitted.
- Initial instrumentation batch was 60/76 and is retained. Runner fixes corrected post-action occlusion injection, STOP reason capture and missing-donor detection; expected case behavior did not change.
- Baseline full suite: **686 passed**. Benchmark unit tests: **19 passed**. Candidate focused checks: **65 passed**. Candidate full suite is **still running at this checkpoint**; no pass is claimed yet.
- Independent built-in evidence review found no blocker to retaining the isolated opt-in. A real saved local reviewer, **`lucky-brook`**, independently reached the same conclusion and completed a follow-up.

## Revisions And Evidence

- Baseline: `47a00c1dcf95c8d0077a5007ff825b4c5de7737e`, requested branch tip of `victor/integration-device-expert`.
- Candidate: `0287c6e35f36c2f690ccbb6104bf146e1570aa61`, branch `victor/harness-checkpoint-pinned-47a00c1`, worktree `/Users/victor/OpenArms/harness-checkpoint-v2`.
- Candidate API: `Lab.guarded_demo_bench_checkpoint = True`; default remains false. The benchmark's `--guarded` records and separately qualifies its policy scope.
- Coordinator: branch `victor/harness-loop-pinned-47a00c1`, worktree `/Users/victor/OpenArms/harness-loop-v2`.
- Cases: `agentic/benchmarks/cases.jsonl`; protected scoring: `agentic/benchmarks/harness_grader.py`; coordinator-only held-out file: `.devin/harness-loop/heldout.jsonl`.
- Detailed comparisons: `outputs/live-effort-development-comparison.json`, `outputs/checkpoint-live-comparison.json`, `outputs/checkpoint-heldout-live-comparison.json`, `outputs/checkpoint-deterministic-comparison.json`, `outputs/checkpoint-heldout-comparison.json`.
- Each run preserves `protocol.json`, `summary.json`, `results.json`, artifact hashes, exact pre-consent/final state, monotonic events, expert calls/usage and simulator artifacts. Earlier failed runs and frozen runner snapshots are not overwritten.
- No default enablement, merge or push. Software/simulator evidence is not physical, chemistry, new-experiment transfer or D4 product acceptance.

## Run And Open The Reviewer

From the coordinator worktree, using the existing environment:

```bash
PYTHONPATH=agentic:. /Users/victor/OpenArms/device-expert-smoke/.venv-lab/bin/python agentic/scripts/harness_benchmark.py run --out outputs/harness-run-unique
```

This runs the real simulator with a deterministic test expert by default; live mode is explicit and consumes account usage. A fresh output directory is required.

```bash
python3 /Users/victor/.config/devin/skills/local-devin-sessions/scripts/local_sessions.py open worker-37e3af00af12
```

That worker owns read-only review, not simulator execution. Initial full-session launches were blocked on per-worktree trust; Victor approved the review worktree and exited the idle CLI. The real session ID, actual review and successful follow-up are now verified. New workers should use Victor's requested 6.1 Sol Fast once its exact CLI catalog identifier is verified; this reviewer was started before that request and used the existing default.
