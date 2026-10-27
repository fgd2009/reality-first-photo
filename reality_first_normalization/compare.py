"""Four local recipes, using the same export pipeline and explicit provenance."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from . import local_cli
from . import report_state
from .comparison_report import render_comparison_html
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


def _check_unchanged(source: Path, expected: dict[str, str], lut_path: Path, lut_sha256: str) -> None:
    if _signature(source) != expected:
        raise ValueError("Input set or content changed during comparison; results are incomplete")
    if lut_path.is_symlink():
        raise ValueError("LUT changed to a symlink during comparison; results are incomplete")
    if hashlib.sha256(lut_path.read_bytes()).hexdigest() != lut_sha256:
        raise ValueError("LUT changed during comparison; results are incomplete")


def _collect_items(names: list[Path], expected: dict[str, str],
                   recipes: list[dict], manifests: dict[str, dict], lut_sha256: str) -> list[dict]:
    output_to_input = {Path(name).with_suffix(".png").as_posix(): name for name in expected}
    wanted = {name.as_posix() for name in names}
    stage_items = {}
    for recipe in recipes:
        recipe_id = recipe["id"]
        manifest = manifests[recipe_id]
        entries = manifest.get("items", [])
        indexed = {entry.get("output"): entry for entry in entries}
        if manifest.get("status") != "complete" or len(entries) != len(wanted) or set(indexed) != wanted:
            raise ValueError(f"Incomplete or inconsistent {recipe_id} export manifest")
        expected_lut = lut_sha256 if recipe["lut_selected"] else None
        if (manifest.get("lut_sha256") != expected_lut
                or manifest.get("normalize_strength") != recipe["normalize_strength"]
                or manifest.get("lut_strength") != recipe["lut_strength"]):
            raise ValueError(f"Recipe or LUT fingerprint mismatch in {recipe_id}")
        stage_items[recipe_id] = indexed
    items = []
    for relative in names:
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
            }
        items.append({"input_name": input_name, "input_sha256": expected[input_name],
                      "width": reference["width"], "height": reference["height"], "variants": variants})
    return items


def run_comparison(source: Path, output: Path, lut_path: Path, *, normalize_strength: float = .6,
                   lut_strength: float = 1.0, max_long_edge: int = 2048,
                   assume_srgb: bool = False) -> int:
    """Write a private local comparison. Return 0, 2 (failed) or 130 (cancelled).

    Invalid options/paths raise ValueError or OSError before output is created.
    This checks hashes between recipes; it does not lock or snapshot source files.
    """
    normalize_strength = _strength(normalize_strength, "normalize_strength")
    lut_strength = _strength(lut_strength, "lut_strength")
    if isinstance(max_long_edge, bool) or not isinstance(max_long_edge, int) or max_long_edge < 0:
        raise ValueError("max_long_edge must be a nonnegative integer")
    if not isinstance(assume_srgb, bool):
        raise ValueError("assume_srgb must be a boolean")
    source, output, files, names = local_cli.plan_inputs(Path(source), Path(output), max_long_edge)
    lut_path = Path(lut_path)
    if lut_path.is_symlink():
        raise ValueError("LUT symlinks are unsupported; choose the actual file")
    lut_path = lut_path.resolve()
    lut = load_cube_lut(str(lut_path))
    expected = _signature(source)
    # Successful report items preserve relative names; the pipeline skips EXIF.
    try:
        for name in [*expected, lut_path.name]:
            name.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("Comparison filenames must be valid UTF-8") from exc
    if {p.relative_to(source).as_posix() if source.is_dir() else p.name for p in files} != set(expected):
        raise ValueError("Input set changed during comparison preparation")
    recipes = []
    for recipe_id, label, normalization, selected in [
        ("original", "Input reference", 0.0, False),
        ("normalized", "Normalization only", normalize_strength, False),
        ("lut_only", "LUT only", 0.0, True),
        ("normalized_lut", "Normalization + LUT", normalize_strength, True),
    ]:
        recipes.append({"id": recipe_id, "label": label, "normalize_strength": normalization,
                        "lut_strength": lut_strength if selected else 0.0,
                        "lut_selected": selected, "lut_applied": selected and lut_strength > 0})
    report = {
        "kind": "four_way_comparison", "status": "running", "format": "png",
        "working_space": "encoded sRGB", "max_long_edge": max_long_edge, "assume_srgb": assume_srgb,
        "reference_notice": "Decoded, ICC-converted/resized sRGB PNG reference, not a source-file copy.",
        "notice": "Four alternatives, no automatic ranking. Input and LUT hashes are checked between stages.",
        "lut": {"name": lut_path.name, "sha256": lut.source_sha256},
        "recipes": recipes, "stages": {}, "items": [], "active_recipe": None,
    }
    # Exclusive root creation: no existing content is opened for writing.
    output.mkdir(parents=True, exist_ok=False)
    manifests = {}
    code = 0
    try:
        _write_report(output, report)
        for recipe in recipes:
            _check_unchanged(source, expected, lut_path, lut.source_sha256)
            recipe_id = recipe["id"]
            report["active_recipe"] = recipe_id
            _write_report(output, report)
            args = argparse.Namespace(input=source, output=output / recipe_id,
                                      lut=lut_path if recipe["lut_selected"] else None,
                                      normalize_strength=recipe["normalize_strength"], lut_strength=recipe["lut_strength"],
                                      format="png", max_long_edge=max_long_edge, assume_srgb=assume_srgb)
            result = local_cli.run(args)
            manifest_path = output / recipe_id / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
            report["stages"][recipe_id] = {"status": manifest.get("status", "incomplete"),
                                           "manifest": f"{recipe_id}/manifest.json",
                                           "exported": len(manifest.get("items", [])),
                                           "failed_input": manifest.get("failed_input"),
                                           "failed_stage": manifest.get("failed_stage")}
            _write_report(output, report)
            if result == 130:
                raise KeyboardInterrupt
            if result:
                raise RuntimeError(f"{recipe_id} export failed at {json.dumps(manifest.get('failed_input'), ensure_ascii=True)} "
                                   f"({manifest.get('failed_stage')}): {manifest.get('error', 'see partial stage output')}")
            manifests[recipe_id] = manifest
            _check_unchanged(source, expected, lut_path, lut.source_sha256)
        report["items"] = _collect_items(names, expected, recipes, manifests, lut.source_sha256)
        report["active_recipe"] = None
        report["status"] = "complete"
        html = render_comparison_html(report)
        _check_unchanged(source, expected, lut_path, lut.source_sha256)
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
    if code:
        (output / "index.html").unlink(missing_ok=True)
        (output / ".index.html.tmp").unlink(missing_ok=True)
        try:
            _write_report(output, report)
        except OSError as exc:
            print(f"Cannot save final comparison status: {exc}. Treat all outputs as incomplete.", file=sys.stderr)
        print(f"Comparison {report['status']}: {report.get('error', report['notice'])}", file=sys.stderr)
        print(f"Partial outputs: {output}. Use a new --output directory to retry.", file=sys.stderr)
    else:
        print(f"Comparison complete: {len(report['items'])} inputs, four recipes each.", flush=True)
        print(f"Open locally: {output / 'index.html'}", flush=True)
        print("No result is selected as best. Source files are unchanged; report stays local.", flush=True)
    return code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="reality-first-photo compare",
        description="Privately compare input reference, normalization only, LUT only, and normalization + LUT.",
        epilog="Open OUTPUT/index.html locally. Exports are 8-bit sRGB PNG previews; sources are not overwritten.",
    )
    parser.add_argument("--input", type=Path, required=True, help="Tagged RGB file or folder; RAW and symlinks are unsupported.")
    parser.add_argument("--output", type=Path, required=True, help="New directory outside the input tree; no overwrite.")
    parser.add_argument("--lut", type=Path, required=True, help="Your local red-fastest encoded-sRGB 3D CUBE.")
    parser.add_argument("--normalize-strength", type=local_cli.unit_float, default=.6)
    parser.add_argument("--lut-strength", type=local_cli.unit_float, default=1.0)
    parser.add_argument("--max-long-edge", type=int, default=2048, help="Preview long edge; 0 keeps full dimensions (large-image performance unverified).")
    parser.add_argument("--assume-srgb", action="store_true", help="Explicitly declare untagged sRGB pixels; never bypasses an invalid ICC.")
    args = parser.parse_args(argv)
    try:
        return run_comparison(args.input, args.output, args.lut, normalize_strength=args.normalize_strength,
                              lut_strength=args.lut_strength, max_long_edge=args.max_long_edge,
                              assume_srgb=args.assume_srgb)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Comparison cancelled during preparation; use a new output directory to retry.", file=sys.stderr)
        return 130
