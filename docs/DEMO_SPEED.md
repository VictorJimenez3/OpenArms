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

Existing runtime/voice integrator, [issue #19](https://github.com/VictorJimenez3/OpenArms/issues/19): qualify completed confirmation -> exactly one executor dispatch, and timestamp through first motion while the replacement voice agent remains responsive. Preserve STOP, existing authorization, correction/staleness and the working fallback. Reuse the active overhaul repair rather than creating another runtime. Finish with actual-device and supervised physical evidence through [#12](https://github.com/VictorJimenez3/OpenArms/issues/12).

## Smallest P1 experiment

Compare familiar-request dispatch with and without unnecessary provider/setup work while preserving equivalent behavior and observation freshness. Current main `live.py:text_reply` opens an AUDIO Live connection for each typed question; that is a plausible setup overhead, not a proven cause of 11.93 s. Reusing the active session is a bounded candidate if current architecture permits. Known skills should avoid redundant expert calls without bypassing validation.

Optional simulator preview blocks proposal/confirmation when enabled and launches a rendering process. It is off by default. Keep it backstage unless needed for a verified control decision; do not claim a speedup by disabling something the baseline did not run.

Measure the same task/setup before and after, including failures, human waits, first motion and outcome. Select only a demonstrated improvement; never add artificial baseline work. If a larger measured bottleneck appears, change this one experiment rather than expand into a research program.
