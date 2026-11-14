# agentic/

The agent harness: the LLM "brain" turns a student's words into a short plan, local code checks it, the teacher approves it, and the arm runs it. Design: [research/duc/harness.md](../research/duc/harness.md). Owner: Duc.

## Setup

```bash
conda create -y -n openarms python=3.12
conda activate openarms
pip install -r agentic/requirements.txt
echo "ANTHROPIC_API_KEY=..." > agentic/.env   # ignored by git
```

Run everything from the repo root as modules, for example `python -m agentic.scripts.check_validator`.

## Layout

| File | What it does | Lane |
|---|---|---|
| `contracts/*.example.json` | One example of each shared shape; the team agrees on these in `docs/INTERFACES.md` | master |
| `openarms_agent/types.py` | Key names for those shapes, the `ArmPort` protocol, `ArmError` | master |
| `openarms_agent/catalog.py` | Plan actions (`add_sample`, `wait`, `look`) and `expand()` into arm steps | core |
| `openarms_agent/validator.py` | `validate(plan, state, stations)`: fixed rules, one readable reason | core |
| `openarms_agent/mock_arm.py` | Fake `ArmPort` for development | core |
| `openarms_agent/runner.py` | Runs approved steps on an `ArmPort`; stops on error or STOP; never retries | core |
| `openarms_agent/notebook.py` | Session log to `outputs/sessions/<id>.json` | core |
| `prompts/brain_system.md`, `openarms_agent/prompting.py` | The brain's system prompt | brain |
| `openarms_agent/tools.py`, `openarms_agent/brain.py` | Claude tools and the turn loop | brain |
| `relay_adapter.py`, `server.py`, `preview.py` | Links to the voice relay, teacher UI and sim | api (later) |

The real `ArmPort` (saved-pose replay on the SO-101) is drafted in `firmware/openarms_executor/` for Joseph to review.

Files marked "M0 stub" return canned values so lanes can run before the real code lands.

## Simulation-first skill harness

Start the offline text harness from the repository root with Python 3.12 or later.

```sh
python -m agentic.scripts.skill_harness --bench block
```

Enter `Move the block from A to B`. Read the expanded preview and enter
`confirm <plan_id>` using the ID it returned. The receipt reports the modeled
placement and separately leaves the experiment observation empty. Repeating the
same confirmation does not dispatch again. Use `--bench mandarin` for a named
mandarin, or `--bench liquid` for `Add two portions from A to C then wait 2 seconds
then look at C`. Wait is modeled in this CLI. Look supplies no camera data.
`predict TEXT` and `observe TEXT` keep the student's own words in the notebook.
`--session NAME` reloads the notebook while starting a fresh simulated bench.
`history` shows the saved entries. The default data directory is
`outputs/skill-harness`.

Recognized commands run through the catalog and state validator with zero
provider calls. Novel text requests clarification by default. To enable a single
optional cold call, install `agentic/requirements.txt`, configure the Anthropic
key as above, and add `--planner claude --model MODEL_NAME`. After inspecting and
confirming a cold plan and reviewing its successful receipt, use
`promote <plan_id>` to save a versioned exact phrase. Skill reuse is bound to
the catalog version, backend mode, station configuration, and full starting
state. Reuse revalidates the plan and still requires confirmation. The local
registry and notebook are single-writer files. A restart reloads history and
skills. Pending plan IDs and promotion eligibility expire on restart.

### Integration contract

- `SkillHarness.propose(text)` returns a status and reason or an immutable
  server-held `Plan` preview, expanded steps, expected state, and opaque plan ID.
  A revised request invalidates pending confirmation.
- `confirm(plan_id)` consumes a matching preview once and compares current state
  to the validated snapshot before the first step. The existing catalog and
  runner execute through `ArmPort`. The backend must provide complete and
  truthful state snapshots. State is checked after each step, and failure latches
  the simulated bench without retry.
- `stop()` invalidates pending motion and bypasses planning. During a run it
  requests a hold between steps. The synchronous terminal demo can accept text
  only when it is at the prompt. The API supports STOP from a separate thread.
- The receipt distinguishes controller status, state and observation. Missing
  evidence remains empty. The checkpoint log is local audit context. It does
  not restore or replay actions.
- Keep Joseph's current `TransferRunner` contract at the physical boundary.
  A future adapter should translate a validated, confirmed fixed mandarin
  A-to-B transfer to the same `plan_id`, `object`, `source`, and
  `destination` fields in [INTERFACES.md](../docs/INTERFACES.md). Use one runner
  authority and retain exact-ID operator authorization, STOP, and independent
  placement evidence. Validate this with a fake runner before hardware work and
  keep the working A-to-B flow as a regression baseline.

### Tests and optional MuJoCo preflight

```sh
uv run --python 3.12 --with pytest --with-requirements agentic/requirements.txt python -m pytest -q agentic/tests
uv run --python 3.12 python -m agentic.scripts.benchmark_harness --repeats 50
uv run --python 3.12 python -m agentic.scripts.benchmark_harness --baseline --repeats 50
```

The benchmark uses a zero-delay mock and a cold planner fixture. It reports
route checks, expected outcomes, postconditions, and p50/p95/max. Local
command-to-receipt assumes immediate confirmation and excludes human response,
live model calls, physics, and hardware times.

In a separate worktree for Stefanie's `origin/stefanie/simulation` at
`502e4e8042c756b55ebc3f9fbd885ab4dabd697e`, install its optional simulator and
test dependencies. Run the harness from the skill worktree with that interpreter.

```sh
git worktree add --detach ../OpenArms-stefanie 502e4e8042c756b55ebc3f9fbd885ab4dabd697e
(cd ../OpenArms-stefanie/simulation && uv sync --python 3.12 --extra dev)
../OpenArms-stefanie/simulation/.venv/bin/python -m agentic.scripts.benchmark_harness --physics --repeats 20
../OpenArms-stefanie/simulation/.venv/bin/python -m agentic.scripts.skill_harness --mujoco
```

The block adapter uses headless MuJoCo kinematics and contact checks, scripted
grasp/release and provisional pose/joint mapping. It checks the simulator's
reported block placement against the validated target. A pass is a preflight
result. Confirmation still runs the deterministic mock. Mandarin geometry,
dynamic grasping, liquid science, and Isaac Sim execution need separate work.
