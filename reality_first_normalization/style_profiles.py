from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_PROFILE_FIELDS = {
    "display_name_zh",
    "philosophy_zh",
    "tone_target",
    "white_balance_policy",
    "skin_priority",
    "sky_policy",
    "vegetation_policy",
    "contrast_policy",
    "saturation_policy",
    "highlight_policy",
    "shadow_policy",
    "normalization_strength_bias",
}


def profile_dir() -> Path:
    return Path(__file__).resolve().parent / "data" / "style_profiles"


def list_style_profiles() -> list[str]:
    return sorted(path.stem for path in profile_dir().glob("*.json"))


def load_style_profile(profile_id: str = "reality_standard") -> dict[str, Any]:
    profile_id = profile_id or "reality_standard"
    path = profile_dir() / f"{profile_id}.json"
    if not path.exists():
        available = ", ".join(list_style_profiles())
        raise ValueError(f"Unknown style profile: {profile_id}. Available: {available}")
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("id", profile_id)
    missing = sorted(REQUIRED_PROFILE_FIELDS - set(data))
    if missing:
        raise ValueError(f"Style profile {profile_id} is missing fields: {', '.join(missing)}")
    return data
