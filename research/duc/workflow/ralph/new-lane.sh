#!/usr/bin/env bash
# Make lane worktree ../OpenArms-<lane> on duc/<lane> (from duc) with its own Ralph copy, tickets and permissions.
# Usage, from the main checkout: tmp/ralph/new-lane.sh core
set -euo pipefail
lane=${1:?usage: new-lane.sh <lane>}
root=$(git rev-parse --show-toplevel)
[ "$(git rev-parse --git-dir)" = "$(git rev-parse --git-common-dir)" ] || { echo "run from the main checkout, not a worktree" >&2; exit 1; }
[ -f "$root/tmp/tickets/$lane.md" ] || { echo "no tickets at tmp/tickets/$lane.md" >&2; exit 1; }
wt="$(dirname "$root")/OpenArms-$lane"
git worktree add -b "duc/$lane" "$wt" duc
mkdir -p "$wt/tmp/ralph" "$wt/.claude"
cp "$root/tmp/ralph/"{prompt.md,once.sh,afk.sh} "$wt/tmp/ralph/"
cp "$root/tmp/tickets/$lane.md" "$wt/tmp/ralph/PRD.md"
: > "$wt/tmp/ralph/progress.txt"
cp "$root/tmp/ralph/settings.local.json" "$wt/.claude/settings.local.json"
echo "lane ready: cd $wt && tmp/ralph/once.sh"
