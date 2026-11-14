# Demo verification

Run from the repository root with the relay already running:

```sh
cd research/joseph/iphone-voice-bridge/relay
uv run --locked python -m unittest discover -s tests -v
bash ../ios/Checks/check.sh
uv run --locked python ../../mandarin-verification/voice_rehearsal.py \
  --relay-dir "$PWD" --output /tmp/openarms-rehearsal.json \
  --command 'Could you take that little orange from station A over to station B for me please?'
```

The rehearsal generates speech, sends real PCM through WebSocket/VAD/Whisper/AGY/MCP, confirms one plan, cancels another, and checks mute/reconnect. It validates reply WAVs and simulates the playback acknowledgement; it does not test phone speaker audibility or physical movement.

November 14 results: 31 Python tests and 100 iOS portable checks passed. Personal Team device build/install/launch succeeded. Actual intent-based synthetic voice confirm/cancel and unsupported-destination checks passed. Audio-retention smoke wrote one student WAV and two reply WAVs. The final live rerun also verifies structured planning/execution log events and retained WAVs.

Raw local evidence is under `.openarms/runs/mandarin-20261114/` from the repository root. Runtime sessions and actual MCP traces are under `~/Library/Logs/OpenArmsVoiceRelay/`. These are local evidence paths, not files bundled in the repository. Follow the [human to-do](../mandarin-transfer-handoff.md#human-to-do) for remaining physical-phone and bench checks.
