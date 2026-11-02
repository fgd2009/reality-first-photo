"""Four local recipes, using the same export pipeline and explicit provenance."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

from . import local_cli, report_state
from .comparison_report import render_comparison_html
from .film.recipe import load_recipe
from .film.version import MODEL_VERSION
from .io import resolve_untagged_policy
from .lut import load_cube_lut


def _strength(value: float, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite and between 0 and 1") from exc
    if isinstance(value, bool) or not math.isfinite(number) or not 0 <= number <= 1:
        raise ValueError(f"{name} must be finite and between 0 and 1")
    return number


def _signature(source: Path) -> dict[str, str]:
    return {
        (p.relative_to(source).as_posix() if source.is_dir() else p.name):
        hashlib.sha256(p.read_bytes()).hexdigest()
        for p in local_cli.discover_inputs(source)
    }


def _write_report(output: Path, report: dict) -> None:
    report_state.write_json(output / "compare.json", report)


def _check_unchanged(
    source: Path,
    expected: dict[str, str],
    lut_path: Path | None,
    lut_sha256: str | None,
    film_path: Path | None = None,
    film_sha256: str | None = None,
) -> None:
    if _signature(source) != expected:
        raise ValueError("Input set or content changed during comparison; results are incomplete")
    if lut_path is not None:
        if lut_path.is_symlink():
            raise ValueError("LUT changed to a symlink during comparison; results are incomplete")
        if lut_sha256 is None or hashlib.sha256(lut_path.read_bytes()).hexdigest() != lut_sha256:
            raise ValueError("LUT changed during comparison; results are incomplete")
    if film_path is not None:
        if film_path.is_symlink():
            raise ValueError("Film recipe changed to a symlink during comparison; results are incomplete")
        if film_sha256 is None or hashlib.sha256(film_path.read_bytes()).hexdigest() != film_sha256:
            raise ValueError("Film recipe changed during comparison; results are incomplete")


def _collect_items(names: list[Path], expected: dict[str, str],
                   recipes: list[dict], manifests: dict[str, dict], lut_sha256: str | None) -> list[dict]:
    output_to_input = {Path(name).with_suffix(".png").as_posix(): name for name in expected}
    wanted = {name.as_posix() for name in names}
    stage_items = {}
    for recipe in recipes:
        recipe_id = str(recipe["id"])
        manifest = manifests[recipe_id]
        entries = manifest.get("items", [])
        indexed = {entry.get("output"): entry for entry in entries}
        if not manifest.get("batch_completed"):
            raise ValueError(f"Incomplete or inconsistent {recipe_id} export manifest")
        if manifest.get("status") == "complete" and (len(entries) != len(wanted) or set(indexed) != wanted):
            raise ValueError(f"Incomplete or inconsistent {recipe_id} export manifest")
        if manifest.get("status") not in {"complete", "failed"} or (manifest.get("status") == "failed" and not entries):
            raise ValueError(f"Incomplete or inconsistent {recipe_id} export manifest")
        expected_lut = lut_sha256 if recipe["lut_selected"] else None
        if (manifest.get("lut_sha256") != expected_lut
                or manifest.get("normalize_strength") != recipe["normalize_strength"]
                or manifest.get("lut_strength") != recipe["lut_strength"]):
            raise ValueError(f"Recipe or LUT fingerprint mismatch in {recipe_id}")
        film_meta = manifest.get("film")
        if recipe.get("film_selected"):
            if (
                not isinstance(film_meta, dict)
                or film_meta.get("recipe_sha256") != recipe["film_recipe_sha256"]
                or film_meta.get("strength") != recipe["film_strength"]
                or film_meta.get("seed") != recipe["film_seed"]
                or film_meta.get("spatial_effects") != recipe["film_spatial"]
                or film_meta.get("model_version") != recipe["film_model_version"]
                or film_meta.get("applied") != (recipe["film_strength"] > 0)
            ):
                raise ValueError(f"Film recipe fingerprint mismatch in {recipe_id}")
        elif isinstance(film_meta, dict) and film_meta.get("applied"):
            raise ValueError(f"Unexpected film application in {recipe_id}")
        stage_items[recipe_id] = indexed
    common = set.intersection(*(set(indexed) for indexed in stage_items.values())) if stage_items else set()
    selected = [name for name in names if name.as_posix() in common]
    if not selected:
        raise ValueError("No input succeeded in every comparison recipe")
    items = []
    for relative in selected:
        key = relative.as_posix()
        input_name = output_to_input[key]
        reference = stage_items["original"][key]
        variants = {}
        for recipe in recipes:
            recipe_id = recipe["id"]
            item = stage_items[recipe_id][key]
            if item.get("input_sha256") != expected[input_name]:
                raise ValueError("Input fingerprint differs across comparison recipes")
            if any(item.get(field) != reference.get(field) for field in ("width", "height", "color")):
                raise ValueError("Image dimensions or ICC decisions differ across comparison recipes")
            variants[recipe_id] = {
                "output": (Path(recipe_id) / relative).as_posix(),
                "normalization": item["normalization"], "color": item["color"],
                "film": item.get("film"),
            }
        items.append({"input_name": input_name, "input_sha256": expected[input_name],
                      "width": reference["width"], "height": reference["height"], "variants": variants})
    return items


def _comparison_recipes(
    normalize_strength: float,
    lut_strength: float,
    film_recipe: Any,
    film_strength: float,
    film_seed: int,
    film_color_only: bool,
    lut_available: bool,
) -> list[dict[str, Any]]:
    if film_recipe is None:
        rows = [
            ("original", "Input reference", 0.0, False),
            ("normalized", "Normalization only", normalize_strength, False),
            ("lut_only", "LUT only", 0.0, True),
            ("normalized_lut", "Normalization + LUT", normalize_strength, True),
        ]
    else:
        film_label = "Film color model" if film_color_only else "Film model"
        rows = [
            ("original", "Input reference", 0.0, False),
            ("normalized", "Normalization only", normalize_strength, False),
            ("film", film_label, 0.0, lut_available),
            ("normalized_film", "Normalization + film", normalize_strength, lut_available),
        ]
    recipes: list[dict[str, Any]] = []
    for recipe_id, label, normalization, selected in rows:
        entry: dict[str, Any] = {
            "id": recipe_id, "label": label, "normalize_strength": normalization,
            "lut_strength": lut_strength if selected else 0.0,
            "lut_selected": selected, "lut_applied": selected and lut_strength > 0,
        }
        if film_recipe is not None and recipe_id in {"film", "normalized_film"}:
            entry.update({
                "film_selected": True,
                "film_strength": film_strength,
                "film_seed": film_seed,
                "film_spatial": (not film_color_only) and film_strength > 0.0,
                "film_color_only": film_color_only,
                "film_recipe_id": film_recipe.id,
                "film_recipe_sha256": film_recipe.sha256,
                "film_model_version": MODEL_VERSION,
            })
        recipes.append(entry)
    return recipes


def _film_seed(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or abs(value) > 2**63 - 1:
        raise ValueError("film_seed must be a signed 64-bit integer")
    return value


def run_comparison(source: Path, output: Path, lut_path: Path | None = None, *, normalize_strength: float = .6,
                   lut_strength: float = 1.0, max_long_edge: int = 2048,
                   assume_srgb: bool = False, untagged_policy: str | None = None,
                   film: str | None = None, film_strength: float = 1.0, film_seed: int = 0,
                   film_color_only: bool = False) -> int:
    """Write a private local comparison. Return 0, 2 (failed or partial) or 130 (cancelled).

    Invalid options/paths raise ValueError or OSError before output is created.
    This checks hashes between recipes; it does not lock or snapshot source files.
    A per-file failure is skipped. Successful inputs are still published with status partial.
    """
    normalize_strength = _strength(normalize_strength, "normalize_strength")
    lut_strength = _strength(lut_strength, "lut_strength")
    film_strength = _strength(film_strength, "film_strength")
    film_seed = _film_seed(film_seed)
    if not isinstance(film_color_only, bool):
        raise ValueError("film_color_only must be a bool")
    if lut_path is None and film is None:
        raise ValueError("A comparison needs a CUBE LUT, a film recipe, or both")
    if film is None and (film_strength != 1.0 or film_seed != 0 or film_color_only):
        raise ValueError("film_strength, film_seed and film_color_only require a film recipe")
    if isinstance(max_long_edge, bool) or not isinstance(max_long_edge, int) or max_long_edge < 0:
        raise ValueError("max_long_edge must be a nonnegative integer")
    policy = resolve_untagged_policy(assume_srgb, untagged_policy)
    source, output, files, names = local_cli.plan_inputs(Path(source), Path(output), max_long_edge)
    lut = None
    resolved_lut: Path | None = None
    if lut_path is not None:
        resolved_lut = Path(lut_path)
        if resolved_lut.is_symlink():
            raise ValueError("LUT symlinks are unsupported; choose the actual file")
        resolved_lut = resolved_lut.resolve()
        lut = load_cube_lut(str(resolved_lut))
    film_recipe = load_recipe(film) if film is not None else None
    film_file = film_recipe.path if film_recipe is not None else None
    expected = _signature(source)
    # Successful report items preserve relative names; the pipeline skips EXIF.
    try:
        extra_names = [path.name for path in (resolved_lut, film_file) if path is not None]
        for name in [*expected, *extra_names]:
            name.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("Comparison filenames must be valid UTF-8") from exc
    if {p.relative_to(source).as_posix() if source.is_dir() else p.name for p in files} != set(expected):
        raise ValueError("Input set changed during comparison preparation")
    recipes = _comparison_recipes(
        normalize_strength, lut_strength, film_recipe, film_strength, film_seed, film_color_only, lut is not None,
    )
    notice = "Four alternatives, no automatic ranking. Input and LUT hashes are checked between stages."
    if film_recipe is not None:
        notice = (
            "Four alternatives, no automatic ranking. Input, LUT and film-recipe hashes are checked between stages. "
            "The film model is unverified against physical film."
        )
    report: dict[str, Any] = {
        "kind": "four_way_comparison", "status": "running", "format": "png",
        "working_space": "encoded sRGB", "max_long_edge": max_long_edge,
        "assume_srgb": policy == "explicit", "untagged_policy": policy, "failures": [],
        "reference_notice": "Decoded, ICC-converted/resized sRGB PNG reference, not a source-file copy.",
        "notice": notice,
        "lut": None if lut is None or resolved_lut is None else {"name": resolved_lut.name, "sha256": lut.source_sha256},
        "film": None if film_recipe is None else {
            "id": film_recipe.id, "name": film_recipe.file_name, "origin": film_recipe.origin,
            "sha256": film_recipe.sha256, "parameters_sha256": film_recipe.parameters_sha256,
            "model_version": MODEL_VERSION, "strength": film_strength, "seed": film_seed,
            "spatial_effects": (not film_color_only) and film_strength > 0.0,
            "verification": "unverified",
        },
        "recipes": recipes, "stages": {}, "items": [], "active_recipe": None,
    }
    # Exclusive root creation: no existing content is opened for writing.
    output.mkdir(parents=True, exist_ok=False)
    manifests = {}
    code = 0
    try:
        _write_report(output, report)
        lut_sha = lut.source_sha256 if lut is not None else None
        film_sha = film_recipe.sha256 if film_recipe is not None else None
        for recipe in recipes:
            _check_unchanged(source, expected, resolved_lut, lut_sha, film_file, film_sha)
            recipe_id = recipe["id"]
            report["active_recipe"] = recipe_id
            _write_report(output, report)
            use_film = bool(recipe.get("film_selected"))
            args = argparse.Namespace(
                input=source, output=output / recipe_id,
                lut=resolved_lut if recipe["lut_selected"] else None,
                normalize_strength=recipe["normalize_strength"], lut_strength=recipe["lut_strength"],
                format="png", max_long_edge=max_long_edge,
                assume_srgb=(policy == "explicit"), strict_color=(policy == "strict"),
                untagged_policy=policy, announce_assumptions=(recipe_id == "original"),
                film=film if use_film else None,
                film_strength=recipe.get("film_strength", 1.0),
                film_seed=recipe.get("film_seed", 0),
                film_color_only=bool(recipe.get("film_color_only", False)) if use_film else False,
            )
            result = local_cli.run(args)
            manifest_path = output / recipe_id / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
            report["stages"][recipe_id] = {
                "status": manifest.get("status", "incomplete"),
                "manifest": f"{recipe_id}/manifest.json",
                "exported": len(manifest.get("items", [])),
                "failed_input": manifest.get("failed_input"),
                "failed_stage": manifest.get("failed_stage"),
                "failures": manifest.get("failures", []),
                "batch_completed": manifest.get("batch_completed", False),
            }
            _write_report(output, report)
            if result == 130:
                raise KeyboardInterrupt
            continuable = bool(manifest.get("batch_completed") and manifest.get("items"))
            if result and not continuable:
                raise RuntimeError(
                    f"{recipe_id} export failed at {json.dumps(manifest.get('failed_input'), ensure_ascii=True)} "
                    f"({manifest.get('failed_stage')}): {manifest.get('error', 'see partial stage output')}"
                )
            manifests[recipe_id] = manifest
            _check_unchanged(source, expected, resolved_lut, lut_sha, film_file, film_sha)
        report["items"] = _collect_items(names, expected, recipes, manifests, lut_sha)
        skipped: list[dict[str, str]] = []
        seen_inputs: set[str] = set()
        for recipe in recipes:
            for failure in manifests[str(recipe["id"])].get("failures", []):
                if failure.get("input") in seen_inputs:
                    continue
                seen_inputs.add(str(failure.get("input")))
                skipped.append(failure)
        report["failures"] = skipped
        report["active_recipe"] = None
        if skipped:
            first = skipped[0]
            report["status"] = "partial"
            report["error"] = f"Skipped {first['input']} ({first['stage']}): {first['error']}"
            code = 2
        else:
            report["status"] = "complete"
        html = render_comparison_html(report)
        _check_unchanged(source, expected, resolved_lut, lut_sha, film_file, film_sha)
        temporary = output / ".index.html.tmp"
        temporary.write_text(html, encoding="utf-8")
        temporary.replace(output / "index.html")
        _write_report(output, report)
    except KeyboardInterrupt:
        report.update(status="cancelled", notice="Partial comparison retained; choose a new output directory to restart.")
        code = 130
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        report.update(status="failed", error=str(exc))
        code = 2
    if code and report.get("status") != "partial":
        (output / "index.html").unlink(missing_ok=True)
        (output / ".index.html.tmp").unlink(missing_ok=True)
        try:
            _write_report(output, report)
        except OSError as exc:
            print(f"Cannot save final comparison status: {exc}. Treat all outputs as incomplete.", file=sys.stderr)
        print(f"Comparison {report['status']}: {report.get('error', report['notice'])}", file=sys.stderr)
        print(f"Partial outputs: {output}. Use a new --output directory to retry.", file=sys.stderr)
    elif report.get("status") == "partial":
        skipped = report.get("failures", [])
        print(
            f"Comparison partial: {len(report['items'])} inputs compared, {len(skipped)} skipped. "
            "compare.json status is partial, not complete.",
            flush=True,
        )
        print(f"Open locally: {output / 'index.html'}", flush=True)
        for failure in skipped:
            print(f"Skipped {failure['input']} ({failure['stage']}): {failure['error']}", file=sys.stderr)
        print(f"Partial outputs: {output}. Use a new --output directory to retry failed inputs.", file=sys.stderr)
    else:
        print(f"Comparison complete: {len(report['items'])} inputs, four recipes each.", flush=True)
        print(f"Open locally: {output / 'index.html'}", flush=True)
        print("No result is selected as best. Source files are unchanged; report stays local.", flush=True)
    return code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="reality-first-photo compare",
        description="Privately compare four routes. Without --film: reference, normalization, LUT, and both. With --film: reference, normalization, film, and normalization + film.",
        epilog="Open OUTPUT/index.html locally. Exports are 8-bit sRGB PNG previews; sources are not overwritten. The film model is unverified against physical film.",
    )
    parser.add_argument("--input", type=Path, required=True, help="RGB file or folder. Untagged inputs are assumed to be encoded sRGB unless --strict-color is set. RAW needs the optional raw extra. Symlinks are unsupported.")
    parser.add_argument("--output", type=Path, required=True, help="New directory outside the input tree; no overwrite.")
    parser.add_argument("--lut", type=Path, help="Your local red-fastest encoded-sRGB 3D CUBE. Required unless --film is set.")
    parser.add_argument("--film", help="Bundled film recipe id or a JSON recipe file. Replaces the LUT routes when set. A LUT can still be applied after the film.")
    parser.add_argument("--film-strength", type=local_cli.unit_float, default=1.0)
    parser.add_argument("--film-seed", type=local_cli.film_seed, default=0)
    parser.add_argument("--film-color-only", action="store_true", help="Compare the film color model without grain or halation.")
    parser.add_argument("--normalize-strength", type=local_cli.unit_float, default=.6)
    parser.add_argument("--lut-strength", type=local_cli.unit_float, default=1.0)
    parser.add_argument("--max-long-edge", type=int, default=2048, help="Preview long edge; 0 keeps full dimensions (large-image performance unverified).")
    local_cli.add_color_policy_arguments(parser)
    args = parser.parse_args(argv)
    try:
        policy = local_cli.untagged_policy_from_flags(assume_srgb=args.assume_srgb, strict_color=args.strict_color)
        return run_comparison(
            args.input, args.output, args.lut, normalize_strength=args.normalize_strength,
            lut_strength=args.lut_strength, max_long_edge=args.max_long_edge,
            assume_srgb=args.assume_srgb, untagged_policy=policy, film=args.film,
            film_strength=args.film_strength, film_seed=args.film_seed, film_color_only=args.film_color_only,
        )
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Comparison cancelled during preparation; use a new output directory to retry.", file=sys.stderr)
        return 130
