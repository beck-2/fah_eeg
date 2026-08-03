"""Adaptive calm / focus scores from Muse band powers.

Uses relative posterior/frontal PSD ratios with a rolling personal baseline
so 0–1 scores track *your* recent distribution instead of fixed absolute cutoffs.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np


def _sigmoid(x: float) -> float:
    x = float(np.clip(x, -8.0, 8.0))
    return float(1.0 / (1.0 + np.exp(-x)))


def _safe_div(num: float, den: float) -> float:
    return float(num / (den + 1e-12))


@dataclass
class RollingZ:
    """Online z-score against a sliding window of recent values."""

    maxlen: int = 180  # ~3 min at 1 Hz feature — we push every emit
    min_n: int = 20
    _vals: deque[float] = field(default_factory=deque)

    def __post_init__(self) -> None:
        self._vals = deque(maxlen=self.maxlen)

    def push(self, value: float) -> float:
        self._vals.append(float(value))
        if len(self._vals) < self.min_n:
            # Warmup: map around 0.5 using a soft absolute scale.
            return value
        arr = np.asarray(self._vals, dtype=np.float64)
        mu = float(arr.mean())
        sd = float(arr.std()) + 1e-8
        return (value - mu) / sd


@dataclass
class MentalStateTracker:
    """Map band-power dicts → calm/focus in [0, 1]."""

    emit_hz: float = 60.0
    baseline_sec: float = 45.0
    ema_alpha: float = 0.12

    _calm_z: RollingZ = field(init=False)
    _focus_z: RollingZ = field(init=False)
    _calm_s: float | None = None
    _focus_s: float | None = None
    last_metrics: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Keep ~baseline_sec of emits (capped so we don't grow forever at 60 Hz).
        n = int(max(30, min(self.baseline_sec * self.emit_hz, 900)))
        warm = max(15, n // 6)
        self._calm_z = RollingZ(maxlen=n, min_n=warm)
        self._focus_z = RollingZ(maxlen=n, min_n=warm)

    def update(
        self,
        post_rel: dict[str, float],
        front_rel: dict[str, float],
    ) -> tuple[float, float]:
        pa = float(post_rel.get("alpha", 0.0))
        pt = float(post_rel.get("theta", 0.0))
        pb = float(post_rel.get("beta", 0.0))
        fa = float(front_rel.get("alpha", 0.0))
        ft = float(front_rel.get("theta", 0.0))
        fb = float(front_rel.get("beta", 0.0))

        # Calm: posterior alpha dominance (relaxed / eyes-closed-ish), penalize beta.
        calm_feat = _safe_div(pa, pa + pb + 0.5 * pt)

        # Focus / engagement: frontal beta over slow rhythms; also inverse TBR.
        engagement = _safe_div(fb, fa + ft)
        inv_tbr = _safe_div(fb, ft)  # high when beta >> theta
        focus_feat = 0.65 * engagement + 0.35 * np.tanh(inv_tbr / 3.0)

        calm_z = self._calm_z.push(calm_feat)
        focus_z = self._focus_z.push(float(focus_feat))

        # Soft competition: high posterior alpha shouldn't also score as focused.
        raw_calm = _sigmoid(1.1 * calm_z - 0.35 * focus_z)
        raw_focus = _sigmoid(1.1 * focus_z - 0.35 * calm_z)

        if self._calm_s is None:
            self._calm_s = raw_calm
            self._focus_s = raw_focus
        else:
            a = self.ema_alpha
            self._calm_s = (1 - a) * self._calm_s + a * raw_calm
            self._focus_s = (1 - a) * self._focus_s + a * raw_focus

        self.last_metrics = {
            "post_alpha": pa,
            "post_beta": pb,
            "front_beta": fb,
            "front_theta": ft,
            "calm_feat": calm_feat,
            "engagement": float(engagement),
            "inv_tbr": float(inv_tbr),
            "calm_z": float(calm_z) if len(self._calm_z._vals) >= self._calm_z.min_n else 0.0,
            "focus_z": float(focus_z) if len(self._focus_z._vals) >= self._focus_z.min_n else 0.0,
        }
        assert self._calm_s is not None and self._focus_s is not None
        return float(self._calm_s), float(self._focus_s)
