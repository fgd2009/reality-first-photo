from __future__ import annotations

import numpy as np

EPSILON = 1e-6


def clamp01(arr: np.ndarray) -> np.ndarray:
    return np.clip(arr, 0.0, 1.0)


def luminance(arr: np.ndarray) -> np.ndarray:
    return 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]


def saturation_rgb(arr: np.ndarray) -> np.ndarray:
    return arr.max(axis=2) - arr.min(axis=2)


def to_uint8(arr: np.ndarray) -> np.ndarray:
    return np.round(clamp01(arr) * 255.0).astype(np.uint8)


def to_uint16(arr: np.ndarray) -> np.ndarray:
    return np.round(clamp01(arr) * 65535.0).astype(np.uint16)


def rgb_to_hsv(arr: np.ndarray) -> np.ndarray:
    arr = clamp01(arr).astype(np.float32, copy=False)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    mx = np.max(arr, axis=2)
    mn = np.min(arr, axis=2)
    delta = mx - mn

    hue = np.zeros_like(mx)
    mask = delta > EPSILON
    r_mask = mask & (mx == r)
    g_mask = mask & (mx == g)
    b_mask = mask & (mx == b)
    hue[r_mask] = ((g[r_mask] - b[r_mask]) / delta[r_mask]) % 6.0
    hue[g_mask] = ((b[g_mask] - r[g_mask]) / delta[g_mask]) + 2.0
    hue[b_mask] = ((r[b_mask] - g[b_mask]) / delta[b_mask]) + 4.0
    hue = hue / 6.0

    sat = np.zeros_like(mx)
    nonzero = mx > EPSILON
    sat[nonzero] = delta[nonzero] / mx[nonzero]
    return np.stack([hue, sat, mx], axis=2)


def apply_channel_gains(arr: np.ndarray, gains: np.ndarray) -> np.ndarray:
    return clamp01(arr * gains.reshape(1, 1, 3))


def adjust_saturation(arr: np.ndarray, gain: float) -> np.ndarray:
    lum = luminance(arr)[..., None]
    return clamp01(lum + (arr - lum) * gain)


def blend(original: np.ndarray, adjusted: np.ndarray, strength: float) -> np.ndarray:
    strength = float(np.clip(strength, 0.0, 1.0))
    return clamp01(original * (1.0 - strength) + adjusted * strength)
