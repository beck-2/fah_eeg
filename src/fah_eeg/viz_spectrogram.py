"""Live Muse 2 EEG spectrogram / band-power visualization with session recording."""

from __future__ import annotations

import argparse
import signal
import sys
import threading
import time
import traceback
from collections import deque
from pathlib import Path

import numpy as np
from brainflow.board_shim import BoardShim
from brainflow.data_filter import DataFilter, DetrendOperations, WindowOperations

from fah_eeg.board import (
    MUSE_2_BOARD_ID,
    MuseConnectionOptions,
    eeg_channel_names,
    muse_session,
    wait_for_board_data,
)
from fah_eeg.pidfile import clear_pid, write_pid
from fah_eeg.session_io import SessionRecorder, default_session_path

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
    parser.add_argument("--serial-number", default=None)
    parser.add_argument("--mac-address", default=None)
    parser.add_argument("--preset", default=None)
    parser.add_argument("--window-sec", type=float, default=2.0)
    parser.add_argument("--history", type=int, default=80)
    parser.add_argument("--channel", type=int, default=0)
    parser.add_argument("--update-ms", type=int, default=150)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--pid-file",
        type=Path,
        default=None,
        help="Write this process PID here while running (removed on exit).",
    )
    return parser.parse_args(argv)


def band_powers(signal: np.ndarray, sampling_rate: int) -> np.ndarray:
    if len(signal) < sampling_rate // 2:
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
    integrate = getattr(np, "trapezoid", None) or np.trapz
    powers = []
    for _, lo, hi in BANDS:
        mask = (freqs >= lo) & (freqs < hi)
        powers.append(float(integrate(dens[mask], freqs[mask])) if np.any(mask) else 0.0)
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

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    pg.setConfigOptions(antialias=True)

    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyRegular

        ns_app = NSApplication.sharedApplication()
        ns_app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        ns_app.activateIgnoringOtherApps_(True)
    except Exception:
        pass

    win = pg.GraphicsLayoutWidget(title=f"Muse 2 live bands — {ch_name}")
    win.resize(1100, 740)

    plot_spec = win.addPlot(row=0, col=0, title=f"Band power over time ({ch_name})")
    img = pg.ImageItem()
    plot_spec.addItem(img)
    plot_spec.setLabel("left", "Band")
    plot_spec.setLabel("bottom", "Time windows")
    plot_spec.getAxis("left").setTicks([[(i, name) for i, (name, _, _) in enumerate(BANDS)]])
    img.setLookupTable(pg.colormap.get("viridis").getLookupTable(0.0, 1.0, 256))
    img.setImage(np.full((len(BANDS), args.history), -12.0), autoLevels=False, levels=(-12, -2))

    win.nextRow()
    plot_bar = win.addPlot(row=1, col=0, title="Current band power")
    bar = pg.BarGraphItem(
        x=np.arange(len(BANDS)),
        height=np.zeros(len(BANDS)),
        width=0.6,
        brush=(80, 160, 220),
    )
    plot_bar.addItem(bar)
    plot_bar.getAxis("bottom").setTicks([[(i, name) for i, (name, _, _) in enumerate(BANDS)]])
    plot_bar.setXRange(-0.5, len(BANDS) - 0.5)
    plot_bar.setYRange(0, 1)
    plot_bar.setLabel("left", "Power")

    status = pg.LabelItem(justify="left")
    win.addItem(status, row=2, col=0)
    status.setText(f"UI ready — connecting to Muse 2 on a background thread… ({out.name})")

    win.show()
    win.raise_()
    win.activateWindow()
    app.processEvents()
    write_pid(args.pid_file)
    print("Plot window open. Connecting to Muse 2 on a worker thread…", flush=True)
    print(f"Recording path: {out.resolve()}", flush=True)

    class StreamWorker(QtCore.QThread):
        """Own all BrainFlow I/O off the GUI thread."""

        status = QtCore.Signal(str)
        frame = QtCore.Signal(object, int)  # powers ndarray, samples_written
        failed = QtCore.Signal(str)

        def __init__(self) -> None:
            super().__init__()
            self._stop = threading.Event()

        def request_stop(self) -> None:
            self._stop.set()

        def run(self) -> None:
            recorder: SessionRecorder | None = None
            try:
                self.status.emit(f"BLE connect in progress… ({out.name})")
                with muse_session(options) as board:
                    self.status.emit("Stream started — waiting for first packet…")
                    first = wait_for_board_data(
                        board,
                        timeout_sec=25.0,
                        should_stop=self._stop.is_set,
                    )
                    if first is None or not first.size:
                        raise RuntimeError(
                            "No samples received. Muse on/worn, phone BT disconnected?"
                        )

                    # Open CSV only after real data arrives.
                    recorder = SessionRecorder(out)
                    recorder.write_matrix(first)
                    self.status.emit(
                        f"Streaming {ch_name} @ {sampling_rate} Hz | recording {out.name}"
                    )
                    print(f"Streaming {ch_name} @ {sampling_rate} Hz", flush=True)
                    buffer = first[board_ch].astype(np.float64).copy()
                    poll = max(args.update_ms, 50) / 1000.0
                    while not self._stop.is_set():
                        data = board.get_board_data()
                        if data.size:
                            recorder.write_matrix(data)
                            channel = data[board_ch]
                            buffer = np.concatenate([buffer, channel])
                            if len(buffer) > window_samples * 3:
                                buffer = buffer[-window_samples * 3 :]

                        if len(buffer) < window_samples:
                            self.status.emit(
                                f"{ch_name} | buffering… n={recorder.samples_written} | {out.name}"
                            )
                        else:
                            powers = band_powers(buffer[-window_samples:], sampling_rate)
                            self.frame.emit(powers, recorder.samples_written)

                        time.sleep(poll)

                    leftover = board.get_board_data()
                    if leftover.size:
                        recorder.write_matrix(leftover)
            except Exception as exc:
                traceback.print_exc()
                self.failed.emit(str(exc))
            finally:
                if recorder is not None:
                    n = recorder.samples_written
                    recorder.close()
                    print(f"Wrote {n} samples → {out.resolve()}", flush=True)

    worker = StreamWorker()
    cleaned = {"done": False}

    def on_status(text: str) -> None:
        status.setText(text)

    def on_frame(powers: object, n: int) -> None:
        arr = np.asarray(powers, dtype=np.float64)
        history.append(arr)
        bar.setOpts(height=arr)
        ymax = float(np.max(arr)) if arr.size else 1.0
        plot_bar.setYRange(0, max(ymax * 1.2, 1e-9))
        matrix = np.full((len(BANDS), args.history), np.nan)
        stacked = np.vstack(history).T
        matrix[:, -stacked.shape[1] :] = np.log10(stacked + 1e-12)
        finite = matrix[np.isfinite(matrix)]
        if finite.size:
            img.setImage(
                np.nan_to_num(matrix, nan=float(np.min(finite))),
                autoLevels=True,
            )
        status.setText(
            f"{ch_name} | n={n} | "
            + "  ".join(f"{name}: {arr[i]:.2e}" for i, (name, _, _) in enumerate(BANDS))
        )

    def on_failed(message: str) -> None:
        status.setText(f"Connect/stream failed: {message}")
        print(f"Worker failed: {message}", flush=True)

    def cleanup() -> None:
        if cleaned["done"]:
            return
        cleaned["done"] = True
        worker.request_stop()
        if not worker.wait(8000):
            print("Worker did not stop in time; terminating thread…", flush=True)
            worker.terminate()
            worker.wait(2000)
        clear_pid(args.pid_file)

    worker.status.connect(on_status)
    worker.frame.connect(on_frame)
    worker.failed.connect(on_failed)
    worker.start()

    def _signal_quit(signum: int, _frame: object) -> None:
        print(f"\nReceived {signal.Signals(signum).name} — closing viz…", flush=True)
        app.quit()

    signal.signal(signal.SIGINT, _signal_quit)
    signal.signal(signal.SIGTERM, _signal_quit)
    # Keep Python signal handlers responsive while Qt is looping.
    keep_alive = QtCore.QTimer()
    keep_alive.start(200)
    keep_alive.timeout.connect(lambda: None)

    app.aboutToQuit.connect(cleanup)

    def close_event(event) -> None:  # type: ignore[no-untyped-def]
        cleanup()
        event.accept()

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
        traceback.print_exc()
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
