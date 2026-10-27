"""LUT pixels and provenance must come from the same current file bytes."""
import hashlib
import json
from pathlib import Path

import numpy as np

from reality_first_normalization import io, local_cli
from reality_first_normalization.lut import apply_cube_lut, load_cube_lut


def cube_bytes(swapped=False):
    rows = ["LUT_3D_SIZE 2"]
    for b in (0, 1):
        for g in (0, 1):
            for r in (0, 1):
                values = (b, g, r) if swapped else (r, g, b)
                rows.append(" ".join(map(str, values)))
    return ("\n".join(rows) + "\n").encode()


def test_same_path_replacement_updates_rendering_and_legacy_manifest_hash(tmp_path):
    lut_path = tmp_path / "changing.cube"
    first_bytes, replacement = cube_bytes(), cube_bytes(swapped=True)
    lut_path.write_bytes(first_bytes)
    pixels = np.array([[[.2, .4, .8]]], dtype=np.float32)
    first = load_cube_lut(str(lut_path))
    np.testing.assert_allclose(apply_cube_lut(pixels, first), pixels, atol=1e-7)
    assert first.source_sha256 == hashlib.sha256(first_bytes).hexdigest()
    lut_path.write_bytes(replacement)
    second = load_cube_lut(str(lut_path))
    np.testing.assert_allclose(apply_cube_lut(pixels, second), pixels[..., ::-1], atol=1e-7)
    assert second.source_sha256 == hashlib.sha256(replacement).hexdigest()
    assert first.source_sha256 != second.source_sha256

    source = tmp_path / "sample.png"
    io.save_image(pixels, source)
    output = tmp_path / "export"
    assert local_cli.main(["--input", str(source), "--output", str(output), "--lut", str(lut_path),
                           "--normalize-strength", "0", "--format", "png"]) == 0
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["lut_sha256"] == hashlib.sha256(replacement).hexdigest()
    exported, _ = io.load_image(output / source.name, read_metadata=False)
    np.testing.assert_allclose(exported, pixels[..., ::-1], atol=1 / 255)


def test_hash_and_table_stay_bound_when_file_changes_after_read(tmp_path, monkeypatch):
    path = tmp_path / "changed-after-read.cube"
    first_bytes, replacement = cube_bytes(), cube_bytes(swapped=True)
    path.write_bytes(first_bytes)
    original_read = Path.read_bytes
    replaced = False

    def read_then_change(self):
        nonlocal replaced
        data = original_read(self)
        if self == path and not replaced:
            path.write_bytes(replacement)
            replaced = True
        return data

    monkeypatch.setattr(Path, "read_bytes", read_then_change)
    lut = load_cube_lut(str(path))
    pixels = np.array([[[.1, .3, .7]]], dtype=np.float32)
    np.testing.assert_allclose(apply_cube_lut(pixels, lut), pixels, atol=1e-7)
    assert lut.source_sha256 == hashlib.sha256(first_bytes).hexdigest()
    assert hashlib.sha256(original_read(path)).hexdigest() != lut.source_sha256
