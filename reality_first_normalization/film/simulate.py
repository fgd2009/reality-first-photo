"""Apply one parametric film recipe to encoded sRGB working pixels.

Pipeline, in order: inverse sRGB EOTF, relative exposure, optional halation,
layer sensitivities, characteristic curve, optional density grain, dye
absorption with the Beer–Lambert law, and for ``negative-print`` a second
paper stage. The result is encoded with the sRGB OETF and blended by strength.
Literature and the limits of this simplification are in docs/FILM_MODEL.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..color import clamp01
from .curve import CharacteristicCurve
from .grain import (
    apply_density_grain,
    generator_from_seed_hex,
    grain_sigma,
    image_seed_hex,
)
from .halation import add_halation
from .recipe import FilmRecipe, PrintStage
from .transfer import linear_to_srgb, srgb_to_linear
from .version import MODEL_VERSION

EXPOSURE_FLOOR = 1e-6


@dataclass(frozen=True)
class FilmResult:
    image: np.ndarray
    record: dict[str, Any]


def inactive_film_manifest() -> dict[str, Any]:
    return {
        "applied": False,
        "recipe_id": None,
        "recipe_name": None,
        "recipe_origin": None,
        "recipe_sha256": None,
        "parameters_sha256": None,
        "model_version": None,
        "strength": 0.0,
        "seed": None,
        "spatial_effects": False,
        "verification": None,
        "numpy": None,
        "rng": None,
    }


def film_manifest(recipe: FilmRecipe, *, strength: float, seed: int, spatial: bool) -> dict[str, Any]:
    return {
        "applied": strength > 0.0,
        "recipe_id": recipe.id,
        "recipe_name": recipe.file_name,
        "recipe_origin": recipe.origin,
        "recipe_sha256": recipe.sha256,
        "parameters_sha256": recipe.parameters_sha256,
        "model_version": MODEL_VERSION,
        "strength": strength,
        "seed": seed,
        "spatial_effects": spatial and strength > 0.0,
        "verification": "unverified",
        "numpy": np.__version__,
        "rng": "numpy.random.Generator(PCG64)" if spatial and strength > 0.0 else None,
    }


def inactive_film_item() -> dict[str, Any]:
    return {
        "applied": False,
        "recipe_id": None,
        "recipe_sha256": None,
        "model_version": None,
        "strength": 0.0,
        "seed": None,
        "image_seed_hex": None,
        "spatial_effects": False,
        "halation_sigma_requested_px": None,
        "halation_sigma_px": None,
        "verification": None,
    }


def apply_film(
    encoded_srgb: np.ndarray,
    recipe: FilmRecipe,
    *,
    strength: float = 1.0,
    seed: int = 0,
    sample_id: str = "",
    spatial: bool = True,
) -> FilmResult:
    """Return encoded sRGB and a per-image provenance record.

    ``spatial=False`` skips grain and halation so a 3D LUT can represent the
    remaining pointwise color mapping. Strength 0 returns the clipped input
    and does not draw random numbers.
    """
    original = _validate_image(encoded_srgb)
    amount = _unit_strength(strength)
    _validate_seed(seed)
    if not isinstance(sample_id, str) or len(sample_id) > 1024:
        raise ValueError("sample_id must be a string of at most 1024 characters")
    if not isinstance(spatial, bool):
        raise ValueError("spatial must be a bool")
    if amount == 0.0:
        return FilmResult(original, inactive_film_item())

    exposure = srgb_to_linear(original) * np.exp2(recipe.exposure_ev) / recipe.scene_mid_gray
    requested_sigma = 0.0
    applied_sigma = 0.0
    if spatial and float(np.max(recipe.halation_gain)) > 0.0 and recipe.halation_sigma_fraction > 0.0:
        exposure, requested_sigma, applied_sigma = add_halation(
            exposure,
            threshold=recipe.halation_threshold,
            gain_rgb=recipe.halation_gain,
            sigma_fraction=recipe.halation_sigma_fraction,
        )
    density = _analytical_density(
        exposure,
        sensitivity=recipe.sensitivity,
        offset=recipe.layer_log_h_offset,
        curve=recipe.curve,
    )
    if recipe.process == "reversal":
        # Reversal removes dye where the layer was exposed. The stored curve is
        # the increasing response; dye left in the layer is its complement.
        density = recipe.curve.d_min + recipe.curve.d_max - density
    seed_hex: str | None = None
    if spatial and recipe.grain_strength > 0.0:
        seed_hex = image_seed_hex(seed, sample_id)
        sigma = grain_sigma(
            density,
            strength=recipe.grain_strength,
            exponent=recipe.grain_exponent,
            midtone_emphasis=recipe.grain_midtone_emphasis,
            d_min=recipe.curve.d_min,
            d_max=recipe.curve.d_max,
        )
        density = apply_density_grain(density, sigma, generator_from_seed_hex(seed_hex))
    transmittance = _transmittance(density, recipe.absorption, recipe.orange_mask)
    if recipe.process == "negative-print":
        if recipe.print_stage is None:
            raise ValueError("negative-print recipe is missing its print stage")
        transmittance = _print_transmittance(transmittance, recipe.print_stage)
    filmed = linear_to_srgb(transmittance)
    blended = original * (1.0 - amount) + filmed * amount
    record = {
        "applied": True,
        "recipe_id": recipe.id,
        "recipe_sha256": recipe.sha256,
        "model_version": MODEL_VERSION,
        "strength": amount,
        "seed": seed,
        "image_seed_hex": seed_hex,
        "spatial_effects": spatial,
        "halation_sigma_requested_px": requested_sigma if spatial else None,
        "halation_sigma_px": applied_sigma if spatial else None,
        "verification": "unverified",
    }
    return FilmResult(clamp01(blended), record)


def _analytical_density(
    exposure: np.ndarray,
    *,
    sensitivity: np.ndarray,
    offset: np.ndarray,
    curve: CharacteristicCurve,
) -> np.ndarray:
    layers = exposure @ sensitivity.T
    log_h = np.log10(np.maximum(layers, EXPOSURE_FLOOR))
    return curve.density(log_h + offset.reshape((1, 1, 3)))


def _transmittance(analytical_density: np.ndarray, absorption: np.ndarray, base_density: np.ndarray) -> np.ndarray:
    """Beer–Lambert transmittance from analytical dye density and a 3x3 overlap matrix."""
    integral = analytical_density @ absorption.T + base_density.reshape((1, 1, 3))
    return np.power(10.0, -np.clip(integral, 0.0, 8.0))


def _print_transmittance(negative: np.ndarray, stage: PrintStage) -> np.ndarray:
    paper_exposure = (
        negative
        * np.exp2(stage.exposure_ev)
        * stage.balance.reshape((1, 1, 3))
        / stage.reference_transmittance
    )
    density = _analytical_density(
        paper_exposure,
        sensitivity=stage.sensitivity,
        offset=stage.layer_log_h_offset,
        curve=stage.curve,
    )
    return _transmittance(density, stage.absorption, stage.base_density)


def _validate_image(image: np.ndarray) -> np.ndarray:
    if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3 or image.shape[0] < 1 or image.shape[1] < 1:
        raise ValueError("Film input must be an array of shape (height, width, 3)")
    encoded = np.asarray(image, dtype=np.float64)
    if not np.all(np.isfinite(encoded)):
        raise ValueError("Film input must be finite")
    return clamp01(encoded)


def _unit_strength(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Film strength must be finite and between 0 and 1")
    number = float(value)
    if not np.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError("Film strength must be finite and between 0 and 1")
    return number


def _validate_seed(seed: int) -> None:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("Film seed must be an integer")
    if abs(seed) > 2**63 - 1:
        raise ValueError("Film seed must fit in a signed 64-bit integer")
