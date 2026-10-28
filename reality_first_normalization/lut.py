from __future__ import annotations

import hashlib
import shlex
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .color import clamp01


@dataclass(frozen=True)
class CubeLut:
    path: str
    title: str
    size: int
    table: np.ndarray
    domain_min: tuple[float, float, float]
    domain_max: tuple[float, float, float]
    source_sha256: str = ""


def resolve_asset_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return Path(__file__).resolve().parents[1] / p


def load_cube_lut(path: str) -> CubeLut:
    lut_path = resolve_asset_path(path)
    if not lut_path.exists():
        raise FileNotFoundError(f"CUBE LUT not found: {lut_path}")

    title = lut_path.stem
    size: int | None = None
    domain_min = (0.0, 0.0, 0.0)
    domain_max = (1.0, 1.0, 1.0)
    rows: list[list[float]] = []

    try:
        source_bytes = lut_path.read_bytes()
        lines = source_bytes.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("CUBE must contain valid UTF-8 text") from exc
    declarations: set[str] = set()
    header_fields = {"TITLE": 2, "LUT_3D_SIZE": 2, "DOMAIN_MIN": 4, "DOMAIN_MAX": 4}
    for line_number, line in enumerate(lines, start=1):
        try:
            # Keep # inside quoted titles, but allow comments after a declaration
            # or table row. Unknown directives must never change the LUT silently.
            parts = shlex.split(line, comments=True, posix=True)
        except ValueError as exc:
            raise ValueError(f"Invalid CUBE quoting on line {line_number}") from exc
        if not parts:
            continue
        key = parts[0].upper()
        if key in header_fields:
            if rows:
                raise ValueError(f"CUBE declaration {key} appears after table rows on line {line_number}")
            if key in declarations:
                raise ValueError(f"Duplicate CUBE declaration {key} on line {line_number}")
            if len(parts) != header_fields[key]:
                raise ValueError(f"Invalid field count for CUBE {key} on line {line_number}")
            declarations.add(key)
        if key == "TITLE":
            title = parts[1]
        elif key == "LUT_3D_SIZE":
            size = int(parts[1])
        elif key == "DOMAIN_MIN":
            domain_min = (float(parts[1]), float(parts[2]), float(parts[3]))
        elif key == "DOMAIN_MAX":
            domain_max = (float(parts[1]), float(parts[2]), float(parts[3]))
        else:
            try:
                float(parts[0])
            except ValueError as exc:
                raise ValueError(f"Unsupported CUBE directive {parts[0]} on line {line_number}") from exc
            if len(parts) != 3:
                raise ValueError(f"CUBE table rows need exactly three values on line {line_number}")
            try:
                rows.append([float(value) for value in parts])
            except ValueError as exc:
                raise ValueError(f"Invalid CUBE table value on line {line_number}") from exc

    if size is None:
        raise ValueError(f"CUBE LUT missing LUT_3D_SIZE: {lut_path}")
    if not 2 <= size <= 256:
        raise ValueError("LUT_3D_SIZE must be between 2 and 256")
    if not np.all(np.isfinite(domain_min + domain_max)) or np.any(np.asarray(domain_max) <= np.asarray(domain_min)):
        raise ValueError("CUBE DOMAIN_MAX must be finite and greater than DOMAIN_MIN")
    expected = size**3
    if len(rows) != expected:
        raise ValueError(f"CUBE LUT {lut_path} has {len(rows)} rows, expected {expected}")

    # Adobe Cube specification 1.0 section 7.2: flat index r + N*g + N*N*b.
    # File layout is [b, g, r, channel]; the interpolator uses [r, g, b, channel].
    table = np.asarray(rows, dtype=np.float32).reshape(size, size, size, 3).transpose(2, 1, 0, 3)
    if not np.all(np.isfinite(table)):
        raise ValueError("CUBE table contains non-finite values")
    if np.any(table < 0.0) or np.any(table > 1.0):
        raise ValueError("This SDR preview requires CUBE output nodes in [0,1]; HDR/extended-range tables are unsupported")
    return CubeLut(
        path=str(lut_path),
        title=title,
        size=size,
        table=table,
        domain_min=domain_min,
        domain_max=domain_max,
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
    )


def apply_cube_lut(arr: np.ndarray, lut: CubeLut) -> np.ndarray:
    # Use the actual finite domain width; an epsilon floor changes narrow LUTs.
    img = arr.astype(np.float64, copy=False)
    dmin = np.asarray(lut.domain_min, dtype=np.float64).reshape(1, 1, 3)
    dmax = np.asarray(lut.domain_max, dtype=np.float64).reshape(1, 1, 3)
    width = dmax - dmin
    if not np.isfinite(width).all() or np.any(width <= 0):
        raise ValueError("CUBE domain width must be finite and positive")
    coords = np.clip((img - dmin) / width, 0.0, 1.0) * (lut.size - 1)

    r = coords[..., 0]
    g = coords[..., 1]
    b = coords[..., 2]
    r0 = np.floor(r).astype(np.int32)
    g0 = np.floor(g).astype(np.int32)
    b0 = np.floor(b).astype(np.int32)
    r1 = np.minimum(r0 + 1, lut.size - 1)
    g1 = np.minimum(g0 + 1, lut.size - 1)
    b1 = np.minimum(b0 + 1, lut.size - 1)

    rd = (r - r0)[..., None]
    gd = (g - g0)[..., None]
    bd = (b - b0)[..., None]
    t = lut.table

    c000 = t[r0, g0, b0]
    c001 = t[r0, g0, b1]
    c010 = t[r0, g1, b0]
    c011 = t[r0, g1, b1]
    c100 = t[r1, g0, b0]
    c101 = t[r1, g0, b1]
    c110 = t[r1, g1, b0]
    c111 = t[r1, g1, b1]

    c00 = c000 * (1.0 - bd) + c001 * bd
    c01 = c010 * (1.0 - bd) + c011 * bd
    c10 = c100 * (1.0 - bd) + c101 * bd
    c11 = c110 * (1.0 - bd) + c111 * bd
    c0 = c00 * (1.0 - gd) + c01 * gd
    c1 = c10 * (1.0 - gd) + c11 * gd
    return clamp01(c0 * (1.0 - rd) + c1 * rd)
