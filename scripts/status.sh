#!/usr/bin/env bash
# Show whether record / viz jobs are running
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/_lib.sh"

job_status_line "record" "$RECORD_PID" "$RECORD_OUT"
if [[ -f "$RECORD_STATUS" ]]; then
  echo "  status: $(tr -d '\n' <"$RECORD_STATUS")"
fi
job_status_line "viz" "$VIZ_PID" "$VIZ_OUT"
job_status_line "stream" "$STREAM_PID" "$STREAM_STATUS"

echo
echo "Recent sessions (non-empty):"
find "$SESSIONS_DIR" -name 'muse2_*.csv' -size +200c -print0 2>/dev/null \
  | xargs -0 ls -lt 2>/dev/null | head -5 || echo "(none yet)"
echo
echo "Header-only / empty stubs:"
find "$SESSIONS_DIR" -name 'muse2_*.csv' -size -200c -print0 2>/dev/null \
  | xargs -0 ls -lt 2>/dev/null | head -5 || echo "(none)"
