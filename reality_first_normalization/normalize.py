from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .analysis import ImageAnalysis
from .ai.safety_clamps import CLAMPS, local_fallback_advice
from .color import EPSILON, adjust_saturation, apply_channel_gains, blend, clamp01, luminance
from .style_profiles import load_style_profile


@dataclass(frozen=True)
class NormalizationResult:
    image: np.ndarray
    operations: dict


DEFAULT_NORMALIZATION_STRATEGY = {
    key: value
    for key, value in local_fallback_advice()["recommended_normalization"].items()
    if key in CLAMPS
}


def _safe_strategy(normalization_strategy: dict | None) -> tuple[dict[str, float], str, list[str]]:
    strategy = dict(DEFAULT_NORMALIZATION_STRATEGY)
    warnings: list[str] = []
    source = "local_default_strategy"
    if not isinstance(normalization_strategy, dict) or not normalization_strategy:
        return strategy, source, warnings
    source = str(normalization_strategy.get("intent", "ai_or_local_advisor_strategy"))
    for key, default in DEFAULT_NORMALIZATION_STRATEGY.items():
        value = normalization_strategy.get(key, default)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = float(default)
            warnings.append(f"{key} 非法，使用本地安全默认值")
        low, high = CLAMPS[key]
        clamped = min(high, max(low, numeric))
        if clamped != numeric:
            warnings.append(f"{key} 已在 normalize 执行层夹逼到安全范围")
        strategy[key] = float(clamped)
    return strategy, source, warnings


def compute_white_balance_gains(white_point_rgb: list[float], strength: float, max_shift: float = 0.10) -> np.ndarray:
    wp = np.asarray(white_point_rgb, dtype=np.float32)
    gray = float(wp.mean())
    raw = gray / np.maximum(wp, EPSILON)
    limited = np.clip(raw, 1.0 - max_shift, 1.0 + max_shift)
    return 1.0 + (limited - 1.0) * float(np.clip(strength, 0.0, 1.0))


def exposure_scale_from_analysis(metrics: dict, strength: float) -> float:
    p50 = float(metrics["exposure_luma_p50"])
    p99 = float(metrics["exposure_luma_p99"])
    target = float(metrics.get("_style_tone_target_midtone", 0.46))
    scale = target / max(p50, EPSILON)
    scale = float(np.clip(scale, 0.78, 1.28))
    if p99 * scale > 0.965:
        scale = min(scale, 0.965 / max(p99, EPSILON))
    if float(metrics["highlight_overflow_risk"]) > 0.35:
        scale = min(scale, 0.99)
    return float(1.0 + (scale - 1.0) * np.clip(strength, 0.0, 1.0))


def highlight_rolloff(arr: np.ndarray, start: float = 0.76, amount: float = 0.45) -> np.ndarray:
    out = arr.copy()
    mask = out > start
    if not np.any(mask):
        return out
    x = out[mask]
    curve = start + (1.0 - start) * (
        1.0 - np.exp(-((x - start) / max(1.0 - start, EPSILON)) * (1.0 + amount))
    ) / (1.0 - math.exp(-(1.0 + amount)))
    out[mask] = np.minimum(x, curve)
    return clamp01(out)


def lift_shadows_safely(arr: np.ndarray, amount: float) -> np.ndarray:
    if amount <= 0:
        return arr
    lum = luminance(arr)[..., None]
    lift = amount * (1.0 - lum) ** 2
    return clamp01(arr + lift * (1.0 - arr))


def saturation_gain_from_analysis(metrics: dict, strength: float) -> float:
    sat_mean = float(metrics["saturation_mean"])
    target = float(metrics.get("_style_saturation_target", 0.155))
    bias = float(metrics.get("_style_saturation_bias", 1.0))
    gain = target / max(sat_mean, 0.01)
    gain *= bias
    gain = float(np.clip(gain, 0.86, 1.22))
    skin = metrics.get("skin_region", {})
    if isinstance(skin, dict) and float(skin.get("coverage_pct", 0.0)) > 2.0:
        gain = float(np.clip(gain, 0.90, 1.12))
    return float(1.0 + (gain - 1.0) * np.clip(strength, 0.0, 1.0))


def _blend_mask(base: np.ndarray, adjusted: np.ndarray, mask: np.ndarray, adjusted_weight: float) -> np.ndarray:
    if not np.any(mask):
        return adjusted
    out = adjusted.copy()
    weight = float(np.clip(adjusted_weight, 0.0, 1.0))
    out[mask] = base[mask] * (1.0 - weight) + adjusted[mask] * weight
    return clamp01(out)


def _apply_region_saturation(arr: np.ndarray, mask: np.ndarray, gain: float) -> np.ndarray:
    if not np.any(mask) or abs(gain - 1.0) < 1e-6:
        return arr
    adjusted = adjust_saturation(arr, gain)
    out = arr.copy()
    out[mask] = adjusted[mask]
    return clamp01(out)


def _reduce_vegetation_neon(arr: np.ndarray, mask: np.ndarray, risk: float) -> np.ndarray:
    if not np.any(mask) or risk <= 0:
        return arr
    out = arr.copy()
    amount = float(np.clip(0.10 + 0.22 * risk, 0.0, 0.30))
    local = out[mask]
    rb_avg = (local[:, 0] + local[:, 2]) / 2.0
    local[:, 1] = local[:, 1] * (1.0 - amount) + rb_avg * amount
    out[mask] = local
    out = _apply_region_saturation(out, mask, 1.0 - 0.18 * risk)
    return clamp01(out)


def _protect_sky_color(arr: np.ndarray, mask: np.ndarray, risk: float) -> np.ndarray:
    if not np.any(mask):
        return arr
    out = arr.copy()
    if risk > 0:
        out = _apply_region_saturation(out, mask, 1.0 - 0.16 * risk)
    local = out[mask]
    cyan_push = np.maximum(0.0, local[:, 1] - local[:, 0] * 1.12)
    local[:, 1] -= cyan_push * (0.08 + 0.18 * risk)
    local[:, 2] = np.minimum(local[:, 2], np.maximum(local[:, 0], local[:, 1]) + 0.42)
    out[mask] = local
    return clamp01(out)


def _apply_midtone_contrast(arr: np.ndarray, amount: float, density: float) -> np.ndarray:
    if abs(amount) < 1e-6 and abs(density) < 1e-6:
        return arr
    lum = luminance(arr)[..., None]
    contrast = (arr - 0.5) * (1.0 + amount) + 0.5
    out = arr * (1.0 - abs(amount)) + contrast * abs(amount) if amount != 0 else arr.copy()
    if amount < 0:
        out = arr * (1.0 - abs(amount)) + (0.5 + (arr - 0.5) * (1.0 + amount)) * abs(amount)
    if density:
        out = out - density * 0.035 * (0.25 + (1.0 - lum) ** 1.4)
    return clamp01(out)


def style_decisions_zh(profile: dict, metrics: dict) -> list[str]:
    profile_id = profile.get("id", "reality_standard")
    name = profile.get("display_name_zh", profile_id)
    decisions = [f"当前选择 {name} 归一化目标，系统按该风格的前置底片需求调整归一化策略。"]
    if profile_id == "reality_standard":
        decisions.append("Reality Standard 目标最克制，因此优先保留真实环境光，不强行拉成中性白。")
    elif profile_id == "fuji_provia":
        decisions.append("Fuji Provia 目标自然通透，因此中间调略提亮，并保持较准确的色彩密度。")
    elif profile_id == "fuji_astia":
        decisions.append("Fuji Astia 目标肤色柔和，因此系统提高肤色保护，并降低反差和饱和修正幅度。")
    elif profile_id == "kodak_portra":
        decisions.append("当前选择 Kodak Portra 归一化目标，因此系统优先保护肤色和高光层次，并限制绿色饱和度。")
    elif profile_id == "contax_t3":
        decisions.append("当前选择 Contax T3 归一化目标，因此系统保留较强中间调微反差，没有过度柔化。")
    elif profile_id == "hasselblad_hncs":
        decisions.append("当前选择 Hasselblad HNCS 归一化目标，因此系统更重视中性色准确和干净色彩，抑制绿/品红偏色。")
    elif profile_id == "leica_natural":
        decisions.append("当前选择 Leica Natural 归一化目标，因此系统保留中间调厚度和克制微反差，避免强烈偏色。")
    if float(metrics.get("skin_region", {}).get("pixel_ratio", 0.0)) > 0.005:
        decisions.append("检测到肤色区域，风格目标中的肤色优先级已参与限制白平衡和饱和度变化。")
    if float(metrics.get("vegetation_neon_risk", 0.0)) > 0.2:
        decisions.append("检测到绿植荧光风险，风格目标中的绿植策略已参与降低绿色抢眼程度。")
    return decisions


def normalize_image(
    arr: np.ndarray,
    analysis: ImageAnalysis,
    strength: float = 1.0,
    style_profile: dict | str | None = None,
    normalization_strategy: dict | None = None,
) -> NormalizationResult:
    profile = load_style_profile(style_profile or "reality_standard") if not isinstance(style_profile, dict) else style_profile
    effective_strength = strength * float(profile.get("normalization_strength_bias", 1.0))
    strength = float(np.clip(effective_strength, 0.0, 1.0))
    metrics = analysis.metrics
    metrics = {
        **metrics,
        "_style_tone_target_midtone": float(profile["tone_target"].get("midtone", 0.46))
        + float(profile["tone_target"].get("brightness_bias", 0.0)),
        "_style_saturation_target": float(profile["saturation_policy"].get("target", 0.155)),
        "_style_saturation_bias": float(profile["saturation_policy"].get("bias", 1.0)),
    }
    masks = analysis.masks
    out = arr.copy()
    strategy, strategy_source, strategy_warnings = _safe_strategy(normalization_strategy)

    cast_strength = 0.34
    if abs(float(metrics["temperature_tendency_score"])) > 0.055 or abs(float(metrics["color_cast_green_magenta_score"])) > 0.035:
        cast_strength = 0.52
    atmosphere_score = float(metrics.get("atmosphere_preservation_score", 0.35))
    skin_ratio = float(metrics.get("skin_region", {}).get("pixel_ratio", 0.0))
    if atmosphere_score > 0.58:
        cast_strength *= 0.68 / max(0.65, float(profile["white_balance_policy"].get("atmosphere_protection", 1.0)))
    if skin_ratio > 0.01:
        cast_strength *= 0.82
    cast_strength *= float(profile["white_balance_policy"].get("correction_bias", 1.0))
    cast_strength *= 0.55 + 0.90 * float(strategy["white_balance_correction_strength"])
    cast_strength *= 1.0 - 0.42 * float(strategy["temperature_preserve_strength"]) * max(0.0, atmosphere_score - 0.35)
    cast_strength *= 0.70 + 0.70 * float(strategy["green_magenta_shift_strength"])
    max_wb_shift = float(profile["white_balance_policy"].get("max_shift", 0.09)) - min(0.035, atmosphere_score * 0.035)
    max_wb_shift = max(0.035, max_wb_shift)
    gains = compute_white_balance_gains(metrics["white_point_rgb"], strength=cast_strength * strength, max_shift=max_wb_shift)
    out = apply_channel_gains(out, gains)
    skin_protection = max(float(profile["skin_priority"].get("protection", 0.72)), float(strategy["skin_protection"]))
    out = _blend_mask(arr, out, masks.skin, 1.0 - 0.72 * skin_protection)
    out = _blend_mask(arr, out, masks.sky, 0.76)

    exposure_strength = strength * (0.40 + 1.05 * float(strategy["exposure_correction_strength"]))
    exposure_scale = exposure_scale_from_analysis(metrics, exposure_strength)
    out = clamp01(out * exposure_scale)

    rolloff_amount = 0.0
    if float(metrics["highlight_rolloff_need"]) > 0.12:
        highlight_strength = strength * (0.35 + 1.05 * float(strategy["highlight_rolloff_strength"]))
        rolloff_amount = (0.30 + 0.46 * float(metrics["highlight_rolloff_need"]) * highlight_strength) * float(
            profile["highlight_policy"].get("rolloff_bias", 1.0)
        )
        rolled = highlight_rolloff(out, amount=rolloff_amount)
        warmth = float(profile["highlight_policy"].get("warmth", 0.0))
        if warmth and np.any(masks.highlight):
            rolled = rolled.copy()
            rolled[masks.highlight, 0] = np.clip(rolled[masks.highlight, 0] + warmth, 0.0, 1.0)
            rolled[masks.highlight, 2] = np.clip(rolled[masks.highlight, 2] - warmth * 0.5, 0.0, 1.0)
        out = _blend_mask(out, rolled, masks.highlight, 1.0)
        out = _blend_mask(out, rolled, ~masks.highlight, 0.35)

    shadow_lift = 0.0
    if float(metrics["shadow_lift_need"]) > 0.10:
        shadow_strength = strength * (0.35 + 1.10 * float(strategy["shadow_lift_strength"]))
        shadow_lift = min(0.030, 0.010 + 0.023 * float(metrics["shadow_lift_need"])) * shadow_strength
        shadow_lift *= float(profile["shadow_policy"].get("lift_bias", 1.0))
        lifted = lift_shadows_safely(out, shadow_lift)
        out = _blend_mask(out, lifted, masks.shadow, 0.88)

    sat_gain = saturation_gain_from_analysis(metrics, strength)
    out = adjust_saturation(out, sat_gain)
    if np.any(masks.skin):
        skin_weight = max(0.20, 1.0 - 0.55 * skin_protection)
        out = _blend_mask(arr, out, masks.skin, skin_weight)
        out = _apply_region_saturation(out, masks.skin, float(profile["skin_priority"].get("saturation_limit", 1.0)))
    sky_risk = float(metrics.get("sky_saturation_risk", 0.0)) * strength
    sky_risk *= 0.55 + 1.20 * float(strategy["sky_cyan_control"])
    sky_risk *= float(profile["sky_policy"].get("cyan_control", 1.0))
    out = _protect_sky_color(out, masks.sky, sky_risk)
    if np.any(masks.sky):
        out = _apply_region_saturation(out, masks.sky, min(1.0, float(profile["sky_policy"].get("saturation_limit", 0.74)) / 0.74))
    veg_risk = float(metrics.get("vegetation_neon_risk", 0.0)) * strength
    veg_risk *= 0.55 + 1.20 * float(strategy["green_suppression"])
    veg_risk *= float(profile["vegetation_policy"].get("neon_control", 1.0))
    out = _reduce_vegetation_neon(out, masks.vegetation, veg_risk)
    if np.any(masks.vegetation):
        out = _apply_region_saturation(
            out,
            masks.vegetation,
            min(1.0, float(profile["vegetation_policy"].get("saturation_limit", 0.62)) / 0.62),
        )

    out = _apply_midtone_contrast(
        out,
        float(profile["contrast_policy"].get("midtone_contrast", 0.0)) + float(strategy["midtone_contrast"]) * 0.55,
        float(profile["tone_target"].get("density", 0.0)),
    )

    out = blend(arr, out, strength)
    protected_regions = []
    for key, mask in {
        "skin": masks.skin,
        "sky": masks.sky,
        "vegetation": masks.vegetation,
        "highlight": masks.highlight,
        "shadow": masks.shadow,
    }.items():
        if np.any(mask):
            protected_regions.append(key)
    operations: dict[str, float | list[float] | str] = {
        "engine": "Reality First Color Engine v1.0",
        "normalization_strategy_source": strategy_source,
        "normalization_strategy": strategy,
        "normalization_strategy_warnings_zh": strategy_warnings,
        "style_profile_used": str(profile.get("id", "reality_standard")),
        "style_profile_name_zh": str(profile.get("display_name_zh", "")),
        "white_balance_gains_rgb": [float(v) for v in gains],
        "white_balance_strength": float(cast_strength * strength),
        "white_balance_max_shift": float(max_wb_shift),
        "exposure_scale": float(exposure_scale),
        "highlight_rolloff_amount": float(rolloff_amount),
        "shadow_lift_amount": float(shadow_lift),
        "saturation_gain": float(sat_gain),
        "sky_saturation_protection": float(sky_risk),
        "vegetation_neon_protection": float(veg_risk),
        "style_sky_cyan_control": float(profile["sky_policy"].get("cyan_control", 1.0)),
        "style_vegetation_neon_control": float(profile["vegetation_policy"].get("neon_control", 1.0)),
        "style_midtone_contrast": float(profile["contrast_policy"].get("midtone_contrast", 0.0)),
        "style_density": float(profile["tone_target"].get("density", 0.0)),
        "style_contrast_policy": profile["contrast_policy"],
        "style_skin_priority": profile["skin_priority"],
        "style_vegetation_policy": profile["vegetation_policy"],
        "style_sky_policy": profile["sky_policy"],
        "style_highlight_policy": profile["highlight_policy"],
        "style_shadow_policy": profile["shadow_policy"],
        "style_normalization_strength_bias": float(profile.get("normalization_strength_bias", 1.0)),
        "atmosphere_preservation_score": atmosphere_score,
        "global_strength": float(strength),
        "style_policy": "no_lut_no_strong_stylization",
        "protected_regions": ",".join(protected_regions),
        "style_aware_decisions_zh": style_decisions_zh(profile, metrics),
    }
    return NormalizationResult(image=clamp01(out), operations=operations)
