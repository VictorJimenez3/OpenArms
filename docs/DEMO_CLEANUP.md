# Client design notes

The original delivery plan is superseded by [the current architecture](ARCHITECTURE.md) and [R1–R6 contract](FULL_SYSTEM_DELIVERY.md). PR #22 and PR #25 are merged. The selected physical scope is the two-vessel Smartivity pour; Gemini Live provides speech and expert inference remains separate. MuJoCo is active development, with optional presentation experiments; Isaac is parked. The design decisions below remain useful; this document assigns no active lanes or extra merge gates.

## Visual direction

Palette reference: [Radix Colors](https://www.radix-ui.com/colors), sage neutrals and jade accent. Tokens: background `#fbfdfc`, subtle `#f7f9f8`, line `#dfe4e2`, ink `#1a211e`, muted `#5f6563`, accent `#208368`; STOP `#b42318`. White foreground on the dark jade action. Use system fonts; no external font dependency.

The lab is a conversation with a camera. Keep one prominent voice control, truthful status and Stop visible. Put typing, history, setup, optional reflection and diagnostic identifiers behind deliberate disclosure. Show the exact pending action with confirm/cancel when needed. Avoid simulated waveforms that imply audio is active.

Browser and SwiftUI use the same authenticated session, task and observation records. `/developer` adds expert/tool progress, provider identity, skill/evaluation evidence and timings. Optional simulation frames/recordings use authenticated session routes and preserve their provenance. No separate runtime or unauthenticated artifacts.

Clients acknowledge actual playback, discard stale audio after interruption/reconnect and never replay consent. The server owns task planning, validation and execution. Follow [the shared interface](INTERFACES.md); keep current ownership and remaining acceptance in the canonical architecture and delivery contract.
