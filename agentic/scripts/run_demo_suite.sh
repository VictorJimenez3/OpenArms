#!/bin/bash
# One app per Smartivity experiment, so a UI can offer all three at once:
#   volcano http://127.0.0.1:8011, potions :8012, lava_lamp :8013
#   agentic/scripts/run_demo_suite.sh [expert-profile] [effort]
# Each keeps its own data directory, execution scope and learned skills. Ctrl-C stops all three.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
port=8011
pids=()
for experiment in volcano potions lava_lamp; do
  OPENARMS_DEMO_EXPERIMENT="$experiment" "$ROOT/agentic/scripts/run_demo_app.sh" "${1:-devin-sol-fast}" "${2:-medium}" "$port" \
    > "$ROOT/outputs/demo-app-$experiment.log" 2>&1 &
  pids+=($!)
  # Seeding runs a real simulation; starting the three at once makes the seed flaky, so wait for each.
  for _ in $(seq 1 90); do sleep 2; curl -s -o /dev/null "http://127.0.0.1:$port/api/health" && break; done
  echo "$experiment -> http://127.0.0.1:$port (log outputs/demo-app-$experiment.log)"
  port=$((port + 1))
done
trap 'kill "${pids[@]}" 2>/dev/null' INT TERM EXIT
wait
