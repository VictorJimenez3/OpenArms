# Choose the expert

One host task loop supports Codex and Claude. The default remains **Sol, medium**. Models receive the same frozen images, context and host-tool catalog. They return decisions; the host retains validation, exact consent, STOP, execution and skill promotion. There is no automatic model fallback.

| Profile | CLI / requested model | Current evidence |
| --- | --- | --- |
| `sol` | Codex / `gpt-6.1-sol` | Actual image/tool and simulation runs; default medium. |
| `astra` | Codex / `gpt-6-astra` | Listed in local catalog; adapter checks, no live run yet. |
| `opus` | Claude / `opus` | Live demo-bench run on Duc's logged-in CLI resolved to `claude-opus-5-5`; each device needs its own authorized login or API key. |
| `sonnet` | Claude / `sonnet` | Offline transport checks; needs an authorized Claude login or API key and live qualification. |
| `fable` | Explicit provider/model binding | Not in this Mac’s catalog. No guessed ID or silent substitution. |

## Start and hot swap

From the repository root, create a host-owned selection file:

```sh
.venv-lab/bin/python -m agentic.openarms_lab.expert_profiles sol --config outputs/expert.json
OPENARMS_EXECUTION=mujoco OPENARMS_EXPERT_CONFIG="$PWD/outputs/expert.json" PORT=8010 .venv-lab/bin/python -m agentic.openarms_lab
```

In another terminal, change the next task’s model without restarting the app:

```sh
.venv-lab/bin/python -m agentic.openarms_lab.expert_profiles astra --effort medium --config outputs/expert.json
```

Use `opus` or `sonnet` the same way after configuring Claude. Existing tasks keep their queued profile through planning, confirmation and execution checkpoints. A new clarification request is a new task. Writes are validated and atomic; a missing/invalid configured file produces an explicit error for new expert work. The config contains no secrets and has no public HTTP editor.

For an operator-verified pinned model, add `--provider codex|claude --model EXACT_ID`. Fable requires both; the code cannot establish access to an unknown ID. Sol/Astra retain their verified identifiers.

Without a config file, `OPENARMS_EXPERT_PROFILE` and `OPENARMS_EXPERT_EFFORT` select the process defaults. `OPENARMS_CODEX_EXECUTABLE` and `OPENARMS_CLAUDE_EXECUTABLE` independently select the CLI paths, so switching providers never sends Claude flags to Codex. `/api/health` reports the selected configuration; it does not claim authentication or live qualification.

## Authentication and evidence

Codex uses its own authenticated CLI account. The isolated Claude adapter uses **bare mode when `ANTHROPIC_API_KEY` is set**; without a key it uses the person's own logged-in Claude CLI with the same isolation (no tools, MCP servers, settings sources or hooks). Do not copy Codex credentials. The logged-in path passed a live image-planning run on the demo bench (`claude-opus-5-5`, [evidence](../research/duc/demo-bench-integration.md)). An unsupported CLI fails explicitly instead of falling back to a text-only model or enabling autonomous tools.

Receipts separate `requested_model` from `actual_model`. When CLI telemetry omits a resolved ID, `actual_model` is null and `model_verified` is false. Effort is requested configuration, not measured reasoning. For an alias, the first reported concrete model is pinned for subsequent calls. Reported substitutions are rejected. Provider errors are sanitized; raw credentials/diagnostics never enter the notebook.

All existing expert rehearsal scripts accept `--expert-profile`, `--expert-config`, `--reasoning-effort` and `--executable`: `full_loop_rehearsal.py`, `improvement_rehearsal.py`, and the retained `codex_expert_smoke.py` name. Rehearsals record the provider actually used. Offline fake-CLI tests verify contracts and cancellation, not live model quality, voice or physical success.

Implementation: `ConfiguredExpert` snapshots selection; `CodexExpert` owns the shared bounded image/tool loop; `ClaudeExpert` changes only CLI transport. Both disable built-in execution/tools; only host tools may run. Keep this seam instead of adding another dispatcher.

## Victor's device: verified typed simulator smoke

November 14, 2026; baseline `origin/integration` at `fcce232`; isolated worktree `/Users/victor/OpenArms/device-expert-smoke`, branch `victor/device-expert-smoke-2026-11-14`. Scope: device setup and one typed app smoke for D3 / R2,R4,R5 (existing issues #10/#19), consuming Duc's demo-bench integration. No runtime, simulator, calibration, speech or phrasing changes.

Diagnosis on this device: Claude Code 2.1.296 was installed, but `claude auth status` reported `loggedIn: false`, and `ANTHROPIC_API_KEY` was unset. The real OpenArms Claude adapter could not complete an Opus connection check. Duc's login is not shared automatically. Codex CLI 0.169.0 reported `Logged in using ChatGPT`, and the existing OpenArms Codex adapter successfully returned structured output when requesting `gpt-6.1-sol`, medium. No model comparison or new transport was needed.

The app and CLI run on Victor's Mac; model inference is served remotely by OpenAI through the Codex CLI's existing authenticated ChatGPT account. Usage draws on that account's allowance, not Duc's Claude account or a newly provisioned API account. No teammate machine, tunnel or separately running expert service is required. Keep this Mac online and the Python server running. The CLI login status does not identify the billing owner or establish remaining quota; no dollar cost is inferred.

One-time setup from this worktree's root, already completed here:

```sh
uv venv --python 3.12 .venv-lab
uv pip install --python .venv-lab/bin/python -r agentic/requirements-lab-dev.txt -e 'simulation[dev]'
codex login status
.venv-lab/bin/python -m agentic.openarms_lab.expert_profiles sol --effort medium --config outputs/device-expert-smoke/expert.json
```

Restart from this worktree's root using the existing selection and the usability-follow-up notebook (the original `app/` notebook is retained):

```sh
OPENARMS_HOST=127.0.0.1 OPENARMS_BENCH=0 \
OPENARMS_EXECUTION=mujoco OPENARMS_SCENE=demo_bench \
OPENARMS_DATA_DIR="$PWD/outputs/device-expert-smoke/rigidity-app" \
OPENARMS_EXPERT_CONFIG="$PWD/outputs/device-expert-smoke/expert.json" \
OPENARMS_CODEX_EXECUTABLE=/Users/victor/.local/bin/codex \
PORT=8010 .venv-lab/bin/python -m agentic.openarms_lab
```

Open `http://127.0.0.1:8010/`, expand **Type instead**, and submit: “Please pour the beaker from A into C, return the beaker to A and go HOME, then check the result.” Review the exact proposal and click **Confirm this action** once. For a subsequent trial use **Start a new notebook entry**. Use a different, fresh `OPENARMS_DATA_DIR` when a new cold-model test is required; do not delete the retained notebook.

Verified through the ordinary browser app, not a standalone planner: one typed request, three planning calls, a presented valid proposal with zero motion before confirmation, one confirmation and one completed `add_sample(A,C,1)` receipt. Three further model calls handled the execution checkpoint and completion. The controller recorded donor return, HOME, 710 frames and 23.67 seconds of simulated motion. A separately captured post-action image produced: “The beaker at A looks empty and is back on its mark; the container at C shows red liquid.” The app displayed **Task complete** and **OBSERVED · SIMULATED**. All four declared observation checks passed.

Requested model: `gpt-6.1-sol`, medium, provider `openai_codex_cli`. The six app calls reported no resolved model ID: `actual_model=null`, `model_verified=false`. This is successful live-provider evidence, not independent verification of the underlying model identity. Receiver red colour is configured before the pour, not evidence of chemistry or measured transfer volume. Physical dispatch remained disabled.

The app's subsequent automatic reusable-skill admission was **rejected**, separately from the successful student action: `routing=false`; outcome, unknown, consent, STOP and unchanged-source gates passed. `routing.json` records that the generated retrieval example did not match. Receipt: `app/evaluations/ddf000673f1d420484998d29316e7823/receipt.json` under the local evidence directory. These evaluation replays use no model and are separate from the single confirmed student action. No warm-reuse claim is made, and this chat did not alter routing, retrieval examples or the evaluator. App-call usage was 182,383 input tokens (91,136 cached) and 1,888 output tokens; the separate connection check is not included.

Local evidence is retained under ignored `outputs/device-expert-smoke/`: connection checks, `before-confirmation.json`, `after-completion.json`, `events.json`, `summary.json`, `proposal.png`, `completed.png`, and the app's SQLite notebook/rendered media. Session `1df5b73e-782a-45cd-bddd-a0bad5a1cdd7`; task `8393999e-796f-4e43-b420-6665cfcb1075`. Focused verification passed 72 tests:

```sh
PYTHONPATH=agentic:simulation:. .venv-lab/bin/python -m pytest -q \
  agentic/tests/test_demo_bench_runtime.py agentic/tests/test_expert_profiles.py \
  agentic/tests/test_codex_expert.py agentic/tests/test_lab_api.py \
  --import-mode=importlib -o asyncio_mode=auto
```

No credential is missing for this verified Sol path. Opus on this device still requires an authorized interactive `claude auth login`, or an independently funded `ANTHROPIC_API_KEY`. Never copy a teammate's credentials. Gemini Live was unconfigured on this worktree and was not exercised or changed; speech/phrasing experiments belong to the other chat. This is a single automated browser-operated simulator smoke on the actual Mac, not a physical, voice, repeated-reliability or D4 qualification.

### Usability follow-up on the same device

After the first smoke, Victor reported rigid responses in session `100bbe9e-79e1-45e8-be45-64e2c27e3ba9`. Read-only inspection of its four requests found that the expert asked for sample selection even though `add_sample` uses one scene-bound prepared beaker. It also returned a useful clarification in `payload.question`, but the task loop displayed the technical `summary` and reused that summary as the previous question. No chemistry hazard or failed authentication caused those replies. Literal cup nesting remains unsupported.

Victor confirmed that the separate phrasing chat had finished. Its durable handoff is `/Users/victor/OpenArms/phrasing-experiment/research/victor/phrasing-fixes-2026-11-14/README.md`. This worktree now includes that lane's completed route/correction, single-repeat, conversation-routing, repeated-slot matching and admission-scope changes; the source worktree and its evidence remain unchanged. Additional fixes scope the sample-choice instruction to operations that actually require a selectable sample, and display a bounded nonempty clarification question when provided. Missing/invalid questions retain the prior summary fallback.

Local handoff branch: **`victor/integration-device-expert`**, based on `origin/integration` at `fcce232`. Prepared by **Devin for Victor**, including the completed phrasing lane's changes and this chat's device connection, clarification fixes, tests and startup documentation. The worktree remains `/Users/victor/OpenArms/device-expert-smoke`; `main`, the other worktrees and remote branches are not switched or updated. Local worktrees share this branch's Git history, so another session can inspect it without changing its checkout:

```sh
git log -1 victor/integration-device-expert
git diff origin/integration...victor/integration-device-expert -- agentic docs/EXPERT_MODELS.md
```

Consuming the changes in a different branch still requires a deliberate merge or cherry-pick coordinated with that branch's owner. The local commit does not imply team integration, independent review, a push or physical acceptance. Local ignored evidence stays at the paths below rather than being bundled with credentials, notebooks or recordings into Git.

The new tests first failed on the hidden question and the inappropriate sample instruction (`rigidity-red.log`: 2 failed, 41 passed). After the fixes, all 43 focused checks passed. Full agentic/simulation verification passed **686 tests**, exit 0, with 11 fixture-class collection warnings and an existing asyncio fixture-scope deprecation warning; audio unit checks passed **5 tests**. Logs: `rigidity-full-tests.log`, `rigidity-green.log`, and `rigidity-audio-unit.log` under `outputs/device-expert-smoke/`.

The restarted normal app accepted “Pour what's in the blue-ring beaker into the yellow-ring container.” with no selected condition. Three live planning calls produced the correct A-to-C proposal, which waited with zero dispatches before confirmation. One confirmation led to one completed simulated action, donor return, HOME and three passing independent observation checks. Session `a8753645-cc4c-4472-957c-531344e7a9e8`; task `373cbe36-00e1-4e15-bbd4-b83b0abc37cb`; scope `demo-bench-56aeeafc1452036e`. Requested model remains Sol/medium, resolved identity unreported. The evidence is retained separately as `rigidity-before-confirmation.json`, `rigidity-after-completion.json`, `rigidity-proposal.png`, `rigidity-completed.png` and `rigidity-app/`. Subsequent reusable-skill admission **promoted** this candidate; routing, outcome, unknown, consent, STOP and unchanged-source gates passed (`rigidity-app/evaluations/45f303ce060b4771b5f8eb9429fa9a4d/receipt.json`). Initial admission is not a substantive measured improvement, and no repeated reliability or warm-reuse claim follows from this single request. The correlated test/deployment receipt is `outputs/device-expert-smoke/rigidity-followup-receipt.json`.

The app is still limited to its connected one-pour routine. Numeric cup/volume ambiguity, some spatial descriptions and unresolved negation can still require clarification or fail closed; this is not unrestricted natural-language manipulation. No new destinations, cup nesting, physics, chemistry, calibration or physical controls were added. Confirmation, STOP, fresh-evidence checks and deterministic bounds remain in force. Restarting with this source changes admission scope; old skills must not inherit authorization. The prior notebook is preserved, while the restarted app uses `rigidity-app/`; reload an old browser tab to establish a fresh session.

The separate session-coordination investigation checked the installed Devin documentation: local sessions support listing/resume and `--export`, but no documented local-session `send` command. A shared handoff inbox surfaced by project-scoped `.devin/hooks.v1.json` is a possible follow-up, not an installed communication service. Never write Devin's internal sessions database or resume another running session to inject messages. Finished work in one worktree does not automatically update another worktree or its running server.

Sources: [Claude CLI flags](https://code.claude.com/docs/en/cli-reference), [bare mode](https://code.claude.com/docs/en/headless), [streaming image input](https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode), [model aliases](https://code.claude.com/docs/en/model-config). Local Codex catalog checked November 14, 2026; listing is not proof of current account access.
