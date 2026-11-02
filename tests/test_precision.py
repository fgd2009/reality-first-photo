"""Precision regressions using generated floating-point pixels only."""
import numpy as np

from reality_first_normalization import io


def ramp():
    x = np.linspace(.1, .9, 4096, dtype=np.float32)
    return np.tile(x[None, :, None], (4, 1, 3))


def test_resize_retains_2048_tonal_levels():
    result = io.resize_long_edge(ramp(), 2048)
    assert result.shape == (2, 2048, 3)
    assert result.dtype == np.float32
    assert np.unique(result[..., 0]).size == 2048


def test_tiff16_retains_4096_levels_with_one_quantization(tmp_path):
    original = ramp()
    path = tmp_path / "synthetic.tif"
    io.save_image(original, path)
    result, _ = io.load_image(path, max_long_edge=0, read_metadata=False)
    assert np.unique(result[..., 0]).size == 4096
    assert np.max(np.abs(result - original)) <= 1 / 65535
