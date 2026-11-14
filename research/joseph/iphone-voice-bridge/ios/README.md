# OpenArms Voice iOS prototype (issue #3)

iOS 17+ SwiftUI client implementing ../PROTOCOL.md. Open `OpenArmsVoice.xcodeproj` in full Xcode, select the OpenArmsVoice scheme and your iPhone, set your Team under Signing & Capabilities, and choose a unique bundle identifier if needed. Automatic signing is configured; no team or credentials are included. Enable Developer Mode and trust the Mac when prompted, then Run.

Start session requests microphone access and connects to the configured relay. Allow Local Network access when iOS asks. The settings sheet accepts `ws://MAC-HOST.local:8765/voice` (replace MAC-HOST), or a hostname. Use the relay's LAN binding and the same trusted Wi-Fi. USB is used for installation/debugging; it does not automatically forward this WebSocket service. Start the relay using its README first.

The single screen exposes Start, Mute/Unmute and End with large controls, Dynamic Type, VoiceOver labels and state announcements. Capture runs only when listening. Audio is converted to mono 16 kHz signed little-endian PCM16. One bounded FIFO orders audio and controls; mute stops capture and invalidates/discards queued audio. Complete PCM WAV replies play once and are acknowledged on completion, including while muted. Disconnect, end, backgrounding and audio interruption stop capture/playback and invalidate the session. Start creates fresh transport and state. An already in-flight WebSocket send cannot be recalled.

Local Network authorization has no reliable directly queried status here: connection failures show permission/network recovery instructions and an app Settings link. Microphone denial has its own recovery path. The app stores the endpoint preference, but does not write transcript/audio files. Relay transcript logging is reported in the developer sheet. Replies are simulated dialogue, not robot execution.

Run `bash Checks/check.sh` for portable protocol/capture/FIFO/WAV checks, plist/project validation and Swift syntax parsing. On 2026-11-13 these passed (100 checks). These checks do not typecheck UIKit/AVFoundation against an iOS SDK. Full Xcode, simulator and device build were unavailable on this host; local signing, on-device permissions, audio quality and VoiceOver still require the validation checklist in the separate validation worktree.

With Xcode installed, build without signing first:

```sh
xcodebuild -project OpenArmsVoice.xcodeproj -scheme OpenArmsVoice -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build
```
