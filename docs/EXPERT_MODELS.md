# Bounded expert providers

Issue #19/#9/#10; R2–R6; D3/D4. This changes provider compatibility for the existing
host task loop. Consent, STOP, registry, evaluator and physical-disabled execution
remain host responsibilities. No Gemini calls or replacement runtime are added.
The integrator must wire application construction and health; app.py/runtime.py
are deliberately outside this change. Parent review is required before integration.

`CodexExpert` owns the shared bounded image/host-tool loop and canonical reply
validator; `ClaudeExpert` inherits it and replaces only CLI transport. Both receive
identical context, frozen image bytes and declared host tools. Tools are JSON
decisions consumed by the host; neither provider gets robot connections or a shell.
Invalid plan validation receipts return to the same expert within its call budget.

| Profile | Provider | Requested model | Qualification |
| --- | --- | --- | --- |
| sol (default) | codex | gpt-6.1-sol | Present in both local Codex caches, default medium preserved |
| astra | codex | gpt-6-astra | Present in both local Codex caches; no new live run |
| opus | claude | opus | Documented alias; CLI absent, offline tested only |
| sonnet | claude | sonnet | Documented alias; CLI absent, offline tested only |
| fable | explicit binding required | no inferred ID | Absent from local Codex catalog; unconfigured fails closed |

Cache verification used `~/.codex/models_cache.json` and
`~/.codex-second/models_cache.json` on November 14, 2026. Catalog presence does not
establish current account access. Fable is not guessed even if another provider's
online documentation lists an alias. An operator must supply a real ID/provider.
No model fallback is requested; unexpected reported model substitution is rejected.
Sol/Astra bindings cannot override their verified identities.

## Host integration

```python
from openarms_lab.expert_profiles import ConfiguredExpert, write_config

expert = ConfiguredExpert(data_dir / 'expert', artifact_roots=[scene.artifact_dir],
                          config_path=operator_config_path)
# Pass expert=expert to the existing Lab constructor.
health = expert.describe()  # safe metadata; no provider calls or secrets
write_config(operator_config_path, {'profile': 'astra', 'reasoning_effort': 'medium'})
```

No config path means the backward-compatible Sol/medium default. An explicitly
provided file must exist and parse; missing, invalid or unsupported configuration
fails closed for new expert work. Files contain only profile/bindings/effort;
executables and injected test transports are host constructor arguments.
`write_config` validates and uses a private temporary file plus atomic replacement.
Restrict filesystem access to the operator; there is no HTTP configuration endpoint.

Pin Opus/Sonnet or bind Fable explicitly, using an operator-verified ID in place of
the placeholders below:

```json
{"profile":"opus","bindings":{"opus":{"provider":"claude","model":"OPERATOR_VERIFIED_PINNED_ID"}},"reasoning_effort":"medium"}
```

```json
{"profile":"fable","bindings":{"fable":{"provider":"claude","model":"OPERATOR_VERIFIED_REAL_FABLE_ID"}},"reasoning_effort":"medium"}
```

These are schema examples, not runnable model recommendations. `provider` is
`codex` or `claude`; Fable without a binding returns `unsupported_profile` and a
binding to an alias returns `unsupported_model`. Provider rejection of a supplied
ID never selects another profile.

The existing TaskLoop saves `expert.snapshot()` when a task is queued. It calls
`bind(task_id, snapshot)` before expert work and releases on terminal status or
cancellation. Waiting for confirmation retains the selection. All checkpoint and
follow-up calls use that original adapter. The resolved Claude ID, when reported,
is pinned for later calls in the same task. Separate clarification tasks take a
new snapshot. Saved tasks retain their configuration record; runtime restart
recovery continues to require existing preparation rules.

Direct callers can use `bind`, `run` and `release` themselves. Call `release` once
the task ends; task IDs supplied to `run` deliberately persist through multiple
phases. Calls without a task ID are ephemeral. A router-wide semaphore preserves
the default single expert concurrency across different profiles.

`describe()` reports configuration/executable availability, never authenticated
readiness. `authentication_verified` and `live_qualified` remain false until
external qualification. Result receipts include `provider`, `requested_model`,
`model`, `actual_model`, `model_verified`, `reasoning_effort`, `effort_source`,
usage/calls/timing and actual host receipts. `model` is the reported actual ID when
available and otherwise the requested ID; `actual_model=null`/`model_verified=false`
must not be represented as independent resolution evidence. CLI effort is requested
configuration (`effort_source=requested`), not measured reasoning or proof that the
provider honored it. Codex telemetry may omit model identity. Usage reflects
provider-reported integer counters, not an estimated bill.

## Claude transport and qualification boundary

The [official CLI reference](https://code.claude.com/docs/en/cli-reference) describes
print/stream JSON, schema output and tool restrictions. This transport uses
`--tools ''`, denies tools, and supplies an empty strict MCP configuration.
Unsupported flags or missing structured output stop the task; there is no text-only
fallback. Schema formatting via `StructuredOutput` is not a host action.

The [official streaming input example](https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode)
provides base64 image content blocks. Those blocks carry the same host-validated
PNG/JPEG/WebP bytes used by Codex. The combination with CLI stream input still needs
qualification on the installed Claude version; fake CLI tests only verify the wire
contract and failure behavior.

[Official bare-mode documentation](https://code.claude.com/docs/en/headless)
says bare mode skips customization discovery and does not read subscription OAuth
or keychain credentials. This adapter therefore requires an independently supplied
`ANTHROPIC_API_KEY`; it does not copy Codex credentials and does not currently
support subscription-only authentication. No provider key or raw diagnostic is
returned in receipts. Environment forwarding is allowlisted separately by provider.

[Official model configuration](https://code.claude.com/docs/en/model-config)
documents Opus/Sonnet aliases and explicit model IDs. Their online alias targets
can change. Requested aliases and telemetry-resolved identities stay separate.

Claude Code was absent during implementation. Installation, independent
Anthropic authentication, image understanding, zero autonomous tool exposure,
structured-output compatibility and alias/pinned-ID behavior require a small
no-actuation live qualification before claiming Claude is ready. If the installed
CLI cannot satisfy images plus tool isolation, block it rather than weakening the
contract. No live calls were made for this change.

## Rehearsals and validation

All three existing scripts accept `--expert-profile`, `--expert-config`,
`--reasoning-effort` and `--executable`, keeping Sol/medium defaults:
`full_loop_rehearsal.py`, `improvement_rehearsal.py`, `codex_expert_smoke.py`.
The smoke script name remains compatible; it now exercises the selected provider.
Rehearsals retain per-run metadata so a config change cannot rewrite the model
identity of earlier measurements. Run only with physical execution disabled.

Tests in `test_expert_profiles.py` are explicitly offline fake transport/CLI tests.
They cover identical image/tool/repair contracts, illegal tools, missing Claude
executable/authentication, unsupported profiles/Fable, metadata, atomic hot swap,
confirmation/checkpoint pinning, timeout/cancel/overflow process cleanup and
sanitized errors. The pre-existing Codex process test remains unchanged. This
worker's delegation-depth guard prevents that one test from reaching its fake CLI;
the guard was preserved and must be checked in a non-nested parent environment.
Unit results do not qualify physical execution, conversation, live Claude or D3/D4
improvement performance. Existing actual Codex evidence remains separate.
