#!/usr/bin/env bash
# Start live scrolling PSD spectrogram (+ CSV record by default)
#
# Usage:
#   ./scripts/start_psd.sh
#   ./scripts/start_psd.sh --serial-number Muse-E88D
#   ./scripts/start_psd.sh --channel 2   # AF8
#
# Note: Muse BLE is exclusive — stop stream/viz/record first if connected.
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/_lib.sh"

OUT="$SESSIONS_DIR/muse2_psd_$(utc_stamp).csv"
EXTRA=("$@")

# Default Muse id unless caller already passed --serial-number
has_serial=0
for a in "$@"; do
  if [[ "$a" == "--serial-number" || "$a" == --serial-number=* ]]; then
    has_serial=1
    break
  fi
done
SERIAL_ARGS=()
if [[ "$has_serial" -eq 0 ]]; then
  SERIAL_ARGS=(--serial-number Muse-E88D)
fi

printf '%s\n' "$OUT" >"$PSD_OUT"
: >"$PSD_LOG"

launch_ble_job "psd" "$PSD_PID" "$PSD_LOG" \
  fah-psd --out "$OUT" --pid-file "$PSD_PID" "${SERIAL_ARGS[@]+"${SERIAL_ARGS[@]}"}" ${EXTRA[@]+"${EXTRA[@]}"}

echo "CSV: $OUT"
echo "Stop with: $ROOT/scripts/stop_psd.sh  (or close the plot window)"
echo "Tip: only one Muse client at a time — stop_stream/stop_viz if needed."
