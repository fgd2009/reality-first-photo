"""Decode four CC0 camera files from raw.pixls.us.

Not collected by the default CI job. Run with:

    python -m pytest -m realraw tests/test_real_raw.py

The files are cached under $REALITY_FIRST_RAW_CACHE or ~/.cache/reality-first-photo/raw-samples.
They are not committed. A missing network or a missing rawpy install skips the test.
A sha256 mismatch fails it.
"""
from __future__ import annotations

import hashlib
import os
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pytest

from reality_first_normalization.raw_decode import (
    RAW_CONTRACT_ID,
    decode_raw,
    raw_decoder_available,
)
from tests.realraw_samples import SAMPLES

pytestmark = pytest.mark.realraw


def _cache_dir() -> Path:
    override = os.environ.get("REALITY_FIRST_RAW_CACHE")
    path = Path(override) if override else Path.home() / ".cache" / "reality-first-photo" / "raw-samples"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _download(sample: dict) -> Path:
    destination = _cache_dir() / sample["filename"]
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == sample["sha256"]:
        return destination
    request = urllib.request.Request(sample["url"], headers={"User-Agent": "reality-first-photo-realraw"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        pytest.skip(f"network unavailable for {sample['id']}: {exc}")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != sample["sha256"]:
        raise AssertionError(f"{sample['id']} sha256 {digest} != {sample['sha256']}")
    destination.write_bytes(payload)
    return destination


@pytest.mark.parametrize("sample", SAMPLES, ids=[item["id"] for item in SAMPLES])
def test_cc0_camera_raw_decodes_twice_with_the_recorded_contract(sample):
    if not raw_decoder_available():
        pytest.skip("rawpy is not installed")
    path = _download(sample)
    first, color = decode_raw(path)
    second, again = decode_raw(path)
    assert first.ndim == 3 and first.shape[2] == 3
    assert first.shape[0] > 100 and first.shape[1] > 100
    assert color["RawOutputBps"] == "16"
    assert color["RawDecodedWidth"] == str(first.shape[1])
    assert color["RawDecodedHeight"] == str(first.shape[0])
    assert color["ColorConversion"] == RAW_CONTRACT_ID
    assert color["RawpyVersion"]
    assert color["LibRawVersion"]
    assert color["RawWhiteBalance"] == "camera"
    assert color["RawDemosaic"] == "ahd"
    assert color["RawGamma"] == "1,1"
    assert color["RawTransfer"] == "linear_srgb_then_iec61966_2_1"
    assert color["ExifOmitted"] == "GPS,MakerNote"
    assert again == color
    np.testing.assert_array_equal(first, second)
    assert np.all(np.isfinite(first))
    assert float(first.min()) >= 0.0 and float(first.max()) <= 1.0
