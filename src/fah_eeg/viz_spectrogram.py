"""Live Muse 2 EEG spectrogram / band-power visualization with session recording."""

from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

import numpy as np
from brainflow.board_shim import BoardShim
from brainflow.data_filter import DataFilter, DetrendOperations, WindowOperations

from fah_eeg.board import MUSE_2_BOARD_ID, MuseConnectionOptions, eeg_channel_names, muse_session
from fah_eeg.session_io import SessionRecorder, default_session_path

# Classic EEG bands (Hz)
BANDS = [
    ("Delta", 1.0, 4.0),
    ("Theta", 4.0, 8.0),
    ("Alpha", 8.0, 13.0),
    ("Beta", 13.0, 30.0),
    ("Gamma", 30.0, 45.0),
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Live spectrogram for Muse 2; always records full board CSV.",
    )
    parser.add_argument(
        "--serial-number",
        default=None,
        help="Optional Muse device name if auto-discover fails.",
    )
    parser.add_argument(
        "--mac-address",
        default=None,
        help="Optional Muse BLE MAC address if auto-discover fails.",
    )
    parser.add_argument(
        "--preset",
        default=None,
        help="Optional Muse startup preset (e.g. p50).",
    )
    parser.add_argument(
        "--window-sec",
        type=float,
        default=2.0,
        help="EEG window length for PSD in seconds (default: 2).",
    )
    parser.add_argument(
        "--history",
        type=int,
        default=80,
        help="Number of time columns in the scrolling spectrogram (default: 80).",
    )
    parser.add_argument(
        "--channel",
        type=int,
        default=0,
        help="EEG channel index into BrainFlow EEG channel list (default: 0 = first).",
    )
    parser.add_argument(
        "--update-ms",
        type=int,
        default=150,
        help="Plot refresh interval in milliseconds (default: 150).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="CSV path (default: data/sessions/muse2_<utc-timestamp>.csv).",
    )
    return parser.parse_args(argv)


def band_powers(signal: np.ndarray, sampling_rate: int) -> np.ndarray:
    """Return absolute band powers for BANDS from one EEG channel window."""
    n = len(signal)
    if n < sampling_rate // 2:
        return np.zeros(len(BANDS))

    data = signal.astype(np.float64).copy()
    DataFilter.detrend(data, DetrendOperations.CONSTANT.value)
    nfft = DataFilter.get_nearest_power_of_two(sampling_rate)
    overlap = nfft // 2
    try:
        psd = DataFilter.get_psd_welch(
            data,
            nfft,
            overlap,
            sampling_rate,
            WindowOperations.HANNING.value,
        )
    except Exception:
        return np.zeros(len(BANDS))

    freqs = np.asarray(psd[1])
    dens = np.asarray(psd[0])
    powers = []
    integrate = getattr(np, "trapezoid", None) or np.trapz
    for _, lo, hi in BANDS:
        mask = (freqs >= lo) & (freqs < hi)
        if np.any(mask):
            powers.append(float(integrate(dens[mask], freqs[mask])))
        else:
            powers.append(0.0)
    return np.asarray(powers, dtype=np.float64)


def run_viz(args: argparse.Namespace) -> Path:
    import pyqtgraph as pg
    from pyqtgraph.Qt import QtCore, QtWidgets

    sampling_rate = BoardShim.get_sampling_rate(MUSE_2_BOARD_ID)
    eeg_channels = BoardShim.get_eeg_channels(MUSE_2_BOARD_ID)
    names = eeg_channel_names()
    if args.channel < 0 or args.channel >= len(eeg_channels):
        raise SystemExit(
            f"--channel {args.channel} out of range; "
            f"available EEG indices 0..{len(eeg_channels) - 1} ({names})"
        )

    board_ch = eeg_channels[args.channel]
    ch_name = names[args.channel] if args.channel < len(names) else f"ch{board_ch}"
    window_samples = int(args.window_sec * sampling_rate)
    history: deque[np.ndarray] = deque(maxlen=args.history)
    out = args.out or default_session_path()

    options = MuseConnectionOptions(
        serial_number=args.serial_number,
        mac_address=args.mac_address,
        other_info=args.preset,
    )

    app = QtWidgets.QApplication([])
    pg.setConfigOptions(antialias=True)
    win = pg.GraphicsLayoutWidget(title=f"Muse 2 live bands — {ch_name}")
    win.resize(1000, 700)
    win.show()

    plot_spec = win.addPlot(row=0, col=0, title=f"Band power over time ({ch_name})")
    img = pg.ImageItem()
    plot_spec.addItem(img)
    plot_spec.setLabel("left", "Band")
    plot_spec.setLabel("bottom", "Time windows")
    plot_spec.getAxis("left").setTicks(
        [[(i, name) for i, (name, _, _) in enumerate(BANDS)]]
    )
    cmap = pg.colormap.get("viridis")
    img.setLookupTable(cmap.getLookupTable(0.0, 1.0, 256))

    win.nextRow()
    plot_bar = win.addPlot(row=1, col=0, title="Current band power")
    plot_bar.setLabel("left", "Power")
    bar = pg.BarGraphItem(
        x=np.arange(len(BANDS)),
        height=np.zeros(len(BANDS)),
        width=0.6,
        brush=(80, 160, 220),
    )
    plot_bar.addItem(bar)
    plot_bar.getAxis("bottom").setTicks(
        [[(i, name) for i, (name, _, _) in enumerate(BANDS)]]
    )
    plot_bar.setXRange(-0.5, len(BANDS) - 0.5)

    status = pg.LabelItem(justify="left")
    win.addItem(status, row=2, col=0)
    status.setText("Connecting to Muse 2…")

    buffer = np.zeros(0, dtype=np.float64)
    recorder = SessionRecorder(out)
    session = muse_session(options)
    board = session.__enter__()
    print(f"Recording all board data → {out.resolve()}")
    status.setText(
        f"Streaming {ch_name} @ {sampling_rate} Hz | recording {out.name} — close window to stop"
    )

    def tick() -> None:
        nonlocal buffer
        try:
            # Drain ring buffer: every sample is recorded once with board timestamps.
            data = board.get_board_data()
            if data.size == 0:
                return
            recorder.write_matrix(data)

            channel = data[board_ch]
            buffer = np.concatenate([buffer, channel])
            if len(buffer) > window_samples * 3:
                buffer = buffer[-window_samples * 3 :]
            if len(buffer) < window_samples:
                return

            window = buffer[-window_samples:]
            powers = band_powers(window, sampling_rate)
            history.append(powers)
            bar.setOpts(height=powers)

            matrix = np.vstack(history).T
            display = np.log10(matrix + 1e-12)
            img.setImage(display, autoLevels=True)
            status.setText(
                f"{ch_name} | n={recorder.samples_written} | "
                + "  ".join(
                    f"{name}: {powers[i]:.2e}" for i, (name, _, _) in enumerate(BANDS)
                )
            )
        except Exception as exc:
            status.setText(f"Update error: {exc}")

    timer = QtCore.QTimer()
    timer.timeout.connect(tick)
    timer.start(args.update_ms)

    cleaned = {"done": False}

    def cleanup() -> None:
        if cleaned["done"]:
            return
        cleaned["done"] = True
        timer.stop()
        try:
            leftover = board.get_board_data()
            if leftover.size:
                recorder.write_matrix(leftover)
        except Exception:
            pass
        recorder.close()
        session.__exit__(None, None, None)
        print(
            f"Wrote {recorder.samples_written} samples → {out.resolve()}",
            flush=True,
        )

    app.aboutToQuit.connect(cleanup)

    class _Window(type(win)):
        pass

    def close_event(event) -> None:  # type: ignore[no-untyped-def]
        cleanup()
        event.accept()
        app.quit()

    win.closeEvent = close_event  # type: ignore[method-assign]
    app.exec()
    cleanup()
    return out


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run_viz(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
