"""A packaged, entirely synthetic first run using the real offline CLI pipeline."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import report_state
from .io import save_image, working_srgb_icc

IMAGE_NAMES = ("gradient", "chart", "geometry")


def _generate_contents(destination: Path) -> None:
    images = destination / "input"
    images.mkdir()
    x = np.linspace(0, 1, 257, dtype=np.float32)
    ramp = np.tile(x[None, :, None], (97, 1, 3))
    chart = np.zeros((97, 257, 3), dtype=np.float32)
    for i, color in enumerate([(1, 0, 0), (0, 1, 0), (0, 0, 1), (.2, .4, .8), (.5, .5, .5)]):
        chart[:, i * 51:(i + 1) * 51] = color
    geometry = np.zeros_like(chart) + .15
    geometry[10:70, 40:180] = (.7, .4, .2)
    geometry[35:90, 170:250] = (.2, .8, .4)
    for name, pixels in zip(IMAGE_NAMES, (ramp, chart, geometry)):
        save_image(pixels, images / (name + ".png"))
    for name, transform in [
        ("identity", lambda r, g, b: (r, g, b)),
        ("demo_warm", lambda r, g, b: (.04 + .92 * r, .96 * g, .9 * b)),
    ]:
        rows = ["# Original synthetic demonstration; not a commercial film look", "LUT_3D_SIZE 2"]
        rows += [" ".join(str(v) for v in transform(r, g, b))
                 for b in (0, 1) for g in (0, 1) for r in (0, 1)]
        (destination / (name + ".cube")).write_text("\n".join(rows) + "\n", encoding="utf-8")


def generate(destination: Path) -> None:
    """Retain the source example's input-only generator without overwriting files."""
    destination.mkdir(parents=True, exist_ok=False)
    _generate_contents(destination)
    print("Generated 3 synthetic images and 2 original demonstration CUBEs")


def make_comparison(destination: Path) -> None:
    """Show exported PNG pixels unchanged; every panel uses the working sRGB ICC."""
    canvas = Image.new("RGB", (851, 583), "#f5f4f0")
    draw = ImageDraw.Draw(canvas)
    title = ImageFont.load_default(size=22)
    label = ImageFont.load_default(size=16)
    small = ImageFont.load_default(size=13)
    draw.text((20, 16), "Reality First Photo | synthetic preview", fill="#17252a", font=title)
    draw.text((20, 48), "Generated test pixels, not real photographs or a claim of photographic quality.",
              fill="#46545a", font=small)
    columns = [("input", "Input", "Generated sRGB"),
               ("normalized", "Normalized", "Normalization strength: 0.6"),
               ("styled", "Normalized + warm LUT", "Same normalization; LUT strength: 0.5")]
    for column, (folder, heading, subtitle) in enumerate(columns):
        left = 20 + column * 277
        draw.text((left, 80), heading, fill="#17252a", font=label)
        draw.text((left, 101), subtitle, fill="#46545a", font=small)
        for row, name in enumerate(IMAGE_NAMES):
            top = 126 + row * 127
            if column == 0:
                draw.text((20, top), name.capitalize(), fill="#46545a", font=small)
            with Image.open(destination / folder / (name + ".png")) as image:
                if image.mode != "RGB" or image.size != (257, 97) or image.info.get("icc_profile") != working_srgb_icc():
                    raise ValueError("Demo comparison requires the generated 257x97 RGB working-sRGB exports")
                canvas.paste(image, (left, top + 20))
    draw.text((20, 521), "The warm LUT is an original affine example, not a branded film stock.",
              fill="#46545a", font=small)
    draw.text((20, 544), "Separate PNG exports: normalized/ and styled/. Working color space: sRGB.",
              fill="#46545a", font=small)
    canvas.save(destination / "comparison.png", icc_profile=working_srgb_icc())


def run_demo(destination: Path) -> int:
    from .local_cli import main as process

    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Demo output already exists; choose a new directory")
    destination = destination.resolve()
    # Own this directory only after exclusive creation succeeds. An existing
    # directory is never opened for writing, even to record a failure manifest.
    destination.mkdir(parents=True, exist_ok=False)
    report = {"kind": "synthetic_demo", "status": "running",
              "notice": "Generated synthetic inputs, not real-photo validation or a commercial film look.",
              "normalize_strength": .6, "lut_strength": .5,
              "input": "input", "normalized": "normalized", "styled": "styled"}
    code = 0
    try:
        report_state.write_json(destination / "demo.json", report)
        _generate_contents(destination)
        print("Synthetic demo: generated pixels only; no real photos or commercial presets.", flush=True)
        common = ["--input", str(destination / "input"), "--normalize-strength", ".6", "--format", "png"]
        for folder, extra in [("normalized", []),
                              ("styled", ["--lut", str(destination / "demo_warm.cube"), "--lut-strength", ".5"])]:
            result = process([*common, "--output", str(destination / folder), *extra])
            if result == 130:
                raise KeyboardInterrupt
            if result:
                raise RuntimeError(f"{folder} export failed; inspect the error above and partial outputs")
        make_comparison(destination)
        report.update(status="complete", comparison="comparison.png")
        report_state.write_json(destination / "demo.json", report)
    except KeyboardInterrupt:
        report.update(status="cancelled", notice="Partial demo retained; choose a new output directory to restart.")
        code = 130
    except (OSError, ValueError, RuntimeError) as exc:
        report.update(status="failed", error=str(exc))
        code = 2
    if code:
        try:
            report_state.write_json(destination / "demo.json", report)
        except OSError as exc:
            print(f"Cannot save final demo status: {exc}. Treat all outputs as incomplete.", file=sys.stderr)
    if code:
        print(f"Demo {report['status']}: {report.get('error', report['notice'])}", file=sys.stderr)
        print(f"Partial outputs: {destination}. Use a new --output directory to retry.", file=sys.stderr)
    else:
        print(f"Demo complete. Open comparison: {destination / 'comparison.png'}", flush=True)
        print(f"Exported PNGs: {destination / 'styled'}", flush=True)
        print("To process your own tagged image, run reality-first-photo --help.", flush=True)
    return code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="reality-first-photo demo",
        description="Create synthetic before/after comparisons and PNG exports offline. No photos or LUT purchase needed.",
        epilog="Open OUTPUT/comparison.png when complete. Synthetic results do not validate real-photo quality.",
    )
    parser.add_argument("--output", type=Path, required=True, help="New demo directory; existing files or directories are never overwritten.")
    args = parser.parse_args(argv)
    try:
        return run_demo(args.output)
    except FileExistsError:
        print(f"Error: Demo output already exists: {args.output}. Choose a new --output directory; nothing was overwritten.", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"Error: Cannot create the demo: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Demo cancelled during preparation; use a new output directory to retry.", file=sys.stderr)
        return 130
