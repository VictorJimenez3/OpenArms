# Choose the expert

One host task loop supports Codex and Claude. The default remains **Sol, medium**. Models receive the same frozen images, context and host-tool catalog. They return decisions; the host retains validation, exact consent, STOP, execution and skill promotion. There is no automatic model fallback.

| Profile | CLI / requested model | Current evidence |
| --- | --- | --- |
| `sol` | Codex / `gpt-6.1-sol` | Actual image/tool and simulation runs; default medium. |
| `astra` | Codex / `gpt-6-astra` | Listed in local catalog; adapter checks, no live run yet. |
| `opus` | Claude / `opus` | Offline transport checks; needs CLI, independent API authentication and live qualification. |
| `sonnet` | Claude / `sonnet` | Same qualification gap as Opus. |
| `fable` | Explicit provider/model binding | Not in this Mac’s catalog. No guessed ID or silent substitution. |

## Start and hot swap

From the repository root, create a host-owned selection file:

```sh
.venv/bin/python -m agentic.openarms_lab.expert_profiles sol --config outputs/expert.json
OPENARMS_EXECUTION=mujoco OPENARMS_EXPERT_CONFIG="$PWD/outputs/expert.json" PORT=8010 .venv/bin/python -m agentic.openarms_lab
```

In another terminal, change the next task’s model without restarting the app:

```sh
.venv/bin/python -m agentic.openarms_lab.expert_profiles astra --effort medium --config outputs/expert.json
```

Use `opus` or `sonnet` the same way after configuring Claude. Existing tasks keep their queued profile through planning, confirmation and execution checkpoints. A new clarification request is a new task. Writes are validated and atomic; a missing/invalid configured file produces an explicit error for new expert work. The config contains no secrets and has no public HTTP editor.

For an operator-verified pinned model, add `--provider codex|claude --model EXACT_ID`. Fable requires both; the code cannot establish access to an unknown ID. Sol/Astra retain their verified identifiers.

Without a config file, `OPENARMS_EXPERT_PROFILE` and `OPENARMS_EXPERT_EFFORT` select the process defaults. `OPENARMS_CODEX_EXECUTABLE` and `OPENARMS_CLAUDE_EXECUTABLE` independently select the CLI paths, so switching providers never sends Claude flags to Codex. `/api/health` reports the selected configuration; it does not claim authentication or live qualification.

## Authentication and evidence

Codex uses its own authenticated CLI account. The isolated Claude adapter uses **bare mode when `ANTHROPIC_API_KEY` is set**; without a key it uses the person's own logged-in Claude CLI with the same isolation (no tools, MCP servers, settings sources or hooks). Do not copy Codex credentials. The logged-in path passed a live image-planning run on the demo bench (`claude-opus-5-5`, [evidence](../research/duc/demo-bench-integration.md)). An unsupported CLI fails explicitly instead of falling back to a text-only model or enabling autonomous tools.

Receipts separate `requested_model` from `actual_model`. When CLI telemetry omits a resolved ID, `actual_model` is null and `model_verified` is false. Effort is requested configuration, not measured reasoning. For an alias, the first reported concrete model is pinned for subsequent calls. Reported substitutions are rejected. Provider errors are sanitized; raw credentials/diagnostics never enter the notebook.

All existing expert rehearsal scripts accept `--expert-profile`, `--expert-config`, `--reasoning-effort` and `--executable`: `full_loop_rehearsal.py`, `improvement_rehearsal.py`, and the retained `codex_expert_smoke.py` name. Rehearsals record the provider actually used. Offline fake-CLI tests verify contracts and cancellation, not live model quality, voice or physical success.

Implementation: `ConfiguredExpert` snapshots selection; `CodexExpert` owns the shared bounded image/tool loop; `ClaudeExpert` changes only CLI transport. Both disable built-in execution/tools; only host tools may run. Keep this seam instead of adding another dispatcher.

Sources: [Claude CLI flags](https://code.claude.com/docs/en/cli-reference), [bare mode](https://code.claude.com/docs/en/headless), [streaming image input](https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode), [model aliases](https://code.claude.com/docs/en/model-config). Local Codex catalog checked November 14, 2026; listing is not proof of current account access.
