#!/usr/bin/env bash
# Run inside the allocated Slurm step. No CUDA work on the login node.
set -euo pipefail
python3 "$(dirname "$0")/execution_context.py"
: "${OPENARMS_ISAAC_ROOT:?Set to an approved writable scratch/project directory}"
printf 'utc=%s\nhost=%s\njob=%s\nstep=%s\n' "$(date -u +%FT%TZ)" "$(hostname -f)" "${SLURM_JOB_ID:-none-dedicated-host}" "${SLURM_STEP_ID:-none}"
printf 'CUDA_VISIBLE_DEVICES=%s\nSLURM_JOB_GPUS=%s\nSLURM_STEP_GPUS=%s\n' "${CUDA_VISIBLE_DEVICES:-unset}" "${SLURM_JOB_GPUS:-unset}" "${SLURM_STEP_GPUS:-unset}"
uname -a
cat /etc/os-release
getconf GNU_LIBC_VERSION
free -h
if [[ -n ${SLURM_JOB_ID:-} ]]; then scontrol show job "$SLURM_JOB_ID"; fi
nvidia-smi --query-gpu=index,uuid,name,driver_version,memory.total,memory.free --format=csv
nvidia-smi
mkdir -p "$OPENARMS_ISAAC_ROOT"
df -hT "$OPENARMS_ISAAC_ROOT" /tmp
for tool in singularity apptainer python3.11 ffmpeg vulkaninfo; do
  command -v "$tool" || true
done
if command -v singularity >/dev/null; then singularity --version; fi
if command -v apptainer >/dev/null; then apptainer --version; fi
ldconfig -p 2>/dev/null | grep -E 'libvulkan|libEGL|libGLX|libnvidia-encode' || true
ls /usr/share/vulkan/icd.d /etc/vulkan/icd.d 2>/dev/null || true
if command -v vulkaninfo >/dev/null; then timeout 45 vulkaninfo --summary; fi
printf 'PREFLIGHT_ONLY: this is not proof Isaac launched.\n'
