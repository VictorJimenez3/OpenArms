#!/usr/bin/env bash
# One attended Ralph iteration. Read its commit before running it again.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
cd "$(git rev-parse --show-toplevel)"
# Refuse the main checkout and the main branch: Ralph commits only on a lane branch in a linked worktree.
if [ "$(git rev-parse --git-dir)" = "$(git rev-parse --git-common-dir)" ]; then
  echo "ralph: this is the main checkout; run from a worktree (git worktree add -b ralph-<lane> ../cb-<lane> main)" >&2; exit 1
fi
case "$(git branch --show-current)" in main|master|"")
  echo "ralph: on '$(git branch --show-current)'; switch this worktree to its lane branch" >&2; exit 1;;
esac
main_before=$(git rev-parse main)
claude --permission-mode acceptEdits "$(sed "s|{{RALPH_DIR}}|$here|g" "$here/prompt.md")"
[ "$(git rev-parse main)" = "$main_before" ] || echo "ralph: WARNING main moved during this run ($main_before -> $(git rev-parse --short main)); review it before anything else" >&2
