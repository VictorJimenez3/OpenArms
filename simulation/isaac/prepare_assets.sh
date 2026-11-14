#!/usr/bin/env bash
set -euo pipefail
: "${OPENARMS_ISAAC_ROOT:?Set the approved installation directory}"
root=$(realpath "$OPENARMS_ISAAC_ROOT")
pin=ce807d99724cb65671abec01f908a2fcb4a6eab7
git lfs version
if [[ ! -d "$root/workshop/.git" ]]; then
  GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/isaac-sim/Sim-to-Real-SO-101-Workshop.git "$root/workshop"
fi
git -C "$root/workshop" checkout --detach "$pin"
git -C "$root/workshop" lfs pull
[[ $(git -C "$root/workshop" rev-parse HEAD) == "$pin" ]]
git -C "$root/workshop" lfs fsck
