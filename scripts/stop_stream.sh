#!/usr/bin/env bash
# Stop the EEG→Godot feature streamer
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/_lib.sh"

stop_job "stream" "$STREAM_PID"
printf 'stopped\n' >"$STREAM_STATUS"
if [[ -f "$STREAM_OUT" ]]; then
  echo "Session file: $(cat "$STREAM_OUT")"
fi
