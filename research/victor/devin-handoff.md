# OpenArms handoff for Devin

Work in `OpenArms-student-loop` on `victor/agentic-student-loop`. Victor owns the shared AI harness and student loop in `agentic/`. On November 14 he asked to implement the agentic system first using text, keep speech lower priority, then integrate and rapidly evaluate the teammate's runnable simulator when available. His project direction is one supervised live SO-101 activity and several simulation examples. Use Victor's handoff, current branch code and verified runs to resolve stale information. Joseph's issue comments and mentions are outside this assignment. The old standalone 20 mL dilution video is historical and supplies no requirement for the next setup.

Read in this order: [AGENTS](../../AGENTS.md), [project objective](../../PROJECT_OBJECTIVE.md), [Victor's student/agent flow](student-and-agent-flow.md), [implementation plan](../../docs/superpowers/plans/2026-11-14-openarms-agentic-system.md), and [interfaces](../../docs/INTERFACES.md). Treat the flow document's baseline table as historical. The newer implementation and this receipt describe the current branch. Use the existing app, expert adapters, registry, observer and executor. Keep the student in charge of one action at a time. Questions, corrections, observable results and the student's next choice belong to the same session. Prediction and reflection are optional.

## What is implemented

- PR #25 at `4f9c3ec` is included in Victor's branch. It supplies shared conversation handling and Gemini Live speech when a key is configured. The local text draft was reconciled with that implementation. A sample correction now preserves the original task intent and the validated replacement sample. Scope changes revoke earlier approval. The approved proposal remains a prerequisite for execution.
- `task_loop.py` validates the current setup, typed arguments, and known cases of negated, unsupported or compound requests. This is a bounded fixture guard. General natural-language request coverage remains open. The executor checks readiness. The independent observer checks the outcome. A failed controller or failed evidence check cannot become successful through an expert `complete` reply. After motion, the expert may propose another observation under fresh consent while preserving the earlier controller receipt and approved outcome checks. It cannot dispatch the action again.
- `contracts.py` exposes the simulator and observation interfaces. The app still permits only its existing synthetic and indicator MuJoCo backends. `openarms_agent/`, old lab demos and standalone previews have historical or separate entrypoints. Keep them out of the active app path.

## Recorded evidence

These real-provider rehearsals ran at intermediate revisions of this implementation. The final test suite covers current code. The expert requested Codex `gpt-6.1-sol` at medium effort. CLI telemetry did not identify the actual model.

| Run | Observed result | Local receipt |
| --- | --- | --- |
| Real expert, synthetic images, clear versus obscured checkpoint | Clear run completed. The obscured run returned `UNKNOWN`, then the expert requested the secondary view and proposed an observation-only revision. Fresh confirmation produced a readable result. Both runs dispatched one action. A both-obscured control remained `UNKNOWN`. Total time was 72.8 s clear and 108.4 s obscured for this pair. | `/tmp/openarms-evidence.BCbvlG/results/summary.json`, plus `clear/state.json` and `adaptive/state.json` in that directory |
| Real expert, current indicator MuJoCo cold and warm | On scope `mujoco-2f834c3ed2930865`, the same skill version and bindings ran with 7 cold and 0 warm expert calls. Time to proposal was 47.67 s cold and 0.62 s warm. Controller time was about 2.17 s on both runs. Both outcomes came from rendered pixels. | `/tmp/openarms-scoped-mujoco.40mtS8/results/summary.json`, `cold.json`, `warm.json` |
| Real expert, mock baseline for the next improvement run | A fresh mock session admitted a skill and reused it with 7 cold and 0 warm expert calls. Use this baseline for the synthetic improvement script while the files are available. | `/tmp/openarms-mock-baseline.aIZIk5/results/summary.json` |
| Real expert synthetic skill revision | The expert added secondary-view recovery. Replay improved from 9 to 12 recovered cases out of 24 under the same frozen suite. This exploratory run reused a definition authored during the MuJoCo rehearsal. The updated script requires a mock-admitted baseline so rehearsals cannot inherit a different setup's admission. | `/tmp/openarms-improvement.hMfctN/results/summary.json` |
| Teammate preview canary | `stefanie/joint-map` at `dc3fd3e` ran `uv run --project . python -m openarms_sim --setup kit --from A --into C` in a temporary archive. It rendered a 20.7 s preview with a qualitative fizzing/foam prediction. The poses are placeholders and the joint mapping is unmeasured. This branch does not expose independently observed execution through the app. `duc` at `21cf9fa` contains an older preview path. | `/tmp/openarms-stefanie-canary.lxhyZL/simulation/outputs/previews/b44d009b593ad879.json` and matching `.mp4` |

Local `/tmp` artifacts may expire. The reproduction commands and the results above travel with the repo. The latest full Python run passed 539 tests. Browser fixtures passed 36 checks and browser audio passed 5. No Gemini key was available in the active environment, so this session verified speech behavior with fixtures and used existing provider evidence from PR #25. Mac and iPhone audibility remain open. No physical motion was authorized.

## Where to resume

1. Verify the branch and run the current suites. Start the existing app in `mock` or `mujoco` mode with a fresh data directory. Run an authenticated typed request, follow-up, exact confirmation, observed result, then STOP as a separate attempt. The [runbook](../../docs/LAB_RUNBOOK.md) gives the server command. `test_student_simulator_trace.py` exercises the authenticated path through real MuJoCo with a deterministic test expert. The reproducible real-provider script uses the same `Lab` runtime.
2. When the new simulator revision is available, inspect its documented entrypoint and evidence first. Require named typed operations, setup revision, reset/readiness, bounded dispatch, interrupt/STOP, and independent evidence with explicit provenance. Attach one supported action to the existing app in Victor's scope. Exercise clear, ambiguous, failed and cancelled cases, then compare cold and warm with the same setup and request. Change one measured bottleneck or failure mode and rerun the same inputs. Keep prediction and independent observation distinct. The published preview is available for rehearsal and documentation while the executable simulator contract is pending.
3. When Gemini credentials are available, run the existing speech rehearsal using the same app and consent path. Use Victor's approved bench and a separate supervised qualification for physical operation. Check `git status` and current remotes on handoff. The handoff is in Victor's local checkout. A separate machine needs the same branch contents before continuing.

## Reproduce from the repo root

```bash
export PYTHONPATH=agentic:simulation:.
uv venv --python 3.12 .venv-lab
uv pip install --python .venv-lab/bin/python -r agentic/requirements-lab-dev.txt -e 'simulation[dev]'
.venv-lab/bin/python -m pytest agentic/tests simulation/tests --import-mode=importlib -o asyncio_mode=auto -q
.venv-lab/bin/python agentic/scripts/student_decision_rehearsal.py --out outputs/decision-rehearsal
.venv-lab/bin/python agentic/scripts/full_loop_rehearsal.py --execution mujoco --out outputs/mujoco-cold-warm
.venv-lab/bin/python agentic/scripts/full_loop_rehearsal.py --execution mock --out outputs/mock-cold-warm
.venv-lab/bin/python agentic/scripts/improvement_rehearsal.py --baseline outputs/mock-cold-warm --out outputs/mock-improvement
```

Reuse an existing `.venv-lab` if present. Each rehearsal needs a fresh output directory. Run the provider-free checks first to conserve account usage. The real-expert scripts use the local authenticated CLI and accept `--expert-profile` and `--expert-config`. Each provider uses its own local credentials.

Suggested prompt for Devin or Codex:

> Continue Victor's OpenArms work on `victor/agentic-student-loop`. Read `research/victor/devin-handoff.md` and its linked plan and project objective. Start at the first pending step whose prerequisites are available. Use text first, keep the existing session, expert, and skill registry, and prove the full request-to-observation path on one supported action. Confirm which simulator revision you are testing and report the evidence gaps. Preserve exact student consent and direct STOP.
