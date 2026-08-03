#!/usr/bin/env bash
# Stop the headless Muse 2 recorder started by start_record.sh
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/_lib.sh"

stop_job "record" "$RECORD_PID"
if [[ -f "$RECORD_OUT" ]]; then
  echo "Session file: $(cat "$RECORD_OUT")"
fi
