"""Read-only input diagnosis with generated pixels, profiles and LUTs only."""
import hashlib
import json
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from reality_first_normalization import check, io, local_cli


def make_image(path, *, profile="working", size=(24, 12)):
    path.parent.mkdir(parents=True, exist_ok=True)
    options = {}
    if profile != "untagged":
        options["icc_profile"] = io.working_srgb_icc() if profile == "working" else b"synthetic invalid ICC"
    Image.new("RGB", size, (50, 100, 160)).save(path, **options)


def make_lut(path):
    path.write_text("LUT_3D_SIZE 2\n" + "\n".join(
        f"{r} {g} {b}" for b in (0, 1) for g in (0, 1) for r in (0, 1)
    ) + "\n", encoding="utf-8")


def snapshot(folder):
    """Detect added reports, new directories and changes to any input bytes."""
    result = {}
    for path in folder.rglob("*"):
        name = path.relative_to(folder).as_posix()
        if path.is_symlink():
            result[name] = ("symlink", str(path.readlink()))
        elif path.is_dir():
            result[name] = ("directory",)
        else:
            result[name] = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
    return result


def run_check(source, *extra):
    return local_cli.main(["check", "--input", str(source), *map(str, extra)])


@pytest.fixture(autouse=True)
def forbid_external_exif(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("The input check must not invoke the external EXIF reader")
    monkeypatch.setattr(io, "read_exif", forbidden)


def test_json_check_decodes_all_inputs_without_export_or_report_writes(tmp_path, monkeypatch, capsys):
    source = tmp_path / "inputs"
    make_image(source / "a.png")
    make_image(source / "nested" / "b.jpg")
    lut = tmp_path / "identity.cube"
    make_lut(lut)
    before = snapshot(tmp_path)
    decoded = []
    original_load = check.load_image

    def observed_load(path, *args, **kwargs):
        assert kwargs["read_metadata"] is False
        decoded.append(path.relative_to(source).as_posix())
        return original_load(path, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("The input check must not export or save a report")

    monkeypatch.setattr(check, "load_image", observed_load)
    monkeypatch.setattr(io, "save_image", forbidden)
    monkeypatch.setattr(local_cli, "save_image", forbidden)
    monkeypatch.setattr(Image.Image, "save", forbidden)
    assert run_check(source, "--lut", lut, "--max-long-edge", "12", "--json") == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert not captured.err
    assert report["kind"] == "input_check" and report["status"] == "ready"
    assert report["counts"] == {"ready": 2, "blocked": 0, "ignored": 0, "checking": 0}
    assert decoded == ["a.png", "nested/b.jpg"]
    assert all((item["width"], item["height"]) == (12, 6) for item in report["items"])
    assert all(item["color"]["ColorConversion"] == "lcms_rgb8_to_working_srgb" for item in report["items"])
    assert report["lut"]["status"] == "ready"
    assert report["lut"]["sha256"] == hashlib.sha256(lut.read_bytes()).hexdigest()
    assert snapshot(tmp_path) == before


def test_tagged_high_depth_tiff_is_decoded_without_reducing_precision(tmp_path):
    source = tmp_path / "synthetic.tiff"
    data = np.arange(72, dtype=np.uint16).reshape(4, 6, 3) * 800
    io.tifffile.imwrite(source, data, photometric="rgb", iccprofile=io.working_srgb_icc())
    before = snapshot(tmp_path)
    report = check.inspect_inputs(source, format="tiff", max_long_edge=0)
    assert report["status"] == "ready"
    assert (report["items"][0]["width"], report["items"][0]["height"]) == (6, 4)
    assert report["items"][0]["color"]["ColorConversion"] == "exact_working_srgb_profile_high_depth_no_conversion"
    assert snapshot(tmp_path) == before


def test_relative_input_and_lut_are_resolved_from_the_current_directory(tmp_path, monkeypatch, capsys):
    source = tmp_path / "input" / "sample.png"
    make_image(source)
    lut = tmp_path / "local-example.cube"
    make_lut(lut)
    before = snapshot(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert run_check(Path("input"), "--lut", Path("local-example.cube"), "--json") == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "ready"
    assert report["items"][0]["input_name"] == "sample.png"
    assert report["lut"]["sha256"] == hashlib.sha256(lut.read_bytes()).hexdigest()
    assert snapshot(tmp_path) == before


def test_mixed_folder_reports_every_candidate_even_after_a_bad_image(tmp_path, capsys):
    source = tmp_path / "mixed"
    make_image(source / "a_bad.png", profile="invalid")
    (source / "b_corrupt.jpg").write_bytes(b"synthetic corrupt JPEG, no image data")
    (source / "c_raw.dng").write_bytes(b"synthetic unsupported RAW marker")
    (source / "d_notes.txt").write_text("ordinary non-image input", encoding="utf-8")
    make_image(source / "e_good.png")
    before = snapshot(tmp_path)
    assert run_check(source, "--json") == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "blocked"
    assert {item["input_name"]: item["status"] for item in report["items"]} == {
        "a_bad.png": "blocked", "b_corrupt.jpg": "blocked", "c_raw.dng": "blocked",
        "d_notes.txt": "ignored", "e_good.png": "ready",
    }
    assert report["counts"] == {"ready": 1, "blocked": 3, "ignored": 1, "checking": 0}
    assert "ICC" in report["items"][0]["error"]
    assert "RAW" in report["items"][2]["error"]
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("profile,assume,status", [
    ("untagged", False, "blocked"), ("untagged", True, "ready"),
    ("invalid", False, "blocked"), ("invalid", True, "blocked"),
])
def test_srgb_assumption_only_allows_untagged_input(tmp_path, profile, assume, status):
    source = tmp_path / "synthetic.png"
    make_image(source, profile=profile)
    before = snapshot(tmp_path)
    report = check.inspect_inputs(source, assume_srgb=assume)
    assert report["status"] == status and report["items"][0]["status"] == status
    if status == "ready":
        assert report["items"][0]["color"]["ColorConversion"] == "explicit_assume_srgb_untagged_rgb8"
    else:
        assert "ICC" in report["items"][0]["error"]
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("problem", ["missing", "invalid", "symlink"])
def test_blocked_optional_lut_still_diagnoses_input(tmp_path, capsys, problem):
    source = tmp_path / "valid.png"
    make_image(source)
    lut = tmp_path / "selected.cube"
    if problem == "invalid":
        lut.write_text("LUT_1D_SIZE 2\n0 0 0\n1 1 1\n")
    elif problem == "symlink":
        target = tmp_path / "actual.cube"
        make_lut(target)
        lut.symlink_to(target)
    before = snapshot(tmp_path)
    assert run_check(source, "--lut", lut, "--json") == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "blocked"
    assert report["lut"]["status"] == "blocked" and report["lut"]["error"]
    assert report["issues"] and report["items"][0]["status"] == "ready"
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("collision", ["extension", "casefold", "manifest", "checkpoint"])
def test_export_name_collisions_block_check_without_hiding_decode_results(tmp_path, collision):
    source = tmp_path / "inputs"
    make_image(source / "sample.png")
    other = {
        "extension": "sample.jpg", "casefold": "SAMPLE.PNG",
        "manifest": "manifest.json/nested.png", "checkpoint": ".manifest.json.tmp/nested.png",
    }[collision]
    make_image(source / other)
    before = snapshot(tmp_path)
    report = check.inspect_inputs(source, format="tiff")
    assert report["status"] == "blocked" and report["issues"]
    assert report["counts"]["ready"] == 2
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("kind", ["root_file", "root_directory", "nested_file", "nested_directory", "dangling"])
def test_candidate_symlinks_are_rejected_before_decoding(tmp_path, monkeypatch, kind):
    actual = tmp_path / "actual"
    make_image(actual / "image.png")
    source = tmp_path / "inputs"
    if kind == "root_file":
        source.symlink_to(actual / "image.png")
    elif kind == "root_directory":
        source.symlink_to(actual, target_is_directory=True)
    else:
        source.mkdir()
        if kind == "nested_file":
            (source / "link.png").symlink_to(actual / "image.png")
        elif kind == "nested_directory":
            (source / "linked").symlink_to(actual, target_is_directory=True)
        else:
            (source / "missing.png").symlink_to(tmp_path / "does-not-exist")
    before = snapshot(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("Symlink inputs must be rejected before decoding")

    monkeypatch.setattr(check, "load_image", forbidden)
    report = check.inspect_inputs(source)
    assert report["status"] == "blocked" and report["items"] == []
    assert any("symlink" in issue.lower() for issue in report["issues"])
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("kind", ["missing", "empty", "unsupported_file", "only_ignored"])
def test_no_supported_input_returns_cli_error_without_reports(tmp_path, capsys, kind):
    source = tmp_path / "input"
    if kind == "empty":
        source.mkdir()
    elif kind == "unsupported_file":
        source.write_text("synthetic text input")
    elif kind == "only_ignored":
        source.mkdir()
        (source / "notes.txt").write_text("synthetic text input")
    before = snapshot(tmp_path)
    assert run_check(source, "--json") == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "blocked" and report["issues"]
    if kind == "unsupported_file":
        assert report["items"][0]["status"] == "blocked"
    elif kind == "only_ignored":
        assert report["items"][0]["status"] == "ignored"
    assert snapshot(tmp_path) == before


def test_folder_nonimage_is_ignored_but_supported_image_can_be_ready(tmp_path):
    make_image(tmp_path / "valid.png")
    (tmp_path / "notes.txt").write_text("synthetic notes")
    report = check.inspect_inputs(tmp_path)
    assert report["status"] == "ready"
    assert report["counts"] == {"ready": 1, "blocked": 0, "ignored": 1, "checking": 0}


def test_huge_png_header_is_blocked_without_allocating_pixels_or_traceback(tmp_path, monkeypatch, capsys):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)

    source = tmp_path / "synthetic_huge.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n"
                       + chunk(b"IHDR", struct.pack(">IIBBBBB", 30000, 30000, 8, 2, 0, 0, 0))
                       + chunk(b"IDAT", zlib.compress(b"\0\0\0\0")) + chunk(b"IEND", b""))
    before = snapshot(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("An oversized header must be rejected before allocating pixels")

    monkeypatch.setattr(Image.Image, "load", forbidden)
    assert run_check(source, "--assume-srgb", "--json") == 2
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["status"] == "blocked" and report["items"][0]["status"] == "blocked"
    assert "pixel limit" in report["items"][0]["error"]
    assert "Traceback" not in captured.err and not captured.err
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("json_output", [False, True])
def test_cancel_after_one_input_never_reports_remaining_files_ready(tmp_path, monkeypatch, capsys, json_output):
    for name in ("a.png", "b.png", "c.png"):
        make_image(tmp_path / name)
    before = snapshot(tmp_path)
    original_load = check.load_image
    visited = []

    def interrupted_load(path, *args, **kwargs):
        visited.append(path.name)
        if path.name == "b.png":
            raise KeyboardInterrupt
        return original_load(path, *args, **kwargs)

    monkeypatch.setattr(check, "load_image", interrupted_load)
    assert run_check(tmp_path, *(["--json"] if json_output else [])) == 130
    output = capsys.readouterr().out
    assert visited == ["a.png", "b.png"]
    if json_output:
        report = json.loads(output)
        assert report["status"] == "cancelled"
        assert report["counts"]["ready"] == 1 and report["counts"]["checking"] == 1
        assert [item["status"] for item in report["items"]] == ["ready", "checking"]
    else:
        assert "Check cancelled" in output and "Check ready" not in output
        assert "Not completed" in output
    assert snapshot(tmp_path) == before


def test_text_output_escapes_control_characters_and_states_read_only_limit(tmp_path, capsys):
    source = tmp_path / "synthetic\n\x1b[31m.png"
    make_image(source)
    before = snapshot(tmp_path)
    assert run_check(source) == 0
    output = capsys.readouterr().out
    assert json.dumps(source.name, ensure_ascii=True) in output
    assert "\x1b" not in output
    assert "No exports written" in output and "guarantee" in output
    assert snapshot(tmp_path) == before


def test_invalid_cli_resize_returns_two_without_creating_report(tmp_path, capsys):
    source = tmp_path / "valid.png"
    make_image(source)
    before = snapshot(tmp_path)
    assert run_check(source, "--max-long-edge", "-1") == 2
    captured = capsys.readouterr()
    assert "nonnegative" in captured.err and "Traceback" not in captured.err
    assert snapshot(tmp_path) == before
