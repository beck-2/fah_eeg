#!/usr/bin/env bash
# Stream Muse features (or --demo) to Godot over UDP :14141.
# Live Muse always records a CSV under data/sessions/ unless --no-record.
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

has_demo=0
has_no_record=0
has_out=0
has_serial=0
for a in "$@"; do
  case "$a" in
    --demo) has_demo=1 ;;
    --no-record) has_no_record=1 ;;
    --out|--out=*) has_out=1 ;;
    --serial-number|--serial-number=*) has_serial=1 ;;
  esac
done

RECORD_ARGS=()
SERIAL_ARGS=()
OUT=""

if [[ "$has_demo" -eq 0 ]]; then
  if [[ "$has_serial" -eq 0 ]]; then
    SERIAL_ARGS=(--serial-number Muse-E88D)
  fi
  if [[ "$has_no_record" -eq 0 && "$has_out" -eq 0 ]]; then
    OUT="$SESSIONS_DIR/muse2_stream_$(utc_stamp).csv"
    RECORD_ARGS=(--out "$OUT")
    printf '%s\n' "$OUT" >"$STREAM_OUT"
  elif [[ "$has_no_record" -eq 0 ]]; then
    : # caller passed --out already; fah-stream still records by default
    : >"$STREAM_OUT"
  else
    printf 'no-record\n' >"$STREAM_OUT"
  fi
else
  printf 'demo\n' >"$STREAM_OUT"
fi

: >"$STREAM_LOG"
printf 'starting\n' >"$STREAM_STATUS"

launch_ble_job "stream" "$STREAM_PID" "$STREAM_LOG" \
  fah-stream --pid-file "$STREAM_PID" \
  "${SERIAL_ARGS[@]+"${SERIAL_ARGS[@]}"}" \
  "${RECORD_ARGS[@]+"${RECORD_ARGS[@]}"}" \
  ${EXTRA[@]+"${EXTRA[@]}"}

echo "UDP → 127.0.0.1:14141"
if [[ -n "$OUT" ]]; then
  echo "CSV: $OUT"
elif [[ "$has_demo" -eq 1 ]]; then
  echo "Demo mode — no CSV (no headset)"
elif [[ "$has_no_record" -eq 1 ]]; then
  echo "CSV recording: off (--no-record)"
else
  echo "CSV recording: on (fah-stream default)"
fi
echo "Log: $STREAM_LOG"
echo "Stop with: $ROOT/scripts/stop_stream.sh"
echo "Then launch the game: $ROOT/scripts/start_game.sh"
