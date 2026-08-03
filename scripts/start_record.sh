#!/usr/bin/env bash
# Start headless Muse 2 recording until ./scripts/stop_record.sh
#
# Usage:
#   ./scripts/start_record.sh
#   ./scripts/start_record.sh data/sessions/custom.csv
#   ./scripts/start_record.sh --serial-number Muse-XXXX
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/_lib.sh"

OUT="$SESSIONS_DIR/muse2_$(utc_stamp).csv"
EXTRA=()

if [[ $# -ge 1 && "${1:-}" != -* ]]; then
  OUT="$1"
  shift
fi
EXTRA=("$@")

printf '%s\n' "$OUT" >"$RECORD_OUT"
: >"$RECORD_LOG"

launch_ble_job "record" "$RECORD_PID" "$RECORD_LOG" \
  fah-record --seconds 0 --out "$OUT" --pid-file "$RECORD_PID" \
  --status-file "$RECORD_STATUS" ${EXTRA[@]+"${EXTRA[@]}"}

echo "CSV: $OUT"
echo "Status: $RECORD_STATUS"
echo "Stop with: $ROOT/scripts/stop_record.sh"
