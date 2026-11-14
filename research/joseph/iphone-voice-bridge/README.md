# OpenArms iPhone voice bridge

The iPhone hosts the microphone, speaker, and call controls. The Mac hosts speech recognition, the lab dialogue, synthesized speech, and local session logs. The prototype's lab runs are simulated.

## Run the prototype

1. Start the [Mac relay](relay/README.md) on a trusted local network. For the iPhone, use the relay's LAN mode and find the Mac's local hostname with `scutil --get LocalHostName`. Append `.local`.
2. Open the [iPhone project](ios/) in Xcode and run it on a paired iPhone with a signing team selected. Allow local network and microphone access. Enter the Mac's `.local` hostname in the app's developer settings.
3. Start a conversation. Predict where the block will land, listen to the preview, then say “I confirm” or “cancel.” After the simulated result, describe your observation. End the session and inspect the relay's `events.jsonl` for the student and relay turns.
4. Unplug USB and repeat over Wi-Fi. While listening, mute and speak, then unmute and verify that the relay only received the unmuted turn. Stop the relay mid-session, check the phone's connection error, then restart the relay and start a new session. Verify a new session ID.

Device verification is tracked in [issue #4](https://github.com/VictorJimenez3/OpenArms/issues/4).

## Connect the team agent

The [WebSocket protocol](PROTOCOL.md) carries conversation and status. The relay's [dialogue adapter](relay/dialogue.py) receives the recognized transcript and session and turn IDs. Agree on a concrete team example in [the repository interface notes](../../../docs/INTERFACES.md) before wiring in action previews and execution. The team agent owns plan identity and any preview, approval, or execution boundary.

Use the Mac relay's local logs for transcript, connection, and timing review. Raw audio is retained only when the relay is started with the explicit test option.
