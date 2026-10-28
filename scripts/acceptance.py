"""Verify an installed wheel outside the checkout using disposable synthetic data.

Run: python scripts/acceptance.py --python /path/to/wheel-venv/bin/python
No browser, photo, network call, telemetry or third-party LUT is needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path


def hashes(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob("*") if p.is_file()}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def accept(python: str, root: Path) -> None:
    prefix = [python, "-I", "-m", "reality_first_normalization.local_cli"]

    def cli(*args, code=0):
        result = subprocess.run([*prefix, *map(str, args)], check=False, cwd=root, capture_output=True, text=True, timeout=60)
        assert result.returncode == code, (result.returncode, result.stdout, result.stderr)
        return result

    # -I and a cwd outside checkout must still import the separately installed package.
    subprocess.run([python, "-I", "-c",
                    ("import pathlib,sys,reality_first_normalization as p; "
                     "assert not pathlib.Path(p.__file__).resolve().is_relative_to(pathlib.Path(sys.argv[1]))"),
                    str(Path(__file__).resolve().parents[1])], cwd=root, check=True, timeout=30)
    cli("demo", "--output", "demo")
    inputs = root / "demo" / "input"
    lut = root / "demo" / "demo_warm.cube"
    source_hashes = hashes(inputs)
    lut_hash = hashlib.sha256(lut.read_bytes()).hexdigest()
    checked = json.loads(cli("check", "--input", "demo/input", "--lut", "demo/demo_warm.cube", "--json").stdout)
    assert checked["status"] == "ready" and checked["counts"]["ready"] == 3
    assert checked["lut"]["sha256"] == lut_hash
    cli("compare", "--input", inputs, "--lut", lut, "--output", "compare")
    comparison = root / "compare"
    report = read_json(comparison / "compare.json")
    assert report["status"] == "complete" and len(report["items"]) == 3
    assert len(list(comparison.rglob("*.png"))) == 12
    assert (comparison / "index.html").is_file()
    preserved = hashes(comparison)
    cli("compare", "--input", inputs, "--lut", lut, "--output", "compare", code=2)
    assert hashes(comparison) == preserved
    # A user's explicit choice can be exported with the same strengths, in TIFF16.
    cli("--input", inputs, "--lut", lut, "--normalize-strength", ".6", "--lut-strength", "1",
        "--format", "tiff", "--output", "selected-tiff")
    assert read_json(root / "selected-tiff" / "manifest.json")["status"] == "complete"
    assert len(list((root / "selected-tiff").glob("*.tif"))) == 3
    subprocess.run([python, "-I", "-c", '''
from pathlib import Path
import sys
from PIL import Image
import tifffile
from reality_first_normalization.io import working_srgb_icc
root = Path(sys.argv[1])
for path in (root / "compare").rglob("*.png"):
    with Image.open(path) as image:
        image.load()
        assert image.mode == "RGB" and image.size == (257, 97)
        assert image.info["icc_profile"] == working_srgb_icc()
for path in (root / "selected-tiff").glob("*.tif"):
    with tifffile.TiffFile(path) as image:
        pixels = image.asarray()
        assert pixels.shape == (97, 257, 3) and pixels.dtype.name == "uint16"
        assert image.pages[0].iccprofile == working_srgb_icc()
''', str(root)], cwd=root, check=True, timeout=30)

    mixed = root / "mixed"
    shutil.copytree(inputs, mixed)
    (mixed / "z-broken.png").write_bytes(b"original synthetic corrupt fixture, no photograph")
    before = hashes(mixed)
    blocked = json.loads(cli("check", "--input", mixed, "--json", code=2).stdout)
    assert blocked["counts"]["ready"] == 3 and blocked["counts"]["blocked"] == 1
    cli("--input", mixed, "--output", "partial", "--format", "png", code=2)
    partial = root / "partial"
    state = read_json(partial / "manifest.json")
    assert state["status"] == "failed" and state["failed_input"] == "z-broken.png"
    assert state["failed_stage"] == "decode" and len(state["items"]) == 3
    assert hashes(mixed) == before
    preserved_partial = hashes(partial)
    cli("--input", mixed, "--output", "partial", code=2)
    assert hashes(partial) == preserved_partial
    (mixed / "z-broken.png").unlink()  # Only this disposable fixture is corrected.
    cli("--input", mixed, "--output", "retry", "--format", "png")
    assert read_json(root / "retry" / "manifest.json")["status"] == "complete"
    (mixed / "unsupported.dng").write_bytes(b"synthetic unsupported placeholder")
    cli("check", "--input", mixed, code=2)
    cli("--input", mixed, "--output", "raw-refused", code=2)
    assert not (root / "raw-refused").exists()

    if os.name == "posix":
        # Pause only a test wrapper at the second decode, after a real checkpoint.
        # Send real OS signals; the installed command's handlers remain unchanged.
        child = '''
import signal, sys
from pathlib import Path
from reality_first_normalization import local_cli
original = local_cli.load_image
calls = 0
def paused(*args, **kwargs):
    global calls
    calls += 1
    if calls == 2:
        Path(sys.argv[3]).write_text("ready")
        signal.pause()
    return original(*args, **kwargs)
local_cli.load_image = paused
raise SystemExit(local_cli.main(["--input", sys.argv[1], "--output", sys.argv[2], "--format", "png"]))
'''
        for name, sig, status, expected_code in [
            ("interrupt", signal.SIGINT, "cancelled", 130),
            ("terminate", signal.SIGTERM, "running", -signal.SIGTERM),
        ]:
            output, marker = root / name, root / (name + ".ready")
            process = subprocess.Popen([python, "-I", "-c", child, str(inputs), str(output), str(marker)],
                                       cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 10
                while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(.02)
                assert marker.exists(), "Child did not reach the synthetic checkpoint"
                process.send_signal(sig)
                stdout, stderr = process.communicate(timeout=10)
                assert process.returncode == expected_code, (stdout, stderr, process.returncode)
                state = read_json(output / "manifest.json")
                assert state["status"] == status and len(state["items"]) == 1
                assert "complete:" not in stdout
                cli("--input", inputs, "--output", output, code=2)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=10)
        print("PASS: real POSIX SIGINT cancellation and SIGTERM incomplete checkpoint")
    else:
        print("NOT RUN: POSIX signal checks on this platform")
    untagged = root / "phone-untagged.jpg"
    subprocess.run([python, "-I", "-c",
                    ("import sys\nfrom PIL import Image\n"
                     "Image.new('RGB', (8, 6), (40, 80, 120)).save(sys.argv[1], 'JPEG')\n"),
                    str(untagged)], cwd=root, check=True, timeout=30)
    assumed = cli("--input", untagged, "--output", "assumed-srgb", "--format", "png", "--normalize-strength", "0")
    assumed_state = read_json(root / "assumed-srgb" / "manifest.json")
    assert assumed_state["status"] == "complete" and assumed_state["untagged_policy"] == "default_assume"
    assert assumed_state["items"][0]["color"]["ColorConversion"] == "default_assume_srgb_untagged_rgb8"
    assert assumed_state["items"][0]["color"]["UntaggedAssumption"] == "default"
    assert "assuming encoded sRGB" in assumed.stderr
    cli("--input", untagged, "--output", "strict-untagged", "--strict-color", "--format", "png", code=2)
    strict_state = read_json(root / "strict-untagged" / "manifest.json")
    assert strict_state["status"] == "failed" and "ICC" in strict_state["error"]
    assert hashes(inputs) == source_hashes
    assert hashlib.sha256(lut.read_bytes()).hexdigest() == lut_hash
    print("PASS: installed demo → check → compare → TIFF export; partial failure, repeat refusal and new-directory retry")
    print("NOT RUN: browser visual rendering, real-photo quality, RAW or cross-platform behavior")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, help="Python in the independently installed wheel environment")
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="reality-first-acceptance-") as folder:
        # Preserve the venv's interpreter symlink; resolving it loses the venv.
        accept(str(Path(options.python).expanduser().absolute()), Path(folder))
