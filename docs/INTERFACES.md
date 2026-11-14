# Shared conversational lab session contract

[Architecture](ARCHITECTURE.md) defines D1–D4 product targets; [FULL_SYSTEM_DELIVERY](FULL_SYSTEM_DELIVERY.md) defines the R1–R6 software scope. Prediction and reflection are optional. Software/simulation evidence does not complete the supervised physical milestone.

> **Architecture correction:** [FULL_SYSTEM_DELIVERY.md](FULL_SYSTEM_DELIVERY.md) is the authoritative R1–R6 responsibility map, domain contract and acceptance checklist. The transport details below are the compatible implementation seam, not the complete product. The kit activity is undecided; retained simulation is an optional presentation extra. Regardless of activity, background expert planning, image/perception tools, two-agent feedback, reusable candidates and evaluated improvement are required. Physical actuation alone is excluded.

The existing regression implementation exposes simulated indicator pH. Its payload details below document current code, not the main product architecture or kit requirements. It does not implement a Smartivity kit activity yet. Browser and SwiftUI use the same Python service, notebook, trial rules and server-owned voice connection. Joseph withdrew Gemini on November 14; the default voice connection is disabled pending replacement. This does not remove the required continuous conversation or feedback to both agents. The application selects a synthetic fixture or actual MuJoCo execution; physical dispatch is disabled. Historical mandarin and dilution demonstrations are research evidence, not selectable experiments.

## Existing regression-fixture trial authority

Current experiment ID: `indicator_ph`; prepared-sample skill: `indicator_ph.v1`; preparation: `prepared_sample_with_ph_indicator`; MuJoCo scene: `indicator_ph_metered_dropper`, version 2. Previous session identities remain passive history. Existing evaluation hashes/receipts are not rewritten, and the current execution scope requires fresh skill admission.

A natural request supplies the prepared vinegar, mild baking-soda solution, or water condition; prediction and reflection are optional. The server freezes one exact proposal, binding session, trial, request, proposal version, immutable skill version, condition, source fixture A and receiver C. Only a fresh confirmation after presentation consumes that proposal. Changing the condition or prediction revokes the previous proposal. Cancellation, STOP, reconnect, expiry and reuse cannot grant approval.

The controller returns to HOME automatically on successful completion. Controller completion and independent image observations are distinct records. MuJoCo images and their pixel observations are SIMULATED; synthetic fixture images are SYNTHETIC; reference expectations remain MODEL-PREDICTED. None is measured pH or physical camera evidence. Missing evidence remains UNKNOWN. Reflection and preparation of another trial preserve the notebook. No operator acknowledgment is needed for mock preparation. Future physical readiness must distinguish automatic normal return, replenished materials, and recovery after faults.

## HTTP

`POST /api/sessions` returns a snapshot and an access token. A remote deployment requires `OPENARMS_DEMO_TOKEN` as the creation bearer credential. All subsequent session HTTP requests use `Authorization: Bearer <access_token>`. Tokens do not belong in URLs, logs or screenshots. Native clients and browsers use the same grant. Saved history reads must not initialize hardware.

`GET /api/sessions/{sid}` restores a snapshot. POST endpoints under that session:

| Endpoint | JSON body |
| --- | --- |
| `condition` | `condition_id`: `vinegar`, `baking_soda`, or `water` |
| `prediction` | `text` |
| `request` | `text`, optional `client_request_id` |
| `present` | `request_id`, `proposal_version`, `channel: text` |
| `confirm` | `request_id`, `proposal_version` |
| `cancel` | optional `request_id` |
| `reflection` | `text` |
| `prepare`, `stop`, `disconnect` | empty object |

Snapshots contain session ID, monotonically increasing revision, generation, trial, condition choices, prediction, pending proposal, requests, observations, conversation and notebook. Clients reject older revisions. Session and evidence IDs are distinct; the backend/provenance is explicit throughout.

## Streaming connection

Both clients connect to `/api/sessions/{sid}/live`. The first frame is `hello` with protocol version 1, a fresh connection ID and the session access token. Only one connection owns session cleanup. A replacement revokes previous approval and prevents the old socket's cleanup from modifying the new connection.

The socket remains useful for state and text when voice is off or the provider is unavailable. Client `ping` frames every five seconds receive matching `pong` sequence numbers. A 15-second missing heartbeat revokes pending work and ends the connection. Reconnect restores history, drops queued audio, and never replays commands or consent.

| Client frames | Purpose |
| --- | --- |
| `start_voice`, `stop_voice` | Start/stop provider speech while keeping the application session |
| `audio` | Base64 PCM16 little-endian, mono 16 kHz, at most 200 ms, current `epoch`/generation |
| `mute` | Explicit microphone state; discard partial input |
| `text` | Student message and optional idempotency ID |
| `present` | Acknowledgment after the exact proposal is displayed |
| `played` | Reply ID acknowledged after actual speaker playback completes |
| `interrupt` | Cancel playback of a particular reply |
| `stop`, `close` | Immediate direct control, independent of provider reasoning |

Server frames include `hello`, `state`, `pong`, `status`, `transcript`, `reply_start`, `audio`, `reply_end`, `interrupted`, and `error`. Transcript fragments share a turn ID and a final marker. Reply audio is PCM16 mono 24 kHz with a reply ID. `reply_start` may bind a proposal ID/version. Model generation finishing is not proof of playback: only matching completed playback of an exact canonical preview may acknowledge audio presentation. Interrupted or stale replies cannot do so.

Microphone permission, provider readiness, and active speaker playback are separate states. Muted speech cannot become consent. Spoken STOP depends on speech recognition; the direct STOP control bypasses the voice provider. A lost provider connection does not remove text controls.

## Voice and intent

The voice agent may interpret a condition, record a prediction, explain reference evidence and guide reflection. It never supplies motor targets, operator authorization or trusted consent. The server independently handles completed confirmation/cancel/STOP input; a delayed model tool call cannot execute again. Updates reach the voice agent through correlated tool outcomes, not fabricated student turns.

The positive integration fixture is: natural vinegar request → expert scene inspection → exact proposal → presentation → new explicit confirmation → one confirmed simulated execution → automatic HOME → independently observed rendered color → reflection → fresh trial. The correction fixture changes water to baking soda, rejects the old proposal, disconnects before confirming the replacement, restores the notebook and requires a fresh proposal.

## Optional simulation identity and artifacts

The selected MuJoCo backend executes the updated lab apparatus from source `16a975e`, adapted for qualitative indicator dosing. Simulation state carries `scene_id`, `scene_version`, `source_revision`, `control_mode`, frame count, elapsed simulated motion, and warnings. Clients display actual evidence; they do not substitute a gallery video for an execution. Source lab videos are historical recordings.

Session-authenticated GET routes `/api/sessions/{sid}/evidence/{id}` and `/api/sessions/{sid}/media/{id}.mp4` serve scoped PNG/MP4 artifacts. Paths and tokens are never exposed in URLs. Scene-specific skill admission prevents an old simulator evaluation from activating a skill in a changed apparatus.

## Evidence and release

Automated checks cover state, permissions, stale/negated/duplicate confirmation, client reconnect, microphone/playback lifecycle and grounded reference outcomes. Actual Mac and unplugged iPhone rehearsals must separately establish audible speech and real-device recovery. Neither browser emulation nor generated microphone input proves that someone heard the physical device.
