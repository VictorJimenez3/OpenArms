# OpenArms iPhone client

The iOS 17+ SwiftUI app connects to the canonical OpenArms lab gateway. The red-cabbage pH investigation is one demonstration. Use **Lab connection** to enter the gateway's HTTPS origin and the pairing code if the host requires one. A Debug build can opt into local HTTP for trusted development hosts. USB debugging does not provide a route to the lab gateway.

The app restores a private session from Keychain and opens the gateway's version 1 session WebSocket. **Talk with OpenArms** requests microphone permission and starts continuous voice. The phone sends 16 kHz mono PCM16 input and plays 24 kHz mono PCM16 replies. It acknowledges a reply only after the server ends it and AVAudioPlayerNode reports playback of all scheduled buffers. The audio frame epoch follows accepted session generations. A generation change clears queued audio and unfinished input before capture resumes. Text and the notebook remain available while voice is off or unavailable.

The task card shows server-reported progress, clarification, or failure, with a cancel action for an active task. Reply to a clarification through normal conversation. Exact proposal previews use the server's presentation and confirmation endpoints. Scene evidence displays capture time, provenance and identifiers when supplied. Controller receipts and independent observations have separate displays. Reusable skill versions, lifecycle and evaluation decisions appear when supplied by the gateway. Absent records are omitted. The current scene image contract supplies artifact metadata. Displaying image bytes in the iPhone app requires a gateway delivery contract for those artifacts.

## Offline verification

Run the portable streaming test suite and project validation:

```sh
bash Checks/check.sh
```

The XCTest suite replaces the older relay WAV and turn-gating checks with streaming PCM, generation changes, ordered controls, stale callback rejection, playback acknowledgments and optional session record fixtures.

With full Xcode installed, compile for simulator and device without signing:

```sh
xcodebuild -project OpenArmsVoice.xcodeproj -scheme OpenArmsVoice \
  -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build
xcodebuild -project OpenArmsVoice.xcodeproj -scheme OpenArmsVoice \
  -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build
```

A signed deployment and audible rehearsal on an iPhone are tracked separately. The current assignment covers portable tests and simulator/device compilation. [Architecture delivery #19](https://github.com/VictorJimenez3/OpenArms/issues/19) · [Shared interface #9](https://github.com/VictorJimenez3/OpenArms/issues/9) · [Software loop #10](https://github.com/VictorJimenez3/OpenArms/issues/10) · [iPhone connectivity #4](https://github.com/VictorJimenez3/OpenArms/issues/4)
