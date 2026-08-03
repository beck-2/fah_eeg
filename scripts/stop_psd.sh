#!/usr/bin/env bash
# Stop the live PSD window started by start_psd.sh
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/_lib.sh"

stop_job "psd" "$PSD_PID"
if [[ -f "$PSD_OUT" ]]; then
  echo "Session file: $(cat "$PSD_OUT")"
fi
