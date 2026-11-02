"""CIEDE2000 scaffold. The Sharma pairs check the formula; they are not a film trial."""
import json

import numpy as np
import pytest

from reality_first_normalization import io, local_cli
from reality_first_normalization.metrics.delta_e import (
    delta_e2000_lab,
    delta_e2000_srgb,
    encoded_srgb_to_lab,
    summarize_delta_e2000,
)

# Published numerical pairs for checking an implementation.
# Sharma, Wu and Dalal, Color Research & Application 30 (2005) 21–30.
# Plain-text pairs: https://hajim.rochester.edu/ece/sites/gsharma/ciede2000/
_SHARMA = """
50.0000 2.6772 -79.7751 50.0000 0.0000 -82.7485 2.0425
50.0000 3.1571 -77.2803 50.0000 0.0000 -82.7485 2.8615
50.0000 2.8361 -74.0200 50.0000 0.0000 -82.7485 3.4412
50.0000 -1.3802 -84.2814 50.0000 0.0000 -82.7485 1.0000
50.0000 -1.1848 -84.8006 50.0000 0.0000 -82.7485 1.0000
50.0000 -0.9009 -85.5211 50.0000 0.0000 -82.7485 1.0000
50.0000 0.0000 0.0000 50.0000 -1.0000 2.0000 2.3669
50.0000 -1.0000 2.0000 50.0000 0.0000 0.0000 2.3669
50.0000 2.4900 -0.0010 50.0000 -2.4900 0.0009 7.1792
50.0000 2.4900 -0.0010 50.0000 -2.4900 0.0010 7.1792
50.0000 2.4900 -0.0010 50.0000 -2.4900 0.0011 7.2195
50.0000 2.4900 -0.0010 50.0000 -2.4900 0.0012 7.2195
50.0000 -0.0010 2.4900 50.0000 0.0009 -2.4900 4.8045
50.0000 -0.0010 2.4900 50.0000 0.0010 -2.4900 4.8045
50.0000 -0.0010 2.4900 50.0000 0.0011 -2.4900 4.7461
50.0000 2.5000 0.0000 50.0000 0.0000 -2.5000 4.3065
50.0000 2.5000 0.0000 73.0000 25.0000 -18.0000 27.1492
50.0000 2.5000 0.0000 61.0000 -5.0000 29.0000 22.8977
50.0000 2.5000 0.0000 56.0000 -27.0000 -3.0000 31.9030
50.0000 2.5000 0.0000 58.0000 24.0000 15.0000 19.4535
50.0000 2.5000 0.0000 50.0000 3.1736 0.5854 1.0000
50.0000 2.5000 0.0000 50.0000 3.2972 0.0000 1.0000
50.0000 2.5000 0.0000 50.0000 1.8634 0.5757 1.0000
50.0000 2.5000 0.0000 50.0000 3.2592 0.3350 1.0000
60.2574 -34.0099 36.2677 60.4626 -34.1751 39.4387 1.2644
63.0109 -31.0961 -5.8663 62.8187 -29.7946 -4.0864 1.2630
61.2901 3.7196 -5.3901 61.4292 2.2480 -4.9620 1.8731
35.0831 -44.1164 3.7933 35.0232 -40.0716 1.5901 1.8645
22.7233 20.0904 -46.6940 23.0331 14.9730 -42.5619 2.0373
36.4612 47.8580 18.3852 36.2715 50.5065 21.2231 1.4146
90.8027 -2.0831 1.4410 91.1528 -1.6435 0.0447 1.4441
90.9257 -0.5406 -0.9208 88.6381 -0.8985 -0.7239 1.5381
6.7747 -0.2908 -2.4247 5.8714 -0.0985 -2.2286 0.6377
2.0776 0.0795 -1.1350 0.9033 -0.0636 -0.5514 0.9082
"""


def test_ciede2000_matches_published_sharma_pairs():
    rows = np.array([[float(value) for value in line.split()] for line in _SHARMA.strip().splitlines()])
    got = delta_e2000_lab(rows[:, 0:3], rows[:, 3:6])
    # The published column is rounded to 4 decimal places.
    assert np.max(np.abs(got - rows[:, 6])) < 5.1e-5
    swapped = delta_e2000_lab(rows[:, 3:6], rows[:, 0:3])
    assert np.max(np.abs(got - swapped)) < 1e-9


def test_encoded_white_is_lab_100_and_identical_images_have_zero_difference():
    lab = encoded_srgb_to_lab(np.array([1.0, 1.0, 1.0]))
    np.testing.assert_allclose(lab, [100.0, 0.0, 0.0], atol=1e-8)
    image = np.zeros((2, 3, 3))
    summary = summarize_delta_e2000(image, image)
    assert summary["pixels"] == 6
    assert summary["max"] == 0.0
    assert summary["threshold"] is None
    assert "Not a film-accuracy score" in summary["note"]
    other = np.ones((2, 3, 3))
    assert summarize_delta_e2000(image, other)["mean"] > 50.0
    assert float(np.max(delta_e2000_srgb(image, image))) == 0.0


def test_delta_e_command_prints_json_and_rejects_a_shape_mismatch(tmp_path, capsys):
    reference = tmp_path / "reference.png"
    sample = tmp_path / "sample.png"
    io.save_image(np.full((4, 6, 3), 0.2), reference)
    io.save_image(np.full((4, 6, 3), 0.8), sample)
    assert local_cli.main(["delta-e", "--reference", str(reference), "--sample", str(sample), "--json"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["pixels"] == 24
    assert summary["mean"] > 0.0
    assert summary["threshold"] is None
    captured = tmp_path / "different.png"
    io.save_image(np.full((5, 6, 3), 0.8), captured)
    assert local_cli.main(["delta-e", "--reference", str(reference), "--sample", str(captured)]) == 2


def test_summary_rejects_unequal_shapes():
    with pytest.raises(ValueError):
        summarize_delta_e2000(np.zeros((2, 2, 3)), np.zeros((3, 2, 3)))
