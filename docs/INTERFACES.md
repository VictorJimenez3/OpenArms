# Shared conversational lab session contract

[Architecture](ARCHITECTURE.md) defines D1–D4 product targets; [FULL_SYSTEM_DELIVERY](FULL_SYSTEM_DELIVERY.md) defines the R1–R6 software scope. Prediction and reflection are optional. Software/simulation evidence does not complete the supervised physical milestone.

> **Architecture correction:** [FULL_SYSTEM_DELIVERY.md](FULL_SYSTEM_DELIVERY.md) is the authoritative R1–R6 responsibility map, domain contract and acceptance checklist. The transport details below are the compatible implementation seam, not the complete product. The physical contract is the selected two-vessel A→C pour; MuJoCo is active development and Isaac is parked. Regardless of activity, background expert planning, image/perception tools, two-agent feedback, reusable candidates and evaluated improvement are required. Physical actuation alone is excluded.

The integrated runtime selects a water-only two-vessel MuJoCo scene explicitly, while retaining the default metered-dropper indicator-pH regression. Neither implements verified Smartivity chemistry. The shared transport below is unchanged; experiment/condition/proposal content comes from the selected backend. Browser and SwiftUI use the same Python service, notebook, trial rules and server-owned voice connection. Joseph retained Gemini Live speech on November 14 and withdrew only Gemini thinking; expert inference uses its independently configured profile. This does not remove the required continuous conversation or feedback to both agents. The application selects a synthetic fixture or actual MuJoCo execution; physical dispatch is disabled. Historical mandarin and dilution demonstrations are research evidence, not selectable experiments.

## Selected scene and trial authority

With `OPENARMS_EXECUTION=mujoco OPENARMS_SCENE=two_vessel`: experiment `two_vessel_water`, condition `water`, scene `two_vessel_docks` version 1, control mode `mujoco_kinematic_water_pour`. Supported execution is one complete A→C water pour with donor return/HOME. Its content-derived execution scope separates admission from all previous indicator skills. Admission requires the supported water action, declared outcome checks and `expected_state.at = HOME`; `355a224` exposes these requirements to the expert. The first candidate missing HOME was rejected, then the corrected candidate passed independent replay and was reused unchanged in the warm run. See [reconciliation evidence](../research/joseph/reconciliation-2026-11-14/README.md).

With `OPENARMS_SCENE=metered_dropper` (default): experiment `indicator_ph`; prepared-sample skill `indicator_ph.v1`; preparation `prepared_sample_with_ph_indicator`; scene `indicator_ph_metered_dropper` version 2. Previous session identities remain passive history. Existing evaluation hashes/receipts are not rewritten, and the current execution scope requires fresh skill admission.

The two-vessel backend exposes water only. The indicator regression exposes prepared vinegar, mild baking-soda solution or water. Browser and native clients consume server-provided choices; unsupported condition corrections cannot retain executable old consent. Prediction and reflection are optional. The server freezes one exact proposal, binding session, trial, request, proposal version, immutable skill version, condition, source fixture A and receiver C. Only a fresh confirmation after presentation consumes that proposal. Changing the condition or prediction revokes the previous proposal. Cancellation, STOP, reconnect, expiry and reuse cannot grant approval.

The controller returns to HOME automatically on successful completion. Controller completion and independent image observations are distinct records. MuJoCo images and their pixel observations are SIMULATED; synthetic fixture images are SYNTHETIC; reference expectations remain MODEL-PREDICTED. None is measured pH or physical camera evidence. Missing evidence remains UNKNOWN. Reflection and preparation of another trial preserve the notebook. No operator acknowledgment is needed for mock preparation. Future physical readiness must distinguish automatic normal return, replenished materials, and recovery after faults.

## Two-vessel scene and camera contract

This seam is implemented in the local two-vessel simulation integration; it does not activate the physical dispatcher. Bind donor identity to station A, receiver identity to station C, and return the donor to A before HOME. Historical mandarin C→B and old four-vessel station maps are separate scene/calibration identities. Additional simulator vessels never silently become active physical stations.

Every relevant frame/observation carries capture timestamp and clock, frame/evidence ID, camera ID, camera/configuration revision, coordinate frame/units, provenance and an immutable image reference/hash. Unknown registration stays explicitly unknown. The current synthetic and MuJoCo scene services expose image capture and pixel localization; this does not establish a live calibrated webcam or arbitrary cup detector. The two-vessel backend captures a new frame before each action, independently rechecks fixture/camera/objects against the approved scope, and captures a separate post-action image. Its primary/secondary view names alias the same overview; they are not independent cameras. Post-action pixels are rendered again from saved final state: visible water appearance does not measure transferred quantity, and controller HOME is a separate check. [MAIN_INTEGRATION](MAIN_INTEGRATION.md) records the camera adapter's integration status.

The expert can request a frame through the existing inspection tool when needed. Capture FPS, inference cadence and deterministic motion are independent. Validate freshness, scene/fixture identity, object presence and parameter coverage before dispatch/reuse; moved, missing, swapped or stale objects require refresh, clarification or rejection. Revalidate the exact scene assumptions used by a proposal; a changed executable proposal needs fresh presentation and consent. STOP invalidates pending capture/tool/task generations, and late results cannot revive work.

The fixture handoff must version dock centres, marker IDs/physical dimensions/corners, fixture origin/axes and camera-to-fixture registration; robot-base registration is separate evidence. The integrated simulator still uses colored rim/tabletop patches, not decoded ArUco/AprilTag patterns. The locally integrated fixture `4b2e3df` provides a 170×156 mm design and actual ArUco 20–23 patterns at 27 mm with a manifest. Independent digital rebuild/review and decoding passed; the simulator does not yet consume this geometry or these patterns, and physical checks remain unverified. Printed ArUco/AprilTag patterns are distinct from recessed letters/ruler ticks. A flat marker localizes its plane only under the documented calibration, not arbitrary cup depth or a grasp pose. The existing fixture lane owns machine-readable geometry; consumers must reject missing or mismatched configuration rather than invent coordinates.

## HTTP

`POST /api/sessions` returns a snapshot and an access token. A remote deployment requires `OPENARMS_DEMO_TOKEN` as the creation bearer credential. All subsequent session HTTP requests use `Authorization: Bearer <access_token>`. Tokens do not belong in URLs, logs or screenshots. Native clients and browsers use the same grant. Saved history reads must not initialize hardware.

`GET /api/sessions/{sid}` restores a snapshot. POST endpoints under that session:

| Endpoint | JSON body |
| --- | --- |
| `condition` | `condition_id`: one of the selected backend's choices (`water` only for `two_vessel`) |
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

The voice agent may interpret a condition, record a prediction, explain reference evidence and guide reflection. It never supplies motor targets, operator authorization or trusted consent. The server independently handles completed confirmation/cancel/STOP input. Completed explicit action requests, sample corrections and resets are recorded atomically with their voice turn, before a later confirmation can see a superseded proposal. Provider tool readbacks share that turn’s mutation receipt; delayed tools cannot execute again or cross STOP. STOP takes effect before transcript or playback delivery. Updates reach the voice agent through correlated tool outcomes, not fabricated student turns.

The existing positive regression fixture is: natural vinegar request → expert scene inspection → exact proposal → presentation → new explicit confirmation → one confirmed simulated execution → automatic HOME → independently observed rendered color → optional reflection → fresh trial. The correction fixture changes water to baking soda, rejects the old proposal, disconnects before confirming the replacement, restores the notebook and requires a fresh proposal.

## Simulation identity and artifacts

The two-vessel backend executes the integrated A/C water scene with provisional 70/60 mm vessel heights and dock geometry. It does not yet consume the latest measured-vessel/base-plate assets. The retained metered-dropper regression derives from source `16a975e`, adapted for qualitative indicator dosing. Simulation state carries `scene_id`, `scene_version`, `source_revision`, `control_mode`, frame count, elapsed simulated motion, and warnings. Clients display actual evidence; they do not substitute a gallery video for an execution. Source lab videos are historical recordings.

Session-authenticated GET routes `/api/sessions/{sid}/evidence/{id}` and `/api/sessions/{sid}/media/{id}.mp4` serve scoped PNG/MP4 artifacts. Paths and tokens are never exposed in URLs. Scene-specific skill admission prevents an old simulator evaluation from activating a skill in a changed apparatus.

## Evidence and release

Automated checks cover state, permissions, stale/negated/duplicate confirmation, client reconnect, microphone/playback lifecycle and grounded reference outcomes. Actual Mac and unplugged iPhone rehearsals must separately establish audible speech and real-device recovery. Neither browser emulation nor generated microphone input proves that someone heard the physical device.
