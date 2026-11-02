"""Load a JSON film recipe. The file is data, never code.

Bundled recipes use generic names and author-chosen round parameters. They are
not measurements of commercial stocks. ``verification`` must stay
``unverified`` until a later version has a real scan protocol; this loader
rejects any other status so a file cannot claim a check that the software did
not perform.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .curve import CharacteristicCurve
from .version import MODEL_VERSION

_RECIPE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_LAYER_ORDER = ["cyan", "magenta", "yellow"]
_MAX_BYTES = 1_000_000


@dataclass(frozen=True, eq=False)
class PrintStage:
    exposure_ev: float
    reference_transmittance: float
    balance: np.ndarray
    sensitivity: np.ndarray
    layer_log_h_offset: np.ndarray
    curve: CharacteristicCurve
    absorption: np.ndarray
    base_density: np.ndarray


@dataclass(frozen=True, eq=False)
class FilmRecipe:
    id: str
    display_name: str
    process: str
    path: Path
    file_name: str
    origin: str
    sha256: str
    parameters_sha256: str
    verification: str
    exposure_ev: float
    scene_mid_gray: float
    sensitivity: np.ndarray
    layer_log_h_offset: np.ndarray
    curve: CharacteristicCurve
    absorption: np.ndarray
    orange_mask: np.ndarray
    print_stage: PrintStage | None
    grain_strength: float
    grain_exponent: float
    grain_midtone_emphasis: float
    halation_threshold: float
    halation_gain: np.ndarray
    halation_sigma_fraction: float


def bundled_recipe_dir() -> Path:
    return Path(__file__).resolve().parent / "data" / "recipes"


def list_recipes() -> list[str]:
    directory = bundled_recipe_dir()
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob("*.json") if path.is_file())


def resolve_recipe_path(name: str) -> tuple[Path, str]:
    """Return the recipe file and ``bundled`` or ``file``. Symlinks are rejected."""
    candidate = Path(name)
    looks_like_path = candidate.suffix.lower() == ".json" or "/" in name or "\\" in name or candidate.exists()
    if looks_like_path:
        if candidate.is_symlink():
            raise ValueError("Film recipe symlinks are unsupported; choose the actual JSON file")
        if not candidate.is_file():
            raise ValueError(f"Film recipe file not found: {candidate}")
        return candidate.resolve(), "file"
    path = bundled_recipe_dir() / f"{name}.json"
    if not path.is_file():
        known = ", ".join(list_recipes()) or "(none packaged)"
        raise ValueError(f"Unknown film recipe {name!r}. Bundled recipes: {known}")
    return path, "bundled"


def load_recipe(name: str) -> FilmRecipe:
    path, origin = resolve_recipe_path(name)
    if path.is_symlink():
        raise ValueError("Film recipe symlinks are unsupported; choose the actual JSON file")
    size = path.stat().st_size
    if size > _MAX_BYTES:
        raise ValueError("Film recipe file exceeds 1 MB")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Film recipe must be UTF-8 JSON") from exc
    try:
        data = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except ValueError as exc:
        raise ValueError(f"Invalid film recipe JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Film recipe must be a JSON object")
    return _parse_recipe(data, path=path, origin=origin, file_sha256=hashlib.sha256(raw).hexdigest())


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate key {key}")
        document[key] = value
    return document


def _parse_recipe(data: dict[str, Any], *, path: Path, origin: str, file_sha256: str) -> FilmRecipe:
    document = _object(
        data,
        required={
            "id", "display_name", "process", "model_version", "verification", "summary",
            "constants_origin", "notes", "sources", "exposure", "sensitivity", "curve",
            "dyes", "grain", "halation",
        },
        allowed={
            "id", "display_name", "process", "model_version", "verification", "summary",
            "constants_origin", "notes", "sources", "exposure", "sensitivity", "curve",
            "dyes", "grain", "halation", "print",
        },
        label="film recipe",
    )
    if document["model_version"] != MODEL_VERSION:
        raise ValueError(
            f"Film recipe model_version must be {MODEL_VERSION}; "
            "this file needs the matching interpreter"
        )
    if document["verification"] != "unverified":
        raise ValueError("This version only accepts film recipes marked verification 'unverified'")
    notes = _text(document["notes"], "notes", limit=800)
    if "unverified" not in notes.casefold():
        raise ValueError("Film recipe notes must say that the recipe is unverified")
    recipe_id = _text(document["id"], "id", limit=64)
    if _RECIPE_ID.fullmatch(recipe_id) is None:
        raise ValueError("Film recipe id must be lowercase words separated by hyphens")
    if origin == "bundled" and path.stem != recipe_id:
        raise ValueError("Bundled film recipe id must match its file name")
    process = document["process"]
    if process not in {"negative-print", "reversal"}:
        raise ValueError("Film process must be 'negative-print' or 'reversal'")
    _text(document["summary"], "summary", limit=600)
    _text(document["constants_origin"], "constants_origin", limit=600)
    _text(document["display_name"], "display_name", limit=80)
    _sources(document["sources"])
    exposure = _object(
        document["exposure"],
        required={"scene_mid_gray", "exposure_ev"},
        allowed={"scene_mid_gray", "exposure_ev"},
        label="exposure",
    )
    sensitivity = _object(
        document["sensitivity"],
        required={"layer_order", "matrix_rgb_to_layers", "layer_log_h_offset"},
        allowed={"layer_order", "matrix_rgb_to_layers", "layer_log_h_offset"},
        label="sensitivity",
    )
    if sensitivity["layer_order"] != _LAYER_ORDER:
        raise ValueError("sensitivity.layer_order must be ['cyan', 'magenta', 'yellow']")
    dyes = _object(
        document["dyes"],
        required={"absorption_rgb_from_layers", "orange_mask_density_rgb"},
        allowed={"absorption_rgb_from_layers", "orange_mask_density_rgb"},
        label="dyes",
    )
    grain = _object(
        document["grain"],
        required={"strength", "exponent", "midtone_emphasis"},
        allowed={"strength", "exponent", "midtone_emphasis"},
        label="grain",
    )
    halation = _object(
        document["halation"],
        required={"threshold", "gain_rgb", "sigma_fraction"},
        allowed={"threshold", "gain_rgb", "sigma_fraction"},
        label="halation",
    )
    print_stage = _parse_print(document.get("print"), process)
    parameters = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return FilmRecipe(
        id=recipe_id,
        display_name=str(document["display_name"]),
        process=str(process),
        path=path,
        file_name=path.name,
        origin=origin,
        sha256=file_sha256,
        parameters_sha256=hashlib.sha256(parameters.encode("utf-8")).hexdigest(),
        verification="unverified",
        exposure_ev=_number(exposure["exposure_ev"], "exposure.exposure_ev", low=-8.0, high=8.0),
        scene_mid_gray=_number(exposure["scene_mid_gray"], "exposure.scene_mid_gray", low=1e-4, high=1.0, low_open=True),
        sensitivity=_matrix(sensitivity["matrix_rgb_to_layers"], "sensitivity.matrix_rgb_to_layers"),
        layer_log_h_offset=_vector(sensitivity["layer_log_h_offset"], "sensitivity.layer_log_h_offset", low=-2.0, high=2.0),
        curve=_curve(document["curve"], "curve"),
        absorption=_matrix(dyes["absorption_rgb_from_layers"], "dyes.absorption_rgb_from_layers"),
        orange_mask=_vector(dyes["orange_mask_density_rgb"], "dyes.orange_mask_density_rgb", low=0.0, high=3.0),
        print_stage=print_stage,
        grain_strength=_number(grain["strength"], "grain.strength", low=0.0, high=0.5),
        grain_exponent=_number(grain["exponent"], "grain.exponent", low=0.25, high=1.5),
        grain_midtone_emphasis=_number(grain["midtone_emphasis"], "grain.midtone_emphasis", low=0.0, high=1.0),
        halation_threshold=_number(halation["threshold"], "halation.threshold", low=0.0, high=64.0),
        halation_gain=_vector(halation["gain_rgb"], "halation.gain_rgb", low=0.0, high=2.0),
        halation_sigma_fraction=_number(halation["sigma_fraction"], "halation.sigma_fraction", low=0.0, high=0.2),
    )


def _parse_print(value: object, process: str) -> PrintStage | None:
    if process == "reversal":
        if value is not None:
            raise ValueError("A reversal recipe must not include a print stage")
        return None
    stage = _object(
        value,
        required={
            "exposure_ev", "reference_transmittance", "balance_rgb", "sensitivity", "curve",
            "absorption_rgb_from_layers", "base_density_rgb",
        },
        allowed={
            "exposure_ev", "reference_transmittance", "balance_rgb", "sensitivity", "curve",
            "absorption_rgb_from_layers", "base_density_rgb",
        },
        label="print",
    )
    sensitivity = _object(
        stage["sensitivity"],
        required={"layer_order", "matrix_rgb_to_layers", "layer_log_h_offset"},
        allowed={"layer_order", "matrix_rgb_to_layers", "layer_log_h_offset"},
        label="print.sensitivity",
    )
    if sensitivity["layer_order"] != _LAYER_ORDER:
        raise ValueError("print.sensitivity.layer_order must be ['cyan', 'magenta', 'yellow']")
    return PrintStage(
        exposure_ev=_number(stage["exposure_ev"], "print.exposure_ev", low=-8.0, high=8.0),
        reference_transmittance=_number(
            stage["reference_transmittance"], "print.reference_transmittance", low=1e-6, high=1.0, low_open=True,
        ),
        balance=_vector(stage["balance_rgb"], "print.balance_rgb", low=1e-4, high=100.0, low_open=True),
        sensitivity=_matrix(sensitivity["matrix_rgb_to_layers"], "print.sensitivity.matrix_rgb_to_layers"),
        layer_log_h_offset=_vector(
            sensitivity["layer_log_h_offset"], "print.sensitivity.layer_log_h_offset", low=-2.0, high=2.0,
        ),
        curve=_curve(stage["curve"], "print.curve"),
        absorption=_matrix(stage["absorption_rgb_from_layers"], "print.absorption_rgb_from_layers"),
        base_density=_vector(stage["base_density_rgb"], "print.base_density_rgb", low=0.0, high=3.0),
    )


def _curve(value: object, label: str) -> CharacteristicCurve:
    curve = _object(
        value,
        required={"d_min", "d_max", "log_h_mid", "gamma", "asymmetry", "skew_softness"},
        allowed={"d_min", "d_max", "log_h_mid", "gamma", "asymmetry", "skew_softness"},
        label=label,
    )
    return CharacteristicCurve(
        d_min=_number(curve["d_min"], f"{label}.d_min", low=0.0, high=6.0),
        d_max=_number(curve["d_max"], f"{label}.d_max", low=0.0, high=6.0),
        log_h_mid=_number(curve["log_h_mid"], f"{label}.log_h_mid", low=-4.0, high=4.0),
        gamma=_number(curve["gamma"], f"{label}.gamma", low=0.0, high=8.0, low_open=True),
        asymmetry=_number(curve["asymmetry"], f"{label}.asymmetry", low=-0.85, high=0.85),
        skew_softness=_number(curve["skew_softness"], f"{label}.skew_softness", low=0.05, high=5.0),
    )


def _sources(value: object) -> None:
    if not isinstance(value, list) or not 1 <= len(value) <= 12:
        raise ValueError("sources must be a list of 1 to 12 citations")
    for index, item in enumerate(value):
        source = _object(item, required={"title", "role"}, allowed={"title", "role", "url"}, label=f"sources[{index}]")
        _text(source["title"], f"sources[{index}].title", limit=240)
        _text(source["role"], f"sources[{index}].role", limit=240)
        if "url" in source:
            url = source["url"]
            if not isinstance(url, str) or len(url) > 300 or not url.startswith(("https://", "http://")):
                raise ValueError(f"sources[{index}].url must be an http(s) URL")


def _object(value: object, *, required: set[str], allowed: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    keys = set(value)
    missing = sorted(required - keys)
    if missing:
        raise ValueError(f"{label} missing {missing[0]}")
    extra = sorted(keys - allowed)
    if extra:
        raise ValueError(f"{label} has unsupported field {extra[0]}")
    return value


def _text(value: object, label: str, *, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label} must be a non-empty string of at most {limit} characters")
    return value


def _number(
    value: object,
    label: str,
    *,
    low: float,
    high: float,
    low_open: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    above = number > low if low_open else number >= low
    if not above or number > high:
        raise ValueError(f"{label} must be between {low} and {high}")
    return number


def _vector(
    value: object,
    label: str,
    *,
    low: float,
    high: float,
    low_open: bool = False,
) -> np.ndarray:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{label} must have three numbers")
    return np.asarray(
        [_number(item, f"{label}[{index}]", low=low, high=high, low_open=low_open) for index, item in enumerate(value)],
        dtype=np.float64,
    )


def _matrix(value: object, label: str) -> np.ndarray:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(not isinstance(row, list) or len(row) != 3 for row in value)
    ):
        raise ValueError(f"{label} must be a 3x3 matrix")
    matrix = np.asarray(
        [
            [_number(item, f"{label}[{row}][{col}]", low=0.0, high=4.0) for col, item in enumerate(row_values)]
            for row, row_values in enumerate(value)
        ],
        dtype=np.float64,
    )
    if np.any(matrix.sum(axis=1) <= 0.0):
        raise ValueError(f"{label} rows must each sum to a positive weight")
    return matrix
