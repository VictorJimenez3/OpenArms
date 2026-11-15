#!/usr/bin/env bash
# Records one full student run in the real app: predict -> direct -> plan -> yes -> pour -> observe,
# then "Do it again" so the saved-skill plan (0 AI calls) is on camera. Needs the lab server running.
# Usage: scripts/capture_app_run.sh [base_url] [lab] [out.webm] [instruction]
set -euo pipefail
BASE=${1:-http://127.0.0.1:8031}; LAB=${2:-volcano}; OUT=${3:-footage/app/$LAB-1080.webm}
SAY=${4:-"Ollie, pour the beaker from A into the flask at C"}
P="playwright-cli -s=cap"
ref() { $P snapshot 2>&1 | rg -o "$1 \[ref=(e[0-9]+)\]" | rg -o 'e[0-9]+' | tail -1; }
waitfor() { for _ in $(seq 1 60); do $P snapshot 2>&1 | rg -q "$1" && return 0; sleep 1; done; echo "timeout: $1" >&2; return 1; }
$P open "$BASE/student/" >/dev/null; $P resize 1920 1080 >/dev/null
$P goto "$BASE/student/#/lab/$LAB" >/dev/null; sleep 2
$P video-start "$OUT" --size 1920x1080 --fps 30 >/dev/null; sleep 2.5
$P click "$(ref 'button "Next"')" >/dev/null; sleep 2.5
$P click "$(ref 'radio "[^"]+"' | head -1)" >/dev/null 2>&1 || $P click "$($P snapshot | rg -o 'radio "[^"]+" \[ref=(e[0-9]+)' | head -1 | rg -o 'e[0-9]+$')" >/dev/null; sleep 1.5
$P click "$(ref 'button "Next"')" >/dev/null; sleep 2
$P click "$(ref 'textbox "Your instruction"')" >/dev/null; $P type "$SAY" >/dev/null; sleep 1
$P click "$(ref 'button "Send"')" >/dev/null
waitfor 'Yes, do it'; sleep 3.5
$P click "$(ref 'button "Yes, do it"')" >/dev/null
waitfor 'Do it again'; sleep 10
$P click "$(ref 'button "Do it again"')" >/dev/null
waitfor 'Yes, do it'; sleep 3.5
$P click "$(ref 'button "Yes, do it"')" >/dev/null
waitfor 'Do it again'; sleep 6
$P video-stop >/dev/null; $P close >/dev/null
echo "$OUT"
