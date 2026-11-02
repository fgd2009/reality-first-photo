"""Optional RAW decode through upstream rawpy. This project does not vendor LibRaw.

The raw extra installs rawpy, whose wheels load an unmodified LibRaw built by
the rawpy project (LGPL-2.1 or CDDL). Nothing here patches LibRaw or requests
its GPL demosaic packs. The numeric contract is docs/RAW_CONTRACT.md.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np

from .film.transfer import linear_to_srgb

RAW_CONTRACT_ID = "raw-linear-srgb-iec-v1"
_MISSING = (
    "RAW decode requires the optional raw extra: pip install 'reality-first-photo[raw]'. "
    "This project does not bundle or modify LibRaw."
)
_DEMOSAIC = {"linear": "LINEAR", "vng": "VNG", "ppg": "PPG", "ahd": "AHD"}
_EXIF_TAGS = (
    "Make",
    "Model",
    "DateTime",
    "ExposureTime",
    "FNumber",
    "ISOSpeedRatings",
    "FocalLength",
    "LensModel",
    "Orientation",
    "WhiteBalance",
)
_OMITTED_EXIF = "GPS,MakerNote"


def raw_decoder_available() -> bool:
    """True when import machinery can see rawpy. Does not decode a file."""
    return importlib.util.find_spec("rawpy") is not None


def decode_raw(
    path: Path,
    *,
    white_balance: str = "camera",
    wb_gains: tuple[float, float, float] | None = None,
    demosaic: str = "ahd",
    half_size: bool = False,
) -> tuple[np.ndarray, dict[str, str]]:
    """Return encoded sRGB float64 and a string-only provenance record."""
    from .io import ColorManagementError

    if not path.is_file():
        raise ColorManagementError(f"RAW file does not exist: {path}")
    if not raw_decoder_available():
        raise ColorManagementError(_MISSING)
    if demosaic not in _DEMOSAIC:
        raise ColorManagementError(
            "RAW demosaic must be ahd, linear, vng, or ppg. GPL demosaic packs are not used."
        )
    if white_balance not in {"camera", "daylight", "custom"}:
        raise ColorManagementError("RAW white balance must be camera, daylight, or custom")
    if not isinstance(half_size, bool):
        raise ColorManagementError("RAW half_size must be a bool")
    import rawpy  # type: ignore[import-untyped]

    user_wb: list[float] | None = None
    use_camera_wb = white_balance == "camera"
    if white_balance == "custom":
        if wb_gains is None:
            raise ColorManagementError("custom RAW white balance requires three R,G,B gains")
        red, green, blue = (float(wb_gains[0]), float(wb_gains[1]), float(wb_gains[2]))
        if min(red, green, blue) <= 0.0 or not all(np.isfinite([red, green, blue])):
            raise ColorManagementError("RAW white-balance gains must be finite and positive")
        user_wb = [red, green, blue, green]
    try:
        with rawpy.imread(str(path)) as raw:
            flip = int(raw.sizes.flip)
            algorithm = getattr(rawpy.DemosaicAlgorithm, _DEMOSAIC[demosaic])
            rgb16 = raw.postprocess(
                demosaic_algorithm=algorithm,
                half_size=half_size,
                four_color_rgb=False,
                fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off,
                median_filter_passes=0,
                use_camera_wb=use_camera_wb,
                use_auto_wb=False,
                user_wb=user_wb,
                output_color=rawpy.ColorSpace.sRGB,
                output_bps=16,
                user_flip=flip,
                no_auto_bright=True,
                bright=1.0,
                highlight_mode=rawpy.HighlightMode.Clip,
                gamma=(1.0, 1.0),
                no_auto_scale=False,
            )
            camera_wb = _fmt_floats(raw.camera_whitebalance)
            daylight_wb = _fmt_floats(raw.daylight_whitebalance)
            color_matrix = _fmt_floats(raw.color_matrix)
            rgb_xyz = _fmt_floats(raw.rgb_xyz_matrix)
            black_level = _fmt_floats(raw.black_level_per_channel)
            white_level = _fmt_floats(raw.white_level)
    except rawpy.LibRawError as exc:
        raise ColorManagementError(f"RAW decode failed: {exc}") from exc
    except OSError as exc:
        raise ColorManagementError(f"RAW decode failed: {exc}") from exc
    if rgb16.ndim != 3 or rgb16.shape[2] != 3 or rgb16.dtype != np.uint16:
        raise ColorManagementError("RAW decode did not return 16-bit RGB")
    linear = np.asarray(rgb16, dtype=np.float64) / 65535.0
    encoded = np.clip(linear_to_srgb(linear), 0.0, 1.0)
    preserved = technical_exif(path)
    version = getattr(rawpy, "__version__", "unknown")
    libraw = getattr(rawpy, "libraw_version", "unknown")
    from .io import _color_metadata

    color = _color_metadata(None, RAW_CONTRACT_ID, "not_applicable")
    color.update({
        "RenderingIntent": "raw_contract_not_icc",
        "RawContract": RAW_CONTRACT_ID,
        "RawpyVersion": str(version),
        "LibRawVersion": _version_text(libraw),
        "RawWhiteBalance": white_balance,
        "RawUserWb": "" if user_wb is None else _fmt_floats(user_wb),
        "RawCameraWhiteBalance": camera_wb,
        "RawDaylightWhiteBalance": daylight_wb,
        "RawOutputColor": "sRGB",
        "RawTransfer": "linear_srgb_then_iec61966_2_1",
        "RawGamma": "1,1",
        "RawOutputBps": "16",
        "RawDemosaic": demosaic,
        "RawHighlight": "Clip",
        "RawNoAutoBright": "true",
        "RawBright": "1",
        "RawNoAutoScale": "false",
        "RawHalfSize": "true" if half_size else "false",
        "RawUserFlip": str(flip),
        "RawDecodedWidth": str(encoded.shape[1]),
        "RawDecodedHeight": str(encoded.shape[0]),
        "RawColorMatrix": color_matrix,
        "RawRgbXyzMatrix": rgb_xyz,
        "RawBlackLevel": black_level,
        "RawWhiteLevel": white_level,
        "PreservedExif": json.dumps(preserved, sort_keys=True, ensure_ascii=True),
        "ExifOmitted": _OMITTED_EXIF,
    })
    return encoded, color


def technical_exif(path: Path) -> dict[str, str]:
    """TIFF/DNG technical tags only. GPS and MakerNote are not read."""
    from .io import tifffile

    if tifffile is None:
        return {}
    found: dict[str, str] = {}
    try:
        with tifffile.TiffFile(path) as handle:
            if not handle.pages:
                return {}
            tags: Any = handle.pages[0].tags
            for name in _EXIF_TAGS:
                tag = tags.get(name) if hasattr(tags, "get") else None
                if tag is None:
                    continue
                text = _format_tag(getattr(tag, "value", None))
                if text:
                    found[name] = text
    except (OSError, ValueError, RuntimeError):
        return {}
    return found


def _format_tag(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip("\x00").strip()
    if isinstance(value, str):
        return value.strip("\x00").strip()
    if isinstance(value, tuple) and value and all(isinstance(item, tuple) and len(item) == 2 for item in value):
        return ",".join(_rational(item) for item in value)
    if isinstance(value, tuple) and len(value) == 2 and all(isinstance(item, (int, float)) for item in value):
        return _rational(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return str(value).strip()


def _rational(pair: tuple[Any, ...]) -> str:
    numerator, denominator = pair
    if denominator in (0, 0.0):
        return "0"
    return f"{int(numerator)}/{int(denominator)}"


def _fmt_floats(values: object) -> str:
    flat = np.asarray(values, dtype=np.float64).reshape(-1)
    return ",".join(f"{float(item):.6g}" for item in flat)


def _version_text(value: object) -> str:
    if isinstance(value, tuple):
        return ".".join(str(part) for part in value)
    return str(value)
