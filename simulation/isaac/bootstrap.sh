#!/usr/bin/env bash
# Non-root Python installation; call only within an allocated Slurm job.
set -euo pipefail
: "${SLURM_JOB_ID:?Run through Slurm}"
: "${OPENARMS_ISAAC_ROOT:?Set to an approved writable project/scratch directory}"
: "${OMNI_KIT_ACCEPT_EULA:?Set YES after accepting NVIDIA Omniverse EULA}"
[[ "$OMNI_KIT_ACCEPT_EULA" == YES ]]
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]]
glibc=$(getconf GNU_LIBC_VERSION | awk '{print $2}')
[[ $(printf '%s\n' 2.35 "$glibc" | sort -V | head -1) == 2.35 ]] || { echo "GLIBC >= 2.35 required"; exit 1; }
root=$(realpath "$OPENARMS_ISAAC_ROOT")
mkdir -p "$root/cache" "$root/runs" "$root/tmp" "$root/data" "$root/config"
export TMPDIR="$root/tmp"
export XDG_DATA_HOME="$root/data"
export XDG_CONFIG_HOME="$root/config"
export PIP_CACHE_DIR="$root/cache/pip"
export XDG_CACHE_HOME="$root/cache"
export CUDA_CACHE_PATH="$root/cache/cuda"
python_cmd=${ISAAC_PYTHON311:-python3.11}
"$python_cmd" -c 'import sys; assert sys.version_info[:2] == (3,11), "Isaac 5.1 needs Python 3.11"'
"$python_cmd" -m venv "$root/venv"
"$root/venv/bin/python" -m pip install --upgrade pip
"$root/venv/bin/python" -m pip install 'isaacsim[all,extscache,compatibility-check]==5.1.0' --extra-index-url https://pypi.nvidia.com
"$root/venv/bin/python" -m pip install 'imageio==2.37.0' 'imageio-ffmpeg==0.6.0'
"$root/venv/bin/python" -m pip freeze > "$root/installed-packages.txt"
