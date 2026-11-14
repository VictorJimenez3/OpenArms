# OpenArms iPhone client

The iOS 17+ SwiftUI app connects to the OpenArms lab gateway. When setting up a phone, open **Settings**, enter the gateway's trusted HTTPS origin and its pairing code if required, then tap **Connect to lab**. The app restores the private session from Keychain on later launches. Debug builds can opt into local HTTP for trusted development hosts. USB debugging does not provide a route to the lab gateway.

The main screen shows the lab camera, the current connection and task or audio status, and a **Talk** button. **Talk** requests the server’s voice connection after microphone permission. The server uses Gemini Live when locally configured; if voice is unavailable, text remains connected. **End voice** ends audio while keeping the session connected. **Stop** remains available during scrolling and in all sheets. It ends local voice and sends a direct stop request to the gateway whenever a session grant is available.

**Type instead** opens a request composer that uses the same session. **History** contains transcripts, task progress, execution receipts, independent observations, and published skill and evaluation records when supplied by the gateway. The retained optional simulation exposes its prepared conditions and prediction under **Optional trial context**; it is not the undecided kit activity. Reflection appears once a current trial has observations. Mute and playback interruption are under **Settings**.

A pending action opens the on-screen proposal with ordered steps and **Confirm plan** and **Cancel proposal**. Confirm follows the gateway's acknowledgement of the displayed preview and uses its exact request ID and JSON integer proposal version. Incoming snapshots and reply bindings also accept the gateway's temporary positive digit-string version format.

The phone sends 16 kHz mono PCM16 input and plays 24 kHz mono PCM16 replies. It acknowledges a reply after both the server's end event and playback completion for every scheduled buffer. The gateway binds the reply ID to the proposal version. Accepted generation changes clear queued audio and unfinished input before capture resumes. Moving the app to the background closes the live transport and pauses audio. Returning restores the session without replaying commands.

Scene images and optional MuJoCo frames use the same-origin `/api/sessions/{session_id}/evidence/{evidence_id}` PNG endpoint with a Bearer header. Requests refuse redirects. The client limits displayed image data to the active connection, session, and generation. The camera shows execution frames while MuJoCo reports running and otherwise uses the latest observation image when present. Image provenance and capture time accompany observation images. MuJoCo frames are labeled as simulation.

## Verification

From this directory, run the portable tests and project validation.

```sh
bash Checks/check.sh
```

For a signed simulator build with full Xcode, set `DERIVED_DATA` to your own build directory.

```sh
DERIVED_DATA="$PWD/.build/simulator-derived-data"
xcodebuild -project OpenArmsVoice.xcodeproj -scheme OpenArmsVoice \
  -destination 'generic/platform=iOS Simulator' -derivedDataPath "$DERIVED_DATA" \
  CODE_SIGNING_ALLOWED=YES build
codesign --verify --deep --strict \
  "$DERIVED_DATA/Build/Products/Debug-iphonesimulator/OpenArmsVoice.app"
```

Simulator signing uses Xcode's **Sign to Run Locally** identity. Keep signing enabled for Keychain access. Device deployment requires an iOS provisioning profile and signing team.

A connected text/STOP rehearsal needs a reachable gateway with session grants, the configured expert and scene artifacts. Actual voice rehearsal requires the server’s Gemini Live credential and a reachable audio connection. Optional Devpost/presentation simulation can use `OPENARMS_EXECUTION=mujoco`; it is outside main architecture and kit acceptance. A signed build verifies compilation and signing. Simulator UI, authenticated playback, and human audibility require separate runtime checks. Physical actuation is disabled in this software lane. [Architecture delivery #19](https://github.com/VictorJimenez3/OpenArms/issues/19) · [Shared interface #9](https://github.com/VictorJimenez3/OpenArms/issues/9) · [Software loop #10](https://github.com/VictorJimenez3/OpenArms/issues/10) · [iPhone connectivity #4](https://github.com/VictorJimenez3/OpenArms/issues/4)
