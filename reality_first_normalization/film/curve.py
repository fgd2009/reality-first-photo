"""Parametric Hurter–Driffield characteristic curve.

The curve maps log10 exposure to optical density. Its inflection slope is the
recipe gamma. Asymmetry warps log exposure so the toe and shoulder can differ
while the slope at the midpoint stays equal to gamma. The warp is an original
smooth skew, not a digitized manufacturer curve. See docs/FILM_MODEL.md.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, eq=False)
class CharacteristicCurve:
    d_min: float
    d_max: float
    log_h_mid: float
    gamma: float
    asymmetry: float
    skew_softness: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.d_min < self.d_max <= 6.0:
            raise ValueError("Characteristic curve densities must satisfy 0 <= d_min < d_max <= 6")
        if not 0.0 < self.gamma <= 8.0:
            raise ValueError("Characteristic curve gamma must be in (0, 8]")
        if not -4.0 <= self.log_h_mid <= 4.0:
            raise ValueError("Characteristic curve log_h_mid must be in [-4, 4]")
        if not -0.85 <= self.asymmetry <= 0.85:
            raise ValueError("Characteristic curve asymmetry must be in [-0.85, 0.85]")
        if not 0.05 <= self.skew_softness <= 5.0:
            raise ValueError("Characteristic curve skew_softness must be in [0.05, 5]")

    def density(self, log_exposure: np.ndarray) -> np.ndarray:
        """Optical density. Positive asymmetry lengthens the toe and shortens the shoulder."""
        span = self.d_max - self.d_min
        slope_scale = 4.0 * self.gamma / span
        centered = np.asarray(log_exposure, dtype=np.float64) - self.log_h_mid
        warped = centered * np.exp(self.asymmetry * np.tanh(centered / self.skew_softness))
        exponent = np.clip(-slope_scale * warped, -60.0, 60.0)
        sigmoid = 1.0 / (1.0 + np.exp(exponent))
        return self.d_min + span * sigmoid
