"""Adaptive calm / focus / valence scores from Muse band powers.

Uses relative posterior/frontal PSD ratios with a rolling personal baseline
so 0–1 scores track *your* recent distribution instead of fixed absolute cutoffs.

Valence uses frontal alpha asymmetry (FAA): ln(α_right) − ln(α_left) on AF8/AF7
(Muse stand-ins for F4/F3). Positive FAA → relatively greater left frontal
activation (approach / positive valence); negative → rightward / withdrawal.
See Smith et al. (2017) and common open-source FAA pipelines.

Temporal smoothing follows common neurofeedback practice: average / EMA over
~1–3 s so feedback tracks state changes without flicker from short artifacts
(blinks, motion, Welch-window edge effects).
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


def _ema_alpha(dt: float, tau_sec: float) -> float:
    """EMA weight for time-constant τ: y += α (x − y), α = 1 − e^(−Δt/τ)."""
    return float(1.0 - np.exp(-dt / max(tau_sec, 1e-3)))


def frontal_alpha_asymmetry(left_alpha: float, right_alpha: float) -> float:
    """Classic FAA: ln(P_right) − ln(P_left). Higher → relative left activation."""
    return float(np.log(float(right_alpha) + 1e-12) - np.log(float(left_alpha) + 1e-12))


@dataclass
class RollingZ:
    """Online z-score against a sliding window of recent values."""

    maxlen: int = 180
    min_n: int = 20
    _vals: deque[float] = field(default_factory=deque)

    def __post_init__(self) -> None:
        self._vals = deque(maxlen=self.maxlen)

    def push(self, value: float) -> float:
        self._vals.append(float(value))
        if len(self._vals) < self.min_n:
            # Warmup: return raw feature (mapped later via sigmoid).
            return value
        arr = np.asarray(self._vals, dtype=np.float64)
        mu = float(arr.mean())
        sd = float(arr.std()) + 1e-8
        return (value - mu) / sd


@dataclass
class MentalStateTracker:
    """Map band-power dicts → calm/focus/valence in [0, 1]."""

    emit_hz: float = 60.0
    baseline_sec: float = 45.0
    # Pre-smooth band features before z-score (~literature ~1 s epochs).
    feature_tau_sec: float = 1.5
    # Display / game feedback (~2–3 s is typical for stable NFT gauges).
    output_tau_sec: float = 3.0

    _calm_z: RollingZ = field(init=False)
    _focus_z: RollingZ = field(init=False)
    _valence_z: RollingZ = field(init=False)
    _calm_feat_s: float | None = None
    _focus_feat_s: float | None = None
    _valence_feat_s: float | None = None
    _calm_s: float | None = None
    _focus_s: float | None = None
    _valence_s: float | None = None
    last_metrics: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Baseline buffer sized in *seconds of samples*, but we push features
        # every emit — downsample into z by storing EMA'd feats only.
        n = int(max(30, min(self.baseline_sec * self.emit_hz, 900)))
        warm = max(15, n // 6)
        self._calm_z = RollingZ(maxlen=n, min_n=warm)
        self._focus_z = RollingZ(maxlen=n, min_n=warm)
        self._valence_z = RollingZ(maxlen=n, min_n=warm)
        dt = 1.0 / max(self.emit_hz, 1.0)
        self._a_feat = _ema_alpha(dt, self.feature_tau_sec)
        self._a_out = _ema_alpha(dt, self.output_tau_sec)

    def update(
        self,
        post_rel: dict[str, float],
        front_rel: dict[str, float],
        *,
        left_alpha: float = 0.0,
        right_alpha: float = 0.0,
    ) -> tuple[float, float, float]:
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

        # Valence / approach: frontal alpha asymmetry (ln right − ln left).
        faa = frontal_alpha_asymmetry(left_alpha, right_alpha)

        af = self._a_feat
        if self._calm_feat_s is None:
            self._calm_feat_s = calm_feat
            self._focus_feat_s = float(focus_feat)
            self._valence_feat_s = faa
        else:
            self._calm_feat_s += af * (calm_feat - self._calm_feat_s)
            self._focus_feat_s += af * (float(focus_feat) - self._focus_feat_s)
            assert self._valence_feat_s is not None
            self._valence_feat_s += af * (faa - self._valence_feat_s)

        calm_z = self._calm_z.push(float(self._calm_feat_s))
        focus_z = self._focus_z.push(float(self._focus_feat_s))
        valence_z = self._valence_z.push(float(self._valence_feat_s))

        # Soft competition: high posterior alpha shouldn't also score as focused.
        raw_calm = _sigmoid(1.1 * calm_z - 0.35 * focus_z)
        raw_focus = _sigmoid(1.1 * focus_z - 0.35 * calm_z)
        # Valence is independent of arousal axes (calm/focus).
        raw_valence = _sigmoid(1.0 * valence_z)

        ao = self._a_out
        if self._calm_s is None:
            self._calm_s = raw_calm
            self._focus_s = raw_focus
            self._valence_s = raw_valence
        else:
            self._calm_s += ao * (raw_calm - self._calm_s)
            self._focus_s += ao * (raw_focus - self._focus_s)
            assert self._valence_s is not None
            self._valence_s += ao * (raw_valence - self._valence_s)

        warm_v = len(self._valence_z._vals) >= self._valence_z.min_n
        self.last_metrics = {
            "post_alpha": pa,
            "post_beta": pb,
            "front_beta": fb,
            "front_theta": ft,
            "calm_feat": calm_feat,
            "engagement": float(engagement),
            "inv_tbr": float(inv_tbr),
            "left_alpha": float(left_alpha),
            "right_alpha": float(right_alpha),
            "faa": faa,
            "faa_feat": float(self._valence_feat_s),
            "feature_tau_sec": self.feature_tau_sec,
            "output_tau_sec": self.output_tau_sec,
            "calm_z": float(calm_z) if len(self._calm_z._vals) >= self._calm_z.min_n else 0.0,
            "focus_z": float(focus_z) if len(self._focus_z._vals) >= self._focus_z.min_n else 0.0,
            "valence_z": float(valence_z) if warm_v else 0.0,
        }
        assert (
            self._calm_s is not None
            and self._focus_s is not None
            and self._valence_s is not None
        )
        return float(self._calm_s), float(self._focus_s), float(self._valence_s)
