"""A directory of image pairs for a later, user-supplied acceptance check.

The format does not contain film scans. Whoever adds images states their license
in the JSON. Placeholder gates are not a claim that a recipe matches a stock.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .delta_e import PLACEHOLDER_MEAN_MAX, PLACEHOLDER_P95_MAX, apply_delta_e_gate

FORMAT = "reality-first-reference-set-v1"


def evaluate_reference_set(
    path: Path,
    *,
    max_long_edge: int,
    policy: str,
    mean_max: float | None,
    p95_max: float | None,
    role: str,
    report_only: bool,
) -> dict[str, Any]:
    root, document = _load_document(Path(path))
    file_mean, file_p95, file_role = _thresholds(document.get("thresholds"))
    if report_only:
        chosen_mean, chosen_p95, chosen_role = None, None, "not_applied"
    else:
        chosen_mean = file_mean if mean_max is None else mean_max
        chosen_p95 = file_p95 if p95_max is None else p95_max
        chosen_role = file_role if mean_max is None and p95_max is None else "user"
        if role == "placeholder" and mean_max is None and p95_max is None:
            chosen_role = file_role
    from .delta_e import _load_pair

    items: list[dict[str, Any]] = []
    for entry in document["items"]:
        if not isinstance(entry, dict):
            raise ValueError("reference-set items must be objects")
        item_id = entry.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("each reference-set item needs an id")
        reference = _contained(root, entry.get("reference"), f"{item_id} reference")
        sample = _contained(root, entry.get("sample"), f"{item_id} sample")
        measured = _load_pair(reference, sample, max_long_edge, policy)
        judged = apply_delta_e_gate(
            measured,
            mean_max=None if report_only else chosen_mean,
            p95_max=None if report_only else chosen_p95,
            role=chosen_role,
        )
        judged["id"] = item_id
        items.append(judged)
    if not items:
        raise ValueError("reference-set items must not be empty")
    passed: bool | None
    if report_only:
        passed = None
    else:
        passed = all(item["passed"] is True for item in items)
    return {
        "format": FORMAT,
        "license": document["license"],
        "passed": passed,
        "item_count": len(items),
        "items": items,
        "note": (
            "Reference-set result. Gates do not mean a recipe matches a film stock. "
            "Image licenses are whatever the set declares; this tool does not grant one."
        ),
    }


def _load_document(path: Path) -> tuple[Path, dict[str, Any]]:
    document_path = path / "reference-set.json" if path.is_dir() else path
    if document_path.name != "reference-set.json":
        raise ValueError("A reference set file must be named reference-set.json")
    if not document_path.is_file():
        raise ValueError(f"reference set not found: {document_path}")
    try:
        parsed = json.loads(document_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid reference-set JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("reference-set JSON must be an object")
    if parsed.get("format") != FORMAT:
        raise ValueError(f"reference-set format must be {FORMAT}")
    license_text = parsed.get("license")
    if not isinstance(license_text, str) or not license_text.strip():
        raise ValueError("reference-set license must be a non-empty string stating who may use the images")
    items = parsed.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("reference-set items must be a non-empty list")
    return document_path.parent.resolve(), parsed


def _thresholds(value: object) -> tuple[float, float, str]:
    if value is None:
        return PLACEHOLDER_MEAN_MAX, PLACEHOLDER_P95_MAX, "placeholder"
    if not isinstance(value, dict):
        raise ValueError("reference-set thresholds must be an object")
    mean = value.get("mean_max", PLACEHOLDER_MEAN_MAX)
    p95 = value.get("p95_max", PLACEHOLDER_P95_MAX)
    role = value.get("role", "user")
    if role == "film-match":
        raise ValueError("threshold role 'film-match' is not a supported claim")
    if not isinstance(role, str) or not role:
        raise ValueError("threshold role must be a string")
    return float(mean), float(p95), role


def _contained(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or value.startswith(("/", "\\")):
        raise ValueError(f"{label} must be a relative path inside the reference set")
    parts = Path(value).parts
    if ".." in parts or not parts:
        raise ValueError(f"{label} must stay inside the reference set")
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"{label} escapes the reference set")
    if not path.is_file():
        raise ValueError(f"{label} is missing: {value}")
    return path
