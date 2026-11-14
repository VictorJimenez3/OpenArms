# Gemini Live conversation repair — November 14, 2026

D2 / R1,R4, [issue #10](https://github.com/VictorJimenez3/OpenArms/issues/10). This is a voice and student-turn change to the existing application runtime. It does not bring the separate two-vessel scene, camera-dispatch branch, evaluator, geometry, calibration, or trajectories into main. Victor was notified on issue #10; Joseph subsequently explicitly requested main merge.

## Behavior

Gemini Live remains the speech provider, independent of the expert profile. Questions and repeat requests preserve pending work. Completed explicit action requests enter the existing task loop; completed sample corrections and resets commit with their transcript, before a later confirmation can approve a superseded proposal. Exact proposal playback and fresh consent remain mandatory. Provider callbacks share a turn receipt rather than creating duplicate tasks.

The guide grounds progress in controller phases, distinguishes observation from controller completion, and preserves an already completed result on idle STOP. Common polite STOP phrases work through voice and text. STOP is applied before transcript/playback delivery, survives the silence-boundary timer, and invalidates delayed voice mutations. Paraphrased confirmation invitations cannot grant presentation; the gateway requests up to two exact rereads and otherwise exposes a recoverable error.

## Evidence

Product changes: `4a379b8`; bounded preview repair: `a52df7e` / `c925cd5`; audio-duration acknowledgment fix: `be0101e`. [Live receipts](live-runs.json) preserve failures and successes, transcript wording, provider metadata, and hashes of local full results. Earlier larger-integration water evidence is explicitly separate from this main change.

- Real Gemini `gemini-3.8-live` plus real Codex expert: a cold generated-speech run answered during planning, discussed the water control without replacing the proposal, cancelled vinegar on correction, presented a fresh water plan, accepted one confirmation, reported the independent synthetic purple observation, and handled idle STOP. The expert requested `gpt-6.1-sol` at high effort; CLI telemetry did not independently establish actual model identity. The two tasks used 6 and 6 expert calls respectively.
- The final dialogue run answered ambiguity, hardware provenance, quantity limits, and confirmation questions without starting a task. “Please stop now” and “Emergency stop” each generated accepted idle STOP events.
- Actual Gemini speech stopped a deliberately slowed mock controller (3-second phases) after its first reported phase. The receipt says `execution_stopped`; a follow-up explained cancellation. Speaking over a longer explanation interrupted playback, produced a short answer, and did not resume execution. This is mock-controller evidence, not a physical stop-time measurement.
- Three fixed status/scene questions previously took 13.2–41.9 seconds, consumed 1–3 expert calls and replaced the pending proposal. The candidate returned in 1.49–1.65 ms with zero expert calls and preserved it. These are local server reply timings, **not speech latency**, with only three examples. [Baseline](questions-baseline.json), [candidate](questions-candidate.json).

Retained failures include: generated “Stop” recognized as “Stap”; the previously unsupported polite STOP; a provider connection failure (1011 followed by a rejected resume); a requested test answered with an expected color instead of dispatch; and a warm proposal paraphrased instead of read exactly. Fixes and precise regression cases accompany this change. Do not represent failed attempts as successful acceptance.

The final `be0101e` live rerun passed the full conversation: the initial request reused the active skill with zero expert calls; its sample correction used seven expert calls, produced a new exact proposal, required fresh confirmation, completed, and preserved the result through idle STOP. The audio acknowledgment window now includes the actual generated duration plus the existing 15-second grace; proposal expiry is unchanged.

## Independent review and verification

The independent Sol high reviewer reproduced and checked correction/confirmation ordering, delayed transcript STOP, silence-timer STOP cancellation, stale voice mutations, full correction sample binding, reset recovery, cross-tool duplication, and bounded preview repair. No blocking findings remained. [Review receipt](review.json). The separate Account 2 audit hit its usage limit and is not counted as completed review.

The final check counts and latest warm live receipt are recorded in `verification.json`. Browser checks use fixture transports; generated audio and synthetic observations do not establish Mac speaker audibility, an unplugged iPhone, real-camera perception, or physical readiness. Gemini connection/recognition failures remain possible; the direct Stop control does not depend on speech recognition.

## Reproduce

Use the configured server and command in [the runbook](../../../docs/LAB_RUNBOOK.md#real-gemini-live-conversation-rehearsal). The script saves generated audio, replies, events, and `result.json` in a new local directory. Run the full Python suite and browser/audio checks documented there. Credentials remain in the local environment, never in this receipt.
