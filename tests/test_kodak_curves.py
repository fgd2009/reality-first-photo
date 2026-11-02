"""Sanity checks for digitized Kodak chart samples. No PDF is stored in the repo."""
from pathlib import Path

import numpy as np

from reality_first_normalization.film.recipe import load_recipe

ROOT = Path(__file__).resolve().parents[1] / "data" / "curves"


def _rows(name: str) -> tuple[list[str], np.ndarray]:
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    header = [line for line in lines if line.startswith("#")]
    data = np.array([
        [float(part) for part in line.split(",")]
        for line in lines if line and not line.startswith("#") and not line.startswith("log") and not line.startswith("wave")
    ])
    return header, data


def test_curve_csvs_name_the_source_and_stay_inside_the_chart_axes():
    assert "not numeric tables released by the manufacturer" in (ROOT / "README.md").read_text(encoding="utf-8")
    for name, x_limit, y_limit in (
        ("kodak_portra_400_characteristic.csv", 6.0, 4.2),
        ("kodak_ektar_100_characteristic.csv", 6.0, 4.2),
        ("kodak_portra_400_spectral_dye_density.csv", 800.0, 2.6),
        ("kodak_ektar_100_spectral_dye_density.csv", 800.0, 2.6),
    ):
        header, data = _rows(name)
        text = "\n".join(header)
        assert "Digitized by this project" in text
        assert "E-40" in text
        assert data.shape[0] > 100
        assert np.all(np.isfinite(data))
        assert float(np.min(data[:, 1:])) > 0.0
        assert float(np.max(data[:, 1:])) < y_limit
        assert float(np.max(data[:, 0])) < x_limit


def test_recipe_gamma_follows_the_digitized_straight_line():
    pairs = (
        ("warm-negative-400", "kodak_portra_400_characteristic.csv", -1.44),
        ("neutral-negative-100", "kodak_ektar_100_characteristic.csv", -0.84),
    )
    for recipe_id, filename, reference in pairs:
        _header, data = _rows(filename)
        log_h = data[:, 0] - reference
        green = data[:, 2]
        mask = (log_h > -1.0) & (log_h < 0.4)
        slope = float(np.polyfit(log_h[mask], green[mask], 1)[0])
        recipe = load_recipe(recipe_id)
        assert abs(recipe.curve.gamma - slope) < 0.05
        assert "unverified" in recipe.verification
