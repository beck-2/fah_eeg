"""Record Muse 2 EEG (and optionally other streams) to CSV."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from brainflow.board_shim import BoardShim

from fah_eeg.board import MUSE_2_BOARD_ID, MuseConnectionOptions, muse_session
from fah_eeg.session_io import SessionRecorder, default_session_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record Muse 2 data via BrainFlow into a CSV file.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=60.0,
        help="Recording duration in seconds (default: 60).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output CSV path (default: data/sessions/muse2_<utc-timestamp>.csv).",
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
    return parser.parse_args(argv)


def record(
    seconds: float,
    out: Path,
    options: MuseConnectionOptions,
    poll: float = 0.25,
) -> Path:
    sampling_rate = BoardShim.get_sampling_rate(MUSE_2_BOARD_ID)
    eeg_channels = BoardShim.get_eeg_channels(MUSE_2_BOARD_ID)

    print(f"Connecting to Muse 2 (board {MUSE_2_BOARD_ID})…")
    print(f"EEG channels: {eeg_channels}, sampling rate: {sampling_rate} Hz")
    print(f"Recording for {seconds:g}s → {out}")

    with muse_session(options) as board, SessionRecorder(out) as recorder:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            time.sleep(poll)
            data = board.get_board_data()
            if data.size:
                recorder.write_matrix(data)

        data = board.get_board_data()
        if data.size:
            recorder.write_matrix(data)

        if recorder.samples_written == 0:
            raise RuntimeError("No samples received. Is the Muse 2 on and in range?")

        print(f"Wrote {recorder.samples_written} samples to {out}")
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
        record(args.seconds, out, options, poll=args.poll)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
