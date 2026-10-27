from __future__ import annotations

import json
import hashlib
from functools import lru_cache
from io import BytesIO
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageOps

from .color import clamp01, to_uint16, to_uint8

try:
    import tifffile
except Exception:  # pragma: no cover - optional dependency
    tifffile = None


JPEG_EXTS = {".jpg", ".jpeg"}
PNG_EXTS = {".png"}
TIFF_EXTS = {".tif", ".tiff"}
RAW_EXTS = {".arw", ".cr2", ".cr3", ".nef", ".raf", ".dng", ".rw2", ".orf", ".srw", ".pef"}
SUPPORTED_EXTS = JPEG_EXTS | PNG_EXTS | TIFF_EXTS


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
    except Exception:
        return {}
    return {}


class ColorManagementError(ValueError):
    """An input cannot be safely interpreted in the fixed working color space."""


@lru_cache(maxsize=1)
def working_srgb_icc() -> bytes:
    """One generated, versioned LittleCMS sRGB profile; never a source profile."""
    path = Path(__file__).with_name("data") / "working_srgb.icc"
    if not path.is_file():
        raise ColorManagementError("缺少工作 sRGB ICC 配置，已停止处理。")
    return path.read_bytes()


def _color_metadata(source_icc: bytes | None, decision: str) -> dict[str, str]:
    return {
        "WorkingColorSpace": "sRGB encoded RGB, float32 [0,1]",
        "InputICC_SHA256": hashlib.sha256(source_icc).hexdigest() if source_icc else "none",
        "WorkingICC_SHA256": hashlib.sha256(working_srgb_icc()).hexdigest(),
        "ColorConversion": decision,
        "RenderingIntent": "relative_colorimetric",
    }


def _rgb8_to_working(im: Image.Image, source_icc: bytes | None, assume_srgb: bool) -> tuple[np.ndarray, dict[str, str]]:
    if "transparency" in im.info:
        raise ColorManagementError("暂不支持带透明色键的图像；请先明确处理透明度。")
    if im.mode != "RGB":
        raise ColorManagementError(f"暂不支持 {im.mode} 色彩模式；请先显式转换成带 ICC 的 RGB。")
    if not source_icc:
        if not assume_srgb:
            raise ColorManagementError("输入缺少 ICC；请先在可信色彩管理工具中转换并标记 sRGB，或在已确认像素为 sRGB 时显式设置 assume_srgb=True。")
        result = im
        decision = "explicit_assume_srgb_untagged_rgb8"
    else:
        try:
            source = ImageCms.ImageCmsProfile(BytesIO(source_icc))
            if source.profile.xcolor_space.strip() != "RGB":
                raise ColorManagementError("输入 ICC 不是 RGB 配置，不能与 RGB 像素匹配。")
            result = ImageCms.profileToProfile(
                im, source, ImageCms.ImageCmsProfile(BytesIO(working_srgb_icc())),
                renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
                outputMode="RGB",
            )
        except ColorManagementError:
            raise
        except Exception as exc:
            raise ColorManagementError("输入 ICC 无效或无法转换到工作 sRGB；已停止处理。") from exc
        decision = "lcms_rgb8_to_working_srgb"
    return np.asarray(result).astype(np.float32) / 255.0, _color_metadata(source_icc, decision)


def resize_long_edge(arr: np.ndarray, max_long_edge: int) -> np.ndarray:
    """Resize encoded working RGB using independent float32 channels, not uint8."""
    if max_long_edge <= 0:
        return arr
    h, w = arr.shape[:2]
    long_edge = max(h, w)
    if long_edge <= max_long_edge:
        return arr
    scale = max_long_edge / long_edge
    new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
    bands = [
        np.asarray(Image.fromarray(arr[..., c].astype(np.float32)).resize(new_size, Image.Resampling.LANCZOS), dtype=np.float32)
        for c in range(3)
    ]
    return clamp01(np.stack(bands, axis=-1))


def _load_tiff(path: Path, assume_srgb: bool) -> tuple[np.ndarray, dict[str, str]]:
    if tifffile is None:
        raise ColorManagementError("TIFF 需要现有 tifffile 依赖；不允许静默降为 8 位。")
    with tifffile.TiffFile(path) as tif:
        if len(tif.pages) != 1:
            raise ColorManagementError("暂不支持多页 TIFF。")
        page = tif.pages[0]
        if int(page.compression) != 1:
            raise ColorManagementError("当前预览仅支持未压缩 TIFF；请先导出为未压缩 RGB TIFF，不会自动安装额外解码器。")
        if int(page.photometric) != 2 or int(page.planarconfig) != 1:
            raise ColorManagementError("仅支持逐像素排列的 RGB TIFF。")
        orientation = page.tags.get("Orientation")
        if orientation is not None and orientation.value != 1:
            raise ColorManagementError("TIFF 方向变换尚未验证；请先规范化方向。")
        bits = page.bitspersample
        bit_values = set(bits) if isinstance(bits, tuple) else {bits}
        kind_size = (page.dtype.kind, page.dtype.itemsize)
        expected_bits = {("u", 1): 8, ("u", 2): 16, ("f", 4): 32}.get(kind_size)
        if expected_bits is None or bit_values != {expected_bits}:
            raise ColorManagementError("TIFF 实际位深仅支持 8/16 位整数或 32 位浮点；不按解包后的 dtype 猜测比例。")
        source_icc = page.iccprofile
        data = page.asarray()
    if data.ndim != 3 or data.shape[2] != 3:
        raise ColorManagementError("暂不支持灰度、Alpha 或多通道 TIFF。")
    if data.dtype == np.uint8:
        return _rgb8_to_working(Image.fromarray(data), source_icc, assume_srgb)
    if data.dtype.kind not in "uf" or (data.dtype.kind == "u" and data.dtype.itemsize != 2):
        raise ColorManagementError("仅支持 RGB 8/16 位整数或 [0,1] 浮点 TIFF。")
    if source_icc:
        # Deliberately strict: no profile-name guess and no 16-bit -> 8-bit CMS path.
        if source_icc != working_srgb_icc():
            raise ColorManagementError("高位深 TIFF 的 ICC 不是本工具固定工作 sRGB；当前不支持保持精度的任意 ICC 转换，请先在可信工具中转换。")
        decision = "exact_working_srgb_profile_high_depth_no_conversion"
    elif assume_srgb:
        decision = "explicit_assume_srgb_untagged_high_depth"
    else:
        raise ColorManagementError("高位深 TIFF 缺少 ICC；必须确认 sRGB 并显式设置 assume_srgb=True。")
    arr = data.astype(np.float32) / 65535.0 if data.dtype.kind == "u" else data.astype(np.float32)
    if not np.isfinite(arr).all() or arr.min() < 0.0 or arr.max() > 1.0:
        raise ColorManagementError("当前工作空间仅支持有限的 [0,1] SDR 数据，不接受未知 HDR 范围。")
    return arr, _color_metadata(source_icc, decision)


def load_image(path: Path, max_long_edge: int = 0, raw_half_size: bool = False, *, assume_srgb: bool = False, read_metadata: bool = True) -> tuple[np.ndarray, dict[str, str]]:
    """Decode to encoded sRGB. Untagged or unsupported inputs fail unless explicitly handled."""
    ext = path.suffix.lower()
    if ext in RAW_EXTS:
        raise ColorManagementError("当前恢复预览暂不支持 RAW：需先验证解码传递曲线和真实 RAW 样本，不能直接假设为 sRGB。")
    exif = read_exif(path) if read_metadata else {}
    if ext in TIFF_EXTS:
        arr, color = _load_tiff(path, assume_srgb)
    elif ext in JPEG_EXTS | PNG_EXTS:
        if ext in PNG_EXTS:
            with path.open("rb") as f:
                header = f.read(26)
            if header[:8] != b"\x89PNG\r\n\x1a\n" or len(header) < 26 or header[24] != 8:
                raise ColorManagementError("仅支持 8 位 RGB PNG；高位深 PNG 不允许静默降为 8 位。")
        with Image.open(path) as opened:
            expected_format = "PNG" if ext in PNG_EXTS else "JPEG"
            if opened.format != expected_format:
                raise ColorManagementError("文件内容格式与扩展名不一致；请先更正名称，不能绕过位深检查。")
            if getattr(opened, "n_frames", 1) != 1:
                raise ColorManagementError("暂不支持多帧图像；请先明确导出单帧 RGB 图像。")
            source_icc = opened.info.get("icc_profile")
            im = ImageOps.exif_transpose(opened)
            arr, color = _rgb8_to_working(im, source_icc, assume_srgb)
    else:
        raise ColorManagementError(f"不支持的输入格式：{ext}")
    exif.update(color)
    return resize_long_edge(arr, max_long_edge), exif


def save_image(arr: np.ndarray, path: Path, jpeg_quality: int = 94, *, color_space: str = "sRGB") -> None:
    """Export working sRGB pixels; never attach an untransformed input profile.

    Contract: caller arrays use the encoded sRGB working primaries/transfer curve.
    TIFF is 16-bit; PNG/JPEG quantize to 8-bit. JPEG is also lossy.
    """
    if color_space != "sRGB":
        raise ColorManagementError("导出只接受工作 sRGB；请先执行明确的像素色域转换。")
    if arr.ndim != 3 or arr.shape[2] != 3 or not np.isfinite(arr).all():
        raise ColorManagementError("导出需要有限的 HxWx3 RGB 像素。")
    profile = working_srgb_icc()
    ext = path.suffix.lower()
    if ext not in TIFF_EXTS | JPEG_EXTS | PNG_EXTS:
        raise ColorManagementError(f"不支持的输出格式：{ext}")
    if ext in TIFF_EXTS and tifffile is None:
        raise ColorManagementError("16 位 TIFF 导出需要 tifffile；不会降为 8 位。")
    path.parent.mkdir(parents=True, exist_ok=True)
    if ext in TIFF_EXTS:
        tifffile.imwrite(path, to_uint16(arr), photometric="rgb", iccprofile=profile)
    elif ext in JPEG_EXTS:
        Image.fromarray(to_uint8(arr), "RGB").save(path, quality=jpeg_quality, subsampling=1, icc_profile=profile)
    else:
        Image.fromarray(to_uint8(arr), "RGB").save(path, icc_profile=profile)
