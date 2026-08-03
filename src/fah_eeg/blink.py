"""Low-latency Muse blink (EOG) detection using BrainFlow filters + z-score peaks."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from brainflow.data_filter import DataFilter, FilterTypes, NoiseTypes


@dataclass
class BlinkDetector:
    """Detect blinks from AF7/AF8 using BrainFlow signal processing.

    Pipeline (common Muse EOG approach):
      average AF7+AF8 → notch 50Hz → bandpass 0.5–10 Hz → BrainFlow
      detect_peaks_z_score → rising-edge fire with refractory.
    """

    sampling_rate: int = 256
    lag: int = 128  # ~0.5s baseline window for z-score
    threshold: float = 3.5
    influence: float = 0.2
    refractory_sec: float = 0.15
    min_buffer_sec: float = 1.0

    _buf: np.ndarray | None = None
    _last_fire_mono: float = -1e9
    _armed: bool = True

    def __post_init__(self) -> None:
        self._buf = np.zeros(0, dtype=np.float64)
        self._max_keep = int(3.0 * self.sampling_rate)

    def push_channels(
        self,
        af7: np.ndarray,
        af8: np.ndarray,
        now_mono: float,
    ) -> tuple[bool, float]:
        if af7.size == 0 and af8.size == 0:
            return False, 0.0
        n = (
            int(min(af7.size, af8.size))
            if af7.size and af8.size
            else int(max(af7.size, af8.size))
        )
        if n <= 0:
            return False, 0.0
        a7 = np.asarray(af7[:n] if af7.size else af8[:n], dtype=np.float64)
        a8 = np.asarray(af8[:n] if af8.size else af7[:n], dtype=np.float64)
        return self.push(0.5 * (a7 + a8), now_mono)

    def push(self, frontal_samples: np.ndarray, now_mono: float) -> tuple[bool, float]:
        """Ingest new AF7/AF8-averaged samples. Returns (fired, peak_score)."""
        if frontal_samples.size == 0:
            return False, 0.0

        chunk = np.asarray(frontal_samples, dtype=np.float64).ravel()
        assert self._buf is not None
        self._buf = np.concatenate([self._buf, chunk])
        if len(self._buf) > self._max_keep:
            self._buf = self._buf[-self._max_keep :]

        min_n = int(self.min_buffer_sec * self.sampling_rate)
        if len(self._buf) < max(min_n, self.lag + 8):
            return False, 0.0

        # Work on a copy — BrainFlow filters mutate in-place.
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

        lookback = max(len(chunk) + 4, 8)
        recent = scores[-lookback:]
        peak_score = float(np.max(recent)) if recent.size else 0.0
        active = bool(np.any(recent > 0.0))

        # Rising-edge: require a quiet stretch before the next fire so a sticky
        # peak flag doesn't re-trigger after refractory alone.
        rising = active and self._armed
        if not active:
            self._armed = True

        if not rising:
            return False, peak_score
        if (now_mono - self._last_fire_mono) < self.refractory_sec:
            return False, peak_score

        self._last_fire_mono = now_mono
        self._armed = False
        return True, peak_score
