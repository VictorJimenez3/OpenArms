#!/usr/bin/env bash
# Explicit dedicated-host route. Rutgers continues to use runtime_job.sh.
set -euo pipefail
[[ ${OPENARMS_EXECUTION_CONTEXT:-} == dedicated ]]
: "${OPENARMS_ISAAC_ROOT:?Isolated runtime directory required}"
: "${OPENARMS_EVIDENCE_ROOT:?Evidence destination required}"
repo=$(git rev-parse --show-toplevel)
python3 "$repo/simulation/isaac/execution_context.py"
run="$OPENARMS_EVIDENCE_ROOT/run-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$run" "$OPENARMS_ISAAC_ROOT/cache" "$OPENARMS_ISAAC_ROOT/tmp"
exec > >(tee "$run/startup.log") 2>&1
trap 'rc=$?; printf "exit_code=%s\n" "$rc" > "$run/exit-status.txt"' EXIT
export XDG_CACHE_HOME="$OPENARMS_ISAAC_ROOT/cache"
export XDG_DATA_HOME="$OPENARMS_ISAAC_ROOT/data"
export XDG_CONFIG_HOME="$OPENARMS_ISAAC_ROOT/config"
export TMPDIR="$OPENARMS_ISAAC_ROOT/tmp"
export CUDA_CACHE_PATH="$OPENARMS_ISAAC_ROOT/cache/cuda"
export OMNI_KIT_ACCEPT_EULA=YES
bash "$repo/simulation/isaac/preflight.sh"
printf 'git_commit=%s\n' "$(git rev-parse HEAD)"
git status --short
"$OPENARMS_ISAAC_ROOT/venv/bin/python" "$repo/simulation/isaac/run_recording.py" \
  --workshop "$OPENARMS_ISAAC_ROOT/workshop" --output "$run/recording" "$@"
