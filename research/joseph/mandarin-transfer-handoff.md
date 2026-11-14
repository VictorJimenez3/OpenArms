# Mandarin transfer demo

Updated November 14, 2026. Current scope: phone, intent-based planning, confirmation, logging, and a replaceable execution runner. Simulation is deferred.

## Run the demo

From the repository root:

```sh
./research/joseph/mandarin-verification/start-demo.sh
```

Requirements: macOS, Python 3.13 with `uv`, authenticated `agy`, local whisper.cpp and an English model. The launcher uses the already installed tools under `~/Library/Caches/OpenArms/voice-bridge/`. Other machines can set `OPENARMS_WHISPER_CLI` and `OPENARMS_WHISPER_MODEL` to their absolute paths. Install the iPhone app using the [iOS setup](iphone-voice-bridge/ios/README.md).

On the phone, set the connection URL printed by the launcher. On Joseph's Mac it is `ws://MacBook-Air-4.local:8765/voice`. Start a session and allow Microphone and Local Network access. Speak naturally, for example: "Could you take that little orange from station A over to B?" AGY interprets intent and calls the real local MCP `submit_plan` tool. Review the mandarin A-to-B proposal, then say `confirm` or `cancel`. No exact movement sentence is required.

The default runner is mocked. Confirmation reports a simulated placement at B; cancellation keeps it at A. A new request clears the old proposal. Repeated or stale confirmation does not execute twice. Start a new session after resetting the mock mandarin for another completed trial.

## What is verified

- Personal Team signed build succeeded and the app installed on the physical iPhone 15 Plus. The user trusted its profile; command-line launch subsequently succeeded.
- A live phone session delivered microphone speech to Whisper and acknowledged playback of generated replies. The first live request exposed an overly strict wording gate; that gate was removed. A complete physical-phone run through the final intent-based adapter still needs a human check.
- Generated speech describing a "little orange" reached actual Whisper, AGY Gemini Flash High, and an actual MCP tool call. Confirm and cancel rehearsals completed with matching plan IDs. This is synthetic loopback evidence, not a physical movement claim.
- An actual unsupported A-to-C request returned no plan.
- Relay tests cover plan identity, cancellation, duplicate confirmation, operator rejection, mismatched runner results, transport behavior, and timeout/cancellation cleanup. iOS portable checks pass; the signed device build was separately verified.
- Raw audio retention is enabled by default in the demo launcher and was checked by writing student/reply WAVs. Earlier live-phone audio was not retained because recording was off then.

Local raw evidence: `.openarms/runs/mandarin-20261114/`. Runtime logs: `~/Library/Logs/OpenArmsVoiceRelay/`. These local artifacts are not committed. See [verification notes](mandarin-verification/README.md).

## Logging

Each `s-<uuid>/` contains `events.jsonl` and `<turn_id>-student.wav` / `<turn_id>-relay.wav`. Logs connect session, turn, and plan IDs with transcription, planning latency, proposal, confirmation, cancellation/invalidation, runner results, playback acknowledgements, mute, disconnect, and errors. WAVs retain endpointed microphone turns and synthesized replies, not continuous room recording or muted audio. `agent/mandarin_plan_*/` holds the real MCP trace and authoritative plan. Files remain on the Mac; the phone displays audio logging status.

## Next steps

1. Teammate pushes the robotics implementation. Connect its zero-argument runner factory with `--runner module:create_runner`; follow [the runner contract](../../docs/INTERFACES.md#robotics-runner-handoff). Default execution remains mocked until this explicit selection.
2. Have the runner obtain operator approval for the exact plan ID, validate the local station/motion configuration, execute once, stop on cancellation, and report status plus observed placement. Do not infer placement from command completion.
3. Run the runner contract tests against that adapter, then one complete phone-to-physical trial. Check cancel, rejected operator approval, and stop behavior before the demo.
4. Record actual placement, failures, latency, and whether the operator had to intervene. Only then describe physical execution as verified.
5. Revisit the simulator and broader [research to-do](TODO.md) after the command-to-robot test works.

## Human to-do

- [ ] On the phone, run one fresh natural-language request, confirm, hear the result, then test cancel in a new session. Toggle mute and End/Start once. Keep the Mac and phone on a reachable trusted network.
- [ ] Check the new session folder for the student WAV, reply WAVs, and matching plan/result IDs. Listen to the retained student clip to assess microphone quality.
- [ ] With the robotics teammate, connect the SO-101 and verify its calibration, taught grasp/lift/place/retreat, local limits, and physical stop. No arm was connected in this software session.
- [ ] Mark A/B with the actual mandarin; record the fixed origin, coordinate frame, units, and measured positions for the physical routine. No invented coordinates or 3D scan is needed for the current test.
- [ ] Authorize and observe the first complete voice-to-physical transfer; record where the mandarin actually lands.
