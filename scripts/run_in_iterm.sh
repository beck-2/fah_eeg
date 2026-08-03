#!/usr/bin/env bash
# Run a command inside iTerm2 so macOS Bluetooth permissions apply to iTerm,
# not Cursor's integrated terminal / Apple Terminal.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# -eq 0 ]]; then
  echo "Usage: $0 <command...>" >&2
  echo "Example: $0 .venv/bin/fah-record --seconds 30" >&2
  exit 2
fi

# Join args into a single shell command, cd into repo, activate venv.
CMD=$(printf '%q ' "$@")
FULL_CMD=$(printf 'cd %q && source .venv/bin/activate && %s; echo; echo "[done — exit $? — press enter]"; read' "$ROOT" "$CMD")

# Escape for AppleScript string literal
AS_CMD=${FULL_CMD//\\/\\\\}
AS_CMD=${AS_CMD//\"/\\\"}

osascript <<EOF
tell application "iTerm"
  activate
  if (count of windows) = 0 then
    create window with default profile
  else
    tell current window
      create tab with default profile
    end tell
  end if
  tell current session of current window
    write text "${AS_CMD}"
  end tell
end tell
EOF
