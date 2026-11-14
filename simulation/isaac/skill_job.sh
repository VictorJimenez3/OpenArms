#!/usr/bin/env bash
# Submit with sbatch. No GPU work on a Rutgers login node.
set -euo pipefail
condition=${1:-light}
[[ "$condition" == light || "$condition" == heavy ]]
: "${SLURM_JOB_ID:?A Slurm GPU allocation is required}"
: "${OPENARMS_ISAAC_ROOT:?Isolated Isaac 5.1 environment required}"
: "${OPENARMS_EVIDENCE_ROOT:?Approved evidence directory required}"
export OPENARMS_EXECUTION_CONTEXT=slurm
export OMNI_KIT_ACCEPT_EULA=YES
export XDG_CACHE_HOME="$OPENARMS_ISAAC_ROOT/cache"
export XDG_DATA_HOME="$OPENARMS_ISAAC_ROOT/data"
export XDG_CONFIG_HOME="$OPENARMS_ISAAC_ROOT/config"
export TMPDIR="$OPENARMS_ISAAC_ROOT/tmp"
export CUDA_CACHE_PATH="$OPENARMS_ISAAC_ROOT/cache/cuda"
repo=$(git rev-parse --show-toplevel)
run="$OPENARMS_EVIDENCE_ROOT/job-$SLURM_JOB_ID-$condition-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$OPENARMS_EVIDENCE_ROOT" "$TMPDIR" "$XDG_CACHE_HOME"
bash "$repo/simulation/isaac/preflight.sh" > "$run-preflight.log" 2>&1
python3 - "$condition" "$run-request.json" <<'PY'
import json, sys, uuid
from pathlib import Path
condition, destination = sys.argv[1:]
Path(destination).write_text(json.dumps({
    'request_id': str(uuid.uuid4()), 'session_id': 'isaac-mass-weight',
    'skill_id': f'isaac.mass_weight.{condition}.v1',
    'parameters': {'object': 'sample', 'source': 'A', 'destination': 'B'},
}, indent=2))
PY
"$OPENARMS_ISAAC_ROOT/venv/bin/python" "$repo/simulation/isaac/skill.py" \
  --request "$run-request.json" --output "$run" \
  --workshop "$OPENARMS_ISAAC_ROOT/workshop" --cleanup sensors
