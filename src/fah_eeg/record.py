"""Record Muse 2 EEG (and optionally other streams) to CSV."""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

import numpy as np
from brainflow.board_shim import BoardShim

from fah_eeg.board import (
    MUSE_2_BOARD_ID,
    MuseConnectionOptions,
    muse_session,
    wait_for_board_data,
)
from fah_eeg.pidfile import clear_pid, write_pid
from fah_eeg.session_io import SessionRecorder, default_session_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record Muse 2 data via BrainFlow into a CSV file.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=0.0,
        help="Duration in seconds. 0 = run until SIGINT/SIGTERM (default: 0).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output CSV path (default: data/sessions/muse2_<utc-timestamp>.csv).",
    )
    parser.add_argument(
        "--pid-file",
        type=Path,
        default=None,
        help="Write this process PID here while recording (removed on exit).",
    )
    parser.add_argument(
        "--status-file",
        type=Path,
        default=None,
        help="Optional file updated with sample count / state while recording.",
    )
    parser.add_argument(
        "--serial-number",
        default=None,
        help="Optional Muse device name (e.g. Muse-XXXX) if auto-discover fails.",
    )
    parser.add_argument(
        "--mac-address",
        default=None,
        help="Optional Muse BLE MAC address if auto-discover fails.",
    )
    parser.add_argument(
        "--preset",
        default=None,
        help="Optional Muse startup preset (e.g. p50 or preset=p50).",
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=0.25,
        help="Seconds between board data polls while recording (default: 0.25).",
    )
    parser.add_argument(
        "--first-packet-timeout",
        type=float,
        default=25.0,
        help="Seconds to wait for first EEG packet before failing (default: 25).",
    )
    return parser.parse_args(argv)


def _write_status(path: Path | None, text: str) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")


def record(
    seconds: float,
    out: Path,
    options: MuseConnectionOptions,
    poll: float = 0.25,
    pid_file: Path | None = None,
    status_file: Path | None = None,
    first_packet_timeout: float = 25.0,
) -> Path:
    sampling_rate = BoardShim.get_sampling_rate(MUSE_2_BOARD_ID)
    eeg_channels = BoardShim.get_eeg_channels(MUSE_2_BOARD_ID)
    stop = {"flag": False}
    out = out.resolve()

    def _request_stop(signum: int, _frame: object) -> None:
        name = signal.Signals(signum).name
        print(f"\nReceived {name} — finishing recording…", flush=True)
        stop["flag"] = True

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    until = "until stopped (SIGINT/SIGTERM)" if seconds <= 0 else f"for {seconds:g}s"
    print(f"Connecting to Muse 2 (board {MUSE_2_BOARD_ID})…", flush=True)
    print(f"EEG channels: {eeg_channels}, sampling rate: {sampling_rate} Hz", flush=True)
    print(f"Will record {until} → {out}", flush=True)
    _write_status(status_file, "connecting")

    write_pid(pid_file)
    try:
        with muse_session(options) as board:
            print("Stream started — waiting for first packet…", flush=True)
            _write_status(status_file, "waiting_for_first_packet")
            first = wait_for_board_data(
                board,
                timeout_sec=first_packet_timeout,
                should_stop=lambda: stop["flag"],
            )
            if first is None:
                if stop["flag"]:
                    raise RuntimeError("Stopped before any samples arrived.")
                raise RuntimeError(
                    "No samples received before timeout. Is the Muse 2 on, worn, "
                    "and disconnected from the phone?"
                )

            # Open CSV only after real data exists (avoids empty header-only files).
            with SessionRecorder(out) as recorder:
                recorder.ingest_sidebands(board)
                recorder.write_matrix(first)
                print(
                    f"Recording… first packet {first.shape[1]} samples → {out}",
                    flush=True,
                )
                print(
                    "Includes accel/gyro + PPG (+ derived heart_rate/SpO2 when ready)",
                    flush=True,
                )
                _write_status(status_file, f"recording samples={recorder.samples_written}")

                deadline = None if seconds <= 0 else time.monotonic() + seconds
                last_status = 0.0
                while not stop["flag"]:
                    if deadline is not None and time.monotonic() >= deadline:
                        break
                    time.sleep(poll)
                    data = recorder.push_from_board(board)
                    now = time.monotonic()
                    if now - last_status >= 2.0:
                        msg = f"… {recorder.samples_written} samples"
                        if np.isfinite(recorder._heart_rate):
                            msg += f"  HR≈{recorder._heart_rate:.0f}"
                        print(msg, flush=True)
                        _write_status(
                            status_file,
                            f"recording samples={recorder.samples_written}",
                        )
                        last_status = now

                recorder.push_from_board(board)

                if recorder.samples_written == 0:
                    raise RuntimeError("No samples received. Is the Muse 2 on and in range?")

                print(f"Wrote {recorder.samples_written} samples to {out}", flush=True)
                _write_status(status_file, f"done samples={recorder.samples_written}")
    finally:
        clear_pid(pid_file)
    return out


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.out or default_session_path()
    options = MuseConnectionOptions(
        serial_number=args.serial_number,
        mac_address=args.mac_address,
        other_info=args.preset,
    )
    try:
        record(
            args.seconds,
            out,
            options,
            poll=args.poll,
            pid_file=args.pid_file,
            status_file=args.status_file,
            first_packet_timeout=args.first_packet_timeout,
        )
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
