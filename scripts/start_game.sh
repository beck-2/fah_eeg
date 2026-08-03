#!/usr/bin/env bash
# Open the Godot game project (expects feature stream on UDP :14141)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GAME="$ROOT/game"

if [[ ! -f "$GAME/project.godot" ]]; then
  echo "Missing $GAME/project.godot" >&2
  exit 1
fi

GODOT_BIN=""
if command -v godot >/dev/null 2>&1; then
  GODOT_BIN="$(command -v godot)"
elif [[ -x /Applications/Godot.app/Contents/MacOS/Godot ]]; then
  GODOT_BIN="/Applications/Godot.app/Contents/MacOS/Godot"
else
  echo "Godot not found. Install with: brew install --cask godot" >&2
  exit 1
fi

echo "Launching FAH EEG game with $GODOT_BIN"
echo "Tip: start ./scripts/start_stream.sh --demo first if you have no Muse."
exec "$GODOT_BIN" --path "$GAME"
