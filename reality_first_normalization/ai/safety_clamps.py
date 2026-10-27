from __future__ import annotations

from typing import Any


CLAMPS: dict[str, tuple[float, float]] = {
    "exposure_correction_strength": (0.0, 1.0),
    "white_balance_correction_strength": (0.0, 1.0),
    "temperature_preserve_strength": (0.0, 1.0),
    "green_magenta_shift_strength": (0.0, 0.75),
    "highlight_rolloff_strength": (0.0, 1.0),
    "shadow_lift_strength": (0.0, 0.65),
    "midtone_contrast": (-0.25, 0.35),
    "skin_protection": (0.55, 1.0),
    "green_suppression": (0.0, 0.7),
    "sky_cyan_control": (0.0, 0.65),
    "style_strength": (0.55, 1.0),
}


def local_fallback_advice(reason: str = "AI 建议未采用，已使用本地安全策略。") -> dict[str, Any]:
    return {
        "recommended_normalization": {
            "intent": "local_reality_first_safe_normalization",
            "exposure_correction_strength": 0.52,
            "white_balance_correction_strength": 0.35,
            "temperature_preserve_strength": 0.72,
            "green_magenta_shift_strength": 0.18,
            "highlight_rolloff_strength": 0.58,
            "shadow_lift_strength": 0.22,
            "midtone_contrast": 0.08,
            "skin_protection": 0.82,
            "green_suppression": 0.24,
            "sky_cyan_control": 0.22,
            "grain_recommendation": "subtle",
        },
        "recommended_style": {
            "style_id": "reality_clean",
            "strength": 0.78,
            "alternates": ["leica_natural_depth", "kodak_portra_real"],
        },
        "confidence": 0.62,
        "reason_zh": reason,
        "risk_notes_zh": ["未采用不可靠 AI 输出；本地策略保持肤色、高光、天空和绿植安全。"],
        "ai_adopted": False,
        "fallback_used": True,
    }


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clamp_advice(advice: dict[str, Any] | None, min_confidence: float = 0.45) -> dict[str, Any]:
    warnings: list[str] = []
    if not isinstance(advice, dict):
        fallback = local_fallback_advice("AI 返回为空或格式非法，已使用本地安全策略。")
        fallback["safety_warnings_zh"] = ["AI 返回为空或格式非法"]
        return fallback

    confidence = _as_float(advice.get("confidence"))
    if confidence is None or confidence < min_confidence:
        fallback = local_fallback_advice("AI 置信度不足，已使用本地安全策略。")
        fallback["safety_warnings_zh"] = ["AI 置信度不足"]
        fallback["raw_ai_advice"] = advice
        return fallback

    normalized = dict(advice)
    rn = dict(normalized.get("recommended_normalization") or {})
    if not rn:
        fallback = local_fallback_advice("AI 缺少归一化参数，已使用本地安全策略。")
        fallback["safety_warnings_zh"] = ["AI 缺少 recommended_normalization"]
        fallback["raw_ai_advice"] = advice
        return fallback

    for key, (low, high) in CLAMPS.items():
        source_key = "strength" if key == "style_strength" else key
        container = normalized.get("recommended_style", {}) if key == "style_strength" else rn
        value = _as_float(container.get(source_key))
        if value is None:
            if key == "style_strength":
                normalized.setdefault("recommended_style", {})["strength"] = 0.78
            else:
                rn[key] = local_fallback_advice()["recommended_normalization"][key]
            warnings.append(f"{key} 缺失，使用本地默认值")
            continue
        clamped = min(high, max(low, value))
        if clamped != value:
            warnings.append(f"{key} 超出安全范围，已从 {value:.3f} 夹逼到 {clamped:.3f}")
        if key == "style_strength":
            normalized.setdefault("recommended_style", {})["strength"] = clamped
        else:
            rn[key] = clamped

    normalized["recommended_normalization"] = rn
    normalized["confidence"] = float(confidence)
    normalized["safety_warnings_zh"] = warnings
    normalized["ai_adopted"] = True
    normalized["fallback_used"] = False
    return normalized
