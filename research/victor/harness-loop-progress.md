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
- Baseline full suite: **686 passed**. Benchmark unit tests: **19 passed**. Candidate focused checks: **65 passed**. Candidate full suite completed after checkpoint 1: **747 passed, 11 existing warnings, 310.18 s**.
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

## Checkpoint 1 Verification Update

The candidate full suite completed with **747 passing tests**. The real saved reviewer completed both its initial review and follow-up; no blocker to the isolated opt-in was found. The coordinator still makes no default-enablement or physical-acceptance claim. The next latency experiment remains unmeasured.

## Checkpoint 2: Where The Remaining 66 s Goes (Measured Trace)

Unseen-wording live run with Sol medium + guard (`outputs/heldout-live-checkpoint/H01-end-to-end-cold-0`), monotonic event times from the request:

| Segment | Time | What happens |
| --- | ---: | --- |
| Planning call 1 | 1.1 to 7.5 s | Expert asks the host to localize vessels (one tool round trip) |
| Planning call 2 | 7.6 to 25.8 s | `validate_plan` **rejected**: expert repeated `preconditions/expected_state/outcome_checks` beside `skill_definition` ("A skill proposal cannot override its definition") |
| Planning calls 3 to 4 | 25.8 to 55.2 s | Corrected plan validated and returned |
| Consent to first motion | 55.2 to 56.9 s | Guarded checkpoint (was about 13 s before) |
| Simulated motion + controller | 56.9 to 63.8 s | One `add_sample(A,C,1)`, return, HOME |
| Independent observation | 63.8 to 64.4 s | Fresh pixel observation, all checks pass |
| Completion expert call | 64.4 to 74.3 s | One more model call before the student answer |

Across all 16 live cold traces, the duplicate-field rejection cost one extra model turn in 7. Every host tool round trip costs one full model call (about 6 to 18 s).

Parallel candidates now in flight (each opt-in, separate worktree, coordinator measures):

1. **Codex fast service tier** (`service_tier="priority"`, advertised by the CLI for gpt-6.1-sol as "2x speed, increased usage"; unsupported tiers produce an explicit omission warning, and none appeared). Interleaved standard/fast live runs on D01 and H01 are running now.
2. **Planning turns** (`TaskLoop.fast_planning_context`): host pre-localizes the fresh planning frame and accepts only exactly identical duplicated fields; conflicting fields still rejected. Local Devin worker, 6.1 Sol Medium Fast.
3. **Guarded completion** (`TaskLoop.guarded_demo_bench_completion`): skip only the final post-observation expert call when the independent observation and controller facts are clean; anything else escalates. Local Devin worker, 6.1 Sol Medium Fast.

**Projection, not a measurement:** removing the failed validation turn and the localization turn would leave roughly one planning call (about 15 to 20 s); skipping the clean completion call saves about 10 s; a working fast tier could roughly halve the remaining model time. Combined, that could plausibly land near 25 to 35 s request-to-answer. Only measured matched runs will be reported as results.

## Checkpoint 3: Fast-Tier Attempt Interrupted By Account Limit (00:34 EST)

Interleaved live runs, Sol medium + guard, D01 familiar request, cold end-to-end:

| Arm | Passed | Request to proposal | Request to answer | Model calls |
| --- | ---: | ---: | ---: | ---: |
| Standard tier, repeat 0 | yes | 38.8 s | 58.2 s | 4 |
| Standard tier, repeat 1 | yes | 61.8 s | 80.9 s | 5 |
| Fast tier (`priority`), repeat 0 | yes | 30.5 s | 46.3 s | 4 |
| Fast tier, repeat 1 | no: `quota` | n/a | n/a | 0 |

The local Codex account then returned: *"You've hit your usage limit ... try again at 3:08 AM."* The runner stopped each batch at the first dependency failure, used no fallback model, and dispatched nothing. The H01 standard/fast pair produced no model output. **The fast tier is inconclusive (one good sample) and is not reported as an improvement.** The fast tier advertises increased usage, which may have contributed to reaching the limit.

Live blockers right now:

- Codex/Sol: account usage limit until about 03:08 EST, unless more credits are added.
- Claude profiles (Opus/Sonnet): local Claude CLI says `OAuth session expired and could not be refreshed`. It needs Victor to log in again; credentials are never copied between tools.

Work that continues without live access: the two opt-in implementation workers (they run unit tests, not live models) and deterministic simulator correctness runs. When live access returns, the plan is matched, interleaved runs: guard alone vs guard + planning-turn change vs guard + guarded completion vs all three, then fast tier on the winner.
