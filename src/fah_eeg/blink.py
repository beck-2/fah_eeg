"""Muse blink (EOG) detection using BrainFlow filters + peak z-score."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from brainflow.data_filter import DataFilter, FilterTypes, NoiseTypes


@dataclass
class BlinkDetector:
    """Sensitive realtime blink detector for Muse AF7/AF8.

    Pipeline:
      mean(AF7, AF8) → BrainFlow 50 Hz notch → bandpass 0.5–10 Hz
      → ``DataFilter.detect_peaks_z_score`` → refractory edge fire.
    """

    sampling_rate: int = 256
    lag: int = 96
    threshold: float = 3.8  # lower = more sensitive
    influence: float = 0.2
    refractory_sec: float = 0.32
    history_sec: float = 1.5

    _buf: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float64), init=False)
    _last_fire_mono: float = field(default=-1e9, init=False)

    def __post_init__(self) -> None:
        self._max_keep = int(self.history_sec * self.sampling_rate)

    def push_channels(
        self,
        af7: np.ndarray,
        af8: np.ndarray,
        now_mono: float,
    ) -> tuple[bool, float]:
        if af7.size == 0 and af8.size == 0:
            return False, 0.0
        n = int(min(af7.size, af8.size)) if af8.size and af7.size else int(max(af7.size, af8.size))
        if n <= 0:
            return False, 0.0
        a7 = np.asarray(af7[:n] if af7.size else af8[:n], dtype=np.float64)
        a8 = np.asarray(af8[:n] if af8.size else af7[:n], dtype=np.float64)
        chunk = 0.5 * (a7 + a8)

        self._buf = np.concatenate([self._buf, chunk])
        if len(self._buf) > self._max_keep:
            self._buf = self._buf[-self._max_keep :]

        min_n = self.lag + 32
        if len(self._buf) < min_n:
            return False, 0.0

        sig = self._buf.copy()
        try:
            DataFilter.remove_environmental_noise(
                sig, self.sampling_rate, NoiseTypes.FIFTY.value
            )
            DataFilter.perform_bandpass(
                sig,
                self.sampling_rate,
                0.5,
                10.0,
                2,
                FilterTypes.BUTTERWORTH.value,
                0.0,
            )
            scores = np.asarray(
                DataFilter.detect_peaks_z_score(
                    sig,
                    lag=self.lag,
                    threshold=self.threshold,
                    influence=self.influence,
                ),
                dtype=np.float64,
            )
        except Exception:
            return False, 0.0

        lookback = max(n + 4, 8)
        recent = scores[-lookback:]
        score = float(np.max(recent)) if recent.size else 0.0
        if not np.any(recent > 0.0):
            return False, score
        if (now_mono - self._last_fire_mono) < self.refractory_sec:
            return False, score

        self._last_fire_mono = now_mono
        return True, score

    def push(self, frontal_samples: np.ndarray, now_mono: float) -> tuple[bool, float]:
        return self.push_channels(frontal_samples, frontal_samples, now_mono)
