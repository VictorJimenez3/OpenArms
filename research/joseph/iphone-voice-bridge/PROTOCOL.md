# Prototype WebSocket protocol

Connect to `ws://MAC-HOST.local:8765/voice` on a trusted local network. This transport carries test audio in plaintext. Use `ws://127.0.0.1:8765/voice` for loopback tests. Each connection creates a distinct session. Closing the connection ends it. After disconnect, the student starts a new session.

Text frames contain UTF-8 JSON objects. Binary frames are audio. The server sends events in order:

1. `{"type":"session","session_id":"s-...","mode":"mock","logging":true,"raw_audio":false}` after accepting a connection.
2. `{"type":"state","state":"processing"}` while preparing a reply, including the opening prompt. Any student transcript is sent as `{"type":"transcript","role":"student","turn_id":"t-...","text":"..."}`.
3. `{"type":"reply","turn_id":"t-...","text":"...","lab_stage":"prediction"}`, followed by exactly one binary frame containing a complete mono PCM WAV file. Optional `lab_stage` is descriptive and does not authorize any action. The app plays the WAV once and sends `{"type":"played","turn_id":"t-..."}` when playback finishes. A playback failure ends the session and is shown on the device.
4. `{"type":"state","state":"listening"}` after playback acknowledgement, provided the student is not muted. Repeat from step 2 for each utterance.
5. `{"type":"state","state":"muted"}` acknowledges mute. `{"type":"error","message":"...","fatal":false}` reports an error. Recoverable errors are followed by a state event. Fatal errors close the connection.

The app sends microphone frames only while listening. Each binary frame contains raw mono signed little-endian 16-bit PCM at 16,000 Hz (no header). Frames may vary in duration. The relay determines utterance boundaries from audio energy and silence. Use a FIFO for outgoing frames and controls. On mute, stop the input tap, discard queued microphone frames and send `{"type":"mute","muted":true}`. Send `{"type":"mute","muted":false}` when resuming. The relay discards a partial utterance on mute. A mute during playback affects the microphone only. Playback completion still requires its acknowledgement. `{"type":"end"}` ends a session. Closing the socket also ends the session.

The relay sends `{"type":"pong"}` in response to `{"type":"ping"}`. The app may use this to detect a dropped connection. Neither message changes conversation state.

The mock dialogue uses simulated results. A spoken confirmation is a conversational event. A future agent adapter must use the team's preview, approval and execution rules.
