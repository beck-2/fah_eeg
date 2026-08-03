"""Incremental session CSV writer with named channels and BrainFlow timestamps."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from brainflow.board_shim import BoardShim, BrainFlowPresets
from brainflow.data_filter import DataFilter

from fah_eeg.board import MUSE_2_BOARD_ID


def default_session_path(prefix: str = "muse2") -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path("data/sessions") / f"{prefix}_{stamp}.csv"


def channel_header_names(board_id: int = MUSE_2_BOARD_ID) -> list[str]:
    """One CSV column name per BrainFlow DEFAULT_PRESET row."""
    descr = BoardShim.get_board_descr(board_id)
    n = int(descr["num_rows"])
    names = [f"ch{i}" for i in range(n)]

    pkg = descr.get("package_num_channel")
    if pkg is not None:
        names[int(pkg)] = "package_num"

    eeg_idx = descr.get("eeg_channels") or []
    eeg_names = descr.get("eeg_names")
    if isinstance(eeg_names, str):
        labels = [s.strip() for s in eeg_names.split(",") if s.strip()]
    else:
        labels = []
    for i, ch in enumerate(eeg_idx):
        names[int(ch)] = labels[i] if i < len(labels) else f"eeg_{ch}"

    for ch in descr.get("other_channels") or []:
        names[int(ch)] = f"other_{ch}"

    ts = descr.get("timestamp_channel")
    if ts is not None:
        names[int(ts)] = "timestamp"

    marker = descr.get("marker_channel")
    if marker is not None:
        names[int(marker)] = "marker"

    return names


def full_session_header(board_id: int = MUSE_2_BOARD_ID) -> list[str]:
    """EEG clock rows plus forward-filled AUX (IMU) and ANCILLARY (PPG/HR)."""
    return [
        *channel_header_names(board_id),
        "accel_x",
        "accel_y",
        "accel_z",
        "gyro_x",
        "gyro_y",
        "gyro_z",
        "ppg_red",
        "ppg_ir",
        "ppg_other",
        "heart_rate_bpm",
        "oxygen_pct",
        "timestamp_iso",
    ]


class SessionRecorder:
    """Appends drained Muse matrices to one CSV (EEG rows @ ~256 Hz).

    Each poll should call ``push_from_board(board)``, which drains
    DEFAULT (EEG), AUXILIARY (accel/gyro), and ANCILLARY (PPG) presets and
    writes EEG-timed rows with the latest IMU/PPG values forward-filled.
    Heart rate / SpO2 are derived when enough PPG is buffered.
    """

    def __init__(self, path: Path, board_id: int = MUSE_2_BOARD_ID) -> None:
        self.path = path
        self.board_id = board_id
        self.header = full_session_header(board_id)
        self.eeg_header = channel_header_names(board_id)
        self.timestamp_channel = BoardShim.get_timestamp_channel(board_id)
        self.samples_written = 0

        self._aux_sr = BoardShim.get_sampling_rate(
            board_id, BrainFlowPresets.AUXILIARY_PRESET
        )
        self._anc_sr = BoardShim.get_sampling_rate(
            board_id, BrainFlowPresets.ANCILLARY_PRESET
        )
        self._accel_chs = BoardShim.get_accel_channels(
            board_id, BrainFlowPresets.AUXILIARY_PRESET
        )
        self._gyro_chs = BoardShim.get_gyro_channels(
            board_id, BrainFlowPresets.AUXILIARY_PRESET
        )
        self._ppg_chs = BoardShim.get_ppg_channels(
            board_id, BrainFlowPresets.ANCILLARY_PRESET
        )

        # Latest hold values for non-EEG streams.
        self._accel = [np.nan, np.nan, np.nan]
        self._gyro = [np.nan, np.nan, np.nan]
        self._ppg = [np.nan, np.nan, np.nan]
        self._heart_rate = np.nan
        self._oxygen = np.nan

        # Rolling PPG for heart rate.
        # BrainFlow: fft_size even and >= 1024, and data_len must be > fft_size.
        self._ppg_red_buf: deque[float] = deque(maxlen=max(4096, self._anc_sr * 60))
        self._ppg_ir_buf: deque[float] = deque(maxlen=max(4096, self._anc_sr * 60))
        self._hr_fft = 1024
        self._hr_need = 1280  # ~20s @ 64 Hz
        self._hr_every = 64  # recompute ~1/s at 64 Hz PPG
        self._ppg_since_hr = 0

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", newline="", buffering=1)
        self._file.write(",".join(self.header) + "\n")

    def ingest_sidebands(self, board: BoardShim) -> None:
        """Drain AUX + ANCILLARY into forward-fill holds (does not touch EEG)."""
        try:
            aux = board.get_board_data(preset=BrainFlowPresets.AUXILIARY_PRESET)
        except Exception:
            aux = np.zeros((0, 0))
        try:
            anc = board.get_board_data(preset=BrainFlowPresets.ANCILLARY_PRESET)
        except Exception:
            anc = np.zeros((0, 0))
        self._ingest_aux(aux)
        self._ingest_anc(anc)

    def push_from_board(self, board: BoardShim) -> np.ndarray:
        """Drain all Muse presets, append EEG-timed rows, return EEG matrix (may be empty)."""
        self.ingest_sidebands(board)
        eeg = board.get_board_data()
        if eeg.size:
            self.write_matrix(eeg)
        return eeg


    def write_matrix(self, data: np.ndarray) -> int:
        """Write a DEFAULT_PRESET (EEG) matrix; IMU/PPG columns use latest holds."""
        if data.size == 0:
            return 0
        if data.ndim != 2:
            raise ValueError(f"Expected 2D board data, got shape {data.shape}")

        samples = data.T
        ts_col = self.timestamp_channel
        ax, ay, az = self._accel
        gx, gy, gz = self._gyro
        pr, pi, po = self._ppg
        hr, o2 = self._heart_rate, self._oxygen

        lines: list[str] = []
        for row in samples:
            values = [f"{v:.10g}" for v in row]
            unix_ts = float(row[ts_col])
            iso = datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()
            extra = [
                ax,
                ay,
                az,
                gx,
                gy,
                gz,
                pr,
                pi,
                po,
                hr,
                o2,
            ]
            extra_s = [("" if not np.isfinite(v) else f"{float(v):.10g}") for v in extra]
            lines.append(",".join([*values, *extra_s, iso]))
        self._file.write("\n".join(lines) + "\n")
        self.samples_written += samples.shape[0]
        return int(samples.shape[0])

    def _ingest_aux(self, data: np.ndarray) -> None:
        if data is None or data.size == 0:
            return
        # last sample hold
        n = data.shape[1]
        for i, ch in enumerate(self._accel_chs[:3]):
            self._accel[i] = float(data[ch, n - 1])
        for i, ch in enumerate(self._gyro_chs[:3]):
            self._gyro[i] = float(data[ch, n - 1])

    def _ingest_anc(self, data: np.ndarray) -> None:
        if data is None or data.size == 0:
            return
        n = data.shape[1]
        red_ch = self._ppg_chs[0] if len(self._ppg_chs) > 0 else None
        ir_ch = self._ppg_chs[1] if len(self._ppg_chs) > 1 else None
        other_ch = self._ppg_chs[2] if len(self._ppg_chs) > 2 else None

        for i in range(n):
            if red_ch is not None:
                r = float(data[red_ch, i])
                self._ppg[0] = r
                self._ppg_red_buf.append(r)
            if ir_ch is not None:
                ir = float(data[ir_ch, i])
                self._ppg[1] = ir
                self._ppg_ir_buf.append(ir)
            if other_ch is not None:
                self._ppg[2] = float(data[other_ch, i])
            self._ppg_since_hr += 1

        if self._ppg_since_hr >= self._hr_every:
            self._ppg_since_hr = 0
            self._recompute_vitals()

    def _recompute_vitals(self) -> None:
        need = self._hr_need
        fft_size = self._hr_fft
        if len(self._ppg_ir_buf) < need or len(self._ppg_red_buf) < need:
            return
        ppg_ir = np.asarray(list(self._ppg_ir_buf)[-need:], dtype=np.float64)
        ppg_red = np.asarray(list(self._ppg_red_buf)[-need:], dtype=np.float64)
        try:
            self._heart_rate = float(
                DataFilter.get_heart_rate(ppg_ir, ppg_red, self._anc_sr, fft_size)
            )
        except Exception:
            pass
        try:
            self._oxygen = float(
                DataFilter.get_oxygen_level(ppg_ir, ppg_red, self._anc_sr)
            )
        except Exception:
            pass

    def close(self) -> None:
        if getattr(self, "_file", None) is not None:
            self._file.flush()
            self._file.close()
            self._file = None  # type: ignore[assignment]

    def __enter__(self) -> SessionRecorder:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
