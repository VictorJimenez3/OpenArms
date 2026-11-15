#!/bin/bash
# Kept for earlier notes; the portable launcher lives in agentic/scripts/run_demo_app.sh.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec "$ROOT/agentic/scripts/run_demo_app.sh" "$@" > "$ROOT/outputs/demo-app-${1:-devin-sol-fast}-${3:-8011}.log" 2>&1
