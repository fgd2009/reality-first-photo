"""CLI defaults for untagged inputs, batch skips, and English user-facing errors."""
import json
import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from reality_first_normalization import compare, io, local_cli

CJK = re.compile(r"[\u4e00-\u9fff]")


def write_png(path: Path, color=(40, 90, 140), *, profile: bytes | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    options = {} if profile is None else {"icc_profile": profile}
    Image.new("RGB", (8, 6), color).save(path, **options)


def read_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_default_assumption_matches_explicit_pixels_and_records_the_decision(tmp_path):
    source = tmp_path / "phone.png"
    write_png(source)
    with pytest.raises(io.ColorManagementError, match="ICC"):
        io.load_image(source)
    default_pixels, default_meta = io.load_image(source, untagged_policy="default_assume")
    explicit_pixels, explicit_meta = io.load_image(source, assume_srgb=True)
    np.testing.assert_array_equal(default_pixels, explicit_pixels)
    np.testing.assert_allclose(default_pixels[0, 0], np.array([40, 90, 140]) / 255)
    assert default_meta["ColorConversion"] == "default_assume_srgb_untagged_rgb8"
    assert default_meta["UntaggedAssumption"] == "default"
    assert explicit_meta["ColorConversion"] == "explicit_assume_srgb_untagged_rgb8"
    assert explicit_meta["UntaggedAssumption"] == "explicit"
    assert default_meta["InputICC_SHA256"] == "none"
    broken = tmp_path / "broken.png"
    write_png(broken, profile=b"invalid-profile")
    with pytest.raises(io.ColorManagementError, match="ICC"):
        io.load_image(broken, untagged_policy="default_assume")


def test_default_high_depth_assumption_keeps_samples_and_strict_mode_rejects(tmp_path):
    source = tmp_path / "untagged16.tiff"
    data = np.arange(48, dtype=np.uint16).reshape(4, 4, 3) * 1000
    io.tifffile.imwrite(source, data, photometric="rgb")
    with pytest.raises(io.ColorManagementError, match="ICC"):
        io.load_image(source)
    pixels, metadata = io.load_image(source, untagged_policy="default_assume")
    assert np.max(np.abs(pixels - data / 65535)) < 1e-6
    assert metadata["ColorConversion"] == "default_assume_srgb_untagged_high_depth"
    assert metadata["UntaggedAssumption"] == "default"


def test_user_facing_color_errors_are_english(tmp_path):
    cases = [
        tmp_path / "untagged.png",
        tmp_path / "generated.dng",
    ]
    Image.new("RGB", (2, 2)).save(cases[0])
    cases[1].write_bytes(b"not a raw photo")
    for path in cases:
        with pytest.raises(io.ColorManagementError) as raised:
            io.load_image(path)
        assert not CJK.search(str(raised.value))


def test_batch_skips_a_middle_failure_and_exports_the_rest(tmp_path, capsys):
    source = tmp_path / "batch"
    write_png(source / "a.png", profile=io.working_srgb_icc())
    (source / "b.png").write_bytes(b"synthetic corrupt png, not a photograph")
    write_png(source / "c.png", profile=io.working_srgb_icc(), color=(10, 20, 30))
    output = tmp_path / "out"
    assert local_cli.main([
        "--input", str(source), "--output", str(output), "--format", "png", "--normalize-strength", "0",
    ]) == 2
    manifest = read_manifest(output / "manifest.json")
    assert manifest["status"] == "failed" and manifest["batch_completed"] is True
    assert [item["output"] for item in manifest["items"]] == ["a.png", "c.png"]
    assert manifest["failed_input"] == "b.png" and manifest["failed_stage"] == "decode"
    assert [failure["input"] for failure in manifest["failures"]] == ["b.png"]
    assert (output / "a.png").is_file() and (output / "c.png").is_file()
    assert not (output / "b.png").exists()
    captured = capsys.readouterr()
    assert "Skipped 1 of 3 inputs." in captured.err
    assert "b.png" in captured.err and "decode" in captured.err
    assert "complete:" not in captured.out
    preserved = (output / "a.png").read_bytes()
    assert local_cli.main(["--input", str(source), "--output", str(output)]) == 2
    assert (output / "a.png").read_bytes() == preserved
    assert not (output / "b.png").exists()


def test_check_cli_assumes_untagged_srgb_and_strict_mode_blocks(tmp_path, capsys):
    source = tmp_path / "phone.jpg"
    Image.new("RGB", (8, 6), (12, 34, 56)).save(source, "JPEG")
    assert local_cli.main(["check", "--input", str(source), "--json"]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["status"] == "ready" and report["untagged_policy"] == "default_assume"
    assert report["items"][0]["color"]["ColorConversion"] == "default_assume_srgb_untagged_rgb8"
    assert "assuming encoded sRGB" in captured.err
    assert "assuming encoded sRGB" in report["items"][0]["warning"]
    assert local_cli.main(["check", "--input", str(source), "--strict-color", "--json"]) == 2
    strict = json.loads(capsys.readouterr().out)
    assert strict["status"] == "blocked" and strict["untagged_policy"] == "strict"
    assert "ICC" in strict["items"][0]["error"]
    assert not CJK.search(strict["items"][0]["error"])


def test_compare_html_records_default_srgb_assumption(tmp_path, capsys):
    source = tmp_path / "phone.png"
    write_png(source)
    lut = tmp_path / "identity.cube"
    lut.write_text(
        "LUT_3D_SIZE 2\n" + "\n".join(f"{r} {g} {b}" for b in (0, 1) for g in (0, 1) for r in (0, 1)) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "report"
    assert local_cli.main([
        "compare", "--input", str(source), "--output", str(output), "--lut", str(lut),
        "--normalize-strength", "0", "--max-long-edge", "0",
    ]) == 0
    report = read_manifest(output / "compare.json")
    color = report["items"][0]["variants"]["original"]["color"]
    assert report["untagged_policy"] == "default_assume"
    assert color["ColorConversion"] == "default_assume_srgb_untagged_rgb8"
    page = (output / "index.html").read_text(encoding="utf-8")
    assert "Untagged input assumed encoded sRGB (default_assume_srgb_untagged_rgb8)" in page
    assert "assuming encoded sRGB" in capsys.readouterr().err
    strict = tmp_path / "strict-report"
    assert local_cli.main([
        "compare", "--input", str(source), "--output", str(strict), "--lut", str(lut), "--strict-color",
    ]) == 2
    assert read_manifest(strict / "compare.json")["status"] == "failed"
    assert not (strict / "index.html").exists()


def test_compare_skips_one_corrupt_file_and_keeps_the_others(tmp_path, capsys):
    source = tmp_path / "inputs"
    write_png(source / "a.png", profile=io.working_srgb_icc())
    (source / "b.png").write_bytes(b"synthetic corrupt png, not a photograph")
    write_png(source / "c.png", profile=io.working_srgb_icc(), color=(9, 8, 7))
    lut = tmp_path / "identity.cube"
    lut.write_text(
        "LUT_3D_SIZE 2\n" + "\n".join(f"{r} {g} {b}" for b in (0, 1) for g in (0, 1) for r in (0, 1)) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "partial-compare"
    assert compare.run_comparison(source, output, lut, normalize_strength=0, max_long_edge=0) == 2
    report = read_manifest(output / "compare.json")
    assert report["status"] == "partial"
    assert [item["input_name"] for item in report["items"]] == ["a.png", "c.png"]
    assert [failure["input"] for failure in report["failures"]] == ["b.png"]
    page = (output / "index.html").read_text(encoding="utf-8")
    assert "partial, not complete" in page
    assert "b.png" in page and "a.png" in page and "c.png" in page
    for name in ("a.png", "c.png"):
        for recipe in ("original", "normalized", "lut_only", "normalized_lut"):
            assert (output / recipe / name).is_file()
    assert not (output / "original" / "b.png").exists()
    captured = capsys.readouterr()
    assert "Comparison complete" not in captured.out
    assert "Comparison partial" in captured.out
    assert "b.png" in captured.err
