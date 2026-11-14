# OpenArms UI

`ui/lab` is the voice-first browser client. The native iPhone client lives in `research/joseph/iphone-voice-bridge/ios`. Both use the same authenticated session gateway. Voice is disabled pending a replacement for the withdrawn provider; the server owns task planning, exact proposals, consent, execution and independent observations.

The main screen presents the current scene, voice state, Talk and Stop. History and text are available without imposing a lesson sequence. `/developer` shows the authenticated MuJoCo preview and diagnostic records. Preview footage is labeled simulation and never establishes physical success.

Clients acknowledge actual audio playback using the reply ID. Starting, interrupting, reconnecting and replacing a session invalidate stale audio and consent. Preserve the contracts in [INTERFACES](../docs/INTERFACES.md) and [FULL_SYSTEM_DELIVERY](../docs/FULL_SYSTEM_DELIVERY.md). Product priorities and remaining physical requirements are in [ARCHITECTURE](../docs/ARCHITECTURE.md). Victor remains the UI contact; the integrator coordinates changes across clients and server.
