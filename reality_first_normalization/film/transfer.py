"""IEC 61966-2-1 sRGB transfer, used as the film model's input and output encoding.

The inverse transfer turns encoded working-space pixels into a relative
exposure proxy. It does not recover camera scene-linear light.
"""
from __future__ import annotations

import numpy as np

_ENCODED_BREAK = 0.04045
_LINEAR_BREAK = 0.0031308


def srgb_to_linear(encoded: np.ndarray) -> np.ndarray:
    """Inverse opto-electronic transfer of IEC 61966-2-1."""
    channel = np.asarray(encoded, dtype=np.float64)
    linear: np.ndarray = np.where(
        channel <= _ENCODED_BREAK,
        channel / 12.92,
        ((channel + 0.055) / 1.055) ** 2.4,
    )
    return linear


def linear_to_srgb(linear: np.ndarray) -> np.ndarray:
    """Opto-electronic transfer of IEC 61966-2-1. Negative light is clipped to 0."""
    light = np.maximum(np.asarray(linear, dtype=np.float64), 0.0)
    encoded: np.ndarray = np.where(
        light <= _LINEAR_BREAK,
        12.92 * light,
        1.055 * np.power(light, 1.0 / 2.4) - 0.055,
    )
    return encoded
