"""Density-dependent grain with a reproducible NumPy PCG64 stream.

Selwyn granularity and Nutting's grain-count relation both put the noise in
density, with a scale that grows with developed density and can fall again
near saturation. The recipe supplies the scale. The seed mixes the model
version, the user seed and a sample id so one master seed does not paint the
same field onto every file. See docs/FILM_MODEL.md.
"""
from __future__ import annotations

import hashlib

import numpy as np

from .version import MODEL_VERSION


def image_seed_hex(master_seed: int, sample_id: str) -> str:
    payload = f"{MODEL_VERSION}\n{master_seed}\n{sample_id}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def generator_from_seed_hex(seed_hex: str) -> np.random.Generator:
    entropy = int(seed_hex, 16)
    sequence = np.random.SeedSequence([entropy])
    return np.random.Generator(np.random.PCG64(sequence))


def grain_sigma(
    density: np.ndarray,
    *,
    strength: float,
    exponent: float,
    midtone_emphasis: float,
    d_min: float,
    d_max: float,
) -> np.ndarray:
    """Standard deviation in optical density.

    ``strength`` is the deviation at density 1 when the midtone window is 1.
    ``midtone_emphasis`` 0 follows a power of density. 1 restricts noise to the
    middle of the characteristic curve.
    """
    span = d_max - d_min
    unit = np.clip((density - d_min) / span, 0.0, 1.0)
    window = (1.0 - midtone_emphasis) + midtone_emphasis * (4.0 * unit * (1.0 - unit))
    base = np.power(np.maximum(density, 0.0), exponent)
    return strength * base * window


def apply_density_grain(density: np.ndarray, sigma: np.ndarray, generator: np.random.Generator) -> np.ndarray:
    noise = generator.standard_normal(size=density.shape)
    return np.maximum(density + noise * sigma, 0.0)
