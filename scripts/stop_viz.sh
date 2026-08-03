#!/usr/bin/env bash
# Stop the live spectrogram started by start_viz.sh
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/_lib.sh"

stop_job "viz" "$VIZ_PID"
if [[ -f "$VIZ_OUT" ]]; then
  echo "Session file: $(cat "$VIZ_OUT")"
fi
