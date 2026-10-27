"""Read-only, local input diagnosis using the same decoder as every export."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import local_cli
from .io import RAW_EXTS, SUPPORTED_EXTS, load_image
from .lut import load_cube_lut


def inspect_inputs(source: Path, *, lut_path: Path | None = None, format: str = "png",
                   max_long_edge: int = 2048, assume_srgb: bool = False) -> dict:
    """Decode each candidate without exporting or extracting external EXIF.

    A ready result describes this check only: it does not reserve output paths,
    lock files, check free disk space, or guarantee a later export will succeed.
    """
    if format not in {"png", "jpeg", "tiff"}:
        raise ValueError("format must be png, jpeg or tiff")
    if isinstance(max_long_edge, bool) or not isinstance(max_long_edge, int) or max_long_edge < 0:
        raise ValueError("max_long_edge must be a nonnegative integer")
    if not isinstance(assume_srgb, bool):
        raise ValueError("assume_srgb must be a boolean")
    report = {"kind": "input_check", "status": "checking", "format": format,
              "max_long_edge": max_long_edge, "assume_srgb": assume_srgb,
              "items": [], "issues": [], "lut": None,
              "notice": "Read-only decode check, not a photo-quality assessment or a guarantee of export success."}
    try:
        source = Path(source)
        # Check before resolve, so a root symlink cannot bypass enumeration.
        candidates = local_cli.inventory_inputs(source)
        supported = [p for p in candidates if p.suffix.lower() in SUPPORTED_EXTS]
        if not supported:
            report["issues"].append("No supported RGB inputs found; use tagged RGB JPEG/PNG or supported TIFF.")
        try:
            local_cli.output_names(source, supported, {"png": ".png", "jpeg": ".jpg", "tiff": ".tif"}[format])
        except ValueError as exc:
            report["issues"].append(str(exc))
        if lut_path is not None:
            lut_path = Path(lut_path)
            try:
                if lut_path.is_symlink():
                    raise ValueError("LUT symlinks are unsupported; choose the actual file")
                lut = load_cube_lut(str(lut_path.resolve()))
                report["lut"] = {"name": lut_path.name, "status": "ready", "sha256": lut.source_sha256}
            except (OSError, ValueError) as exc:
                report["lut"] = {"name": lut_path.name, "status": "blocked", "error": str(exc)}
                report["issues"].append("Selected LUT could not be loaded. Correct its path or use a supported encoded-sRGB 3D CUBE.")
        for path in candidates:
            name = path.relative_to(source).as_posix() if source.is_dir() else path.name
            entry = {"input_name": name, "status": "checking"}
            report["items"].append(entry)
            extension = path.suffix.lower()
            if extension in RAW_EXTS:
                entry.update(status="blocked", error="RAW/DNG is unsupported, including inside mixed folders.",
                             action="Export a separate tagged RGB sRGB copy in a trusted RAW developer first.")
            elif extension not in SUPPORTED_EXTS:
                entry.update(status="ignored" if source.is_dir() else "blocked",
                             error="Unsupported extension; folder exports ignore it, single-file exports reject it.")
            else:
                try:
                    pixels, color = load_image(path, max_long_edge=max_long_edge,
                                               assume_srgb=assume_srgb, read_metadata=False)
                    entry.update(status="ready", width=int(pixels.shape[1]), height=int(pixels.shape[0]), color=color)
                    del pixels
                except (OSError, ValueError, RuntimeError) as exc:
                    entry.update(status="blocked", error=str(exc), action=(
                        "Check the file in a trusted color-managed tool and export a separate supported tagged RGB sRGB copy. "
                        "Use --assume-srgb only for untagged pixels you already know are encoded sRGB; it cannot bypass invalid ICC."))
        report["status"] = "blocked" if report["issues"] or any(i["status"] == "blocked" for i in report["items"]) else "ready"
    except KeyboardInterrupt:
        report["status"] = "cancelled"
        report["issues"].append("Check cancelled; remaining files were not diagnosed. No exports were written.")
    except (OSError, ValueError) as exc:
        report["status"] = "blocked"
        report["issues"].append(str(exc))
    report["counts"] = {status: sum(i["status"] == status for i in report["items"])
                        for status in ("ready", "blocked", "ignored", "checking")}
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="reality-first-photo check",
        description="Check local files, ICC decisions and an optional LUT without creating exports.",
        epilog="This fully decodes each image using the export reader; large-image memory limits still apply. No EXIF helper or network calls.",
    )
    parser.add_argument("--input", type=Path, required=True, help="Local file or folder; filenames are printed locally.")
    parser.add_argument("--lut", type=Path, help="Optional local encoded-sRGB 3D CUBE to validate.")
    parser.add_argument("--format", choices=["png", "jpeg", "tiff"], default="png", help="Planned export format for filename-collision checks (default: png).")
    parser.add_argument("--max-long-edge", type=int, default=2048)
    parser.add_argument("--assume-srgb", action="store_true", help="Declare only known untagged sRGB; invalid ICC remains blocked.")
    parser.add_argument("--json", action="store_true", help="Print the diagnosis as JSON to stdout; no report file is created.")
    args = parser.parse_args(argv)
    try:
        report = inspect_inputs(args.input, lut_path=args.lut, format=args.format,
                                max_long_edge=args.max_long_edge, assume_srgb=args.assume_srgb)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False))
    else:
        for item in report["items"]:
            name = json.dumps(item["input_name"], ensure_ascii=True)
            detail = (item.get("error") or item["color"]["ColorConversion"]
                      if item["status"] != "checking" else "Not completed")
            print(f"{item['status'].upper()}: {name}: {detail}")
            if item.get("action"):
                print("  " + item["action"])
        if report["lut"]:
            print("LUT: " + json.dumps(report["lut"], ensure_ascii=True))
        for issue in report["issues"]:
            print("Issue: " + issue)
        print(f"Check {report['status']}: " + ", ".join(f"{n} {status}" for status, n in report["counts"].items()))
        print(report["notice"] + " No exports written.")
    return {"ready": 0, "blocked": 2, "cancelled": 130}[report["status"]]
