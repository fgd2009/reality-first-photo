"""Bake the pointwise film color mapping to an encoded-sRGB 3D CUBE.

Grain and halation depend on neighboring pixels, so they are omitted. The
sidecar records that omission, the recipe hash and the model version. The
table order matches the loader: Adobe Cube 1.0 section 7.2, red fastest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from .recipe import load_recipe
from .simulate import apply_film
from .version import MODEL_VERSION


def bake_film_cube(recipe_name: str, *, size: int = 17, strength: float = 1.0) -> tuple[str, dict[str, Any]]:
    if isinstance(size, bool) or not isinstance(size, int) or not 2 <= size <= 64:
        raise ValueError("Film LUT size must be an integer from 2 to 64")
    recipe = load_recipe(recipe_name)
    level = np.linspace(0.0, 1.0, size, dtype=np.float64)
    blue, green, red = np.meshgrid(level, level, level, indexing="ij")
    encoded = np.stack((red, green, blue), axis=-1).reshape(size * size, size, 3)
    result = apply_film(
        encoded,
        recipe,
        strength=strength,
        seed=0,
        sample_id="film-lut",
        spatial=False,
    )
    table = result.image.reshape(size, size, size, 3)
    title = f"{recipe.id} parametric film model, no grain or halation, unverified"
    lines = [
        "# Parametric film color model. Grain and halation are spatial and are not in this table.",
        "# Not a measurement or reproduction of a commercial film stock.",
        f'TITLE "{title}"',
        f"LUT_3D_SIZE {size}",
    ]
    for blue_index in range(size):
        for green_index in range(size):
            for red_index in range(size):
                red_value, green_value, blue_value = (float(channel) for channel in table[blue_index, green_index, red_index])
                lines.append(f"{red_value:.8f} {green_value:.8f} {blue_value:.8f}")
    body = "\n".join(lines) + "\n"
    provenance: dict[str, Any] = {
        "kind": "film_cube_provenance",
        "model_version": MODEL_VERSION,
        "recipe_id": recipe.id,
        "recipe_name": recipe.file_name,
        "recipe_origin": recipe.origin,
        "recipe_sha256": recipe.sha256,
        "parameters_sha256": recipe.parameters_sha256,
        "strength": float(strength),
        "size": size,
        "domain_min": [0.0, 0.0, 0.0],
        "domain_max": [1.0, 1.0, 1.0],
        "spatial_effects_included": False,
        "omitted": ["grain", "halation"],
        "verification": "unverified",
        "cube_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "note": "Encoded-sRGB lattice of the pointwise model only. Not verified against a film scan.",
    }
    return body, provenance


def write_film_cube(recipe_name: str, output: Path, *, size: int = 17, strength: float = 1.0) -> Path:
    destination = Path(output)
    if destination.suffix.lower() != ".cube":
        raise ValueError("Film LUT output must end in .cube")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Film LUT output already exists; choose a new file (no overwrite)")
    provenance_path = destination.with_name(destination.stem + ".provenance.json")
    if provenance_path.exists() or provenance_path.is_symlink():
        raise ValueError("Film LUT provenance file already exists; choose a new output name")
    if not destination.parent.is_dir():
        raise ValueError("Film LUT output directory does not exist")
    body, provenance = bake_film_cube(recipe_name, size=size, strength=strength)
    destination.write_text(body, encoding="utf-8")
    try:
        provenance_path.write_text(json.dumps(provenance, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except OSError:
        destination.unlink(missing_ok=True)
        raise
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reality-first-photo film-lut",
        description="Export the pointwise film color model as an encoded-sRGB 3D CUBE. Grain and halation are omitted.",
        epilog="Bundled recipes: " + ", ".join(_recipe_names())
        + ". The result has not been verified against physical film.",
    )
    parser.add_argument("--recipe", required=True, help="Bundled recipe id or a JSON recipe path.")
    parser.add_argument("--output", type=Path, required=True, help="New .cube path. A .provenance.json file is written beside it.")
    parser.add_argument("--size", type=int, default=17, help="Lattice size from 2 to 64 (default: 17).")
    parser.add_argument("--strength", type=float, default=1.0, help="Blend toward the film color model, from 0 to 1 (default: 1).")
    args = parser.parse_args(argv)
    try:
        if not np.isfinite(args.strength) or not 0.0 <= args.strength <= 1.0:
            raise ValueError("strength must be finite and between 0 and 1")
        path = write_film_cube(args.recipe, args.output, size=args.size, strength=args.strength)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(f"Exported {path.name}", flush=True)
    print(f"Provenance: {path.with_name(path.stem + '.provenance.json')}", flush=True)
    print("Grain and halation are not in the CUBE. The model is unverified against physical film.", flush=True)
    return 0


def _recipe_names() -> list[str]:
    from .recipe import list_recipes

    return list_recipes()
