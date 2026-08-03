#!/usr/bin/env bash
# Stream Muse features (or --demo) to Godot over UDP :14141.
# Live Muse streams record a CSV under data/sessions/ by default (--no-record to skip).
#
# Usage:
#   ./scripts/start_stream.sh --demo
#   ./scripts/start_stream.sh
#   ./scripts/start_stream.sh --serial-number Muse-E88D
#   ./scripts/start_stream.sh --no-record
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/_lib.sh"

EXTRA=("$@")
: >"$STREAM_LOG"
printf 'starting\n' >"$STREAM_STATUS"

launch_ble_job "stream" "$STREAM_PID" "$STREAM_LOG" \
  fah-stream --pid-file "$STREAM_PID" ${EXTRA[@]+"${EXTRA[@]}"}

echo "UDP → 127.0.0.1:14141"
echo "CSV recording: on by default for live Muse (pass --no-record to disable)"
echo "Log: $STREAM_LOG"
echo "Stop with: $ROOT/scripts/stop_stream.sh"
echo "Then launch the game: $ROOT/scripts/start_game.sh"
