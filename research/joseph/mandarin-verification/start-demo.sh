#!/bin/bash
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
relay="$here/../iphone-voice-bridge/relay"
cache="$HOME/Library/Caches/OpenArms/voice-bridge"
command -v uv >/dev/null
command -v agy >/dev/null
whisper_cli=${OPENARMS_WHISPER_CLI:-"$cache/whisper.cpp/build/bin/whisper-cli"}
whisper_model=${OPENARMS_WHISPER_MODEL:-"$cache/ggml-base.en.bin"}
[[ -x "$whisper_cli" ]] || { echo "Set OPENARMS_WHISPER_CLI to whisper-cli" >&2; exit 1; }
[[ -f "$whisper_model" ]] || { echo "Set OPENARMS_WHISPER_MODEL to the English model" >&2; exit 1; }
echo "Phone relay URL: ws://$(scutil --get LocalHostName).local:8765/voice"
cd "$relay"
exec uv run --locked python relay.py --lan --raw-audio --dialogue agy --whisper-cli "$whisper_cli" --model "$whisper_model" "$@"
