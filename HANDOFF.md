# OpenArms handoff

Written 2026-11-16 from the demo baseline `5cce0e9`, for any person or AI agent picking this project up. Victor Jimenez is now the sole developer. The HackPrinceton Fall 2026 hackathon is over.

**Read this file first. It is the current source of truth.** Most other documents in this repo were written during the hackathon by four people and several AI agents working in parallel. Many of them describe plans, team rules and scenes that no longer apply, and several contradict each other. Section 9 says which ones to trust. When a document and the code disagree, the code is right.

Statements here are marked when they were not checked. Everything unmarked was verified against the code or by running it on 2026-11-15 or 2026-11-16.

## 1. What this is

OpenArms is a robot lab partner called Ollie. A student who cannot hold lab equipment tells Ollie what to do, by voice or text. Ollie proposes one exact action, waits for the student's yes, performs it once on a simulated or real SO-101 arm, and a separate camera check reports what happened.

Brand line: "You're the scientist. Ollie's the hands."

The loop every feature must preserve:

1. The student asks in their own words.
2. A planner model proposes one bounded action from a fixed set of tested operations.
3. The app shows the exact plan. Nothing moves until the student confirms that exact version.
4. A deterministic executor runs it once.
5. An independent observer reads a fresh image and reports the result, or says it does not know.
6. Stop cancels at any point, and a cancelled plan can never start later.

## 2. Current status

| Area | Status |
| --- | --- |
| Student app (`/student/`) on the simulator | Works. Typed request, plan, confirm, simulated pour, observation and report were run end to end. |
| Several commands in one session (half pour, the rest, reset) | Works on the simulator. |
| Gemini Live voice in the student app | Worked with synthesized speech fed to the browser microphone. Not tested with a human voice, real speakers or room noise. |
| Ask Ollie chat (Gemini, text) | Works and stays on topic. |
| Real-bench lane (`/bench`) with a stand-in arm | Works: look, plan, preview, execute, result labelled MOCK. |
| Real-bench lane with the real arm | The server was started against the real arm and a phone camera on 2026-11-15. No result of a real pour was recorded in this handoff's source session. Treat it as unverified. |
| Spoken yes/no to the bench operator's questions | Tested only with a fake Gemini session. |
| Bench voice | Failed once on 2026-11-15 with "Voice stopped (APIError)". Cause not found. A bare Gemini Live connection with the same key worked minutes later. |
| Tests | 1003 passed, 4 skipped, 0 failed on `5cce0e9` (agentic, simulation, firmware arm and camera tests). |
| Accessibility | Built to WCAG 2.2 AA. An axe-core audit reported 0 violations on 27 screen states and one full lab was run by keyboard only. No real switch, eye tracker, voice-control app, screen reader or disabled student has used it. |

Simulated results, software tests and physical results are three separate things. Never report one as another.

## 3. Start here

### Environment

Python 3.12 and [uv](https://docs.astral.sh/uv/). One environment runs the server, the simulator, the tests and the real arm. It lives outside the repo so git does not see it.

```sh
cd /Users/victor/OpenArms/OpenArms
git clone https://github.com/huggingface/lerobot.git LeRobot/lerobot      # only for the real arm; LeRobot/ is git-ignored
git -C LeRobot/lerobot checkout e0d50211                                  # pinned, LeRobot 0.6.2
uv venv --python 3.12 /Users/victor/OpenArms/.venv-arm
uv pip install --python /Users/victor/OpenArms/.venv-arm/bin/python \
  -e "LeRobot/lerobot[feetech]" -r agentic/requirements-lab.txt \
  mujoco==4.0.1 scipy pyyaml pillow imageio imageio-ffmpeg pandas pyarrow anthropic==2.8.0 pytest pytest-asyncio
```

On Victor's Mac this environment and the LeRobot clone already exist. Leave out the LeRobot lines if you only need the simulator.

### Keys

`.env` at the repo root, git-ignored, never committed:

| Variable | Used for |
| --- | --- |
| `GEMINI_API_KEY` | Gemini Live voice (student app and bench) |
| `OLLIE_CHAT_API_KEY` | Ask Ollie text chat. Falls back to `GEMINI_API_KEY` when unset |
| `ANTHROPIC_API_KEY` | Optional. Free-form planning in the real-bench lane. Without it the bench accepts fixed phrases only |

Both Gemini keys currently in `.env` were pasted into a chat during the hackathon and one belongs to Joseph. **Rotate them and use Victor's own.**

### Run the simulator app

```sh
cd /Users/victor/OpenArms/OpenArms
PYTHON=/Users/victor/OpenArms/.venv-arm/bin/python \
OPENARMS_DEMO_EXPERIMENT=volcano \
agentic/scripts/run_demo_app.sh <planner-profile> medium 8031
```

Then open `http://127.0.0.1:8031/student/`. `OPENARMS_DEMO_EXPERIMENT` is `volcano`, `potions` or `lava_lamp`. One server runs one experiment; `agentic/scripts/run_demo_suite.sh` starts three servers on ports 8011 to 8013.

Running `python -m agentic.openarms_lab` with no environment gives a mock pH experiment, which is not the product. Always use the script, or set `OPENARMS_EXECUTION=mujoco OPENARMS_SCENE=demo_bench`.

### The planner profile: read this before the first run

The planner is a separate model reached through a command-line tool that must be logged in on this machine. The script's default is `devin-sol-fast`, which needs the Devin CLI and a Devin subscription. **That stops working when the Devin subscription ends.**

| Profile | Needs | State on 2026-11-16 |
| --- | --- | --- |
| `devin-sol-fast` (script default), other `devin-*` | Devin CLI logged in | Worked all weekend. Ends with the subscription |
| `sol`, `astra` | Codex CLI logged in, with quota | Server starts. A planning call failed: the Codex account had hit its usage limit |
| `opus`, `sonnet` | Claude Code CLI logged in, or `ANTHROPIC_API_KEY` | Server starts. A planning call failed: the Claude CLI login had expired |

So the Codex and Claude paths are wired and the server accepts them, but **neither has completed a planning call in this session.** Both failures were account problems, not code errors. First task for the next agent: log in (`claude` then `/login`, or wait for Codex quota), run the scripted check below with `sonnet` or `sol`, and then change the default profile in `agentic/scripts/run_demo_app.sh`.

A request that matches a saved skill (for example "pour A into C" after seeding) needs no planner call, so the app can look healthy while the planner is broken. Test with new wording.

### Check it works

Scripted student, one session, real planner calls:

```sh
/Users/victor/OpenArms/.venv-arm/bin/python .devin/harness-loop/live_app_check.py \
  http://127.0.0.1:8031 "tip half of the little beaker into the big container"
```

A good run prints `"status": "completed"`, `"executions": 1` and an `answer` from the observer. `.devin/` is git-ignored, so this script exists only on Victor's Mac. Moving it into `agentic/scripts/` is a worthwhile early task.

Tests, about ten minutes:

```sh
PYTHONPATH=agentic:simulation:. /Users/victor/OpenArms/.venv-arm/bin/python -m pytest \
  agentic/tests simulation/tests \
  firmware/openarms_executor/test_arm.py firmware/openarms_executor/test_transfer_runner.py firmware/openarms_camera \
  --import-mode=importlib -o asyncio_mode=auto -q -p no:cacheprovider
```

Do not pass the whole `firmware/` folder to pytest. Several files in it are command-line scripts that parse arguments on import and crash collection.

Browser tests exist in `ui/lab/tests` (Playwright). They were not run for this handoff.

### Run the real bench

Only with a person at the bench, the arm's power switch within reach, and nothing in the arm's path. Cutting power is the emergency stop.

```sh
cd /Users/victor/OpenArms/OpenArms
source env.sh
PYTHON=/Users/victor/OpenArms/.venv-arm/bin/python \
OPENARMS_BENCH=1 \
OPENARMS_OVERHEAD_CAMERA=0 \
OPENARMS_FOLLOWER_PORT=/dev/tty.usbmodem5B7B0148501 \
OPENARMS_POUR_POSES=/Users/victor/OpenArms/OpenArms/outputs/pour-take-2.json \
OPENARMS_DEMO_EXPERIMENT=volcano \
agentic/scripts/run_demo_app.sh <planner-profile> medium 8032
```

Open `http://127.0.0.1:8032/bench`, press Look now, ask for a pour, then Execute, then answer the operator's questions.

- Leave out `OPENARMS_FOLLOWER_PORT` to rehearse with a stand-in arm. Nothing moves.
- The port and camera number change between computers and USB sockets. Find the port with `/Users/victor/OpenArms/.venv-arm/bin/lerobot-find-port`. List cameras with `PYTHONPATH=. <python> -m firmware.openarms_camera list`, run from Terminal, because macOS must grant that Terminal camera access.
- If LeRobot ever asks to calibrate, stop. `source env.sh` was skipped or the arm id is wrong. The calibration in `calibration/` fits the team's two physical arms only.
- `outputs/pour-take-2.json` and its `.layout.json` are Stefanie's recorded pour. `outputs/` is git-ignored, so they exist only on Victor's Mac. Without a recorded pour, Execute stays disabled for pours.
- Never set `OPENARMS_BENCH_CONFIRM=page` with a real arm. It removes the operator's yes.
- The camera came from an Android phone in USB webcam mode. Continuity Camera needs an iPhone on the same Apple Account as the Mac.
- The arm hardware belonged to the hackathon team. Whether Victor still has access to it is not known here.

`docs/LAB_RUNBOOK.md` has more detail on the bench lane and is mostly accurate for it.

## 4. How the code is organised

### The path a student request takes

| Step | File |
| --- | --- |
| HTTP and WebSocket routes, which backend is selected | `agentic/openarms_lab/app.py` |
| Session state, review, consent | `agentic/openarms_lab/runtime.py` |
| Decide, dispatch, check evidence, stale-consent rules | `agentic/openarms_lab/task_loop.py` |
| Operations and their typed arguments | `agentic/openarms_lab/contracts.py` |
| Wording rules, repeat and stop detection | `agentic/openarms_lab/conversation.py`, `request_intent.py` |
| Planner adapters and profile table | `expert_profiles.py`, `codex_expert.py`, `claude_expert.py`, `devin_expert.py` |
| Saved skills, admission, reuse | `skills.py`, `evaluation.py`, `store.py` |
| The demo bench: actions, state between commands, observer | `demo_bench.py` |
| The MuJoCo process that performs a demo-bench action | `demo_bench_worker.py` |
| Gemini Live voice for a session | `live.py`, `voice_controls.py` |
| Ask Ollie text chat | `ollie_chat.py` |
| Simulator core: scene, motion, player, chemistry | `simulation/openarms_sim/` |
| The demo bench layout, poses and experiments | `simulation/config/setups/demo/` |

`demo_bench.py` builds on `two_vessel_backend.py`, which builds on `mujoco_backend.py`. Those two are therefore live code even though the scenes they were written for are not the product.

### The real-bench lane

Separate from the session task loop. It does not share consent or skills with it.

| Step | File |
| --- | --- |
| The whole lane: look, plan, preview, execute, verify | `agentic/openarms_lab/bench_lane.py` |
| Bench voice, spoken yes/no, "stop the voice" | `agentic/openarms_lab/bench_voice.py` |
| Free-form planning with Claude | `free_plan.py` (uses `agentic/openarms_agent/`) |
| Simulated preview | `sim_preview.py` |
| Overhead camera, rulers, container positions | `firmware/openarms_camera/` |
| Arm driver, recorded-pour replay | `firmware/openarms_executor/pose_arm.py`, `pour_once.py`, `motion.py`, `robot.py` |
| Correcting a recorded pour for moved containers | `simulation/openarms_sim/shift.py`, `reach.py` |

### Front ends

| URL | Source | What it is |
| --- | --- | --- |
| `/student/` | `ui/student/` | Ollie, the product. Plain HTML, CSS and JavaScript modules, no build step. Victor's. |
| `/bench` | `ui/lab/` plus `ui/student/bench-skin.css` | The real-bench screen in the Ollie look. The skin is one stylesheet injected by the server; it changes no behaviour. |
| `/` and `/developer` | `ui/lab/` | Joseph's original lab client and trace view. |

`ui/student/live.js` reuses `ui/lab/live-client.js` for voice, so the student app depends on that one file in `ui/lab`. `ui/student/DESIGN.md` records the visual system and the WCAG mapping. `ui/student/labs.js` holds the experiment copy; the science text was never reviewed by anyone qualified.

### API

Session routes need `Authorization: Bearer <access_token>` from `POST /api/sessions`. Bench routes accept the same computer only.

- Session: `POST /api/sessions`, `GET /api/sessions/{sid}`, then `request`, `present`, `confirm`, `cancel`, `prepare`, `stop`, `prediction`, `reflection`, `condition`, `ollie`, and `WS /api/sessions/{sid}/live`.
- `present` and `confirm` both take the pending `request_id` and `proposal_version`. A plan must be presented before it can be confirmed.
- `pending.student_summary` is the plain-language plan; `pending.summary` is the exact text consent binds to.
- Bench: `GET /api/bench`, `POST /api/bench/look|request|execute|answer|cancel|stop`, `WS /api/bench/voice`.
- `GET /api/health` reports the planner profile and whether voice is configured. "Configured" only means a key is present.

### Environment variables that matter

`OPENARMS_EXECUTION` (`mock` or `mujoco`), `OPENARMS_SCENE` (`demo_bench`, `two_vessel`, `metered_dropper`), `OPENARMS_DEMO_EXPERIMENT`, `OPENARMS_DATA_DIR`, `OPENARMS_EXPERT_PROFILE`, `OPENARMS_EXPERT_EFFORT`, `OPENARMS_DEMO_FAST_PATH`, `OPENARMS_HOST`, `PORT`, and for the bench `OPENARMS_BENCH`, `OPENARMS_FOLLOWER_PORT`, `OPENARMS_OVERHEAD_CAMERA`, `OPENARMS_OVERHEAD_PHOTO`, `OPENARMS_POUR_POSES`, `OPENARMS_SECONDS`, `OPENARMS_BENCH_CONFIRM`, `OPENARMS_PLACES`. The docstring at the top of `bench_lane.py` explains the bench ones.

Saved skills are tied to the exact simulator and lab source. After changing either, a seeded skill no longer applies and `run_demo_app.sh` seeds it again on start.

## 5. What to ignore

About a third of this repo is hackathon residue: superseded scenes, parallel experiments, evidence dumps and process documents. None of it should be deleted without checking, because tests and a few imports still reach into it. But do not read it to understand the product, and do not extend it.

| Path | What it is | Advice |
| --- | --- | --- |
| `simulation/isaac/` (95 MB) | An Isaac simulator attempt, parked during the hackathon | Ignore |
| `visual_assets/` (77 MB) | Scene and asset experiments | Ignore |
| `research/joseph/` (122 files) | Joseph's notes, evidence folders, a Notion export, an iPhone app | Ignore. The iPhone app is not part of the product |
| `bench_vision/` | A perception package with eight design documents. Four scene files import small parts of it | Do not extend. Do not delete without tracing the imports |
| `agentic/openarms_agent/` | The first agent design. `types`, `validator`, `runner`, `catalog` and `brain` are still used by the bench lane and firmware | Leave as is |
| `OPENARMS_SCENE=two_vessel` and `metered_dropper`, `OPENARMS_EXECUTION=mock` | Earlier scenes (water pour, pH dropper, mock pH). Kept as regression tests | Not the product. Keep the tests passing |
| `agentic/openarms_lab/smartivity.py`, `ui/lab/smartivity.*`, `simulation/openarms_sim/smartivity_*.py` | Joseph's separate Smartivity world (`OPENARMS_SMARTIVITY=1`) and video renderers. It does not go through consent | Not the product path. The recorded lab videos in `ui/student/media/` are Smartivity renders (origin not re-checked) |
| `agentic/openarms_lab/dilution.py`, `live_expert.py` | Imported only by tests and scripts | Likely removable; check first |
| `agentic/scripts/` other than `run_demo_app.sh`, `run_demo_suite.sh`, `seed_demo_skill.py`, `harness_benchmark.py` | Rehearsal and smoke scripts from earlier designs | Unverified, probably stale |
| `work/`, `recordings/`, `voice-lab-arm-outline.md`, `docs/superpowers/` | Old handoffs, a sample recording, the first project outline, an early plan | Historical |
| `pitch/` (73 MB) | Devpost copy, film source, gallery | Finished. Keep for the record |
| D1–D4 and R1–R6 codes, "lanes", "receipts", "ledger" | Hackathon coordination vocabulary | No longer in use |

A cleanup that moves this residue into one `archive/` folder would make the repo far easier to work in. It has not been done, because it touches imports and tests and deserves its own careful pass.

## 6. Known problems and unfinished work

1. **Planner without Devin is unproven.** See section 3. Fix this first.
2. **Bench voice APIError.** Not reproduced or explained. Start by running the server from a terminal and reading what Google returns. The bench voice configuration (system prompt, tools, transcription) differs from the bare connection that worked.
3. **Spoken yes/no on the bench starts real motion.** It has guards (whole utterance must be a plain yes, the question must have been open 1.5 s, Ollie must not be speaking) but was never tested with real audio or echo.
4. **One experiment per server.** The student app cannot switch experiments on a live server.
5. **Empty-beaker pour.** Commit `9203512` (allow pouring an empty beaker as a harmless mistake) was written against an older worker and conflicts with main. It is preserved on tag `archive/victor/integration-device-expert`, not applied. Main still refuses and offers a reset.
6. **Science copy** in `ui/student/labs.js` is unreviewed. Smartivity chemistry in the simulator is illustrative, not measured.
7. **Audience mismatch.** The student app is written for children using the Smartivity kit. `PROJECT_OBJECTIVE.md` and the research describe undergraduate teaching labs. Pick one before writing more copy.
8. **Stale numbers in the pitch material.** `research/victor/judge-cheatsheet.md` says 902 tests and that no real-arm test had happened.
9. **Not built:** Google Classroom or teacher features, a single experiment picker, user testing with disabled students.

## 7. Rules for working here

These are also in `AGENTS.md`, which Codex and Claude Code load automatically.

- Keep the six-step loop in section 1 intact. Exact consent, a deterministic executor, an independent observation and Stop are the product.
- Label every result as simulated, mock, real or unknown. A controller finishing is not a result.
- Never move the real arm unattended, never edit `calibration/`, never send simulator joint targets to the real arm.
- Never commit `.env`, keys, `outputs/` or `LeRobot/`.
- Run the test command in section 3 before pushing. Push only when Victor asks.
- Verify before stating. If something was not run, say so.

## 8. Git state

- `main` is the development branch. `old_main` pins the pre-handoff demo baseline at `5cce0e9`; the handoff commit changes documentation only. GitHub: `VictorJimenez3/OpenArms`.
- Every one of Victor's branches is preserved as an annotated tag `archive/<branch>` on GitHub (20 tags). Restore one with `git switch -c <name> archive/<name>`.
- Teammates' branches still exist on GitHub. Two hold one unmerged commit each: `origin/duc-fix-stale-tests` and `origin/codex/aerial-wrist-scan-video`.
- Main is not branch-protected yet.
- Extra worktrees still on Victor's Mac under `/Users/victor/OpenArms/`: `device-expert-smoke` (holds the unpushed dance commit `b24af22` and an older Python environment), `user-flow-ui`, `smartivity-align`, `harness-loop`, and three with uncommitted changes: `harness-candidate`, `harness-loop-v2`, `phrasing-experiment`. None is needed to develop on main.
- Outside the repo: `/Users/victor/OpenArms/openarms-film/deck/` (the pitch decks; v5 is current) and `/Users/victor/OpenArms/receipts/` (push notes and the archive index).

## 9. Which documents to trust

| Document | Trust |
| --- | --- |
| `HANDOFF.md`, `AGENTS.md` | Current |
| `README.md` | Public summary. Accurate in outline; its timing numbers are from a teammate's logged run |
| `ui/student/DESIGN.md` | Current for the student app's design and accessibility mapping |
| `docs/LAB_RUNBOOK.md` | Useful for the real-bench lane. Its opening sections describe older scenes |
| `simulation/README.md`, `simulation/SMARTIVITY.md`, `firmware/README.md` | Useful reference for the simulator and arm setup |
| `docs/INTERFACES.md`, `docs/EXPERT_MODELS.md` | Partly stale. The transport contract still holds; scene defaults and model status do not |
| `research/victor/` | Victor's research: user evidence, student flow, track notes. Good background, written before the build |
| `docs/ARCHITECTURE.md`, `PROJECT.md`, `FULL_SYSTEM_DELIVERY.md`, `TEAM_WORK_PLAN.md`, `MAIN_INTEGRATION.md`, `MAIN_BRANCH_LEDGER.md`, `WET_LAB.md`, `DEMO_SPEED.md`, `DEMO_CLEANUP.md`, `agentic/README.md`, `research/README.md`, `GLOSSARY.md`, `PROJECT_OBJECTIVE.md` | Historical. Hackathon plans and team process |

## 10. Where the story came from

Product decisions made during the hackathon, for context:

- The student app is a separate front end (`ui/student`) so it never overwrote Joseph's lab client.
- Voice is the emphasised input, with typing, keyboard, switch and eye-gaze paths kept as equals, because some conditions that limit hand use also affect speech.
- The plan card shows a plain sentence first and the exact plan underneath, because the exact plan is what the student consents to.
- Ask Ollie hints and asks back instead of giving answers, and refuses off-topic requests.
- The dance and wave feature was removed from main at Victor's request.
