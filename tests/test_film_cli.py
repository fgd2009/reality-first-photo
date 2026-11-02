"""CLI, CUBE export and four-way report for the parametric film model."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from reality_first_normalization import compare, io, local_cli
from reality_first_normalization.film.lut_export import bake_film_cube
from reality_first_normalization.film.recipe import bundled_recipe_dir, load_recipe
from reality_first_normalization.film.simulate import apply_film
from reality_first_normalization.lut import apply_cube_lut, load_cube_lut


def _image(path: Path) -> None:
    pixels = np.full((12, 16, 3), 0.25)
    pixels[1:5, 2:7] = (0.92, 0.55, 0.3)
    pixels[6:11, 8:15] = (0.15, 0.35, 0.8)
    io.save_image(pixels, path)


def _png(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        assert image.mode == "RGB"
        assert image.info["icc_profile"] == io.working_srgb_icc()
        return np.asarray(image).copy()


def test_export_records_recipe_hash_seed_and_repeats(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    _image(source / "sample.png")
    first = tmp_path / "first"
    second = tmp_path / "second"
    args = [
        "--input", str(source), "--film", "warm-negative-400", "--film-seed", "7",
        "--normalize-strength", "0", "--format", "png", "--max-long-edge", "0",
    ]
    assert local_cli.main([*args, "--output", str(first)]) == 0
    assert local_cli.main([*args, "--output", str(second)]) == 0
    np.testing.assert_array_equal(_png(first / "sample.png"), _png(second / "sample.png"))
    manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    recipe_bytes = (bundled_recipe_dir() / "warm-negative-400.json").read_bytes()
    assert manifest["status"] == "complete"
    assert manifest["film"]["recipe_id"] == "warm-negative-400"
    assert manifest["film"]["recipe_sha256"] == hashlib.sha256(recipe_bytes).hexdigest()
    assert manifest["film"]["parameters_sha256"]
    assert manifest["film"]["seed"] == 7
    assert manifest["film"]["spatial_effects"] is True
    assert manifest["film"]["verification"] == "unverified"
    assert manifest["items"][0]["film"]["applied"] is True
    assert manifest["items"][0]["film"]["image_seed_hex"]
    other = tmp_path / "other-seed"
    assert local_cli.main([
        "--input", str(source), "--output", str(other), "--film", "warm-negative-400",
        "--film-seed", "8", "--normalize-strength", "0", "--format", "png", "--max-long-edge", "0",
    ]) == 0
    assert not np.array_equal(_png(first / "sample.png"), _png(other / "sample.png"))


def test_color_only_export_matches_the_baked_cube_nodes(tmp_path):
    body, provenance = bake_film_cube("neutral-negative-100", size=5, strength=1.0)
    cube_path = tmp_path / "neutral.cube"
    cube_path.write_text(body, encoding="utf-8")
    lut = load_cube_lut(str(cube_path))
    recipe = load_recipe("neutral-negative-100")
    level = np.linspace(0.0, 1.0, 5)
    blue, green, red = np.meshgrid(level, level, level, indexing="ij")
    encoded = np.stack((red, green, blue), axis=-1).reshape(1, 125, 3)
    direct = apply_film(encoded, recipe, spatial=False).image
    through_lut = apply_cube_lut(encoded, lut)
    assert np.max(np.abs(direct - through_lut)) < 2e-5
    assert provenance["spatial_effects_included"] is False
    assert provenance["verification"] == "unverified"
    assert provenance["omitted"] == ["grain", "halation"]
    destination = tmp_path / "written.cube"
    assert local_cli.main([
        "film-lut", "--recipe", "neutral-negative-100", "--output", str(destination), "--size", "5",
    ]) == 0
    sidecar = json.loads(destination.with_name("written.provenance.json").read_text(encoding="utf-8"))
    assert sidecar["cube_sha256"] == hashlib.sha256(destination.read_bytes()).hexdigest()
    assert local_cli.main([
        "film-lut", "--recipe", "neutral-negative-100", "--output", str(destination), "--size", "5",
    ]) == 2


def test_film_comparison_keeps_four_routes_and_says_unverified(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    _image(source / "sample.png")
    output = tmp_path / "compare"
    assert compare.run_comparison(
        source, output, film="cool-reversal-100", film_seed=3, normalize_strength=0.6, max_long_edge=0,
    ) == 0
    report = json.loads((output / "compare.json").read_text(encoding="utf-8"))
    assert report["status"] == "complete"
    assert [item["id"] for item in report["recipes"]] == [
        "original", "normalized", "film", "normalized_film",
    ]
    assert report["film"]["verification"] == "unverified"
    assert report["film"]["seed"] == 3
    assert report["lut"] is None
    page = (output / "index.html").read_text(encoding="utf-8")
    assert "unverified" in page
    assert "cool-reversal-100" in page
    for recipe in ("original", "normalized", "film", "normalized_film"):
        assert (output / recipe / "sample.png").is_file()
    original = _png(output / "original" / "sample.png")
    filmed = _png(output / "film" / "sample.png")
    assert not np.array_equal(original, filmed)
    again = tmp_path / "compare-again"
    assert local_cli.main([
        "compare", "--input", str(source), "--output", str(again),
        "--film", "cool-reversal-100", "--film-seed", "3", "--normalize-strength", "0.6",
        "--max-long-edge", "0",
    ]) == 0
    np.testing.assert_array_equal(filmed, _png(again / "film" / "sample.png"))


def test_color_only_comparison_ignores_the_seed(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    _image(source / "sample.png")
    first = tmp_path / "a"
    second = tmp_path / "b"
    common = [
        "compare", "--input", str(source), "--film", "warm-negative-400",
        "--film-color-only", "--normalize-strength", "0", "--max-long-edge", "0",
    ]
    assert local_cli.main([*common, "--output", str(first), "--film-seed", "1"]) == 0
    assert local_cli.main([*common, "--output", str(second), "--film-seed", "2"]) == 0
    np.testing.assert_array_equal(_png(first / "film" / "sample.png"), _png(second / "film" / "sample.png"))
    manifest = json.loads((first / "film" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["film"]["spatial_effects"] is False
    assert manifest["items"][0]["film"]["image_seed_hex"] is None


def test_changed_recipe_file_fails_the_comparison_without_html(tmp_path, monkeypatch):
    source = tmp_path / "input"
    source.mkdir()
    _image(source / "sample.png")
    recipe_path = tmp_path / "custom.json"
    document = json.loads((bundled_recipe_dir() / "neutral-negative-100.json").read_text(encoding="utf-8"))
    document["id"] = "custom-neutral"
    recipe_path.write_text(json.dumps(document), encoding="utf-8")
    output = tmp_path / "changed"
    original_run = compare.local_cli.run
    calls = {"n": 0}

    def change_after_first(args):
        code = original_run(args)
        calls["n"] += 1
        if calls["n"] == 1:
            document["grain"]["strength"] = 0.2
            recipe_path.write_text(json.dumps(document), encoding="utf-8")
        return code

    monkeypatch.setattr(compare.local_cli, "run", change_after_first)
    assert compare.run_comparison(source, output, film=str(recipe_path), max_long_edge=0) == 2
    assert json.loads((output / "compare.json").read_text(encoding="utf-8"))["status"] == "failed"
    assert not (output / "index.html").exists()


def test_compare_without_lut_or_film_creates_nothing(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    _image(source / "sample.png")
    output = tmp_path / "missing"
    assert local_cli.main(["compare", "--input", str(source), "--output", str(output)]) == 2
    assert not output.exists()
