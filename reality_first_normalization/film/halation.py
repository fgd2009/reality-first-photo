"""Highlight halation as extra exposure spread by a Gaussian.

Halation is light that passes the emulsion, reflects from the film base and
re-exposes it. This module models that as a normalized Gaussian spread of the
exposure above a threshold, added before the characteristic curve. It is not a
measured point-spread function. See docs/FILM_MODEL.md.
"""
from __future__ import annotations

import numpy as np


def limited_sigma(requested: float, height: int, width: int) -> float:
    """Keep the reflect pad narrower than the image. A 1-pixel image cannot spread."""
    if requested <= 1e-6 or min(height, width) < 2:
        return 0.0
    room = min(height, width) - 1
    return float(min(requested, room / 3.0))


def gaussian_kernel(sigma: float) -> np.ndarray:
    if sigma <= 1e-6:
        return np.ones(1, dtype=np.float64)
    radius = max(1, int(np.ceil(3.0 * sigma)))
    offsets = np.arange(-radius, radius + 1, dtype=np.float64)
    kernel = np.exp(-0.5 * (offsets / sigma) ** 2)
    total = float(kernel.sum())
    return kernel / total


def separable_gaussian_blur(image: np.ndarray, sigma: float) -> np.ndarray:
    """Reflect-padded separable blur. The kernel is normalized, so a constant field is unchanged."""
    kernel = gaussian_kernel(sigma)
    if kernel.size == 1:
        return np.asarray(image, dtype=np.float64, copy=True)
    blurred = _blur_axis(np.asarray(image, dtype=np.float64), kernel, axis=1)
    return _blur_axis(blurred, kernel, axis=0)


def _blur_axis(image: np.ndarray, kernel: np.ndarray, axis: int) -> np.ndarray:
    radius = kernel.size // 2
    moved = np.moveaxis(image, axis, 0)
    padded = np.pad(moved, ((radius, radius), (0, 0), (0, 0)), mode="reflect")
    accum = np.zeros(moved.shape, dtype=np.float64)
    length = moved.shape[0]
    for index, weight in enumerate(kernel.tolist()):
        accum += float(weight) * padded[index : index + length]
    return np.moveaxis(accum, 0, axis)


def add_halation(
    exposure: np.ndarray,
    *,
    threshold: float,
    gain_rgb: np.ndarray,
    sigma_fraction: float,
) -> tuple[np.ndarray, float, float]:
    """Return exposure plus spread highlight, the requested sigma and the applied sigma."""
    height, width = int(exposure.shape[0]), int(exposure.shape[1])
    requested = float(sigma_fraction) * float(max(height, width))
    sigma = limited_sigma(requested, height, width)
    if sigma <= 0.0 or not np.any(gain_rgb > 0.0):
        return exposure, requested, 0.0
    excess = np.maximum(exposure - threshold, 0.0) * gain_rgb.reshape(1, 1, 3)
    return exposure + separable_gaussian_blur(excess, sigma), requested, sigma
