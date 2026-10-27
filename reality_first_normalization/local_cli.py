"""Small local-only CLI using the recovered color core; no model or taste profile."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
from . import report_state
from .analysis import analyze_image
from .io import load_image, save_image, SUPPORTED_EXTS, RAW_EXTS
from .lut import apply_cube_lut, load_cube_lut
from .normalize import normalize_image


def unit_float(value: str) -> float:
    number = float(value)
    if not np.isfinite(number) or not 0 <= number <= 1:
        raise argparse.ArgumentTypeError("strength must be finite and between 0 and 1")
    return number


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Local sRGB normalization, then your own CUBE LUT. No network or model calls.",
        epilog="First time? Run: reality-first-photo demo --output first-look. "
               "This creates synthetic inputs, exports and a labelled comparison.png; no photos or LUT purchase needed. "
               "Check inputs without exports: reality-first-photo check --help. "
               "Compare your own input in four ways: reality-first-photo compare --help.",
    )
    p.add_argument("--input", type=Path, required=True, help="Tagged RGB file or folder; RAW is unsupported.")
    p.add_argument("--output", type=Path, required=True, help="New output directory; existing directories are never overwritten.")
    p.add_argument("--lut", type=Path, help="Your own red-fastest SDR 3D CUBE, authored for encoded sRGB; omit for normalization only.")
    p.add_argument("--normalize-strength", type=unit_float, default=1.0, help="Normalization before the LUT: 0 skips it, 1 is full strength (default: 1).")
    p.add_argument("--lut-strength", type=unit_float, default=1.0, help="Blend with the chosen LUT: 0 keeps normalized pixels, 1 uses the full LUT (default: 1).")
    p.add_argument("--format", choices=["tiff", "png", "jpeg"], default="tiff", help="TIFF exports 16-bit; PNG/JPEG export 8-bit (default: tiff).")
    p.add_argument("--max-long-edge", type=int, default=2048, help="Preview long edge in pixels (default: 2048). 0 explicitly keeps full size; large-image memory/performance is unverified.")
    p.add_argument("--assume-srgb", action="store_true", help="Explicitly declare untagged pixels as encoded sRGB; never overrides an invalid embedded ICC.")
    return p


def inventory_inputs(source: Path) -> list[Path]:
    """Enumerate regular files without following input symlinks."""
    if source.is_symlink():
        raise ValueError("Input symlinks are unsupported; choose the actual file or folder")
    if source.is_dir():
        entries = sorted(source.rglob("*"))
        if any(p.is_symlink() for p in entries):
            raise ValueError("Input tree contains a symlink; use regular input files and folders")
        return [p for p in entries if p.is_file()]
    if source.is_file():
        return [source]
    raise ValueError(f"Input must be an existing regular file or folder: {source}")


def discover_inputs(source: Path) -> list[Path]:
    """Read-only enumeration shared by normal export and comparison workflows."""
    candidates = inventory_inputs(source)
    if source.is_dir():
        raw_files = [p for p in candidates if p.suffix.lower() in RAW_EXTS]
        if raw_files:
            raise ValueError(f"RAW/DNG is unavailable; input folder contains {raw_files[0].relative_to(source)}")
        files = [p for p in candidates if p.suffix.lower() in SUPPORTED_EXTS]
    else:
        files = candidates
    if not files or any(p.suffix.lower() not in SUPPORTED_EXTS for p in files):
        raise ValueError("No supported RGB inputs; RAW/DNG is unavailable")
    return files


def output_names(source: Path, files: list[Path], extension: str) -> list[Path]:
    names = [(p.relative_to(source) if source.is_dir() else Path(p.name)).with_suffix(extension) for p in files]
    if len(set(str(p).casefold() for p in names)) != len(names):
        raise ValueError("Input names collide after output-format conversion; rename copies in a separate input folder")
    if any(p.parts[0].casefold() in {"manifest.json", ".manifest.json.tmp"} for p in names):
        raise ValueError("Input folder name conflicts with a reserved manifest.json output/checkpoint")
    return names


def plan_inputs(input_path: Path, output_path: Path, max_long_edge: int, extension: str = ".png"):
    """Validate paths before creating any output, including dangling symlinks."""
    if input_path.is_symlink():
        raise ValueError("Input symlinks are unsupported; choose the actual file or folder")
    source = input_path.resolve()
    if not source.exists():
        raise ValueError(f"Input does not exist: {source}. Check --input, or try 'reality-first-photo demo --output first-look'.")
    if max_long_edge < 0:
        raise ValueError("--max-long-edge must be nonnegative")
    if output_path.exists() or output_path.is_symlink():
        raise ValueError("Output directory already exists; choose a new directory (no overwrite)")
    output = output_path.resolve()
    if source.is_dir() and (output == source or source in output.parents):
        raise ValueError("Output directory must be outside the input tree")
    files = discover_inputs(source)
    names = output_names(source, files, extension)
    return source, output, files, names


def run(args: argparse.Namespace) -> int:
    ext = {"tiff": ".tif", "png": ".png", "jpeg": ".jpg"}[args.format]
    source, output, files, names = plan_inputs(args.input, args.output, args.max_long_edge, ext)
    lut = load_cube_lut(str(args.lut.resolve())) if args.lut else None
    manifest = {
        "status": "running", "working_space": "encoded sRGB", "network": "disabled_by_design",
        "lut_name": args.lut.name if args.lut else None,
        "lut_sha256": lut.source_sha256 if lut else None,
        "normalize_strength": args.normalize_strength, "lut_strength": args.lut_strength,
        "format": args.format, "items": [], "total_inputs": len(files),
        "active_input": None, "active_stage": None,
        "notice": "Only status complete is success. Partial files may be unfinished; use a new output directory to retry.",
    }
    output.mkdir(parents=True)
    code = 0
    try:
        report_state.write_json(output / "manifest.json", manifest)
        for src, relative in zip(files, names):
            manifest["active_input"] = src.relative_to(source).as_posix() if source.is_dir() else src.name
            manifest["active_stage"] = "decode"
            report_state.write_json(output / "manifest.json", manifest)
            before_hash = hashlib.sha256(src.read_bytes()).hexdigest()
            pixels, color = load_image(src, max_long_edge=args.max_long_edge, assume_srgb=args.assume_srgb, read_metadata=False)
            normalization = {"applied": False, "operations": None}
            if args.normalize_strength:
                manifest["active_stage"] = "normalize"
                report_state.write_json(output / "manifest.json", manifest)
                normalized = normalize_image(pixels, analyze_image(pixels), strength=args.normalize_strength, style_profile="reality_standard")
                pixels = normalized.image
                normalization = {"applied": True, "operations": normalized.operations}
            if lut is not None:
                manifest["active_stage"] = "lut"
                report_state.write_json(output / "manifest.json", manifest)
                transformed = apply_cube_lut(pixels, lut)
                pixels = pixels * (1 - args.lut_strength) + transformed * args.lut_strength
            destination = output / relative
            manifest["active_stage"] = "export"
            report_state.write_json(output / "manifest.json", manifest)
            save_image(pixels, destination)
            manifest["active_stage"] = "verify"
            report_state.write_json(output / "manifest.json", manifest)
            if hashlib.sha256(src.read_bytes()).hexdigest() != before_hash:
                raise RuntimeError("Input changed during processing; result requires review")
            manifest["items"].append({"input_name": src.name, "input_sha256": before_hash,
                                      "output": relative.as_posix(), "width": int(pixels.shape[1]),
                                      "height": int(pixels.shape[0]), "color": color,
                                      "normalization": normalization})
            manifest.update(active_input=None, active_stage=None)
            report_state.write_json(output / "manifest.json", manifest)
            print(f"Exported {relative.as_posix()}", flush=True)
        manifest["status"] = "complete"
        report_state.write_json(output / "manifest.json", manifest)
    except KeyboardInterrupt:
        manifest["status"] = "cancelled"
        manifest["notice"] = "Partial files retained; use a new output directory to restart."
        code = 130
    except (OSError, ValueError, RuntimeError) as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        code = 2
    if code:
        manifest["failed_input"] = manifest["active_input"]
        manifest["failed_stage"] = manifest["active_stage"]
        try:
            report_state.write_json(output / "manifest.json", manifest)
        except OSError as exc:
            print(f"Cannot save final status: {exc}. Any earlier checkpoint remains incomplete.", file=sys.stderr)
    print(f"{manifest['status']}: {len(manifest['items'])}/{len(files)} exported", flush=True)
    if code == 0:
        print(f"Export folder: {output}", flush=True)
    if code and "error" in manifest:
        print(f"Input {json.dumps(manifest['failed_input'], ensure_ascii=True)}, stage {manifest['failed_stage']}: {manifest['error']}", file=sys.stderr)
    if code:
        print(f"Partial outputs: {output}. Use a new --output directory to retry. Run 'reality-first-photo check --help' for input diagnosis.", file=sys.stderr)
    return code


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["demo"]:
        from .demo import main as demo_main
        return demo_main(argv[1:])
    if argv[:1] == ["compare"]:
        from .compare import main as compare_main
        return compare_main(argv[1:])
    if argv[:1] == ["check"]:
        from .check import main as check_main
        return check_main(argv[1:])
    if not argv:
        build_parser().print_help()
        return 2
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Cancelled before processing completed. Any existing outputs require review; retry into a new directory.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
