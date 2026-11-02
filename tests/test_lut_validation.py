"""Reject ambiguous CUBE syntax instead of silently changing the user's look."""
import numpy as np
import pytest

from reality_first_normalization.lut import apply_cube_lut, load_cube_lut

IDENTITY_ROWS = "\n".join(
    f"{r} {g} {b}" for b in (0, 1) for g in (0, 1) for r in (0, 1)
)


@pytest.mark.parametrize("directive", [
    "LUT_3D_INPUT_RANGE 0.1 0.9",
    "LUT_1D_SIZE 2",
    "LUT_1D_INPUT_RANGE 0 1",
    "UNKNOWN_METADATA ignored",
])
def test_unsupported_directives_do_not_silently_use_default_domain(tmp_path, directive):
    path = tmp_path / "unsupported.cube"
    path.write_text(f"LUT_3D_SIZE 2\n{directive}\n{IDENTITY_ROWS}\n")
    with pytest.raises(ValueError, match="Unsupported CUBE directive"):
        load_cube_lut(str(path))


@pytest.mark.parametrize("declaration", [
    "TITLE",
    'TITLE "one" "two"',
    "LUT_3D_SIZE",
    "LUT_3D_SIZE 2 extra",
    "DOMAIN_MIN 0 0",
    "DOMAIN_MAX 1 1 1 extra",
])
def test_malformed_declarations_are_not_ignored(tmp_path, declaration):
    path = tmp_path / "malformed.cube"
    header = "" if declaration.startswith("LUT_3D_SIZE") else "LUT_3D_SIZE 2\n"
    path.write_text(f"{header}{declaration}\n{IDENTITY_ROWS}\n")
    with pytest.raises(ValueError, match="Invalid field count"):
        load_cube_lut(str(path))


@pytest.mark.parametrize("declaration", [
    'TITLE "test"', "LUT_3D_SIZE 2", "DOMAIN_MIN 0 0 0", "DOMAIN_MAX 1 1 1",
])
def test_duplicate_declarations_are_rejected(tmp_path, declaration):
    path = tmp_path / "duplicate.cube"
    header = "" if declaration.startswith("LUT_3D_SIZE") else "LUT_3D_SIZE 2\n"
    path.write_text(f"{header}{declaration}\n{declaration}\n{IDENTITY_ROWS}\n")
    with pytest.raises(ValueError, match="Duplicate CUBE declaration"):
        load_cube_lut(str(path))


@pytest.mark.parametrize("row", ["0 0", "0 0 0 9", "0 invalid 0"])
def test_malformed_table_rows_are_not_truncated_or_skipped(tmp_path, row):
    path = tmp_path / "bad-row.cube"
    path.write_text(f"LUT_3D_SIZE 2\n{row}\n{IDENTITY_ROWS}\n")
    with pytest.raises(ValueError, match="CUBE table"):
        load_cube_lut(str(path))


def test_corrupt_encoding_is_rejected(tmp_path):
    path = tmp_path / "bad-encoding.cube"
    path.write_bytes(b'LUT_3D_SIZE 2\nTITLE "bad\xfftext"\n' + IDENTITY_ROWS.encode())
    with pytest.raises(ValueError, match="UTF-8"):
        load_cube_lut(str(path))


def test_declarations_after_table_rows_are_rejected(tmp_path):
    path = tmp_path / "late-domain.cube"
    path.write_text(f"LUT_3D_SIZE 2\n{IDENTITY_ROWS}\nDOMAIN_MIN 0 0 0\n")
    with pytest.raises(ValueError, match="after table rows"):
        load_cube_lut(str(path))


def test_unterminated_title_is_rejected(tmp_path):
    path = tmp_path / "bad-title.cube"
    path.write_text(f'LUT_3D_SIZE 2\nTITLE "unfinished\n{IDENTITY_ROWS}\n')
    with pytest.raises(ValueError, match="quoting"):
        load_cube_lut(str(path))


def test_standard_whitespace_titles_and_inline_comments_preserve_domain(tmp_path):
    path = tmp_path / "comments.cube"
    path.write_text(
        '\n # generated identity with a non-default input domain\n'
        'TITLE\t"Identity # domain" # outside title\n'
        'LUT_3D_SIZE\t2 # red changes fastest\n'
        'DOMAIN_MIN .1 .1 .1\nDOMAIN_MAX .9 .9 .9\n'
        + "\n".join(row + " # node" for row in IDENTITY_ROWS.splitlines()) + "\n"
    )
    lut = load_cube_lut(str(path))
    assert lut.title == "Identity # domain"
    pixels = np.array([[[.1, .3, .9], [.9, .1, .5]]], dtype=np.float32)
    np.testing.assert_allclose(apply_cube_lut(pixels, lut), (pixels - .1) / .8, atol=1e-7)
