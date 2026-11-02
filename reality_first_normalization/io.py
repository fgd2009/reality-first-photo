from __future__ import annotations

import hashlib
import json
import subprocess
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageCms, ImageOps

from .color import clamp01, to_uint8, to_uint16

try:
    import tifffile as _tifffile
except ImportError:  # pragma: no cover - optional dependency
    tifffile: Any = None
else:
    tifffile = _tifffile


JPEG_EXTS = {".jpg", ".jpeg"}
PNG_EXTS = {".png"}
TIFF_EXTS = {".tif", ".tiff"}
RAW_EXTS = {".arw", ".cr2", ".cr3", ".nef", ".raf", ".dng", ".rw2", ".orf", ".srw", ".pef"}
SUPPORTED_EXTS = JPEG_EXTS | PNG_EXTS | TIFF_EXTS
UNTAGGED_POLICIES = ("strict", "default_assume", "explicit")


def list_images(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() in SUPPORTED_EXTS else []
    return sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS)


def read_exif(path: Path) -> dict[str, str]:
    try:
        result = subprocess.run(
            [
                "exiftool",
                "-json",
                "-Make",
                "-Model",
                "-LensModel",
                "-ISO",
                "-ExposureTime",
                "-FNumber",
                "-FocalLength",
                "-WhiteBalance",
                "-ColorTemperature",
                str(path),
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            rows = json.loads(result.stdout)
            return {k: str(v) for k, v in rows[0].items() if k != "SourceFile"}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError, TypeError):
        return {}
    return {}


class ColorManagementError(ValueError):
    """An input cannot be safely interpreted in the fixed working color space."""


def resolve_untagged_policy(assume_srgb: bool = False, untagged_policy: str | None = None) -> str:
    """Map the public flags onto strict rejection, the default assumption, or an explicit declaration.

    ``assume_srgb=True`` remains the explicit library opt-in. Omitting both arguments stays strict
    so existing callers keep the color-contract default. The CLI passes ``default_assume`` itself.
    """
    if not isinstance(assume_srgb, bool):
        raise ValueError("assume_srgb must be a boolean")
    if untagged_policy is None:
        return "explicit" if assume_srgb else "strict"
    if untagged_policy not in UNTAGGED_POLICIES:
        raise ValueError("untagged_policy must be strict, default_assume, or explicit")
    if assume_srgb and untagged_policy != "explicit":
        raise ValueError("assume_srgb=True only allows an explicit untagged policy")
    return untagged_policy


def assumption_warning(name: str, color: dict[str, str]) -> str | None:
    """User-facing warning for the default untagged-sRGB path. Explicit declarations stay quiet."""
    if color.get("UntaggedAssumption") != "default":
        return None
    decision = color.get("ColorConversion", "default_assume_srgb")
    return (
        f"{name} has no ICC profile; assuming encoded sRGB ({decision}). "
        "Use --strict-color to reject untagged inputs."
    )


@lru_cache(maxsize=1)
def working_srgb_icc() -> bytes:
    """One generated, versioned LittleCMS sRGB profile; never a source profile."""
    path = Path(__file__).with_name("data") / "working_srgb.icc"
    if not path.is_file():
        raise ColorManagementError("Working sRGB ICC profile is missing; processing stopped.")
    return path.read_bytes()


def _color_metadata(source_icc: bytes | None, decision: str, assumption: str) -> dict[str, str]:
    return {
        "WorkingColorSpace": "sRGB encoded RGB, float32 [0,1]",
        "InputICC_SHA256": hashlib.sha256(source_icc).hexdigest() if source_icc else "none",
        "WorkingICC_SHA256": hashlib.sha256(working_srgb_icc()).hexdigest(),
        "ColorConversion": decision,
        "UntaggedAssumption": assumption,
        "RenderingIntent": "relative_colorimetric",
    }


def _untagged_rgb8(policy: str) -> tuple[str, str]:
    if policy == "strict":
        raise ColorManagementError(
            "Input has no ICC profile. Convert and tag it as sRGB in a trusted color-managed tool, "
            "or pass --assume-srgb / set assume_srgb=True only when the pixels are already encoded sRGB."
        )
    if policy == "explicit":
        return "explicit_assume_srgb_untagged_rgb8", "explicit"
    return "default_assume_srgb_untagged_rgb8", "default"


def _rgb8_to_working(im: Image.Image, source_icc: bytes | None, policy: str) -> tuple[np.ndarray, dict[str, str]]:
    if "transparency" in im.info:
        raise ColorManagementError(
            "Images with a transparency color key are unsupported. Resolve transparency explicitly before processing."
        )
    if im.mode != "RGB":
        raise ColorManagementError(
            f"Color mode {im.mode} is unsupported. Convert it to RGB with an ICC profile first."
        )
    if not source_icc:
        decision, assumption = _untagged_rgb8(policy)
        result = im
    else:
        try:
            source = ImageCms.ImageCmsProfile(BytesIO(source_icc))
            if source.profile.xcolor_space.strip() != "RGB":
                raise ColorManagementError(
                    "Input ICC profile is not an RGB profile, so it cannot be matched to RGB pixels."
                )
            converted = ImageCms.profileToProfile(
                im, source, ImageCms.ImageCmsProfile(BytesIO(working_srgb_icc())),
                renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
                outputMode="RGB",
            )
            if converted is None:
                raise ColorManagementError(
                    "Input ICC profile could not be converted to working sRGB; processing stopped."
                )
            result = converted
        except ColorManagementError:
            raise
        except Exception as exc:
            raise ColorManagementError(
                "Input ICC profile is invalid or cannot be converted to working sRGB; processing stopped."
            ) from exc
        decision, assumption = "lcms_rgb8_to_working_srgb", "none"
    return np.asarray(result).astype(np.float32) / 255.0, _color_metadata(source_icc, decision, assumption)


def resize_long_edge(arr: np.ndarray, max_long_edge: int) -> np.ndarray:
    """Resize encoded working RGB using independent float32 channels, not uint8."""
    if max_long_edge <= 0:
        return arr
    h, w = arr.shape[:2]
    long_edge = max(h, w)
    if long_edge <= max_long_edge:
        return arr
    scale = max_long_edge / long_edge
    new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
    bands = [
        np.asarray(Image.fromarray(arr[..., c].astype(np.float32)).resize(new_size, Image.Resampling.LANCZOS), dtype=np.float32)
        for c in range(3)
    ]
    return clamp01(np.stack(bands, axis=-1))


def _load_tiff(path: Path, policy: str) -> tuple[np.ndarray, dict[str, str]]:
    if tifffile is None:
        raise ColorManagementError("TIFF requires the installed tifffile dependency; refusing to fall back to 8-bit.")
    with tifffile.TiffFile(path) as tif:
        if len(tif.pages) != 1:
            raise ColorManagementError("Multi-page TIFF is unsupported.")
        page: Any = tif.pages[0]
        if int(page.compression) != 1:
            raise ColorManagementError(
                "This preview only supports uncompressed TIFF. Export uncompressed RGB TIFF first; "
                "extra decoders are not installed automatically."
            )
        if int(page.photometric) != 2 or int(page.planarconfig) != 1:
            raise ColorManagementError("Only interleaved RGB TIFF is supported.")
        orientation = page.tags.get("Orientation")
        if orientation is not None and orientation.value != 1:
            raise ColorManagementError("TIFF orientation transforms are not verified. Normalize orientation first.")
        bits = page.bitspersample
        bit_values = set(bits) if isinstance(bits, tuple) else {bits}
        dtype = page.dtype
        if dtype is None:
            raise ColorManagementError("TIFF sample dtype is missing; refusing to guess a scale.")
        kind_size = (dtype.kind, dtype.itemsize)
        expected_bits = {("u", 1): 8, ("u", 2): 16, ("f", 4): 32}.get(kind_size)
        if expected_bits is None or bit_values != {expected_bits}:
            raise ColorManagementError(
                "TIFF bit depth must be 8-bit or 16-bit integer, or 32-bit float. "
                "The scale is not guessed from the unpacked dtype."
            )
        source_icc = page.iccprofile
        data = page.asarray()
    if data.ndim != 3 or data.shape[2] != 3:
        raise ColorManagementError("Grayscale, alpha, and multi-channel TIFF are unsupported.")
    if data.dtype == np.uint8:
        return _rgb8_to_working(Image.fromarray(data), source_icc, policy)
    if data.dtype.kind not in "uf" or (data.dtype.kind == "u" and data.dtype.itemsize != 2):
        raise ColorManagementError("Only RGB 8-bit or 16-bit integer, or [0,1] float TIFF, is supported.")
    if source_icc:
        # Deliberately strict: no profile-name guess and no 16-bit -> 8-bit CMS path.
        if source_icc != working_srgb_icc():
            raise ColorManagementError(
                "High-depth TIFF ICC is not this tool's fixed working sRGB profile. "
                "Precision-preserving conversion of arbitrary ICC profiles is unavailable; convert in a trusted tool first."
            )
        decision, assumption = "exact_working_srgb_profile_high_depth_no_conversion", "none"
    elif policy == "explicit":
        decision, assumption = "explicit_assume_srgb_untagged_high_depth", "explicit"
    elif policy == "default_assume":
        decision, assumption = "default_assume_srgb_untagged_high_depth", "default"
    else:
        raise ColorManagementError(
            "High-depth TIFF has no ICC profile. Confirm encoded sRGB and pass --assume-srgb or set assume_srgb=True."
        )
    arr = data.astype(np.float32) / 65535.0 if data.dtype.kind == "u" else data.astype(np.float32)
    if not np.isfinite(arr).all() or arr.min() < 0.0 or arr.max() > 1.0:
        raise ColorManagementError(
            "The working space only accepts finite [0,1] SDR values. Unknown HDR ranges are rejected."
        )
    return arr, _color_metadata(source_icc, decision, assumption)


def load_image(path: Path, max_long_edge: int = 0, raw_half_size: bool = False, *, assume_srgb: bool = False, untagged_policy: str | None = None, read_metadata: bool = True) -> tuple[np.ndarray, dict[str, str]]:
    """Decode to encoded sRGB.

    The library default rejects untagged inputs. Pass ``assume_srgb=True`` for an explicit
    declaration, or ``untagged_policy='default_assume'`` for the CLI's warned assumption.
    Neither path accepts a corrupt or non-RGB embedded profile.
    """
    policy = resolve_untagged_policy(assume_srgb, untagged_policy)
    ext = path.suffix.lower()
    if ext in RAW_EXTS:
        raise ColorManagementError(
            "RAW is unsupported in this preview: the decode transfer curve and real RAW samples are not verified, "
            "so the file is not assumed to be sRGB."
        )
    exif = read_exif(path) if read_metadata else {}
    if ext in TIFF_EXTS:
        arr, color = _load_tiff(path, policy)
    elif ext in JPEG_EXTS | PNG_EXTS:
        if ext in PNG_EXTS:
            with path.open("rb") as f:
                header = f.read(26)
            if header[:8] != b"\x89PNG\r\n\x1a\n" or len(header) < 26 or header[24] != 8:
                raise ColorManagementError(
                    "Only 8-bit RGB PNG is supported. High-depth PNG is not silently reduced to 8-bit."
                )
        try:
            opened = Image.open(path)
        except Image.DecompressionBombError as exc:
            raise ColorManagementError("Image exceeds Pillow's safe pixel limit; reduce dimensions in a trusted image tool. The safety limit was not disabled.") from exc
        with opened:
            expected_format = "PNG" if ext in PNG_EXTS else "JPEG"
            if opened.format != expected_format:
                raise ColorManagementError(
                    "File content does not match its extension. Correct the name; the bit-depth check cannot be bypassed."
                )
            if getattr(opened, "n_frames", 1) != 1:
                raise ColorManagementError("Multi-frame images are unsupported. Export one RGB frame explicitly first.")
            source_icc = opened.info.get("icc_profile")
            transposed = ImageOps.exif_transpose(opened)
            if transposed is None:
                raise ColorManagementError("EXIF orientation could not be applied.")
            arr, color = _rgb8_to_working(transposed, source_icc, policy)
    else:
        raise ColorManagementError(f"Unsupported input format: {ext}")
    exif.update(color)
    return resize_long_edge(arr, max_long_edge), exif


def save_image(arr: np.ndarray, path: Path, jpeg_quality: int = 94, *, color_space: str = "sRGB") -> None:
    """Export working sRGB pixels; never attach an untransformed input profile.

    Contract: caller arrays use the encoded sRGB working primaries/transfer curve.
    TIFF is 16-bit; PNG/JPEG quantize to 8-bit. JPEG is also lossy.
    """
    if color_space != "sRGB":
        raise ColorManagementError("Export only accepts working sRGB. Convert pixels to that color space first.")
    if arr.ndim != 3 or arr.shape[2] != 3 or not np.isfinite(arr).all():
        raise ColorManagementError("Export requires finite HxWx3 RGB pixels.")
    profile = working_srgb_icc()
    ext = path.suffix.lower()
    if ext not in TIFF_EXTS | JPEG_EXTS | PNG_EXTS:
        raise ColorManagementError(f"Unsupported output format: {ext}")
    if ext in TIFF_EXTS and tifffile is None:
        raise ColorManagementError("16-bit TIFF export requires tifffile; refusing to fall back to 8-bit.")
    path.parent.mkdir(parents=True, exist_ok=True)
    if ext in TIFF_EXTS:
        tifffile.imwrite(path, to_uint16(arr), photometric="rgb", iccprofile=profile)
    elif ext in JPEG_EXTS:
        Image.fromarray(to_uint8(arr), "RGB").save(path, quality=jpeg_quality, subsampling=1, icc_profile=profile)
    else:
        Image.fromarray(to_uint8(arr), "RGB").save(path, icc_profile=profile)
