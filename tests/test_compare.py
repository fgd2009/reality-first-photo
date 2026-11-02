"""Four-way comparison contracts, using only generated pixels and original LUTs."""
import hashlib
import html
import json
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

import numpy as np
import pytest
from PIL import Image

from reality_first_normalization import compare, io, local_cli

RECIPES = ("original", "normalized", "lut_only", "normalized_lut")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hashes(folder):
    return {path.relative_to(folder).as_posix(): digest(path)
            for path in folder.rglob("*") if path.is_file()}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_rgb(path):
    with Image.open(path) as image:
        assert image.mode == "RGB"
        assert image.info["icc_profile"] == io.working_srgb_icc()
        return np.asarray(image).copy()


def write_image(path, offset=0):
    x, y = np.meshgrid(np.linspace(0, 1, 32), np.linspace(0, 1, 16))
    pixels = np.stack((.15 + .55 * x, .1 + .6 * y, .7 - .4 * x), axis=-1)
    io.save_image(np.clip(pixels + offset, 0, 1), path)


def write_lut(path, identity=False):
    rows = ["LUT_3D_SIZE 2"]
    for b in (0, 1):
        for g in (0, 1):
            for r in (0, 1):
                values = (r, g, b) if identity else (.04 + .92 * r, .96 * g, .9 * b)
                rows.append(" ".join(map(str, values)))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


@pytest.fixture
def generated(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    write_image(source / "sample.png")
    lut = tmp_path / "original-example.cube"
    write_lut(lut)
    return source, lut


def invoke(source, output, lut, *extra):
    return local_cli.main(["compare", "--input", str(source), "--output", str(output),
                           "--lut", str(lut), *extra])


def assert_failed(output, status="failed"):
    assert read_json(output / "compare.json")["status"] == status
    assert not (output / "index.html").exists()


def warm(pixels):
    return np.stack((.04 + .92 * pixels[..., 0], .96 * pixels[..., 1], .9 * pixels[..., 2]), axis=-1)


def test_four_recipes_use_same_source_and_independent_lut_equation(generated, tmp_path):
    source, lut = generated
    before, lut_before = tree_hashes(source), digest(lut)
    output = tmp_path / "comparison"
    assert compare.run_comparison(source / "sample.png", output, lut,
                                  normalize_strength=.6, lut_strength=.65, max_long_edge=0) == 0
    report = read_json(output / "compare.json")
    assert report["kind"] == "four_way_comparison"
    assert report["status"] == "complete"
    assert report["format"] == "png"
    assert report["max_long_edge"] == 0
    assert report["lut"]["sha256"] == lut_before
    assert [recipe["id"] for recipe in report["recipes"]] == list(RECIPES)
    assert len(report["items"]) == 1
    item = report["items"][0]
    assert item["input_name"] == "sample.png"
    assert item["input_sha256"] == before["sample.png"]
    assert (item["width"], item["height"]) == (32, 16)
    pixels = {}
    for recipe in RECIPES:
        variant = item["variants"][recipe]
        assert variant["output"] == f"{recipe}/sample.png"
        pixels[recipe] = read_rgb(output / variant["output"])
        manifest = read_json(output / recipe / "manifest.json")
        assert manifest["status"] == "complete"
        assert manifest["items"][0]["input_sha256"] == before["sample.png"]
        assert manifest["items"][0]["normalization"] == variant["normalization"]
        if recipe in ("original", "lut_only"):
            assert variant["normalization"] == {"applied": False, "operations": None}
        else:
            assert variant["normalization"]["applied"] is True
            assert variant["normalization"]["operations"]["global_strength"] == .6
    np.testing.assert_array_equal(pixels["original"], read_rgb(source / "sample.png"))
    assert np.any(pixels["normalized"] != pixels["original"])
    for unstyled, styled in (("original", "lut_only"), ("normalized", "normalized_lut")):
        base = pixels[unstyled].astype(np.float64) / 255
        expected = .35 * base + .65 * warm(base)
        assert np.max(np.abs(pixels[styled] / 255 - expected)) <= 1 / 255 + 1e-7
    assert item["variants"]["normalized"]["normalization"] == item["variants"]["normalized_lut"]["normalization"]
    assert (output / "index.html").is_file()
    assert tree_hashes(source) == before
    assert digest(lut) == lut_before


@pytest.mark.parametrize("normalization,lut_strength", [(0, 1), (.6, 0), (0, 0)])
def test_zero_strengths_make_the_corresponding_routes_identical(generated, tmp_path, normalization, lut_strength):
    source, lut = generated
    output = tmp_path / "zero-strength"
    assert compare.run_comparison(source, output, lut, normalize_strength=normalization, lut_strength=lut_strength) == 0
    pixels = {recipe: read_rgb(output / recipe / "sample.png") for recipe in RECIPES}
    if normalization == 0:
        np.testing.assert_array_equal(pixels["original"], pixels["normalized"])
        np.testing.assert_array_equal(pixels["lut_only"], pixels["normalized_lut"])
    if lut_strength == 0:
        np.testing.assert_array_equal(pixels["original"], pixels["lut_only"])
        np.testing.assert_array_equal(pixels["normalized"], pixels["normalized_lut"])


def test_original_is_a_resized_srgb_reference_with_explicit_untagged_assumption(tmp_path):
    source = tmp_path / "untagged.png"
    Image.new("RGB", (32, 16), (51, 102, 153)).save(source)
    lut = tmp_path / "identity.cube"
    write_lut(lut, identity=True)
    output = tmp_path / "resized"
    assert invoke(source, output, lut, "--max-long-edge", "16", "--assume-srgb") == 0
    report = read_json(output / "compare.json")
    assert report["assume_srgb"] is True
    assert (report["items"][0]["width"], report["items"][0]["height"]) == (16, 8)
    pixels = read_rgb(output / "original" / source.name)
    assert pixels.shape == (8, 16, 3)
    np.testing.assert_array_equal(pixels, np.broadcast_to([51, 102, 153], pixels.shape))
    assert source.read_bytes() != (output / "original" / source.name).read_bytes()


@pytest.mark.parametrize("existing", ["directory", "file", "symlink", "dangling_symlink"])
def test_existing_output_and_links_are_never_overwritten(generated, tmp_path, existing):
    source, lut = generated
    output = tmp_path / "existing"
    if existing == "directory":
        output.mkdir()
        (output / "sentinel").write_bytes(b"keep directory contents")
    elif existing == "file":
        output.write_bytes(b"keep existing file")
    else:
        target = tmp_path / "target"
        if existing == "symlink":
            target.mkdir()
            (target / "sentinel").write_bytes(b"keep symlink target")
        output.symlink_to(target, target_is_directory=True)
    before = tree_hashes(tmp_path)
    assert invoke(source, output, lut) == 2
    assert tree_hashes(tmp_path) == before
    if "symlink" in existing:
        assert output.is_symlink()
        if existing == "dangling_symlink":
            assert not target.exists()


@pytest.mark.parametrize("through_alias", [False, True])
def test_output_inside_input_tree_is_rejected_even_through_parent_symlink(generated, tmp_path, through_alias):
    source, lut = generated
    parent = source
    if through_alias:
        parent = tmp_path / "input-alias"
        parent.symlink_to(source, target_is_directory=True)
    output = parent / "comparison"
    before = tree_hashes(source)
    assert invoke(source, output, lut) == 2
    assert not output.exists()
    assert tree_hashes(source) == before


def test_safe_parent_symlink_outside_input_tree_keeps_working(generated, tmp_path):
    source, lut = generated
    parent = tmp_path / "actual-output-parent"
    parent.mkdir()
    alias = tmp_path / "output-parent-alias"
    alias.symlink_to(parent, target_is_directory=True)
    assert invoke(source, alias / "comparison", lut) == 0
    assert (parent / "comparison" / "index.html").is_file()
    assert alias.is_symlink()


@pytest.mark.parametrize("collision", ["converted_extension", "reserved_manifest_folder"])
def test_output_name_conflicts_fail_before_creation(generated, tmp_path, collision):
    source, lut = generated
    if collision == "converted_extension":
        io.save_image(np.full((8, 8, 3), .4), source / "sample.jpg")
    else:
        write_image(source / "manifest.json" / "nested.png")
    output = tmp_path / "name-conflict"
    before = tree_hashes(source)
    assert invoke(source, output, lut) == 2
    assert not output.exists()
    assert tree_hashes(source) == before


@pytest.mark.parametrize("link_kind", ["root", "file", "directory", "dangling"])
def test_input_symlinks_are_rejected_before_export(generated, tmp_path, link_kind):
    source, lut = generated
    if link_kind == "root":
        alias = tmp_path / "source-alias"
        alias.symlink_to(source, target_is_directory=True)
        source = alias
    elif link_kind == "file":
        (source / "alias.png").symlink_to(source / "sample.png")
    elif link_kind == "directory":
        nested = tmp_path / "elsewhere"
        nested.mkdir()
        write_image(nested / "other.png")
        (source / "linked-directory").symlink_to(nested, target_is_directory=True)
    else:
        (source / "missing.png").symlink_to(tmp_path / "missing-target.png")
    output = tmp_path / "refused-links"
    assert invoke(source, output, lut) == 2
    assert not output.exists()


class ParsedReport(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.images = []
        self.urls = []
        self.event_attributes = []

    def handle_starttag(self, tag, attributes):
        self.tags.append(tag)
        for key, value in attributes:
            if key.startswith("on"):
                self.event_attributes.append((tag, key, value))
            if key in ("src", "href"):
                self.urls.append(value)
                if tag == "img" and key == "src":
                    self.images.append(value)


def test_same_basenames_and_hostile_filenames_render_as_safe_local_links(generated, tmp_path):
    source, lut = generated
    (source / "sample.png").unlink()
    hostile = 'evil & "<img src=x onerror=alert(1)> #?% 中文\\name.png'
    paths = ["left/same.png", "right/same.png", hostile]
    for index, relative in enumerate(paths):
        write_image(source / relative, offset=.03 * index)
    before = tree_hashes(source)
    output = tmp_path / "html-report"
    assert invoke(source, output, lut) == 0
    report = read_json(output / "compare.json")
    assert {item["input_name"] for item in report["items"]} == set(paths)
    document = (output / "index.html").read_text(encoding="utf-8")
    assert html.escape(hostile, quote=True) in document
    parser = ParsedReport()
    parser.feed(document)
    assert not ({"script", "iframe", "object", "embed", "base"} & set(parser.tags))
    assert not parser.event_attributes
    assert len(parser.images) == 12
    expected_images = {variant["output"] for item in report["items"] for variant in item["variants"].values()}
    assert {unquote(url) for url in parser.images} == expected_images
    for url in parser.urls:
        parts = urlsplit(url)
        assert not parts.scheme and not parts.netloc and not parts.query and not parts.fragment
        assert (output / unquote(parts.path)).is_file()
        assert (output / unquote(parts.path)).resolve().is_relative_to(output)
    assert any("%23" in url and "%3F" in url and "%25" in url and "%5C" in url for url in parser.images)
    assert tree_hashes(source) == before


@pytest.mark.parametrize("problem", ["missing_lut", "invalid_icc", "raw"])
def test_invalid_input_or_missing_lut_cannot_produce_a_success_page(generated, tmp_path, problem):
    source, lut = generated
    if problem == "missing_lut":
        lut = tmp_path / "missing.cube"
    elif problem == "invalid_icc":
        Image.new("RGB", (8, 8), (60, 90, 120)).save(source / "sample.png", icc_profile=b"invalid profile")
    else:
        (source / "unsupported.dng").write_bytes(b"synthetic placeholder, not RAW photo data")
    before = tree_hashes(source)
    output = tmp_path / "invalid"
    assert invoke(source, output, lut) == 2
    assert not (output / "index.html").exists()
    if problem == "invalid_icc":
        assert_failed(output)
    else:
        assert not output.exists()
    assert tree_hashes(source) == before


@pytest.mark.parametrize("mutation", ["modify", "add", "delete", "rename", "lut", "lut_symlink", "last_source", "last_lut"])
def test_cross_recipe_source_or_lut_changes_fail_without_html(generated, tmp_path, monkeypatch, mutation):
    source, lut = generated
    output = tmp_path / "changed"
    original_run = compare.local_cli.run
    calls = 0

    def changing_run(args):
        nonlocal calls
        code = original_run(args)
        calls += 1
        trigger = 4 if mutation.startswith("last_") else 1
        if calls == trigger:
            if mutation in ("modify", "last_source"):
                write_image(source / "sample.png", offset=.1)
            elif mutation == "add":
                write_image(source / "added.png")
            elif mutation == "delete":
                (source / "sample.png").unlink()
            elif mutation == "rename":
                (source / "sample.png").rename(source / "renamed.png")
            elif mutation == "lut_symlink":
                same_bytes = tmp_path / "same-content.cube"
                same_bytes.write_bytes(lut.read_bytes())
                lut.unlink()
                lut.symlink_to(same_bytes)
            else:
                write_lut(lut, identity=True)
        return code

    monkeypatch.setattr(compare.local_cli, "run", changing_run)
    assert compare.run_comparison(source, output, lut) == 2
    assert_failed(output)
    if mutation == "lut_symlink":
        assert "symlink" in read_json(output / "compare.json")["error"].lower()
    assert calls >= 1


@pytest.mark.parametrize("failure,code,status", [("error", 2, "failed"), ("cancel_code", 130, "cancelled"),
                                                ("interrupt", 130, "cancelled")])
def test_recipe_failure_and_cancellation_do_not_report_success(generated, tmp_path, monkeypatch, capsys,
                                                              failure, code, status):
    source, lut = generated
    calls = []

    def failed_run(args):
        calls.append(args)
        if failure == "interrupt":
            raise KeyboardInterrupt
        return code

    monkeypatch.setattr(compare.local_cli, "run", failed_run)
    output = tmp_path / "failed-recipe"
    assert compare.run_comparison(source, output, lut) == code
    assert_failed(output, status)
    assert len(calls) == 1
    assert "complete" not in capsys.readouterr().out.lower()


def test_html_renderer_failure_records_failed_after_real_exports(generated, tmp_path, monkeypatch):
    source, lut = generated

    def failed_renderer(report):
        raise ValueError("injected HTML renderer failure")

    monkeypatch.setattr(compare, "render_comparison_html", failed_renderer)
    output = tmp_path / "render-failed"
    assert compare.run_comparison(source, output, lut) == 2
    assert_failed(output)
    assert "injected HTML renderer failure" in read_json(output / "compare.json")["error"]
    for recipe in RECIPES:
        assert read_json(output / recipe / "manifest.json")["status"] == "complete"


def test_source_change_during_html_rendering_is_checked_before_publication(generated, tmp_path, monkeypatch):
    source, lut = generated
    original_renderer = compare.render_comparison_html

    def render_then_change(report):
        document = original_renderer(report)
        write_image(source / "sample.png", offset=.1)
        return document

    monkeypatch.setattr(compare, "render_comparison_html", render_then_change)
    output = tmp_path / "changed-during-render"
    assert compare.run_comparison(source, output, lut) == 2
    assert_failed(output)


@pytest.mark.parametrize("keyword,value", [
    ("normalize_strength", -.1), ("normalize_strength", 1.1), ("normalize_strength", float("nan")),
    ("lut_strength", -.1), ("lut_strength", 1.1), ("lut_strength", float("inf")),
    ("max_long_edge", -1), ("max_long_edge", 2.5),
])
def test_invalid_api_parameters_fail_before_creating_output(generated, tmp_path, keyword, value):
    source, lut = generated
    output = tmp_path / "bad-parameters"
    with pytest.raises(ValueError):
        compare.run_comparison(source, output, lut, **{keyword: value})
    assert not output.exists()


def test_compare_help_is_discoverable(capsys):
    with pytest.raises(SystemExit) as ended:
        local_cli.main(["compare", "--help"])
    assert ended.value.code == 0
    output = capsys.readouterr().out
    assert "--input" in output and "--output" in output and "--lut" in output
