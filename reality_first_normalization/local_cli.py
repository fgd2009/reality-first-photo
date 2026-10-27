"""Small local-only CLI using the recovered color core; no model or taste profile."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
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
               "This creates synthetic inputs, exports and a labelled comparison.png; no photos or LUT purchase needed.",
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


def run(args: argparse.Namespace) -> int:
    source = args.input.resolve()
    output = args.output.resolve()
    if not source.exists():
        raise ValueError(f"Input does not exist: {source}. Check --input, or try 'reality-first-photo demo --output first-look'.")
    if args.max_long_edge < 0:
        raise ValueError("--max-long-edge must be nonnegative")
    if output.exists():
        raise ValueError("Output directory already exists; choose a new directory (no overwrite)")
    if source.is_dir() and (output == source or source in output.parents):
        raise ValueError("Output directory must be outside the input tree")
    if source.is_dir():
        candidates = sorted(p for p in source.rglob("*") if p.is_file())
        raw_files = [p for p in candidates if p.suffix.lower() in RAW_EXTS]
        if raw_files:
            raise ValueError(f"RAW/DNG is unavailable; input folder contains {raw_files[0].relative_to(source)}")
        files = [p for p in candidates if p.suffix.lower() in SUPPORTED_EXTS]
    else:
        files = [source]
    if not files or any(p.suffix.lower() not in SUPPORTED_EXTS for p in files):
        raise ValueError("No supported RGB inputs; RAW/DNG is unavailable")
    lut = load_cube_lut(str(args.lut.resolve())) if args.lut else None
    ext = {"tiff": ".tif", "png": ".png", "jpeg": ".jpg"}[args.format]
    names = [(p.relative_to(source) if source.is_dir() else Path(p.name)).with_suffix(ext) for p in files]
    if len(set(str(p).casefold() for p in names)) != len(names):
        raise ValueError("Input names collide after output-format conversion")
    manifest = {
        "status": "running", "working_space": "encoded sRGB", "network": "disabled_by_design",
        "lut_name": args.lut.name if args.lut else None,
        "lut_sha256": hashlib.sha256(args.lut.read_bytes()).hexdigest() if args.lut else None,
        "normalize_strength": args.normalize_strength, "lut_strength": args.lut_strength,
        "format": args.format, "items": [],
    }
    output.mkdir(parents=True)
    code = 0
    try:
        for src, relative in zip(files, names):
            before_hash = hashlib.sha256(src.read_bytes()).hexdigest()
            pixels, color = load_image(src, max_long_edge=args.max_long_edge, assume_srgb=args.assume_srgb, read_metadata=False)
            normalization = {"applied": False, "operations": None}
            if args.normalize_strength:
                normalized = normalize_image(pixels, analyze_image(pixels), strength=args.normalize_strength, style_profile="reality_standard")
                pixels = normalized.image
                normalization = {"applied": True, "operations": normalized.operations}
            if lut is not None:
                transformed = apply_cube_lut(pixels, lut)
                pixels = pixels * (1 - args.lut_strength) + transformed * args.lut_strength
            destination = output / relative
            save_image(pixels, destination)
            if hashlib.sha256(src.read_bytes()).hexdigest() != before_hash:
                raise RuntimeError("Input changed during processing; result requires review")
            manifest["items"].append({"input_name": src.name, "input_sha256": before_hash,
                                      "output": relative.as_posix(), "width": int(pixels.shape[1]),
                                      "height": int(pixels.shape[0]), "color": color,
                                      "normalization": normalization})
            print(f"Exported {relative.as_posix()}", flush=True)
        manifest["status"] = "complete"
    except KeyboardInterrupt:
        manifest["status"] = "cancelled"
        manifest["notice"] = "Partial files retained; use a new output directory to restart."
        code = 130
    except (OSError, ValueError, RuntimeError) as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        code = 2
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{manifest['status']}: {len(manifest['items'])}/{len(files)} exported", flush=True)
    if code == 0:
        print(f"Export folder: {output}", flush=True)
    if code and "error" in manifest:
        print(manifest["error"], file=sys.stderr)
    return code


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["demo"]:
        from .demo import main as demo_main
        return demo_main(argv[1:])
    if not argv:
        build_parser().print_help()
        return 2
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
