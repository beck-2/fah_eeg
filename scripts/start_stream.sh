#!/usr/bin/env bash
# Stream Muse features (or --demo) to Godot over UDP :14141
#
# Usage:
#   ./scripts/start_stream.sh --demo
#   ./scripts/start_stream.sh
#   ./scripts/start_stream.sh --record
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/_lib.sh"

EXTRA=("$@")
: >"$STREAM_LOG"
printf 'starting\n' >"$STREAM_STATUS"

launch_ble_job "stream" "$STREAM_PID" "$STREAM_LOG" \
  fah-stream --pid-file "$STREAM_PID" ${EXTRA[@]+"${EXTRA[@]}"}

echo "UDP → 127.0.0.1:14141"
echo "Log: $STREAM_LOG"
echo "Stop with: $ROOT/scripts/stop_stream.sh"
echo "Then launch the game: $ROOT/scripts/start_game.sh"
