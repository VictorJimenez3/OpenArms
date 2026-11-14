# Voice-first demo delivery

User direction, 2026-11-14: simplify both phone and desktop; provide a developer desktop showing the existing MuJoCo simulator; verify the Gemini Live → Codex expert → simulation → independent observation loop; integrate and merge the reviewed result. Physical actuation remains disabled.

## Design

Use the installed Anthropic frontend-design skill. Palette reference: [Radix Colors](https://www.radix-ui.com/colors), sage neutrals and jade accent. Tokens: background `#fbfdfc`, subtle `#f7f9f8`, line `#dfe4e2`, ink `#1a211e`, muted `#5f6563`, accent `#208368`; STOP `#b42318`. White foreground on the dark jade action. System humanist sans on native; a locally available sans on web. No external font dependency.

The lab is a conversation with a camera. The one prominent control starts/ends voice. Keep a short truthful status and Stop visible. Put typing, history, setup, optional prediction/reflection, and diagnostic identifiers behind deliberate disclosure. Exact pending action and confirm/cancel remain readily visible when needed. No marketing hero, decorative tubes, mandatory lesson form, or simulated waveform implying audio activity.

```
OpenArms               Connected     Stop
          [camera / observed image]
             Listening / working
             [ Talk / End voice ]
            Type instead   History
        [exact proposal when pending]
```

Developer route `/developer` uses the SAME session/auth/voice code. It adds a large MuJoCo viewport plus actual expert progress, tool events, provider/model, observations, skill/evaluation evidence and timings. Never invent live motion or success. No second runtime or unauthenticated artifact route.

## Ownership and dependencies

| Lane | Owner | Owned files | Requirements and evidence |
|---|---|---|---|
| Voice-first desktop + developer UI | external browser worker | `ui/lab/**` | R1/R3/R4 UI; preserve audio epochs, explicit consent, auth; browser tests and responsive screenshots |
| Voice-first native | external iOS worker | `research/joseph/iphone-voice-bridge/ios/**` | R1/R3/R4 UI; shared transport and image grants; portable tests and signed simulator build |
| MuJoCo execution/perception | external simulation worker | new `agentic/openarms_lab/mujoco_*.py`, simulation tests, `agentic/tests/test_lab_sim_preview.py` | R3/R4 actual existing MuJoCo execution and independently read rendered outcomes; STOP, failure, no serial imports; recorded frames/video and tests |
| Integrator | primary | app/runtime/voice contracts, expert/skills/evaluation, docs, final review and merge | R1–R6 full loop, D1 direct actions, D2 responsive voice, D3 validated reuse, D4 measured revision; real provider rehearsals and acceptance record |

All workers use isolated existing worktrees based on the same integration commit, commit only owned changes, never push or merge main, and return requirements, dependencies, measured evidence and remaining gaps. Parent controls merges. Preserve current baseline and existing simulator. No hardware calls.

## Simulation connection contract

`MujocoSceneService(artifact_dir)` implements the existing `inspect_scene`, `localize_objects`, `observe` interface. Evidence PNGs retain IDs, timestamps, hash and `SIMULATED` provenance. Its outcome observer must inspect rendered pixels independently of an executor success flag. It must expose limitations of the modeled chemistry and uncalibrated poses. Supported fixture recognition is acceptable when stated explicitly. No replacement synthetic 2D scene as MuJoCo evidence.

`MujocoBackend(scene_service)` implements the current backend interface (`bind_session`, `prepare`, `state`, `capabilities`, `check_step`, `execute_step`, `stop`, `wait_idle`). Reuse `simulation/openarms_sim` liquid Player, model, trajectories and rendering. The existing primitive names are wire-compatible references: `mock_prepared_sample`, `mock_pick_up`, `mock_put_down`, `mock_pour`; backend and evidence identify actual MuJoCo simulation. Unsupported operations must be rejected honestly. Do not import any physical executor/serial path.

Backend state may add `simulation`: `{engine:"MuJoCo", status, frame_name, video_name, frame_count, motion_seconds, warnings}`. Artifact names are basename-only, UUID hex plus `.png`/`.mp4`, under `artifact_dir/session_id`. Live progress updates may change `frame_name`; completed video is from that execution. Parent maps these to authenticated same-session URLs `.../evidence/<hex>` and `.../media/<hex>.mp4`. UI receives `frame_url` / `video_url`, fetches with the existing bearer grant, and uses revocable blob URLs. No secret in URL. Do not expose local paths. Session switching/disconnect invalidates artifacts and pending consent.

Select simulation explicitly with `OPENARMS_EXECUTION=mujoco`. Missing dependencies or simulator errors are failures, never silent mock fallback. Existing synthetic evaluation remains its own labeled regression environment; simulation success does not claim physical qualification.

## Acceptance before merge

- Both apps open to camera/status/voice/Stop; typing and history remain accessible.
- Gemini continuous conversation remains responsive while the actual gpt-6.1-sol medium Codex expert inspects timestamped scene images and tools.
- Exact proposal is presented before fresh consent; duplicate/stale/reconnected consent cannot execute.
- Confirmed actions run the existing MuJoCo model; developer view shows execution-derived frames/video and failure state.
- Independent rendered-image observation reaches the expert and Gemini with simulated provenance.
- Versioned skill registration, equivalent-request reuse, and unchanged-baseline improvement receipts remain available and honest about environment.
- STOP, cancellation, provider failure, unreadable evidence, reconnect and teardown pass meaningful integration tests.
- Signed native simulator and desktop UI exercised; physical unplugged iPhone and human audibility are explicitly distinguished from automated playback/simulator evidence.
- Integration diff receives full-vision review before any push. Merge only the reviewed result; state remaining demo/device/hardware gaps explicitly.
