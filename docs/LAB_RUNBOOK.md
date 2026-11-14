# OpenArms student lab

The canonical application is `agentic/openarms_lab/` with the browser UI in `ui/lab/`. It runs locally with a SQLite notebook, deterministic skill routing, Gemini Live conversation, and an optional bridge to the current hardware checkout. The older SwiftUI/Whisper relay remains a separate historical demo.

## Run

From this checkout, install Python 3.12 dependencies once:

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r agentic/requirements-lab-dev.txt
OPENARMS_ENV_FILE=/Users/joeroche/Developer/OpenArms/.env \
OPENARMS_EXPERT_TRANSPORT=live OPENARMS_BACKEND=mock \
.venv/bin/python -m agentic.openarms_lab
```

Open <http://127.0.0.1:8000>. Run one server worker. `OPENARMS_ENV_FILE` optionally points to an existing ignored env file; keep the API key on the server. No key is required for mock controls, lessons, quizzes, notebook, or local composition. Gemini conversation and provider composition require `GEMINI_API_KEY` (or `GOOGLE_API_KEY`).

Click **Start voice** once and accept microphone permission. Listening continues until you toggle voice off; mute is also available. Nothing captures audio before this gesture. The mic button and the listening indicator show its state. Use localhost or HTTPS: browsers restrict microphone access on ordinary remote HTTP origins.

Try these utterances, waiting for each response:

1. “Choose color dilution.” Ask for the instructions or available experiments.
2. “My prediction is that adding water makes the dye lighter because its concentration decreases.”
3. “Add water from A into B.” Correct it with “Use C into B instead,” or cancel it.
4. After hearing/reviewing the exact proposal, say **“Confirm.”** An action request alone grants no consent.
5. Answer the quiz aloud, then say “Prepare the next trial.” Record a new prediction and compare C with A.

Buoyancy and mandarin transfer are also selectable by voice. Text fields and buttons remain available. **STOP** has a direct UI path. Spoken STOP depends on recognition and network latency; retain the physical bench stop when operating real equipment. Stopping voice or losing the connection cancels pending proposals and stops tracked execution. After a stopped/faulted mock action disarms the apparatus, start a fresh session.

## Evidence and safety boundary

Mock receipts describe controller state; science outcomes are separately labeled **MODEL-PREDICTED** analytical expectations. There is no camera/color/density measurement or physics simulation in these lessons. Water's molar mass, 18.015 g/mol, is a lesson fact. It is not a measured experiment result. Quizzes use a visibly labeled deterministic rubric.

Voice confirmation requires a fresh completed student input saying yes/confirm, bound to the proposal that existed when that utterance began. Corrections, new proposals, expiry, consumed IDs, STOP, and disconnect invalidate old consent. Provider arguments cannot supply that input evidence. **Student consent is separate from physical operator authorization.** No voice tool grants bench approval.

The physical adapter is opt-in with `OPENARMS_BACKEND=physical`, `OPENARMS_HARDWARE_CHECKOUT`, and `OPENARMS_RUNNER=module:create_runner`. It loads that checkout's `TransferRunner`, binds authorization to the exact request, and never retries motion blindly. Only mandarin transfer is exposed; C-to-B is available only if the runner declares that recorded script. The wet-lab A-to-C pour is not wired to this application's MOCK A/C-to-B dilution. Controller completion without independent placement evidence remains **UNKNOWN**. This integration was tested without actuating hardware.

A future simulation implementation can implement `ExecutionBackend` in `agentic/openarms_lab/contracts.py` and be supplied through `Lab(backend_factory=...)`; label its observations `SIMULATED`. No simulation backend ships here.

## Configuration and verification

| Variable | Default / purpose |
| --- | --- |
| `OPENARMS_BACKEND` | `mock`; physical is explicit |
| `OPENARMS_DATA_DIR` | `outputs/lab`; SQLite notebook and skill registry |
| `GEMINI_LIVE_MODEL` | `gemini-3.8-live`; voice, default text, Live expert |
| `OPENARMS_TEXT_TRANSPORT` | `live`; `generate` opts into ordinary generation |
| `OPENARMS_TEXT_MODEL` | `gemini-3.8-flash` for `generate` text |
| `OPENARMS_EXPERT_TRANSPORT` | ordinary generation when keyed; `live` selects the verified Live route |
| `OPENARMS_EXPERT_MODEL` | `gemini-3.8-flash` for ordinary generation |
| `OPENARMS_ALLOWED_HOSTS` | Additional comma-separated private hostnames; same-origin controls still required |
| `OPENARMS_HOST`, `PORT` | `127.0.0.1`, `8000` |

```sh
.venv/bin/python -m pytest agentic/tests -q
.venv/bin/python -m agentic.scripts.lab_demo
.venv/bin/python -m agentic.scripts.lab_browser_demo --url http://127.0.0.1:8000 --output outputs/lab-evidence/final-browser --compose
.venv/bin/python -m agentic.scripts.lab_voice_browser_demo
```

`lab_demo` is provider-free. Browser `--compose` makes a real expert call, then tests/promotes the candidate for mock use only. The supported provider recipe is constrained to reusable transfer→observe; this is not arbitrary motion programming. Ordinary generateContent previously returned provider availability errors; Live is the verified path. The continuous voice browser script uses macOS-generated speech through a synthetic microphone MediaStream and the actual AudioWorklet/provider; it never records the person's microphone. Desktop/mobile browser tests use headless Chromium; mobile viewport emulation is not Safari or student usability testing.

Merge review on 2026-11-14 passed 378 agentic tests and the provider-free `lab_demo` (three mock trials, seven routing cases, stale/duplicate/cancel checks and candidate reuse). This review did not actuate hardware or repeat provider calls. Earlier local provider/browser receipts are retained under `outputs/lab-evidence/`; those ignored artifacts are not included in a fresh checkout. Rerun the commands above for the current environment.
