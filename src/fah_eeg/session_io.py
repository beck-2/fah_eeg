"""Incremental session CSV writer with named channels and BrainFlow timestamps."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from brainflow.board_shim import BoardShim

from fah_eeg.board import MUSE_2_BOARD_ID


def default_session_path(prefix: str = "muse2") -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path("data/sessions") / f"{prefix}_{stamp}.csv"


def channel_header_names(board_id: int = MUSE_2_BOARD_ID) -> list[str]:
    """One CSV column name per BrainFlow row."""
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


class SessionRecorder:
    """Appends drained board matrices to a CSV (samples as rows)."""

    def __init__(self, path: Path, board_id: int = MUSE_2_BOARD_ID) -> None:
        self.path = path
        self.board_id = board_id
        self.header = channel_header_names(board_id)
        self.timestamp_channel = BoardShim.get_timestamp_channel(board_id)
        self.samples_written = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # header + human-readable UTC derived from BrainFlow unix timestamps
        self._file = self.path.open("w", newline="", buffering=1)
        self._file.write(",".join([*self.header, "timestamp_iso"]) + "\n")

    def write_matrix(self, data: np.ndarray) -> int:
        """Write a BrainFlow matrix shaped (channels, samples). Returns sample count."""
        if data.size == 0:
            return 0
        if data.ndim != 2:
            raise ValueError(f"Expected 2D board data, got shape {data.shape}")
        # BrainFlow: rows=channels, cols=samples → CSV rows=samples
        samples = data.T
        ts_col = self.timestamp_channel
        lines: list[str] = []
        for row in samples:
            values = [f"{v:.10g}" for v in row]
            unix_ts = float(row[ts_col])
            iso = datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()
            lines.append(",".join([*values, iso]))
        self._file.write("\n".join(lines) + "\n")
        self.samples_written += samples.shape[0]
        return int(samples.shape[0])

    def close(self) -> None:
        if getattr(self, "_file", None) is not None:
            self._file.flush()
            self._file.close()
            self._file = None  # type: ignore[assignment]

    def __enter__(self) -> SessionRecorder:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
