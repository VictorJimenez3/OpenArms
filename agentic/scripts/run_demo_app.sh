#!/bin/bash
# Start the demo-bench app on the simulation, seeded so the base pour is fast from the first request.
#   agentic/scripts/run_demo_app.sh [expert-profile] [effort] [port]
# Profiles: devin-sol-fast (default), devin-astra-fast, devin-opus-fast, sol, astra (Codex), opus, sonnet (Claude), ...
# Environment: OPENARMS_DEMO_EXPERIMENT=volcano|potions|lava_lamp, OPENARMS_DATA_DIR, PYTHON, OPENARMS_DEMO_TOKEN
# (pairing code for other machines; set OPENARMS_HOST=0.0.0.0 to serve them). Run it where the chosen expert
# CLI is logged in; for Devin on macOS that is a Terminal window.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PROFILE="${1:-devin-sol-fast}" EFFORT="${2:-medium}" PORT="${3:-8011}"
PY="${PYTHON:-}"
[ -z "$PY" ] && { [ -x "$ROOT/.venv-lab/bin/python" ] && PY="$ROOT/.venv-lab/bin/python" || PY="$(command -v python3)"; }
EXPERIMENT="${OPENARMS_DEMO_EXPERIMENT:-volcano}"
find_cli() { command -v "$1" 2>/dev/null || ls -1d $2 2>/dev/null | sort -V | tail -1 || true; }
export OPENARMS_DEVIN_EXECUTABLE="${OPENARMS_DEVIN_EXECUTABLE:-$(find_cli devin "$HOME/.local/share/local-devin-sessions/runtime/*/bin/devin")}"
export OPENARMS_CODEX_EXECUTABLE="${OPENARMS_CODEX_EXECUTABLE:-$(find_cli codex "$HOME/.local/bin/codex")}"
export OPENARMS_CLAUDE_EXECUTABLE="${OPENARMS_CLAUDE_EXECUTABLE:-$(find_cli claude "$HOME/.local/bin/claude")}"
export OPENARMS_HOST="${OPENARMS_HOST:-127.0.0.1}" OPENARMS_BENCH="${OPENARMS_BENCH:-0}" OPENARMS_EXECUTION=mujoco
export OPENARMS_SCENE=demo_bench OPENARMS_DEMO_EXPERIMENT="$EXPERIMENT"
export OPENARMS_DATA_DIR="${OPENARMS_DATA_DIR:-$ROOT/outputs/demo-app-$EXPERIMENT}"
export OPENARMS_EXPERT_PROFILE="$PROFILE" OPENARMS_EXPERT_EFFORT="$EFFORT" PORT PYTHONPATH="agentic:simulation:."
echo "OpenArms demo: experiment=$EXPERIMENT expert=$PROFILE/$EFFORT data=$OPENARMS_DATA_DIR"
"$PY" agentic/scripts/seed_demo_skill.py --data "$OPENARMS_DATA_DIR"
echo "Open http://$OPENARMS_HOST:$PORT"
exec "$PY" -m agentic.openarms_lab
