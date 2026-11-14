# Mac mock voice relay

Local prototype for [issue #2](https://github.com/VictorJimenez3/OpenArms/issues/2), implementing [the shared protocol](../PROTOCOL.md). Uses real local speech recognition and Mac speech synthesis around a session-local, deterministic mock dialogue. No production agent, robot, serial, ROS, or hardware interface is imported or called.

## Run

Requirements: macOS, Python **3.13**, `uv`, an existing `whisper-cli` executable from whisper.cpp, and an explicitly selected local model. Parent/setup owner arranges those shared dependencies; this directory does not install system packages or download models. `say` and `afconvert` are macOS tools.

From this directory:

```sh
uv sync --python 3.13 --locked
uv run python relay.py \
  --whisper-cli /absolute/path/to/whisper-cli \
  --model /absolute/path/to/ggml-base.en.bin
```

`ggml-base.en.bin` is an example English model choice, not a bundled file or automatic fallback. Both paths are required and checked at startup. Recognition uses `-l en`; select an English-capable model. Optionally select an installed `say` voice with `--voice Samantha`.

Default URL: `ws://127.0.0.1:8765/voice`. For a phone on the same trusted LAN, explicitly add `--lan` (binds `0.0.0.0`) or `--host YOUR-MAC-LAN-IP`, then connect the phone to `ws://YOUR-MAC-LAN-IP:8765/voice`. This is unauthenticated plaintext prototype transport; do not expose it beyond the trusted test network. Ctrl-C/SIGTERM closes sessions and stops active speech subprocesses.

## Wire and audio behavior

- Each accepted `/voice` connection gets a new UUID session, new dialogue, and fresh UUIDs for every turn, including the opening prompt. Reconnecting never resumes old state.
- Input is mono signed little-endian PCM16 at 16,000 Hz. A WebSocket binary message must contain **1–3,200 complete samples** (2–6,400 bytes, at most 200 ms); split larger microphone buffers before sending. Transport messages over 6,400 bytes close with code 1009. JSON controls are limited to 2,048 characters.
- VAD analyzes fixed 20 ms windows independent of packet size. RMS threshold is 600/32768, pre-roll is 200 ms, minimum voiced duration is 120 ms, trailing silence is 600 ms, and utterance capture is capped at 15 seconds including pre-roll. The remainder of a packet after an endpoint is discarded. Continuous speech is cut at the cap. This simple energy VAD needs acoustic testing; it is not noise suppression.
- Each reply JSON is immediately followed by exactly one complete mono PCM16/16 kHz WAV binary message, at most 4 MiB. The client must send `played` with that reply's turn ID only when playback finishes. The default timeout is 45 seconds after sending the WAV; override with `--ack-timeout SECONDS`. Wrong, early, stale, and duplicate acknowledgements never unlock a pending reply.
- Mute clears partial microphone capture. It does **not** cancel recognition, TTS, dialogue processing, or playback. Internal phase and microphone mute are independent. Unmuting while processing or awaiting playback sends `processing`, never `listening`. A valid playback acknowledgement while muted sends `muted`; unmute then sends `listening`.
- The phone owns half-duplex echo avoidance: send microphone audio only in `listening`, discard queued microphone frames on mute, and stop capture before playing a reply. The relay also discards audio during processing, playback, and mute. There is no server echo cancellation or barge-in.
- JSON `ping` receives JSON `pong` without changing state, including during recognition/TTS/playback. WebSocket transport pings additionally run every 20 seconds with a 20 second timeout. The phone is responsible for its application heartbeat cadence and missing-pong deadline.
- Recognition and TTS run in separate asyncio tasks via cancellable subprocesses; controls remain responsive. Subprocesses have a 90 second deadline, the full processing pipeline defaults to 120 seconds (`--processing-timeout SECONDS`), and cancellation terminates then kills/reaps a stuck subprocess after 2 seconds. Disconnect/end/server shutdown cancels pending work, closes the adapter, clears buffered PCM, and closes logs. Normal cleanup deletes transient files; an ungraceful process kill may leave scratch files.
- Empty recognition produces a recoverable error followed by the current effective state. Adapter, recognition-command, or TTS failure is fatal because dialogue may already have advanced. The client should display the error and start a new session. Malformed small controls/audio and unexpected acknowledgements produce a recoverable error and state.

## Mock conversation and adapter

Opening asks for a prediction. A student response yields a concrete simulated preview and asks for `confirm` or `cancel`. Only exact normalized `confirm` / `I confirm` runs the simulation; `cancel` / `cancel simulation` cancels it. Case and terminal `. ! ?` are ignored. Negation, hedging, mixed intent, or other speech asks again. Even confirmation never moves hardware. The result prompts reflection; the reflection response invites a new prediction.

The async Mac-side boundary and worked example are in [ADAPTER.md](ADAPTER.md). It is a proposal for the absent real agent, not a shared production interface or permission to execute actions. Shared integration agreements belong in `docs/INTERFACES.md` after owner review; this worker changes only `relay/`.

## Logs and retained audio

Default root is `~/Library/Logs/OpenArmsVoiceRelay`, outside Git. Override with `--log-dir /absolute/path/outside/git`. Runtime CLI rejects paths inside Git working trees. Each session has `s-UUID/events.jsonl`: UTC ISO timestamps, session and turn IDs, connection/disconnect/error events, validated controls and state changes, actual student and relay transcripts, STT/TTS/total-reply/playback timings. Connection-level events have `turn_id: null`. Transcripts are private local records, not console output.

Directories are mode 0700; JSONL and retained WAVs are mode 0600. Symlink directory components are rejected. The CLI uses umask 0077. Raw retention is **off by default**, advertised in the session event. `--raw-audio` explicitly retains complete endpointed student utterances and generated relay replies as WAVs. It does not archive every microphone frame or muted/discarded audio. Speech tools need temporary private audio/text files under `scratch/` even with retention off; normal completion/cancellation removes them. Logs have no automatic retention or rotation: delete completed session directories when no longer needed. Do not commit them.

Tests use disposable, ignored `.local/` fixtures inside this directory and remove them. They intentionally call the internal server factory rather than the production log-location check.

## Verification

```sh
uv run python -m unittest discover -s tests -v
uv run python smoke_real.py --tts-only
uv run python smoke_real.py \
  --whisper-cli /absolute/path/to/whisper-cli \
  --model /absolute/path/to/ggml-base.en.bin
```

Integration tests use a stub recognizer and synthetic WAV synthesis over actual loopback WebSocket connections. They cover conversation/confirmation/cancellation, fresh sessions and turns, mute during processing/playback, partial capture discard, stale/duplicate acknowledgements, heartbeat responsiveness, acknowledgement timeout, disconnect cancellation, malformed input, transport size bounds, JSONL/permissions, raw opt-in, sample-duration VAD/pre-roll, and subprocess timeout/reaping.

`smoke_real.py` uses Mac `say`/`afconvert` to generate “Confirm.” and optionally passes it through the specified whisper.cpp/model. It removes its temporary test files. This verifies local tooling on synthetic audio, not phone microphone quality, acoustic echo behavior, physical robot capability, or real agent integration.

Implementation references: [websockets asyncio server API](https://websockets.readthedocs.io/en/15.0/reference/asyncio/server.html), [whisper.cpp CLI](https://github.com/ggml-org/whisper.cpp/tree/master/examples/cli), and local `afconvert -h` for PCM conversion flags. The dependency lock pins websockets 15.0.1.
