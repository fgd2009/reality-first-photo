"""RAW contract tests. The DNG is synthetic and generated here, not a photograph.

Source: tests/synthetic_dng.py. License: MIT, same as this repository.
No camera file from raw.pixls.us or any other archive is included.
"""
import json

import numpy as np
from PIL import Image

from reality_first_normalization import io, local_cli
from reality_first_normalization.raw_decode import RAW_CONTRACT_ID, decode_raw
from tests.synthetic_dng import write_synthetic_dng


def test_synthetic_dng_is_reproducible_and_records_the_contract(tmp_path):
    path = tmp_path / "synthetic.dng"
    write_synthetic_dng(path)
    first, color = decode_raw(path)
    second, _again = decode_raw(path)
    np.testing.assert_array_equal(first, second)
    assert first.shape == (64, 64, 3)
    assert np.all((first >= 0.0) & (first <= 1.0))
    assert color["ColorConversion"] == RAW_CONTRACT_ID
    assert color["RawpyVersion"] == "0.26.1"
    assert color["LibRawVersion"] == "0.22.0"
    assert color["RawWhiteBalance"] == "camera"
    assert color["RawDemosaic"] == "ahd"
    assert color["RawTransfer"] == "linear_srgb_then_iec61966_2_1"
    assert color["RawOutputBps"] == "16"
    assert color["RawHighlight"] == "Clip"
    assert color["ExifOmitted"] == "GPS,MakerNote"
    preserved = json.loads(color["PreservedExif"])
    assert preserved["Make"] == "Reality First"
    assert preserved["Model"] == "Synthetic DNG"
    assert preserved["ExposureTime"] == "1/125"
    assert "GPS" not in preserved


def test_export_copies_technical_exif_and_not_a_gps_tag(tmp_path):
    source = tmp_path / "synthetic.dng"
    write_synthetic_dng(source)
    output = tmp_path / "out"
    assert local_cli.main([
        "--input", str(source), "--output", str(output), "--format", "jpeg",
        "--normalize-strength", "0", "--max-long-edge", "0",
    ]) == 0
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert manifest["raw"]["contract"] == RAW_CONTRACT_ID
    assert manifest["raw"]["demosaic"] == "ahd"
    item = manifest["items"][0]
    assert item["color"]["RawpyVersion"] == "0.26.1"
    assert item["color"]["LibRawVersion"] == "0.22.0"
    with Image.open(output / "synthetic.jpg") as image:
        exif = image.getexif()
        assert exif.get(271) == "Reality First"
        assert exif.get(272) == "Synthetic DNG"
        assert 34853 not in exif  # GPS IFD


def test_invalid_raw_is_skipped_and_a_missing_extra_creates_no_output(tmp_path, monkeypatch):
    source = tmp_path / "input"
    source.mkdir()
    io.save_image(np.full((8, 8, 3), 0.4), source / "plain.png")
    (source / "broken.dng").write_bytes(b"synthetic placeholder, not RAW photo data")
    exported = tmp_path / "exported"
    assert local_cli.main([
        "--input", str(source), "--output", str(exported), "--format", "png", "--normalize-strength", "0",
    ]) == 2
    manifest = json.loads((exported / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["items"][0]["output"] == "plain.png"
    assert manifest["failures"][0]["input"] == "broken.dng"
    assert manifest["failures"][0]["stage"] == "decode"
    assert "RAW" in manifest["failures"][0]["error"]
    assert not (exported / "broken.png").exists()
    monkeypatch.setattr(local_cli, "raw_decoder_available", lambda: False)
    refused = tmp_path / "refused"
    assert local_cli.main(["--input", str(source), "--output", str(refused), "--format", "png"]) == 2
    assert not refused.exists()


def test_gpl_demosaic_names_are_rejected(tmp_path):
    path = tmp_path / "synthetic.dng"
    write_synthetic_dng(path)
    try:
        decode_raw(path, demosaic="amaze")
    except io.ColorManagementError as exc:
        assert "GPL" in str(exc)
    else:
        raise AssertionError("GPL demosaic name was accepted")
