"""Live Muse spectrum + band traces.

Top: scrolling fine-frequency spectrum (causal ≈1 Hz bands, log₁₀ power).
Bottom: relative δ/θ/α/β/γ band powers (causal filter-bank).
"""

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
from brainflow.data_filter import DataFilter, DetrendOperations, NoiseTypes, WindowOperations

from fah_eeg.board import (
    MUSE_2_BOARD_ID,
    MuseConnectionOptions,
    eeg_channel_names,
    muse_session,
    wait_for_board_data,
)
from fah_eeg.pidfile import clear_pid, write_pid
from fah_eeg.session_io import SessionRecorder, default_session_path

BANDS: list[tuple[str, float, float]] = [
    ("Delta", 1.0, 4.0),
    ("Theta", 4.0, 8.0),
    ("Alpha", 8.0, 13.0),
    ("Beta", 13.0, 30.0),
    ("Gamma", 30.0, 45.0),
]

BAND_COLORS = [
    (70, 130, 180),
    (60, 179, 113),
    (255, 170, 50),
    (220, 90, 70),
    (180, 180, 190),
]

# Contact quality: green / amber / red thresholds on 0..1 score.
_CONTACT_GOOD = 0.75
_CONTACT_OK = 0.40


def electrode_contact_score(samples: np.ndarray) -> float:
    """0 = bad / railed, 1 = solid skin contact (BrainFlow rail + flatness)."""
    x = np.asarray(samples, dtype=np.float64).ravel()
    if x.size < 16:
        return 0.0
    rail = float(DataFilter.get_railed_percentage(x.copy(), 1))
    sat = float(np.mean(np.abs(x) >= 980.0))
    std = float(np.std(x))
    q = 1.0 - min(1.0, rail * 8.0)
    if sat > 0.05:
        q *= max(0.0, 1.0 - sat * 2.0)
    if std < 5.0:
        q *= 0.2
    elif std < 15.0:
        q *= 0.6
    return float(np.clip(q, 0.0, 1.0))


class CausalBandTracker:
    """Streaming relative band powers via causal Butterworth filter bank.

    Sliding Welch relative-δ creates *two* peaks per transient ~window_sec apart
    (enter + leave the analysis window). A causal filter bank does not.
    """

    def __init__(
        self,
        sampling_rate: int,
        bands: list[tuple[str, float, float]] = BANDS,
        power_win_sec: float = 0.4,
        order: int = 4,
    ) -> None:
        from scipy.signal import butter, sosfilt_zi

        self.fs = int(sampling_rate)
        self.bands = bands
        self.power_win = max(16, int(power_win_sec * self.fs))
        self._sos: list[np.ndarray] = []
        self._zi: list[np.ndarray] = []
        self._bufs: list[deque[float]] = []
        nyq = 0.5 * self.fs
        for _, lo, hi in bands:
            hi_c = min(hi, nyq * 0.98)
            lo_c = max(lo, 0.1)
            if lo_c >= hi_c:
                raise ValueError(f"bad band {lo}-{hi} at fs={self.fs}")
            sos = butter(order, [lo_c, hi_c], btype="bandpass", fs=self.fs, output="sos")
            self._sos.append(sos)
            self._zi.append(sosfilt_zi(sos) * 0.0)
            self._bufs.append(deque(maxlen=self.power_win))

    def push(self, samples: np.ndarray) -> np.ndarray:
        from scipy.signal import sosfilt

        x = np.asarray(samples, dtype=np.float64).ravel()
        if x.size == 0:
            return np.zeros(len(self.bands), dtype=np.float64)

        powers = np.zeros(len(self.bands), dtype=np.float64)
        for i, sos in enumerate(self._sos):
            y, self._zi[i] = sosfilt(sos, x, zi=self._zi[i])
            buf = self._bufs[i]
            buf.extend(float(v) for v in y)
            if len(buf) >= 8:
                arr = np.fromiter(buf, dtype=np.float64, count=len(buf))
                powers[i] = float(np.mean(arr * arr))
        total = float(powers.sum()) + 1e-18
        return powers / total


class CausalSpectrumTracker:
    """Fine-grained causal spectrum (≈1 Hz bands) for the scrolling heatmap.

    Same enter/leave echo as Welch does not apply: each bin is a recursive
    bandpass + short power window, not a sliding FFT aperture.
    """

    def __init__(
        self,
        sampling_rate: int,
        fmin: float = 1.0,
        fmax: float = 50.0,
        bw: float = 1.0,
        power_win_sec: float = 0.35,
        order: int = 2,
    ) -> None:
        from scipy.signal import butter, sosfilt_zi

        self.fs = int(sampling_rate)
        self.power_win = max(16, int(power_win_sec * self.fs))
        self.freqs: list[float] = []
        self._sos: list[np.ndarray] = []
        self._zi: list[np.ndarray] = []
        self._bufs: list[deque[float]] = []

        edges = np.arange(fmin, fmax + bw * 0.5, bw, dtype=np.float64)
        nyq = 0.5 * self.fs
        for lo, hi in zip(edges[:-1], edges[1:]):
            hi_c = min(float(hi), nyq * 0.98)
            lo_c = max(float(lo), 0.2)
            if lo_c >= hi_c:
                continue
            sos = butter(order, [lo_c, hi_c], btype="bandpass", fs=self.fs, output="sos")
            self._sos.append(sos)
            self._zi.append(sosfilt_zi(sos) * 0.0)
            self._bufs.append(deque(maxlen=self.power_win))
            self.freqs.append(0.5 * (lo_c + hi_c))

        if not self.freqs:
            raise RuntimeError("CausalSpectrumTracker: no valid frequency bins")

    @property
    def freq_hz(self) -> np.ndarray:
        return np.asarray(self.freqs, dtype=np.float64)

    def push(self, samples: np.ndarray) -> np.ndarray:
        """Return log10 mean-square power per fine band."""
        from scipy.signal import sosfilt

        x = np.asarray(samples, dtype=np.float64).ravel()
        out = np.full(len(self._sos), -12.0, dtype=np.float64)
        if x.size == 0:
            return out

        for i, sos in enumerate(self._sos):
            y, self._zi[i] = sosfilt(sos, x, zi=self._zi[i])
            buf = self._bufs[i]
            buf.extend(float(v) for v in y)
            if len(buf) >= 8:
                arr = np.fromiter(buf, dtype=np.float64, count=len(buf))
                out[i] = float(np.log10(max(float(np.mean(arr * arr)), 1e-18)))
        return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Live scrolling PSD + relative band traces for Muse 2 "
            "(records full-session CSV by default)."
        ),
    )
    parser.add_argument("--serial-number", default=None)
    parser.add_argument("--mac-address", default=None)
    parser.add_argument("--preset", default=None)
    parser.add_argument(
        "--channel",
        type=int,
        default=1,
        help="EEG channel index 0..3 (TP9/AF7/AF8/TP10). Default 1 = AF7.",
    )
    parser.add_argument("--window-sec", type=float, default=1.5)
    parser.add_argument("--fmax", type=float, default=50.0)
    parser.add_argument("--history", type=int, default=150)
    parser.add_argument("--update-ms", type=int, default=100)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--pid-file", type=Path, default=None)
    parser.add_argument(
        "--no-record",
        action="store_true",
        help="Disable CSV session recording (on by default).",
    )
    return parser.parse_args(argv)


def _welch_nfft(data_len: int, sampling_rate: int) -> int:
    """Pick an FFT size BrainFlow accepts: power-of-two and strictly < data_len."""
    # Prefer ~1 Hz bins (nfft ≈ fs); fall back if the window is shorter.
    nfft = int(DataFilter.get_nearest_power_of_two(sampling_rate))
    while nfft >= data_len and nfft > 16:
        nfft //= 2
    return nfft


def compute_psd_and_bands(
    signal: np.ndarray,
    sampling_rate: int,
    *,
    fmax: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (freqs_hz, log10_psd, welch_relative_bands).

    Prefer ``CausalBandTracker`` for live band *traces* — Welch relative bands
    duplicate transient peaks at ≈ window length.
    """
    empty_f = np.zeros(0)
    empty_p = np.zeros(0)
    empty_b = np.zeros(len(BANDS), dtype=np.float64)
    if len(signal) < sampling_rate // 2:
        return empty_f, empty_p, empty_b

    data = signal.astype(np.float64).copy()
    try:
        DataFilter.remove_environmental_noise(
            data, sampling_rate, NoiseTypes.FIFTY.value
        )
    except Exception:
        pass
    DataFilter.detrend(data, DetrendOperations.CONSTANT.value)

    nfft = _welch_nfft(len(data), sampling_rate)
    if nfft < 16:
        return empty_f, empty_p, empty_b
    overlap = nfft // 2
    try:
        dens, freqs = DataFilter.get_psd_welch(
            data,
            nfft,
            overlap,
            sampling_rate,
            WindowOperations.HANNING.value,
        )
    except Exception:
        return empty_f, empty_p, empty_b

    freqs = np.asarray(freqs, dtype=np.float64)
    dens = np.asarray(dens, dtype=np.float64)

    integrate = getattr(np, "trapezoid", None) or np.trapz
    bands = np.zeros(len(BANDS), dtype=np.float64)
    for i, (_, lo, hi) in enumerate(BANDS):
        mask = (freqs >= lo) & (freqs < hi)
        bands[i] = float(integrate(dens[mask], freqs[mask])) if np.any(mask) else 0.0
    bands = bands / (float(bands.sum()) + 1e-18)

    mask = (freqs >= 0.5) & (freqs <= fmax)
    freqs = freqs[mask]
    dens = dens[mask]
    logp = np.log10(np.maximum(dens, 1e-18))
    return freqs, logp, bands


def run_viz(args: argparse.Namespace) -> Path | None:
    import pyqtgraph as pg
    from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

    sampling_rate = BoardShim.get_sampling_rate(MUSE_2_BOARD_ID)
    eeg_channels = BoardShim.get_eeg_channels(MUSE_2_BOARD_ID)
    names = eeg_channel_names()
    if args.channel < 0 or args.channel >= len(eeg_channels):
        raise SystemExit(
            f"--channel {args.channel} out of range; "
            f"available 0..{len(eeg_channels) - 1} ({names})"
        )

    board_ch = eeg_channels[args.channel]
    ch_name = names[args.channel] if args.channel < len(names) else f"ch{board_ch}"
    electrode_names = [names[i] if i < len(names) else f"ch{c}" for i, c in enumerate(eeg_channels)]
    out = None if args.no_record else (args.out or default_session_path("muse2_psd")).resolve()
    options = MuseConnectionOptions(
        serial_number=args.serial_number,
        mac_address=args.mac_address,
        other_info=args.preset,
    )

    # Probe bin grid (no Muse needed).
    _probe = CausalSpectrumTracker(sampling_rate, fmin=1.0, fmax=args.fmax, bw=1.0)
    probe_freqs = _probe.freq_hz
    del _probe

    n_freq = int(probe_freqs.size)
    n_bands = len(BANDS)
    f_lo = float(probe_freqs[0])
    f_hi = float(probe_freqs[-1])
    contact_win = max(64, int(0.5 * sampling_rate))

    psd_history: deque[np.ndarray] = deque(maxlen=args.history)
    band_history: deque[np.ndarray] = deque(maxlen=args.history)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    pg.setConfigOptions(antialias=True)

    class HeadsetHud(QtWidgets.QWidget):
        """4 electrode contact segments (TP9 / AF7 / AF8 / TP10)."""

        def __init__(self, labels: list[str]) -> None:
            super().__init__()
            self.labels = labels
            self.qualities = [0.0] * len(labels)
            self.setFixedHeight(36)
            self.setMinimumWidth(280)

        def set_contact(self, qualities: list[float]) -> None:
            self.qualities = list(qualities)
            self.update()

        def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
            del event
            p = QtGui.QPainter(self)
            p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            w, h = self.width(), self.height()
            p.fillRect(0, 0, w, h, QtGui.QColor(18, 18, 22))

            seg_w, seg_h, gap = 36, 16, 6
            n = len(self.labels)
            cluster_w = n * seg_w + (n - 1) * gap
            sx0 = 14
            seg_y = h - seg_h - 6
            font = p.font()
            font.setPixelSize(9)
            p.setFont(font)
            p.setPen(QtGui.QColor(150, 150, 160))
            p.drawText(sx0, 12, "contact")
            # Right-align segments so empty left space stays clear.
            sx = max(sx0 + 52, w - cluster_w - 14)
            for i, name in enumerate(self.labels):
                q = self.qualities[i] if i < len(self.qualities) else 0.0
                if q >= _CONTACT_GOOD:
                    col = QtGui.QColor(70, 185, 110)
                elif q >= _CONTACT_OK:
                    col = QtGui.QColor(220, 170, 50)
                else:
                    col = QtGui.QColor(200, 70, 65)
                x = sx + i * (seg_w + gap)
                p.setPen(QtCore.Qt.PenStyle.NoPen)
                p.setBrush(col)
                p.drawRoundedRect(x, seg_y, seg_w, seg_h, 3, 3)
                fill_h = max(2, int((seg_h - 2) * float(np.clip(q, 0.0, 1.0))))
                p.setBrush(QtGui.QColor(255, 255, 255, 40))
                p.drawRoundedRect(x + 1, seg_y + seg_h - 1 - fill_h, seg_w - 2, fill_h, 2, 2)
                p.setPen(QtGui.QColor(200, 200, 210))
                p.setFont(font)
                p.drawText(
                    QtCore.QRect(x, 2, seg_w, 12),
                    int(QtCore.Qt.AlignmentFlag.AlignHCenter),
                    name,
                )
            p.end()

    shell = QtWidgets.QWidget()
    shell.setWindowTitle(f"Muse 2 PSD + bands — {ch_name}")
    shell.resize(1200, 856)
    shell_layout = QtWidgets.QVBoxLayout(shell)
    shell_layout.setContentsMargins(0, 0, 0, 0)
    shell_layout.setSpacing(0)
    hud = HeadsetHud(electrode_names)
    shell_layout.addWidget(hud)

    win = pg.GraphicsLayoutWidget()
    shell_layout.addWidget(win, stretch=1)

    # --- Top: causal fine-frequency scrolling spectrum ---
    plot_scroll = win.addPlot(
        row=0,
        col=0,
        title=f"Scrolling spectrum · {ch_name} (causal ≈1 Hz bands, log₁₀ power)",
    )
    img = pg.ImageItem(axisOrder="row-major")
    plot_scroll.addItem(img)
    plot_scroll.setLabel("left", "Frequency", units="Hz")
    plot_scroll.setLabel("bottom", "Recent windows →")
    img.setRect(QtCore.QRectF(0.0, f_lo, float(args.history), f_hi - f_lo))
    plot_scroll.setYRange(f_lo, f_hi, padding=0.0)
    plot_scroll.setXRange(0, args.history, padding=0.0)
    plot_scroll.enableAutoRange(axis="xy", enable=False)
    plot_scroll.getAxis("left").enableAutoSIPrefix(False)
    try:
        cmap = pg.colormap.get("magma")
    except Exception:
        cmap = pg.colormap.get("viridis")
    img.setLookupTable(cmap.getLookupTable(0.0, 1.0, 256))
    img.setImage(
        np.full((n_freq, args.history), -12.0),
        autoLevels=False,
        levels=(-12, -2),
    )
    # Band boundary guides on the spectrogram
    for _, edge, _ in BANDS[1:]:
        if edge < args.fmax:
            plot_scroll.addItem(
                pg.InfiniteLine(
                    pos=edge,
                    angle=0,
                    pen=pg.mkPen((255, 255, 255, 60), style=QtCore.Qt.PenStyle.DotLine),
                )
            )

    # --- Bottom: relative band traces (kept) ---
    win.nextRow()
    plot_lines = win.addPlot(
        row=1,
        col=0,
        title=(
            "Relative band power — causal filter-bank "
            "(δ 1–4 · θ 4–8 · α 8–13 · β 13–30 · γ 30–45)"
        ),
    )
    plot_lines.setLabel("left", "Relative power")
    plot_lines.setLabel("bottom", "Recent windows →")
    plot_lines.setYRange(0.0, 1.0, padding=0.0)
    plot_lines.setXRange(0, args.history, padding=0.0)
    plot_lines.enableAutoRange(axis="xy", enable=False)
    plot_lines.showGrid(x=True, y=True, alpha=0.25)
    plot_lines.addLegend(offset=(10, 10))
    band_curves = [
        plot_lines.plot(pen=pg.mkPen(color, width=2), name=name)
        for (name, _, _), color in zip(BANDS, BAND_COLORS)
    ]

    status = pg.LabelItem(justify="left")
    win.addItem(status, row=2, col=0)
    status.setText(f"UI ready — connecting Muse… ({out.name if out else 'no-record'})")

    shell.show()
    shell.raise_()
    shell.activateWindow()
    app.processEvents()
    write_pid(args.pid_file)
    print(f"PSD+bands window open · {ch_name} · fmax={args.fmax:g}", flush=True)
    if out:
        print(f"Recording path: {out}", flush=True)

    class StreamWorker(QtCore.QThread):
        status = QtCore.Signal(str)
        # freqs, logp, bands, n, contact qualities
        frame = QtCore.Signal(object, object, object, int, object)
        failed = QtCore.Signal(str)

        def __init__(self) -> None:
            super().__init__()
            self._stop = threading.Event()

        def request_stop(self) -> None:
            self._stop.set()

        def run(self) -> None:
            """Run with BLE stall detection + auto-reconnect.

            Muse often drops mid-session on macOS while the Python process keeps
            looping; without this the plot freezes on a stale buffer (\"flatline\").
            """
            recorder: SessionRecorder | None = None
            poll = max(args.update_ms, 40) / 1000.0
            stall_sec = 2.5
            attempt = 0
            try:
                while not self._stop.is_set():
                    attempt += 1
                    bands_tracker = CausalBandTracker(sampling_rate)
                    spectrum_tracker = CausalSpectrumTracker(
                        sampling_rate, fmin=1.0, fmax=args.fmax, bw=1.0
                    )
                    contact_bufs: list[deque[float]] = [
                        deque(maxlen=contact_win) for _ in eeg_channels
                    ]
                    try:
                        self.status.emit(
                            f"BLE connect… attempt {attempt} "
                            f"({out.name if out else 'no CSV'})"
                        )
                        print(f"Muse connect attempt {attempt}…", flush=True)
                        with muse_session(options) as board:
                            self.status.emit("Stream started — waiting for first packet…")
                            first = wait_for_board_data(
                                board,
                                timeout_sec=25.0,
                                should_stop=self._stop.is_set,
                            )
                            if first is None or not first.size:
                                raise RuntimeError(
                                    "No samples. Muse on/worn? Phone app holding BLE?"
                                )

                            if out is not None:
                                if recorder is None:
                                    recorder = SessionRecorder(out)
                                    print(f"Recording → {out}", flush=True)
                                recorder.ingest_sidebands(board)
                                recorder.write_matrix(first)

                            chunk0 = first[board_ch].astype(np.float64).copy()
                            # Warm filter state so first frames aren't garbage.
                            rel0 = bands_tracker.push(chunk0)
                            logp0 = spectrum_tracker.push(chunk0)
                            for i, ch in enumerate(eeg_channels):
                                contact_bufs[i].extend(
                                    float(v) for v in first[ch].astype(np.float64)
                                )
                            qualities0 = [
                                electrode_contact_score(np.fromiter(buf, dtype=np.float64))
                                for buf in contact_bufs
                            ]
                            last_data = time.monotonic()
                            self.status.emit(
                                f"{ch_name} @ {sampling_rate} Hz · "
                                f"causal spectrum + bands · live"
                            )
                            self.frame.emit(
                                spectrum_tracker.freq_hz,
                                logp0,
                                rel0,
                                recorder.samples_written if recorder else 0,
                                qualities0,
                            )

                            while not self._stop.is_set():
                                if recorder is not None:
                                    data = recorder.push_from_board(board)
                                else:
                                    try:
                                        from brainflow.board_shim import BrainFlowPresets

                                        board.get_board_data(
                                            preset=BrainFlowPresets.AUXILIARY_PRESET
                                        )
                                        board.get_board_data(
                                            preset=BrainFlowPresets.ANCILLARY_PRESET
                                        )
                                    except Exception:
                                        pass
                                    data = board.get_board_data()

                                if data.size:
                                    last_data = time.monotonic()
                                    new = data[board_ch].astype(np.float64)
                                    rel = bands_tracker.push(new)
                                    logp = spectrum_tracker.push(new)
                                    for i, ch in enumerate(eeg_channels):
                                        contact_bufs[i].extend(
                                            float(v) for v in data[ch].astype(np.float64)
                                        )
                                    qualities = [
                                        electrode_contact_score(
                                            np.fromiter(buf, dtype=np.float64)
                                        )
                                        for buf in contact_bufs
                                    ]
                                    n = recorder.samples_written if recorder else 0
                                    self.frame.emit(
                                        spectrum_tracker.freq_hz,
                                        logp,
                                        rel,
                                        n,
                                        qualities,
                                    )
                                else:
                                    gap = time.monotonic() - last_data
                                    if gap > stall_sec:
                                        raise RuntimeError(
                                            f"BLE stall: no EEG for {gap:.1f}s"
                                        )
                                    if gap > 1.0:
                                        self.status.emit(
                                            f"BLE weak/no packets ({gap:.1f}s)…"
                                        )

                                time.sleep(poll)
                    except Exception as exc:
                        if self._stop.is_set():
                            break
                        msg = f"Disconnected: {exc} — reconnecting in 2s…"
                        print(msg, flush=True)
                        self.status.emit(msg)
                        # Briefly release radio before retry.
                        for _ in range(20):
                            if self._stop.is_set():
                                break
                            time.sleep(0.1)
            finally:
                if recorder is not None:
                    n = recorder.samples_written
                    recorder.close()
                    print(f"Wrote {n} samples → {out}", flush=True)

    worker = StreamWorker()
    cleaned = {"done": False}

    def on_status(text: str) -> None:
        status.setText(text)

    def on_frame(
        freqs: object,
        logp: object,
        bands: object,
        n: int,
        qualities: object,
    ) -> None:
        f = np.asarray(freqs, dtype=np.float64)
        p = np.asarray(logp, dtype=np.float64)
        rel = np.asarray(bands, dtype=np.float64).ravel()
        qs = [float(q) for q in list(qualities)] if qualities is not None else []
        if qs:
            hud.set_contact(qs)
        if f.size == 0 or p.size == 0:
            return
        if f.size != n_freq:
            p = np.interp(probe_freqs, f, p, left=p[0], right=p[-1])
            f = probe_freqs

        psd_history.append(p.copy())
        matrix = np.full((n_freq, args.history), np.nan)
        stacked_psd = np.column_stack(list(psd_history))
        matrix[:, -stacked_psd.shape[1] :] = stacked_psd
        finite = matrix[np.isfinite(matrix)]
        if finite.size:
            lo = float(np.percentile(finite, 5))
            hi = float(np.percentile(finite, 99))
            if hi <= lo:
                hi = lo + 1.0
            img.setImage(
                np.nan_to_num(matrix, nan=lo),
                autoLevels=False,
                levels=(lo, hi),
            )
            img.setRect(QtCore.QRectF(0.0, f_lo, float(args.history), f_hi - f_lo))
        plot_scroll.setYRange(f_lo, f_hi, padding=0.0)

        if rel.size == n_bands:
            band_history.append(rel.copy())
            stacked_b = np.column_stack(list(band_history))
            xs = np.arange(stacked_b.shape[1], dtype=np.float64) + (
                args.history - stacked_b.shape[1]
            )
            for i, curve in enumerate(band_curves):
                curve.setData(xs, stacked_b[i])
            plot_lines.setYRange(0.0, 1.0, padding=0.0)
            parts = "  ".join(
                f"{BANDS[i][0][0]}={rel[i]*100:.0f}%" for i in range(n_bands)
            )
        else:
            parts = "bands…"

        contact_txt = " ".join(
            f"{electrode_names[i]}={'●' if qs[i] >= _CONTACT_GOOD else '◐' if qs[i] >= _CONTACT_OK else '○'}"
            for i in range(min(len(qs), len(electrode_names)))
        )
        status.setText(
            f"{ch_name} | {contact_txt} | n={n} | {parts} | "
            f"{out.name if out else 'no-record'}"
        )

    def on_failed(message: str) -> None:
        status.setText(f"Failed: {message}")
        print(f"Worker failed: {message}", flush=True)

    def cleanup() -> None:
        if cleaned["done"]:
            return
        cleaned["done"] = True
        worker.request_stop()
        if not worker.wait(8000):
            worker.terminate()
            worker.wait(2000)
        clear_pid(args.pid_file)

    worker.status.connect(on_status)
    worker.frame.connect(on_frame)
    worker.failed.connect(on_failed)
    worker.start()

    def _signal_quit(signum: int, _frame: object) -> None:
        print(f"\nReceived {signal.Signals(signum).name} — closing…", flush=True)
        app.quit()

    signal.signal(signal.SIGINT, _signal_quit)
    signal.signal(signal.SIGTERM, _signal_quit)
    keep_alive = QtCore.QTimer()
    keep_alive.start(200)
    keep_alive.timeout.connect(lambda: None)
    app.aboutToQuit.connect(cleanup)

    def close_event(event) -> None:  # type: ignore[no-untyped-def]
        cleanup()
        event.accept()

    shell.closeEvent = close_event  # type: ignore[method-assign]
    app.exec()
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
