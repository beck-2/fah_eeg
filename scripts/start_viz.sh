#!/usr/bin/env bash
# Start live spectrogram (+ auto CSV record) until stop_viz.sh or window close
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/_lib.sh"

OUT="$SESSIONS_DIR/muse2_$(utc_stamp).csv"
EXTRA=("$@")
# If first arg is a path (not a flag), treat as --out
if [[ $# -ge 1 && "${1:-}" != -* ]]; then
  OUT="$1"
  EXTRA=("${@:2}")
fi

printf '%s\n' "$OUT" >"$VIZ_OUT"
: >"$VIZ_LOG"

launch_ble_job "viz" "$VIZ_PID" "$VIZ_LOG" \
  fah-spectrogram --out "$OUT" --pid-file "$VIZ_PID" ${EXTRA[@]+"${EXTRA[@]}"}

echo "CSV: $OUT"
echo "Stop with: $ROOT/scripts/stop_viz.sh  (or close the plot window)"
