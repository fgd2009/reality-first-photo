"""Persist useful, honest progress when a local export is interrupted or fails."""
import copy
import hashlib
import json
from html import unescape
from pathlib import Path

import pytest
from PIL import Image

from reality_first_normalization import compare, io, local_cli, report_state


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def tree_hashes(folder):
    return {path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in folder.rglob("*") if path.is_file()}


def make_image(path, *, valid_icc=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = io.working_srgb_icc() if valid_icc else b"synthetic invalid ICC"
    Image.new("RGB", (12, 8), (60, 100, 150)).save(path, icc_profile=profile)


@pytest.fixture
def recovery_inputs(tmp_path):
    source = tmp_path / "input"
    make_image(source / "a.png")
    make_image(source / "nested" / "b.png")
    lut = tmp_path / "identity.cube"
    lut.write_text("LUT_3D_SIZE 2\n" + "\n".join(
        f"{r} {g} {b}" for b in (0, 1) for g in (0, 1) for r in (0, 1)
    ) + "\n")
    return source, lut


def export(source, output, *extra):
    return local_cli.main(["--input", str(source), "--output", str(output), "--format", "png", *extra])


def assert_retry_notice(manifest):
    notice = manifest.get("notice", "").lower()
    assert "new" in notice and "director" in notice


def test_running_and_per_item_checkpoints_exist_before_decode(recovery_inputs, tmp_path, monkeypatch):
    source, lut = recovery_inputs
    output = tmp_path / "checkpoints"
    states = []
    decoded = []
    original_write = report_state.write_json
    original_load = local_cli.load_image

    def observed_write(path, document):
        original_write(path, document)
        if path == output / "manifest.json":
            states.append(copy.deepcopy(document))

    def observed_load(path, *args, **kwargs):
        checkpoint = read_json(output / "manifest.json")
        assert checkpoint["status"] == "running"
        assert checkpoint["total_inputs"] == 2
        assert checkpoint["active_input"] == path.relative_to(source).as_posix()
        assert checkpoint["active_stage"] == "decode"
        assert len(checkpoint["items"]) == len(decoded)
        decoded.append(path)
        return original_load(path, *args, **kwargs)

    monkeypatch.setattr(report_state, "write_json", observed_write)
    monkeypatch.setattr(local_cli, "load_image", observed_load)
    before = tree_hashes(source)
    assert export(source, output, "--lut", str(lut), "--normalize-strength", ".6") == 0
    assert states[0]["status"] == "running" and states[0]["items"] == []
    assert any(state["status"] == "running" and len(state["items"]) == 1 for state in states)
    final = read_json(output / "manifest.json")
    assert final["status"] == "complete" and len(final["items"]) == 2
    assert final["active_input"] is None and final["active_stage"] is None
    assert tree_hashes(source) == before


def test_partial_bad_icc_identifies_relative_input_and_retry_preserves_old_output(recovery_inputs, tmp_path, capsys):
    source, _ = recovery_inputs
    bad = source / "nested" / "b.png"
    make_image(bad, valid_icc=False)
    before = tree_hashes(source)
    output = tmp_path / "failed-batch"
    assert export(source, output, "--normalize-strength", "0") == 2
    report = read_json(output / "manifest.json")
    assert report["status"] == "failed"
    assert report["total_inputs"] == 2
    assert report["failed_input"] == "nested/b.png"
    assert report["failed_stage"] == "decode"
    assert [item["output"] for item in report["items"]] == ["a.png"]
    assert_retry_notice(report)
    assert "nested/b.png" in capsys.readouterr().err
    assert tree_hashes(source) == before

    preserved = tree_hashes(output)
    assert export(source, output, "--normalize-strength", "0") == 2
    assert tree_hashes(output) == preserved
    make_image(bad)
    corrected = tree_hashes(source)
    retry = tmp_path / "successful-retry"
    assert export(source, retry, "--normalize-strength", "0") == 0
    assert read_json(retry / "manifest.json")["status"] == "complete"
    assert tree_hashes(source) == corrected
    assert tree_hashes(output) == preserved


@pytest.mark.parametrize("stage", ["decode", "export"])
def test_cancel_after_first_export_retains_completed_progress_and_failed_input(recovery_inputs, tmp_path, monkeypatch, stage):
    source, _ = recovery_inputs
    output = tmp_path / "cancelled-batch"
    before = tree_hashes(source)
    if stage == "decode":
        original_load = local_cli.load_image

        def interrupted_load(path, *args, **kwargs):
            if path.name == "b.png":
                raise KeyboardInterrupt
            return original_load(path, *args, **kwargs)

        monkeypatch.setattr(local_cli, "load_image", interrupted_load)
    else:
        original_save = local_cli.save_image

        def interrupted_save(pixels, path, *args, **kwargs):
            if path.name == "b.png":
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"synthetic interrupted image write")
                raise KeyboardInterrupt
            return original_save(pixels, path, *args, **kwargs)

        monkeypatch.setattr(local_cli, "save_image", interrupted_save)
    assert export(source, output, "--normalize-strength", "0") == 130
    report = read_json(output / "manifest.json")
    assert report["status"] == "cancelled"
    assert report["failed_input"] == "nested/b.png"
    assert report["failed_stage"] == stage
    assert [item["output"] for item in report["items"]] == ["a.png"]
    assert_retry_notice(report)
    assert tree_hashes(source) == before


def test_unhandled_stop_keeps_parseable_running_checkpoint(recovery_inputs, tmp_path, monkeypatch):
    source, _ = recovery_inputs
    output = tmp_path / "unexpected-stop"
    original_load = local_cli.load_image

    def stopped_load(path, *args, **kwargs):
        if path.name == "b.png":
            raise SystemExit(77)
        return original_load(path, *args, **kwargs)

    monkeypatch.setattr(local_cli, "load_image", stopped_load)
    before = tree_hashes(source)
    with pytest.raises(SystemExit) as ended:
        export(source, output, "--normalize-strength", "0")
    assert ended.value.code == 77
    report = read_json(output / "manifest.json")
    assert report["status"] == "running"
    assert report["active_input"] == "nested/b.png"
    assert report["active_stage"] == "decode"
    assert [item["output"] for item in report["items"]] == ["a.png"]
    assert tree_hashes(source) == before


@pytest.mark.parametrize("stage", ["normalize", "lut"])
def test_processing_error_names_the_actual_phase(recovery_inputs, tmp_path, monkeypatch, stage):
    source, lut = recovery_inputs

    def failure(*args, **kwargs):
        raise ValueError(f"injected {stage} failure")

    monkeypatch.setattr(local_cli, "normalize_image" if stage == "normalize" else "apply_cube_lut", failure)
    output = tmp_path / ("failed-" + stage)
    assert export(source, output, "--lut", str(lut)) == 2
    report = read_json(output / "manifest.json")
    assert report["status"] == "failed"
    assert report["failed_input"] == "a.png"
    assert report["failed_stage"] == stage
    assert report["items"] == []
    assert_retry_notice(report)


def test_atomic_json_failure_preserves_previous_document(tmp_path, monkeypatch):
    path = tmp_path / "manifest.json"
    previous = {"status": "running", "items": [{"output": "completed.png"}]}
    report_state.write_json(path, previous)
    original_replace = Path.replace

    def failed_replace(self, target):
        if Path(target) == path:
            raise OSError("injected atomic JSON replacement failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", failed_replace)
    with pytest.raises(OSError, match="replacement failure"):
        report_state.write_json(path, {"status": "complete", "items": []})
    assert read_json(path) == previous


def test_persistent_checkpoint_failure_returns_error_with_prior_progress(recovery_inputs, tmp_path, monkeypatch, capsys):
    source, _ = recovery_inputs
    output = tmp_path / "cannot-commit-next-checkpoint"
    manifest_path = output / "manifest.json"
    original_replace = Path.replace
    failed = False

    def fail_second_input_checkpoint(self, target):
        nonlocal failed
        if Path(target) == manifest_path:
            pending = read_json(self)
            if pending.get("active_input") == "nested/b.png":
                failed = True
            if failed:
                raise OSError("injected persistent checkpoint failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_second_input_checkpoint)
    before = tree_hashes(source)
    assert export(source, output, "--normalize-strength", "0") == 2
    assert failed
    retained = read_json(manifest_path)
    assert retained["status"] != "complete"
    assert [item["output"] for item in retained["items"]] == ["a.png"]
    assert not (output / "nested" / "b.png").exists()
    assert "complete:" not in capsys.readouterr().out
    assert tree_hashes(source) == before


@pytest.mark.parametrize("command", ["export", "compare"])
def test_internal_manifest_temporary_name_is_reserved(recovery_inputs, tmp_path, command):
    source, lut = recovery_inputs
    make_image(source / ".manifest.json.tmp" / "nested.png")
    output = tmp_path / "reserved-name"
    before = tree_hashes(source)
    if command == "export":
        code = export(source, output)
    else:
        code = local_cli.main(["compare", "--input", str(source), "--output", str(output), "--lut", str(lut)])
    assert code == 2
    assert not output.exists()
    assert tree_hashes(source) == before


def test_comparison_never_commits_complete_json_before_html(recovery_inputs, tmp_path, monkeypatch):
    source, lut = recovery_inputs
    output = tmp_path / "publish-order"
    original_write = report_state.write_json
    complete_seen = []

    def observed_write(path, document):
        if path == output / "compare.json" and document.get("status") == "complete":
            assert (output / "index.html").is_file()
            complete_seen.append(True)
        return original_write(path, document)

    monkeypatch.setattr(report_state, "write_json", observed_write)
    assert compare.run_comparison(source, output, lut) == 0
    assert complete_seen
    assert read_json(output / "compare.json")["status"] == "complete"


def test_abrupt_stop_between_html_and_final_checkpoint_cannot_claim_success(recovery_inputs, tmp_path, monkeypatch):
    source, lut = recovery_inputs
    output = tmp_path / "stopped-before-final-status"
    original_write = report_state.write_json

    def stopped_write(path, document):
        if path == output / "compare.json" and document.get("status") == "complete":
            raise SystemExit(77)
        return original_write(path, document)

    monkeypatch.setattr(report_state, "write_json", stopped_write)
    with pytest.raises(SystemExit):
        compare.run_comparison(source, output, lut)
    assert read_json(output / "compare.json")["status"] == "running"
    page = (output / "index.html").read_text(encoding="utf-8")
    assert "This page alone does not establish completion" in page
    settings = json.loads(unescape(page.split("<pre>", 1)[1].split("</pre>", 1)[0]))
    assert "status" not in settings  # Individual stages completed; the run did not commit.


def test_html_publication_failure_cannot_leave_complete_json(recovery_inputs, tmp_path, monkeypatch):
    source, lut = recovery_inputs
    output = tmp_path / "html-publish-failed"
    original_replace = Path.replace

    def failed_html_replace(self, target):
        if Path(target) == output / "index.html":
            assert read_json(output / "compare.json")["status"] != "complete"
            raise OSError("injected HTML publication failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", failed_html_replace)
    assert compare.run_comparison(source, output, lut) == 2
    report = read_json(output / "compare.json")
    assert report["status"] == "failed"
    assert "publication failure" in report["error"]
    assert not (output / "index.html").exists()


def test_demo_refuses_dangling_output_link_without_creating_its_target(tmp_path, capsys):
    output = tmp_path / "existing-link"
    target = tmp_path / "not-created"
    output.symlink_to(target, target_is_directory=True)
    assert local_cli.main(["demo", "--output", str(output)]) == 2
    assert output.is_symlink()
    assert not target.exists()
    captured = capsys.readouterr()
    assert "already exists" in captured.err
    assert "Demo complete." not in captured.out


def test_comparison_publishes_successful_inputs_when_one_decode_fails(recovery_inputs, tmp_path, capsys):
    source, lut = recovery_inputs
    make_image(source / "nested" / "b.png", valid_icc=False)
    before = tree_hashes(source)
    output = tmp_path / "mixed-invalid-comparison"
    assert compare.run_comparison(source, output, lut) == 2
    report = read_json(output / "compare.json")
    assert report["status"] == "partial"
    assert [item["input_name"] for item in report["items"]] == ["a.png"]
    assert any(failure["input"] == "nested/b.png" and failure["stage"] == "decode" for failure in report["failures"])
    assert "nested/b.png" in report["error"] and "decode" in report["error"]
    stage = report["stages"]["original"]
    assert stage["status"] == "failed" and stage["exported"] == 1
    assert stage["failed_input"] == "nested/b.png" and stage["failed_stage"] == "decode"
    manifest = read_json(output / "original" / "manifest.json")
    assert [item["output"] for item in manifest["items"]] == ["a.png"]
    page = (output / "index.html").read_text(encoding="utf-8")
    assert "partial, not complete" in page and "nested/b.png" in page
    for recipe in ("original", "normalized", "lut_only", "normalized_lut"):
        assert (output / recipe / "a.png").is_file()
        assert not (output / recipe / "nested" / "b.png").exists()
    assert tree_hashes(source) == before
    captured = capsys.readouterr()
    assert "Comparison complete" not in captured.out
    assert "nested/b.png" in captured.err
