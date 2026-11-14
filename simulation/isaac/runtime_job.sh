#!/usr/bin/env bash
set -euo pipefail
: "${OPENARMS_ISAAC_ROOT:?Approved runtime directory required}"
: "${OPENARMS_EVIDENCE_ROOT:?Shared evidence destination required}"
: "${SLURM_JOB_ID:?Submit with sbatch -G a6000:1}"
repo=$(git rev-parse --show-toplevel)
run="$OPENARMS_EVIDENCE_ROOT/job-$SLURM_JOB_ID"
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
"$OPENARMS_ISAAC_ROOT/venv/bin/python" "$repo/simulation/isaac/smoke.py" \
  --workshop "$OPENARMS_ISAAC_ROOT/workshop" --output "$run/smoke"
