# First speed task

Scope: D1/D2 first, then D3/D4 in [Architecture](ARCHITECTURE.md). Historical receipts inspected November 14, 2026; these are not fresh benchmarks or proof that active overhaul code still has the same defect.

| Evidence | Retained result | What it establishes |
| --- | --- | --- |
| `continuous-voice/continuous-voice.json` | Proposals 5.20/5.99 s; correction 5.79 s; confirmation failed at 55.61 s with pending proposal | Generated-speech test duration includes utterance playback; not pure reasoning or first-motion time |
| `text-live-final.json` | One text answer 11.93 s | One observation, no causal attribution |
| `expert-final.json` | Fixed recipe selection 0.935 s, 902 tokens | A constrained provider call, not general planning |
| `skill-evaluation.json` | Warm grammar mean 0.1175 ms / 7 cases; cold local composer 0.573 ms / zero calls | Router is already cheap; this pair cannot establish AI cold/warm savings |

Receipts are retained locally under the software-integration worktree's ignored `outputs/lab-evidence/`; they are not shipped by a fresh clone. No comparable physical first-motion/motor-duration traces were inspected. Do not claim motor speed or vision is the largest physical bottleneck from these data.

## Immediate assignment

Existing runtime/voice integrator, [issue #19](https://github.com/VictorJimenez3/OpenArms/issues/19): qualify completed confirmation -> exactly one executor dispatch, and timestamp through first motion while Gemini Live remains responsive. Preserve STOP, existing authorization, correction/staleness and the working fallback. Reuse the active overhaul repair rather than creating another runtime. Finish with actual-device and supervised physical evidence through [#12](https://github.com/VictorJimenez3/OpenArms/issues/12).

## Smallest P1 experiment

Compare familiar-request dispatch with and without unnecessary provider/setup work while preserving equivalent behavior and observation freshness. The historical `live.py:text_reply` implementation opened an AUDIO Live connection per typed question; this was a hypothesis, not a measured cause of 11.93 s. PR #25 now records three local status/scene replies at 1.49–1.65 ms with zero expert calls and preserved proposals; those are server timings, not speech latency or physical first motion. Inspect the current path before proposing another optimization. Known skills should avoid redundant expert calls without bypassing validation.

The old optional simulator-preview path is historical. The selected development backend runs MuJoCo only when explicitly configured. Familiar physical skills must not gain mandatory simulator previews or expert calls without a demonstrated need; do not claim a speedup by removing work the measured baseline did not perform.

Measure the same task/setup before and after, including failures, human waits, first motion and outcome. Select only a demonstrated improvement; never add artificial baseline work. If a larger measured bottleneck appears, change this one experiment rather than expand into a research program.
