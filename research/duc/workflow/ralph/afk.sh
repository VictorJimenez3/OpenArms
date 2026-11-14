#!/usr/bin/env bash
# Unattended Ralph: at most N iterations, stops early on <promise>COMPLETE</promise>.
# Usage: tmp/ralph/afk.sh <max-iterations>   (run from a clean worktree, ideally in a container)
set -euo pipefail
cap=${1:?usage: afk.sh <max-iterations>}
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
# Refuse a tree holding uncommitted tracked edits: they may be another session's work.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "afk.sh: tracked files are modified; run from a clean worktree" >&2; exit 1
fi
prompt=$(sed "s|{{RALPH_DIR}}|$here|g" "$here/prompt.md")
for ((i = 1; i <= cap; i++)); do
  echo "== ralph $i/$cap =="
  out=$(claude -p --permission-mode acceptEdits "$prompt" | tee /dev/stderr)
  if [ "$(git rev-parse main)" != "$main_before" ]; then echo "afk.sh: main moved during iteration $i; stopping" >&2; exit 1; fi
  if [[ $out == *"<promise>COMPLETE</promise>"* ]]; then echo "complete after $i"; exit 0; fi
done
echo "cap of $cap reached"
