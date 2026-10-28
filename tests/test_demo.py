"""The packaged demo uses real exports and reports complete, failed or cancelled work."""
import hashlib
import json
import sys

import numpy as np
import pytest
from PIL import Image

from reality_first_normalization import demo, io, local_cli

NAMES = ("gradient", "chart", "geometry")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def hashes(folder):
    return {
        path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in folder.rglob("*") if path.is_file()
    }


def read_rgb(path):
    with Image.open(path) as image:
        assert image.mode == "RGB"
        assert image.info["icc_profile"] == io.working_srgb_icc()
        return np.asarray(image).copy()


def test_complete_demo_exports_match_comparison_and_independent_lut(tmp_path, capsys):
    output = tmp_path / "first-look"
    assert local_cli.main(["demo", "--output", str(output)]) == 0
    report = read_json(output / "demo.json")
    assert report["kind"] == "synthetic_demo"
    assert report["status"] == "complete"
    assert report["comparison"] == "comparison.png"
    assert report["normalize_strength"] == .6
    assert report["lut_strength"] == .5
    assert "synthetic" in report["notice"].lower()
    assert {path.relative_to(output).as_posix() for path in output.rglob("*.png")} == {
        "comparison.png",
        *(f"{folder}/{name}.png" for folder in ("input", "normalized", "styled") for name in NAMES),
    }

    manifests = {folder: read_json(output / folder / "manifest.json")
                 for folder in ("normalized", "styled")}
    items = {}
    for folder, manifest in manifests.items():
        assert manifest["status"] == "complete"
        assert manifest["normalize_strength"] == .6
        assert len(manifest["items"]) == 3
        items[folder] = {item["input_name"]: item for item in manifest["items"]}
        for name in NAMES:
            item = items[folder][name + ".png"]
            assert item["output"] == name + ".png"
            assert (item["width"], item["height"]) == (257, 97)
            assert item["input_sha256"] == hashlib.sha256((output / "input" / (name + ".png")).read_bytes()).hexdigest()
            assert item["normalization"]["applied"] is True
            operations = item["normalization"]["operations"]
            assert operations["global_strength"] == .6
            assert operations["normalization_strategy_source"] == "local_default_strategy"
            assert operations["style_profile_used"] == "reality_standard"
            assert np.isfinite(operations["exposure_scale"])
            assert len(operations["white_balance_gains_rgb"]) == 3
            assert np.isfinite(operations["white_balance_gains_rgb"]).all()
    assert manifests["normalized"]["lut_name"] is None
    assert manifests["styled"]["lut_name"] == "demo_warm.cube"
    assert manifests["styled"]["lut_strength"] == .5
    assert manifests["styled"]["lut_sha256"] == hashlib.sha256((output / "demo_warm.cube").read_bytes()).hexdigest()

    comparison = read_rgb(output / "comparison.png")
    assert comparison.shape == (583, 851, 3)
    for row, name in enumerate(NAMES):
        for column, folder in enumerate(("input", "normalized", "styled")):
            pixels = read_rgb(output / folder / (name + ".png"))
            assert pixels.shape == (97, 257, 3)
            left, top = 20 + 277 * column, 146 + 127 * row
            np.testing.assert_array_equal(comparison[top:top + 97, left:left + 257], pixels)
        # An independent affine equation checks that the LUT follows the same
        # normalization, instead of normalizing an already normalized PNG again.
        normalized = read_rgb(output / "normalized" / (name + ".png")).astype(np.float64) / 255
        styled = read_rgb(output / "styled" / (name + ".png")).astype(np.float64) / 255
        expected = .5 * normalized + .5 * np.stack(
            (.04 + .92 * normalized[..., 0], .96 * normalized[..., 1], .9 * normalized[..., 2]), axis=-1
        )
        assert np.max(np.abs(styled - expected)) <= 1 / 255 + 1e-7
        assert items["normalized"][name + ".png"]["normalization"] == items["styled"][name + ".png"]["normalization"]
    # Each column has a visible heading above its panels; exact glyph rasterization
    # is left to visual inspection rather than a platform-sensitive font snapshot.
    background = comparison[0, 0]
    for column in range(3):
        left = 20 + 277 * column
        assert np.any(comparison[80:116, left:left + 257] != background)
    captured = capsys.readouterr()
    assert "Demo complete." in captured.out
    assert str(output / "comparison.png") in captured.out
    assert not captured.err


def test_old_example_and_input_folder_named_demo_keep_legacy_cli(tmp_path, monkeypatch):
    from examples.generate_demo import generate

    generate(tmp_path / "demo")
    source = tmp_path / "demo"
    before = hashes(source)
    assert set(before) == {"identity.cube", "demo_warm.cube", *(f"input/{name}.png" for name in NAMES)}
    monkeypatch.chdir(tmp_path)
    assert local_cli.main(["--input", "demo", "--output", "legacy-output",
                           "--normalize-strength", "0", "--format", "png"]) == 0
    manifest = read_json(tmp_path / "legacy-output" / "manifest.json")
    assert manifest["status"] == "complete"
    for item in manifest["items"]:
        assert item["normalization"] == {"applied": False, "operations": None}
        np.testing.assert_array_equal(
            read_rgb(source / item["output"]),
            read_rgb(tmp_path / "legacy-output" / item["output"]),
        )
    assert hashes(source) == before


@pytest.mark.parametrize("existing", ["file", "directory"])
def test_demo_does_not_overwrite_existing_targets(tmp_path, capsys, existing):
    output = tmp_path / "existing"
    if existing == "file":
        output.write_bytes(b"retain this file exactly")
        before = output.read_bytes()
    else:
        output.mkdir()
        (output / "sentinel.txt").write_text("retain all existing contents")
        before = hashes(output)
    assert local_cli.main(["demo", "--output", str(output)]) == 2
    assert (output.read_bytes() if existing == "file" else hashes(output)) == before
    captured = capsys.readouterr()
    assert "already exists" in captured.err
    assert "Demo complete." not in captured.out


@pytest.mark.parametrize("failure,expected_code,status", [
    ("error_return", 2, "failed"),
    ("cancel_return", 130, "cancelled"),
    ("interrupt", 130, "cancelled"),
])
def test_processing_failure_or_cancel_never_reports_demo_success(tmp_path, monkeypatch, capsys,
                                                                failure, expected_code, status):
    calls = []

    def unsuccessful_process(argv):
        calls.append(argv)
        if failure == "interrupt":
            raise KeyboardInterrupt
        return 130 if failure == "cancel_return" else 2

    monkeypatch.setattr(local_cli, "main", unsuccessful_process)
    output = tmp_path / "interrupted-demo"
    assert demo.run_demo(output) == expected_code
    report = read_json(output / "demo.json")
    assert report["status"] == status
    assert len(calls) == 1  # A failed first export must not start the styled run.
    assert "comparison" not in report
    assert not (output / "comparison.png").exists()
    captured = capsys.readouterr()
    assert "Demo complete." not in captured.out
    assert "Demo " + status in captured.err
    assert "new --output directory" in captured.err


def test_comparison_failure_retains_exports_but_marks_demo_failed(tmp_path, monkeypatch, capsys):
    def failed_comparison(destination):
        raise ValueError("injected comparison failure")

    monkeypatch.setattr(demo, "make_comparison", failed_comparison)
    output = tmp_path / "comparison-failed"
    assert local_cli.main(["demo", "--output", str(output)]) == 2
    report = read_json(output / "demo.json")
    assert report["status"] == "failed"
    assert report["error"] == "injected comparison failure"
    assert "comparison" not in report
    for folder in ("normalized", "styled"):
        assert read_json(output / folder / "manifest.json")["status"] == "complete"
        assert len(list((output / folder).glob("*.png"))) == 3
    captured = capsys.readouterr()
    assert "Demo complete." not in captured.out
    assert "injected comparison failure" in captured.err


@pytest.mark.parametrize("argv,expected_code", [([], 2), (["--help"], 0), (["demo", "--help"], 0)])
def test_help_and_no_arguments_expose_the_demo(tmp_path, monkeypatch, capsys, argv, expected_code):
    monkeypatch.chdir(tmp_path)
    if argv:
        with pytest.raises(SystemExit) as ended:
            local_cli.main(argv)
        assert ended.value.code == expected_code
    else:
        assert local_cli.main(argv) == expected_code
    captured = capsys.readouterr()
    assert "demo" in captured.out
    assert "--output" in captured.out
    assert "comparison.png" in captured.out
    assert not list(tmp_path.iterdir())


def test_console_argv_dispatches_demo_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["reality-first-photo", "demo", "--help"])
    with pytest.raises(SystemExit) as ended:
        local_cli.main()
    assert ended.value.code == 0
    assert "reality-first-photo demo" in capsys.readouterr().out
