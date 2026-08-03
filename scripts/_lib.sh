#!/usr/bin/env bash
# Shared helpers for fah_eeg control scripts.
# shellcheck shell=bash

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/data/run"
SESSIONS_DIR="$ROOT/data/sessions"
VENV_PYTHON="$ROOT/.venv/bin/python"

RECORD_PID="$RUN_DIR/record.pid"
RECORD_OUT="$RUN_DIR/record.out"
RECORD_LOG="$RUN_DIR/record.log"
RECORD_STATUS="$RUN_DIR/record.status"
VIZ_PID="$RUN_DIR/viz.pid"
VIZ_OUT="$RUN_DIR/viz.out"
VIZ_LOG="$RUN_DIR/viz.log"
STREAM_PID="$RUN_DIR/stream.pid"
STREAM_LOG="$RUN_DIR/stream.log"
STREAM_STATUS="$RUN_DIR/stream.status"

# Avoid silent empty logs when Python stdout is redirected.
export PYTHONUNBUFFERED=1

mkdir -p "$RUN_DIR" "$SESSIONS_DIR"

utc_stamp() {
  date -u +%Y%m%d_%H%M%S
}

is_running() {
  local pid_file="$1"
  if [[ ! -f "$pid_file" ]]; then
    return 1
  fi
  local pid
  pid="$(tr -d '[:space:]' <"$pid_file")"
  if [[ -z "$pid" ]]; then
    return 1
  fi
  kill -0 "$pid" 2>/dev/null
}

read_pid() {
  tr -d '[:space:]' <"$1"
}

require_venv() {
  if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "Missing venv at $ROOT/.venv — run: python3.13 -m venv .venv && .venv/bin/pip install -e ." >&2
    exit 1
  fi
}

# Launch a command. If already inside iTerm, run in background here (BLE OK).
# Otherwise open a new iTerm tab so Bluetooth permissions apply.
launch_ble_job() {
  local name="$1"
  local pid_file="$2"
  local log_file="$3"
  shift 3

  require_venv

  if is_running "$pid_file"; then
    echo "$name already running (pid $(read_pid "$pid_file"))." >&2
    exit 1
  fi

  if [[ "${TERM_PROGRAM:-}" == "iTerm.app" ]]; then
    (
      cd "$ROOT"
      # shellcheck disable=SC1091
      source .venv/bin/activate
      exec "$@"
    ) >>"$log_file" 2>&1 &
    local bg_pid=$!
    # Python also writes pid_file; keep a fallback until it does.
    echo "$bg_pid" >"$pid_file"
    echo "Started $name in this iTerm session (pid $bg_pid)."
    echo "Log: $log_file"
  else
    # Pass through to iTerm; Python will create the authoritative pid file.
    "$ROOT/scripts/run_in_iterm.sh" "$@"
    echo "Started $name in a new iTerm tab (uses iTerm Bluetooth permission)."
    echo "Watch that tab for logs; pid file: $pid_file"
  fi
}

stop_job() {
  local name="$1"
  local pid_file="$2"
  if ! is_running "$pid_file"; then
    echo "$name is not running."
    rm -f "$pid_file"
    return 0
  fi
  local pid
  pid="$(read_pid "$pid_file")"
  echo "Stopping $name (pid $pid)…"
  kill -INT "$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true

  # BLE teardown can be slow; give it more time before SIGKILL.
  local i
  for i in {1..80}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "$name stopped."
      rm -f "$pid_file"
      return 0
    fi
    sleep 0.25
  done

  echo "$name did not exit cleanly; sending SIGKILL…" >&2
  kill -KILL "$pid" 2>/dev/null || true
  rm -f "$pid_file"
}

job_status_line() {
  local name="$1"
  local pid_file="$2"
  local out_file="$3"
  if is_running "$pid_file"; then
    local pid out=""
    pid="$(read_pid "$pid_file")"
    if [[ -f "$out_file" ]]; then
      out="$(cat "$out_file")"
    fi
    if [[ -n "$out" ]]; then
      echo "$name: running (pid $pid) → $out"
    else
      echo "$name: running (pid $pid)"
    fi
  else
    echo "$name: stopped"
  fi
}
