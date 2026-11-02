"""Parametric film model. Synthetic pixels only; no commercial stock is claimed."""
import json

import numpy as np
import pytest

from reality_first_normalization.film.curve import CharacteristicCurve
from reality_first_normalization.film.grain import (
    apply_density_grain,
    generator_from_seed_hex,
    grain_sigma,
    image_seed_hex,
)
from reality_first_normalization.film.halation import (
    add_halation,
    separable_gaussian_blur,
)
from reality_first_normalization.film.recipe import (
    bundled_recipe_dir,
    list_recipes,
    load_recipe,
)
from reality_first_normalization.film.simulate import _transmittance, apply_film
from reality_first_normalization.film.transfer import linear_to_srgb, srgb_to_linear
from reality_first_normalization.film.version import MODEL_VERSION


def test_srgb_transfer_matches_the_iec_breakpoints():
    np.testing.assert_allclose(linear_to_srgb(np.array([0.0, 1.0])), [0.0, 1.0], atol=1e-12)
    encoded = linear_to_srgb(np.array(128.0 / 255.0))
    assert 187 <= round(float(encoded) * 255.0) <= 189
    ramp = np.linspace(0.0, 1.0, 64)
    assert np.allclose(srgb_to_linear(linear_to_srgb(ramp)), ramp, atol=1e-12)


def test_characteristic_curve_keeps_gamma_and_records_asymmetry():
    symmetric = CharacteristicCurve(0.2, 2.2, 0.0, 0.6, 0.0, 0.5)
    samples = np.linspace(-2.0, 2.0, 401)
    density = symmetric.density(samples)
    assert np.all(np.diff(density) > 0.0)
    epsilon = 1e-4
    slope = (symmetric.density(np.array([epsilon])) - symmetric.density(np.array([-epsilon]))) / (2.0 * epsilon)
    assert abs(float(slope[0]) - 0.6) < 1e-3
    mid = float(symmetric.density(np.array([0.0]))[0])
    above = float(symmetric.density(np.array([0.4]))[0]) - mid
    below = mid - float(symmetric.density(np.array([-0.4]))[0])
    assert abs(above - below) < 1e-9
    longer_toe = CharacteristicCurve(0.2, 2.2, 0.0, 0.6, 0.5, 0.5)
    assert float(longer_toe.density(np.array([-0.8]))[0]) > float(symmetric.density(np.array([-0.8]))[0])


def test_beer_lambert_identity_absorption_is_ten_to_the_minus_density():
    density = np.array([[[1.0, 2.0, 0.0]]])
    transmittance = _transmittance(density, np.eye(3), np.zeros(3))
    np.testing.assert_allclose(transmittance, [[[0.1, 0.01, 1.0]]])


def test_halation_spreads_highlights_and_preserves_a_flat_field():
    flat = np.full((7, 9, 3), 0.4)
    blurred = separable_gaussian_blur(flat, 1.2)
    np.testing.assert_allclose(blurred, flat, atol=1e-12)
    spark = np.zeros((11, 11, 3))
    spark[5, 5] = 4.0
    spread, _requested, applied = add_halation(
        spark, threshold=1.0, gain_rgb=np.array([1.0, 0.0, 0.0]), sigma_fraction=0.15,
    )
    assert applied > 0.0
    assert spread[5, 6, 0] > spread[0, 0, 0]
    assert spread[5, 6, 1] == 0.0
    assert spread[5, 5, 0] > spark[5, 5, 0]


def test_grain_stream_repeats_for_the_same_seed_and_sample():
    density = np.full((6, 5, 3), 0.7)
    sigma = grain_sigma(
        density, strength=0.02, exponent=0.5, midtone_emphasis=0.4, d_min=0.1, d_max=2.0,
    )
    first = apply_density_grain(density, sigma, generator_from_seed_hex(image_seed_hex(4, "frame")))
    second = apply_density_grain(density, sigma, generator_from_seed_hex(image_seed_hex(4, "frame")))
    other = apply_density_grain(density, sigma, generator_from_seed_hex(image_seed_hex(5, "frame")))
    np.testing.assert_array_equal(first, second)
    assert not np.array_equal(first, other)
    assert np.all(first >= 0.0)


def test_strength_zero_returns_the_input_without_a_grain_seed():
    recipe = load_recipe("warm-negative-400")
    image = np.linspace(0.0, 1.0, 36, dtype=np.float64).reshape(3, 4, 3)
    result = apply_film(image, recipe, strength=0.0, seed=9, sample_id="x")
    np.testing.assert_array_equal(result.image, image)
    assert result.record["applied"] is False
    assert result.record["image_seed_hex"] is None


def test_bundled_recipes_are_unverified_and_monotonic_without_grain():
    assert list_recipes() == [
        "cool-reversal-100",
        "high-contrast-reversal-50",
        "neutral-negative-100",
        "soft-portrait-negative-200",
        "warm-negative-400",
    ]
    level = np.linspace(0.0, 1.0, 25)
    ramp = np.stack((level, level, level), axis=-1)[None, :, :]
    outputs = []
    for name in list_recipes():
        recipe = load_recipe(name)
        assert recipe.verification == "unverified"
        assert recipe.sha256
        assert recipe.path == bundled_recipe_dir() / f"{name}.json"
        document = json.loads(recipe.path.read_text(encoding="utf-8"))
        assert document["model_version"] == MODEL_VERSION
        assert "unverified" in document["notes"].casefold()
        assert document["sources"]
        result = apply_film(ramp, recipe, spatial=False)
        luma = 0.2126 * result.image[0, :, 0] + 0.7152 * result.image[0, :, 1] + 0.0722 * result.image[0, :, 2]
        assert luma[-1] > luma[0] + 0.2
        assert np.min(np.diff(luma)) >= -1e-5
        assert np.all((result.image >= 0.0) & (result.image <= 1.0))
        outputs.append(result.image)
    assert not np.allclose(outputs[0], outputs[1])


def test_same_seed_repeats_and_halation_reaches_a_neighbor(tmp_path):
    source = json.loads((bundled_recipe_dir() / "neutral-negative-100.json").read_text(encoding="utf-8"))
    source["id"] = "halo-check"
    source["grain"]["strength"] = 0.0
    source["halation"] = {"threshold": 0.2, "gain_rgb": [0.8, 0.05, 0.02], "sigma_fraction": 0.08}
    path = tmp_path / "halo-check.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    recipe = load_recipe(str(path))
    image = np.full((21, 21, 3), 0.05)
    image[10, 10] = 1.0
    spatial = apply_film(image, recipe, spatial=True, seed=1, sample_id="spark")
    again = apply_film(image, recipe, spatial=True, seed=1, sample_id="spark")
    color_only = apply_film(image, recipe, spatial=False, seed=1, sample_id="spark")
    np.testing.assert_array_equal(spatial.image, again.image)
    assert np.max(np.abs(spatial.image[10, 12] - color_only.image[10, 12])) > 1e-4


def test_recipe_loader_rejects_claims_it_cannot_check(tmp_path):
    document = json.loads((bundled_recipe_dir() / "warm-negative-400.json").read_text(encoding="utf-8"))
    document["verification"] = "checked-against-scans"
    path = tmp_path / "claimed.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="unverified"):
        load_recipe(str(path))
    document["verification"] = "unverified"
    document["mystery"] = 1
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported field"):
        load_recipe(str(path))
    path.write_text('{"id": "a", "id": "b"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate key"):
        load_recipe(str(path))
    with pytest.raises(ValueError, match="Unknown film recipe"):
        load_recipe("not-a-stock")
