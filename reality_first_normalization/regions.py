from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .color import luminance, rgb_to_hsv, saturation_rgb


@dataclass(frozen=True)
class RegionMasks:
    skin: np.ndarray
    sky: np.ndarray
    vegetation: np.ndarray
    neutral: np.ndarray
    highlight: np.ndarray
    shadow: np.ndarray


def detect_regions(arr: np.ndarray) -> RegionMasks:
    hsv = rgb_to_hsv(arr)
    hue = hsv[..., 0]
    sat = hsv[..., 1]
    val = hsv[..., 2]
    lum = luminance(arr)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    chroma = saturation_rgb(arr)

    highlight = (lum >= 0.94) | (arr.max(axis=2) >= 0.985)
    shadow = (lum <= 0.045) | (arr.max(axis=2) <= 0.035)

    skin_hue = (hue >= 0.015) & (hue <= 0.155)
    skin_balance = (r > b * 1.04) & (g > b * 0.70) & (r >= g * 0.88)
    skin = skin_hue & skin_balance & (sat >= 0.09) & (sat <= 0.68) & (lum >= 0.16) & (lum <= 0.90)
    skin &= ~highlight & ~shadow

    sky_hue = (hue >= 0.50) & (hue <= 0.67)
    sky = sky_hue & (sat >= 0.08) & (sat <= 0.86) & (val >= 0.25) & (b > r * 1.04) & (b >= g * 0.92)
    sky &= ~shadow

    vegetation_hue = (hue >= 0.18) & (hue <= 0.46)
    vegetation = vegetation_hue & (sat >= 0.12) & (val >= 0.12) & (g > r * 0.90) & (g > b * 0.88)
    vegetation &= ~highlight & ~shadow

    neutral = (chroma <= 0.08) & (sat <= 0.14) & (lum >= 0.12) & (lum <= 0.96)
    neutral &= ~shadow
    return RegionMasks(skin=skin, sky=sky, vegetation=vegetation, neutral=neutral, highlight=highlight, shadow=shadow)


def _confidence(pixel_ratio: float, sat_mean: float, luma_mean: float, region_name: str) -> float:
    coverage_score = min(1.0, pixel_ratio / 0.08)
    if region_name == "neutral":
        quality = 1.0 - min(1.0, sat_mean / 0.16)
    elif region_name == "highlight":
        quality = min(1.0, max(0.0, (luma_mean - 0.88) / 0.12))
    elif region_name == "shadow":
        quality = min(1.0, max(0.0, (0.12 - luma_mean) / 0.12))
    else:
        quality = min(1.0, sat_mean / 0.22)
    return float(np.clip(0.35 * coverage_score + 0.65 * quality, 0.0, 1.0))


def region_summary(arr: np.ndarray, mask: np.ndarray, region_name: str = "region") -> dict[str, float | list[float]]:
    pixel_ratio = float(mask.mean())
    coverage = float(pixel_ratio * 100.0)
    if not np.any(mask):
        return {
            "pixel_ratio": pixel_ratio,
            "coverage_pct": coverage,
            "mean_rgb": [0.0, 0.0, 0.0],
            "mean_hsv": [0.0, 0.0, 0.0],
            "luma_mean": 0.0,
            "saturation_mean": 0.0,
            "confidence": 0.0,
            "warmth_r_minus_b": 0.0,
            "green_cast_g_minus_avg_rb": 0.0,
        }
    pixels = arr[mask]
    lum = luminance(pixels.reshape(-1, 1, 3)).reshape(-1)
    sat = saturation_rgb(pixels.reshape(-1, 1, 3)).reshape(-1)
    hsv = rgb_to_hsv(pixels.reshape(-1, 1, 3)).reshape(-1, 3)
    r_mean, g_mean, b_mean = pixels.mean(axis=0)
    luma_mean = float(lum.mean())
    sat_mean = float(sat.mean())
    return {
        "pixel_ratio": pixel_ratio,
        "coverage_pct": coverage,
        "mean_rgb": [float(r_mean), float(g_mean), float(b_mean)],
        "mean_hsv": [float(v) for v in hsv.mean(axis=0)],
        "luma_mean": luma_mean,
        "saturation_mean": sat_mean,
        "confidence": _confidence(pixel_ratio, sat_mean, luma_mean, region_name),
        "warmth_r_minus_b": float(r_mean - b_mean),
        "green_cast_g_minus_avg_rb": float(g_mean - (r_mean + b_mean) / 2.0),
    }


def summarize_regions(arr: np.ndarray, masks: RegionMasks) -> dict[str, dict[str, float | list[float]]]:
    return {
        "skin_region": region_summary(arr, masks.skin, "skin"),
        "sky_region": region_summary(arr, masks.sky, "sky"),
        "vegetation_region": region_summary(arr, masks.vegetation, "vegetation"),
        "neutral_region": region_summary(arr, masks.neutral, "neutral"),
        "highlight_region": region_summary(arr, masks.highlight, "highlight"),
        "shadow_region": region_summary(arr, masks.shadow, "shadow"),
    }
