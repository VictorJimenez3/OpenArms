# Attach an observed pour receipt

The existing supervised [`pour_once.py`](../firmware/openarms_executor/pour_once.py) writes JSONL receipts. This importer preserves its request backend, controller result and operator note as separate evidence. It runs entirely offline and does not import any robot modules.

```sh
python -m bench_vision.outcomes attach-receipt \
  --summary outputs/cup-review/summary.json \
  --receipt /path/to/completed/pour-water-receipt.jsonl \
  --out outputs/cup-review/summary-with-receipt.json \
  --observer 'Name of bench observer'
```

The new summary must use a new filename in the **same directory** as the original summary. This preserves existing relative frame paths. The original summary and receipt are unchanged. A content-addressed receipt copy is saved beside the new summary, with its SHA-256 and relative filename recorded. Existing conflicting files are never overwritten. The raw receipt is preserved exactly, including any paths or free text it already contains; review those contents before publishing. The summary does not add absolute source paths.

`controller_status:"executed"` says that the executor finished its command sequence. It does not establish grip, delivery, spill absence, return or reset. Free text such as “looked successful” is preserved verbatim but is never parsed into success. Without explicit structured observations, `outcome.status` remains `unknown`. A fake receipt remains fake evidence even when all its commands completed.

To record structured observations, the actual observer creates a JSON mapping:

```json
{
  "grip_clearance": "passed",
  "delivery": "passed",
  "spill": "passed",
  "cup_return": "passed",
  "home_reset": "passed"
}
```

Each value is `passed`, `failed` or `unknown`; omitted checks remain unknown. **`spill:"passed"` means the observer independently verified no spill**, while `failed` means a spill was observed. `delivery` requires observing the intended delivery; it cannot be inferred from wrist motion. `home_reset` requires independent verification of HOME and the required reset. These are human assessment fields, not automated measurements.

Attach the assessments using the actual line number of the supporting nonempty `operator_observation` row in that receipt:

```sh
python -m bench_vision.outcomes attach-receipt \
  --summary outputs/cup-review/summary.json \
  --receipt /path/to/completed/pour-water-receipt.jsonl \
  --out outputs/cup-review/summary-assessed.json \
  --observer 'Name of bench observer' \
  --checks observed-checks.json --checks-reference operator_observation:19
```

Line 19 is an example, not a fixed position. Non-unknown checks require a physical receipt, a physical/recorded summary, an observer identity and an explicit reference resolving to an actual nonempty operator note. The importer cannot establish that a person told the truth or that a manually attached receipt belongs to this episode; that association is explicitly labeled operator-attached because the existing receipt has no episode identifier. The source provenance never changes. A synthetic, fake, simulated, predicted or unknown summary cannot gain a physical outcome through this command.

The observed outcome is `passed` only when all five checks pass, `failed` when any check fails, and `unknown` otherwise. A controller failure and an observed outcome remain separate fields. A new attachment retains the previous outcome under `prior_outcome` and calculates the new assessment only from the supplied structured checks. No old pass silently carries forward.

Compile the new summary with the existing skill compiler and pass the original candidate as its baseline. The changed summary produces a new content version, preserving rollback; neither attachment nor compilation activates the candidate. The evidence fields include the `reference`, `observer` and `provenance` expected by the skill compiler.

Malformed JSON, missing final newlines, duplicate request/result rows, conflicting backend fields and nonfinite values reject. A well-formed interrupted receipt lacking a result or observer note remains diagnostic evidence with unknown outcome. Tests use constructed receipts and fake inputs only; no physical success is claimed by the test suite.
