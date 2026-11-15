#!/bin/bash
# Launch the demo-bench app where the Devin CLI is logged in (Terminal). Usage: run_demo_app.sh [profile] [effort] [port]
cd /Users/victor/OpenArms/device-expert-smoke
export OPENARMS_HOST=127.0.0.1 OPENARMS_BENCH=0 OPENARMS_EXECUTION=mujoco OPENARMS_SCENE=demo_bench
export OPENARMS_DATA_DIR="$PWD/outputs/sim-main-demo-app" OPENARMS_EXPERT_PROFILE="${1:-devin-sol-fast}" OPENARMS_EXPERT_EFFORT="${2:-medium}"
export OPENARMS_DEVIN_EXECUTABLE=/Users/victor/.local/share/local-devin-sessions/runtime/3000.12.57/bin/devin
export OPENARMS_CODEX_EXECUTABLE=/Users/victor/.local/bin/codex PORT="${3:-8011}" PYTHONPATH=agentic:simulation:.
exec .venv-lab/bin/python -m agentic.openarms_lab > "outputs/demo-app-${OPENARMS_EXPERT_PROFILE}-${PORT}.log" 2>&1
