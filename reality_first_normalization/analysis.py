from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .color import EPSILON, luminance, saturation_rgb
from .regions import RegionMasks, detect_regions, summarize_regions


@dataclass(frozen=True)
class ImageAnalysis:
    metrics: dict[str, float | str | list[float] | dict[str, float]]
    masks: RegionMasks


def _risk(value: float, low: float, high: float) -> float:
    if value <= low:
        return 0.0
    if value >= high:
        return 1.0
    return float((value - low) / (high - low))


def estimate_scene_neutral(arr: np.ndarray, masks: RegionMasks) -> np.ndarray:
    lum = luminance(arr)
    sat = saturation_rgb(arr)
    bright_neutral = (lum >= np.percentile(lum, 55)) & (lum <= 0.94) & (sat <= np.percentile(sat, 45))
    candidate = masks.neutral | bright_neutral
    if np.count_nonzero(candidate) < max(32, arr.shape[0] * arr.shape[1] * 0.002):
        candidate = (lum >= np.percentile(lum, 30)) & (lum <= np.percentile(lum, 92)) & (sat <= np.percentile(sat, 35))
    if not np.any(candidate):
        return arr.reshape(-1, 3).mean(axis=0)
    return arr[candidate].mean(axis=0)


def _skin_tone_bias(skin_region: dict) -> str:
    if float(skin_region.get("pixel_ratio", 0.0)) <= 0.001:
        return "not_detected"
    r, g, b = skin_region.get("mean_rgb", [0.0, 0.0, 0.0])
    sat = float(skin_region.get("saturation_mean", 0.0))
    if sat < 0.075:
        return "gray"
    if g - (r + b) / 2.0 > 0.035:
        return "green"
    if r - g > 0.105:
        return "red"
    if (r + g) / 2.0 - b > 0.115 and abs(r - g) <= 0.105:
        return "yellow"
    return "natural"


def _masked_luma_range(arr: np.ndarray, mask: np.ndarray) -> list[float]:
    if not np.any(mask):
        return [0.0, 0.0]
    values = luminance(arr)[mask]
    return [float(np.percentile(values, 5)), float(np.percentile(values, 95))]


def _scene_preservation_score(metrics: dict[str, float | str | list[float] | dict]) -> float:
    warmth = abs(float(metrics["temperature_tendency_score"]))
    neutral_ratio = float(metrics["neutral_region"]["pixel_ratio"])
    skin_ratio = float(metrics["skin_region"]["pixel_ratio"])
    sky_ratio = float(metrics["sky_region"]["pixel_ratio"])
    atmosphere_signal = min(1.0, warmth / 0.10)
    subject_signal = min(1.0, skin_ratio / 0.08) * 0.35 + min(1.0, sky_ratio / 0.18) * 0.20
    low_neutral_signal = 1.0 - min(1.0, neutral_ratio / 0.16)
    return float(np.clip(0.25 + 0.40 * atmosphere_signal + 0.20 * low_neutral_signal + subject_signal, 0.0, 1.0))


def analyze_image(arr: np.ndarray) -> ImageAnalysis:
    masks = detect_regions(arr)
    lum = luminance(arr)
    sat = saturation_rgb(arr)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    max_rgb = arr.max(axis=2)
    min_rgb = arr.min(axis=2)

    neutral_rgb = estimate_scene_neutral(arr, masks)
    neutral_gray = float(neutral_rgb.mean())
    neutral_error = neutral_rgb - neutral_gray
    warmth = float(neutral_rgb[0] - neutral_rgb[2])
    green_cast = float(neutral_rgb[1] - (neutral_rgb[0] + neutral_rgb[2]) / 2.0)

    p01 = float(np.percentile(lum, 1))
    p05 = float(np.percentile(lum, 5))
    p50 = float(np.percentile(lum, 50))
    p95 = float(np.percentile(lum, 95))
    p99 = float(np.percentile(lum, 99))
    clipped_channels = (arr >= 0.995).any(axis=2)
    shadow_channels = (arr <= 0.005).all(axis=2)
    highlight_clip_pct = float(((lum >= 0.985) | clipped_channels).mean() * 100.0)
    shadow_clip_pct = float(((lum <= 0.012) | shadow_channels).mean() * 100.0)

    exposure_stops_from_target = float(np.log2(max(p50, EPSILON) / 0.46))
    dynamic_range_stops = float(np.log2((p99 + 0.01) / max(p01 + 0.01, EPSILON)))
    highlight_risk = max(_risk(highlight_clip_pct, 0.05, 2.0), _risk(p99, 0.94, 0.995))
    shadow_risk = max(_risk(shadow_clip_pct, 0.15, 4.0), _risk(0.035 - p05, 0.0, 0.035))

    region_metrics = summarize_regions(arr, masks)
    skin_region = region_metrics["skin_region"]
    sky_region = region_metrics["sky_region"]
    vegetation_region = region_metrics["vegetation_region"]

    skin_luma_range = _masked_luma_range(arr, masks.skin)
    sky_saturation_risk = 0.0
    if float(sky_region["pixel_ratio"]) > 0.005:
        sky_saturation_risk = max(
            _risk(float(sky_region["saturation_mean"]), 0.34, 0.62),
            _risk(float(sky_region["mean_hsv"][0]), 0.64, 0.70),
        )
    vegetation_neon_risk = 0.0
    if float(vegetation_region["pixel_ratio"]) > 0.005:
        g_cast = float(vegetation_region["green_cast_g_minus_avg_rb"])
        vegetation_neon_risk = max(
            _risk(float(vegetation_region["saturation_mean"]), 0.28, 0.58),
            _risk(g_cast, 0.12, 0.32),
        )

    metrics: dict[str, float | str | list[float] | dict[str, float]] = {
        "exposure_luma_mean": float(lum.mean()),
        "exposure_luma_p01": p01,
        "exposure_luma_p05": p05,
        "exposure_luma_p50": p50,
        "exposure_luma_p95": p95,
        "exposure_luma_p99": p99,
        "exposure_stops_from_target": exposure_stops_from_target,
        "white_point_rgb": [float(v) for v in neutral_rgb],
        "white_point_balance_error_rgb": [float(v) for v in neutral_error],
        "black_point_luma_p01": p01,
        "black_point_luma_p05": p05,
        "temperature_tendency_score": warmth,
        "temperature_tendency": "warm" if warmth > 0.025 else "cool" if warmth < -0.025 else "neutral",
        "color_cast_green_magenta_score": green_cast,
        "color_cast_tendency": "green" if green_cast > 0.018 else "magenta" if green_cast < -0.018 else "neutral",
        "dynamic_range_luma_span": float(p99 - p01),
        "dynamic_range_stops_estimate": dynamic_range_stops,
        "saturation_mean": float(sat.mean()),
        "saturation_p50": float(np.percentile(sat, 50)),
        "saturation_p95": float(np.percentile(sat, 95)),
        "rgb_channel_means": [float(r.mean()), float(g.mean()), float(b.mean())],
        "rgb_channel_minmax_gap_mean": float((max_rgb - min_rgb).mean()),
        "highlight_clip_pct": highlight_clip_pct,
        "shadow_clip_pct": shadow_clip_pct,
        "highlight_overflow_risk": float(highlight_risk),
        "shadow_crush_risk": float(shadow_risk),
        **region_metrics,
        "skin_tone_bias": _skin_tone_bias(skin_region),
        "skin_luma_range": skin_luma_range,
        "sky_saturation_risk": float(np.clip(sky_saturation_risk, 0.0, 1.0)),
        "vegetation_neon_risk": float(np.clip(vegetation_neon_risk, 0.0, 1.0)),
        "highlight_rolloff_need": float(np.clip(highlight_risk, 0.0, 1.0)),
        "shadow_lift_need": float(np.clip(shadow_risk, 0.0, 1.0)),
    }
    metrics["atmosphere_preservation_score"] = _scene_preservation_score(metrics)
    metrics["normalization_difficulty_score"] = float(
        np.clip(
            0.22 * abs(exposure_stops_from_target)
            + 0.22 * highlight_risk
            + 0.18 * shadow_risk
            + 0.15 * float(metrics["sky_saturation_risk"])
            + 0.15 * float(metrics["vegetation_neon_risk"])
            + 0.08 * min(1.0, abs(green_cast) / 0.06),
            0.0,
            1.0,
        )
    )
    return ImageAnalysis(metrics=metrics, masks=masks)
