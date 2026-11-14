# OpenArms iPhone client

The iOS 17+ SwiftUI app connects to the canonical OpenArms lab gateway. The red-cabbage pH investigation is one demonstration. Use **Lab connection** to enter the gateway's HTTPS origin and the pairing code if the host requires one. A Debug build can opt into local HTTP for trusted development hosts. USB debugging does not provide a route to the lab gateway.

The app restores a private session from Keychain and opens the gateway's version 1 session WebSocket. **Talk with OpenArms** starts continuous Gemini Live voice after microphone permission. The request field beside it sends a student's natural request as soon as the session connects. Conditions and predictions are under **Optional trial context**. Reflection is available when the current trial has observations.

The phone sends 16 kHz mono PCM16 input and plays 24 kHz mono PCM16 replies. It sends a played acknowledgement for the reply ID after the server ends the reply and AVAudioPlayerNode reports playback of every scheduled buffer. The gateway binds that reply ID to the proposal version. Accepted generation changes clear queued audio and unfinished input before capture resumes. Text and the notebook remain available while voice is off or unavailable.

The task card shows when the gateway queues a request, prepares a plan, needs clarification, or runs an approved task. The gateway owns the separate image-aware Codex expert (`gpt-6.1-sol`, medium reasoning effort) and saved-skill routing. Confirm and Present send the exact request ID and a JSON integer proposal version. Incoming snapshots and reply bindings accept the gateway's temporary positive digit-string version format.

Scene images use the same-origin `/api/sessions/{session_id}/evidence/{evidence_id}` PNG endpoint with a private Bearer header. Fetches refuse redirects and are scoped to the active connection, session and generation. Capture time and provenance remain visible if an image cannot load. Controller receipts and independent observations are displayed separately. The client shows saved-skill routing, planning time, model calls and evaluation decisions when the gateway supplies those fields. Evaluation counts require a published evaluation receipt.

## Offline verification

Run the portable streaming test suite and project validation:

```sh
bash Checks/check.sh
```

The portable suite covers streaming PCM, generation changes, ordered controls, stale callbacks, playback acknowledgements, exact proposal versions, evidence request validation, and direct requests with optional context.

With full Xcode installed, compile for simulator and device without signing:

```sh
xcodebuild -project OpenArmsVoice.xcodeproj -scheme OpenArmsVoice \
  -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build
xcodebuild -project OpenArmsVoice.xcodeproj -scheme OpenArmsVoice \
  -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build
```

The November 14 follow-up passed all 16 portable tests and built, installed and launched on the iOS 27.2 **OpenArms Native Verification** simulator with Xcode 27.2. This verified the disconnected launch screen. Connected rehearsal requires a reachable staging gateway with session grants, Gemini Live, the Codex expert, perception artifacts, and the intended skill/evaluation data. Authenticated rendering, live responsiveness, warm reuse, and measured improvement remain unverified on that gateway. Physical actuation is disabled in this software lane. Signed deployment and audible rehearsal on an iPhone are separate. [Architecture delivery #19](https://github.com/VictorJimenez3/OpenArms/issues/19) · [Shared interface #9](https://github.com/VictorJimenez3/OpenArms/issues/9) · [Software loop #10](https://github.com/VictorJimenez3/OpenArms/issues/10) · [iPhone connectivity #4](https://github.com/VictorJimenez3/OpenArms/issues/4)
