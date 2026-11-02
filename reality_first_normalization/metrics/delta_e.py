"""CIEDE2000 between encoded sRGB images, plus the conversions it needs.

The color-difference equations follow CIE 142-2001 / ISO/CIE 11664-6, with the
hue-angle conventions checked against the published Sharma, Wu and Dalal
(2005) numerical pairs. sRGB primaries and the transfer function are IEC
61966-2-1. Nothing here decides whether an image looks like film.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

_D65_XY = (0.3127, 0.3290)
_SRGB_PRIMARIES = ((0.64, 0.33), (0.30, 0.60), (0.15, 0.06))


def _xyz_from_xy(x: float, y: float) -> np.ndarray:
    return np.array([x / y, 1.0, (1.0 - x - y) / y], dtype=np.float64)


def _srgb_to_xyz_matrix() -> np.ndarray:
    basis = np.column_stack([_xyz_from_xy(x, y) for x, y in _SRGB_PRIMARIES])
    white = _xyz_from_xy(*_D65_XY)
    scale = np.linalg.solve(basis, white)
    return basis * scale


D65_XYZ = _xyz_from_xy(*_D65_XY)
SRGB_TO_XYZ = _srgb_to_xyz_matrix()


def srgb_to_linear(encoded: np.ndarray) -> np.ndarray:
    """Inverse IEC 61966-2-1 transfer."""
    channel = np.asarray(encoded, dtype=np.float64)
    linear: np.ndarray = np.where(
        channel <= 0.04045,
        channel / 12.92,
        ((channel + 0.055) / 1.055) ** 2.4,
    )
    return linear


def encoded_srgb_to_xyz(encoded: np.ndarray) -> np.ndarray:
    return srgb_to_linear(encoded) @ SRGB_TO_XYZ.T


def xyz_to_lab(xyz: np.ndarray, white: np.ndarray = D65_XYZ) -> np.ndarray:
    """CIE L*a*b* from XYZ. ``white`` is the reference white in XYZ."""
    scaled = np.asarray(xyz, dtype=np.float64) / np.asarray(white, dtype=np.float64)
    transformed = _lab_f(scaled)
    lightness = 116.0 * transformed[..., 1] - 16.0
    a_star = 500.0 * (transformed[..., 0] - transformed[..., 1])
    b_star = 200.0 * (transformed[..., 1] - transformed[..., 2])
    return np.stack((lightness, a_star, b_star), axis=-1)


def encoded_srgb_to_lab(encoded: np.ndarray) -> np.ndarray:
    return xyz_to_lab(encoded_srgb_to_xyz(encoded))


def delta_e2000_lab(
    lab_reference: np.ndarray,
    lab_sample: np.ndarray,
    *,
    k_l: float = 1.0,
    k_c: float = 1.0,
    k_h: float = 1.0,
) -> np.ndarray:
    """CIEDE2000. Parametric factors default to 1, the CIE reference conditions."""
    reference = np.asarray(lab_reference, dtype=np.float64)
    sample = np.asarray(lab_sample, dtype=np.float64)
    if reference.shape != sample.shape or reference.shape[-1] != 3:
        raise ValueError("CIEDE2000 inputs must share shape (..., 3)")
    for name, factor in (("k_l", k_l), ("k_c", k_c), ("k_h", k_h)):
        if isinstance(factor, bool) or not isinstance(factor, (int, float)) or not np.isfinite(factor) or float(factor) <= 0.0:
            raise ValueError(f"{name} must be a finite number greater than 0")
    lightness_1, a_1, b_1 = reference[..., 0], reference[..., 1], reference[..., 2]
    lightness_2, a_2, b_2 = sample[..., 0], sample[..., 1], sample[..., 2]
    chroma_1 = np.hypot(a_1, b_1)
    chroma_2 = np.hypot(a_2, b_2)
    mean_chroma = 0.5 * (chroma_1 + chroma_2)
    mean_chroma_7 = mean_chroma**7
    chroma_scale = 0.5 * (1.0 - np.sqrt(mean_chroma_7 / (mean_chroma_7 + 25.0**7)))
    a_1p = (1.0 + chroma_scale) * a_1
    a_2p = (1.0 + chroma_scale) * a_2
    chroma_1p = np.hypot(a_1p, b_1)
    chroma_2p = np.hypot(a_2p, b_2)
    hue_1 = np.degrees(np.arctan2(b_1, a_1p)) % 360.0
    hue_2 = np.degrees(np.arctan2(b_2, a_2p)) % 360.0

    delta_lightness = lightness_2 - lightness_1
    delta_chroma = chroma_2p - chroma_1p
    delta_hue_deg = hue_2 - hue_1
    delta_hue_deg = np.where(delta_hue_deg > 180.0, delta_hue_deg - 360.0, delta_hue_deg)
    delta_hue_deg = np.where(delta_hue_deg < -180.0, delta_hue_deg + 360.0, delta_hue_deg)
    neutral = (chroma_1p * chroma_2p) == 0.0
    delta_hue_deg = np.where(neutral, 0.0, delta_hue_deg)
    delta_hue = 2.0 * np.sqrt(np.maximum(chroma_1p * chroma_2p, 0.0)) * np.sin(np.radians(delta_hue_deg) / 2.0)

    mean_lightness = 0.5 * (lightness_1 + lightness_2)
    mean_chroma_p = 0.5 * (chroma_1p + chroma_2p)
    hue_sum = hue_1 + hue_2
    hue_gap = np.abs(hue_1 - hue_2)
    mean_hue = np.where(
        neutral,
        hue_sum,
        np.where(
            hue_gap <= 180.0,
            0.5 * hue_sum,
            np.where(hue_sum < 360.0, 0.5 * (hue_sum + 360.0), 0.5 * (hue_sum - 360.0)),
        ),
    )
    mean_hue_rad = np.radians(mean_hue)
    hue_term = (
        1.0
        - 0.17 * np.cos(mean_hue_rad - np.radians(30.0))
        + 0.24 * np.cos(2.0 * mean_hue_rad)
        + 0.32 * np.cos(3.0 * mean_hue_rad + np.radians(6.0))
        - 0.20 * np.cos(4.0 * mean_hue_rad - np.radians(63.0))
    )
    rotation = np.radians(30.0) * np.exp(-(((mean_hue - 275.0) / 25.0) ** 2))
    mean_chroma_p7 = mean_chroma_p**7
    chroma_rotation = 2.0 * np.sqrt(mean_chroma_p7 / (mean_chroma_p7 + 25.0**7))
    lightness_scale = 1.0 + (0.015 * (mean_lightness - 50.0) ** 2) / np.sqrt(20.0 + (mean_lightness - 50.0) ** 2)
    chroma_weight = 1.0 + 0.045 * mean_chroma_p
    hue_weight = 1.0 + 0.015 * mean_chroma_p * hue_term
    cross = -np.sin(2.0 * rotation) * chroma_rotation
    light = delta_lightness / (float(k_l) * lightness_scale)
    chroma = delta_chroma / (float(k_c) * chroma_weight)
    hue = delta_hue / (float(k_h) * hue_weight)
    return np.sqrt(light**2 + chroma**2 + hue**2 + cross * chroma * hue)


def delta_e2000_srgb(
    reference: np.ndarray,
    sample: np.ndarray,
    *,
    k_l: float = 1.0,
    k_c: float = 1.0,
    k_h: float = 1.0,
) -> np.ndarray:
    """Per-pixel CIEDE2000. Both arrays are encoded sRGB shaped (..., 3), values in [0, 1]."""
    return delta_e2000_lab(
        encoded_srgb_to_lab(reference),
        encoded_srgb_to_lab(sample),
        k_l=k_l,
        k_c=k_c,
        k_h=k_h,
    )


# Round placeholders. They are not a film-match tolerance.
PLACEHOLDER_MEAN_MAX = 10.0
PLACEHOLDER_P95_MAX = 20.0
PLACEHOLDER_NOTE = (
    "Placeholder CIEDE2000 gates on the mean and the 95th percentile. "
    "Passing them does not mean the image matches any film stock."
)


def summarize_delta_e2000(reference: np.ndarray, sample: np.ndarray) -> dict[str, Any]:
    """Aggregate a per-pixel CIEDE2000 map. Thresholds are applied separately."""
    if reference.shape != sample.shape or reference.ndim != 3 or reference.shape[2] != 3:
        raise ValueError("delta E summary expects two images of shape (height, width, 3)")
    values = delta_e2000_srgb(reference, sample).reshape(-1)
    if values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError("delta E summary needs a non-empty finite image")
    return {
        "pixels": int(values.size),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "p95": float(np.percentile(values, 95)),
        "max": float(np.max(values)),
        "metric": "CIEDE2000",
        "working_space": "encoded sRGB",
    }


def apply_delta_e_gate(
    summary: dict[str, Any],
    *,
    mean_max: float | None,
    p95_max: float | None,
    role: str,
) -> dict[str, Any]:
    """Attach a pass/fail gate. ``role`` is recorded and is never treated as a film score."""
    judged = dict(summary)
    if mean_max is None and p95_max is None:
        judged.update({
            "passed": None,
            "failures": [],
            "thresholds": {"mean_max": None, "p95_max": None, "role": "not_applied"},
            "note": "No CIEDE2000 gate was applied. This is not a film-accuracy score.",
        })
        return judged
    mean_limit = PLACEHOLDER_MEAN_MAX if mean_max is None else mean_max
    p95_limit = PLACEHOLDER_P95_MAX if p95_max is None else p95_max
    _positive("mean_max", mean_limit)
    _positive("p95_max", p95_limit)
    failures: list[str] = []
    if float(judged["mean"]) > mean_limit:
        failures.append("mean")
    if float(judged["p95"]) > p95_limit:
        failures.append("p95")
    judged.update({
        "passed": not failures,
        "failures": failures,
        "thresholds": {"mean_max": mean_limit, "p95_max": p95_limit, "role": role},
        "note": PLACEHOLDER_NOTE if role == "placeholder" else (
            "User CIEDE2000 gate on the mean and the 95th percentile. "
            "It does not mean the image matches any film stock."
        ),
    })
    return judged


def _positive(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or float(value) < 0.0:
        raise ValueError(f"{name} must be a finite number >= 0")


def _lab_f(channel: np.ndarray) -> np.ndarray:
    delta = 6.0 / 29.0
    transformed: np.ndarray = np.where(
        channel > delta**3,
        np.cbrt(channel),
        channel / (3.0 * delta**2) + 4.0 / 29.0,
    )
    return transformed


def _load_pair(reference: Path, sample: Path, max_long_edge: int, policy: str) -> dict[str, Any]:
    from ..io import load_image

    reference_pixels, _reference_color = load_image(
        reference, max_long_edge=max_long_edge, assume_srgb=(policy == "explicit"), untagged_policy=policy,
    )
    sample_pixels, _sample_color = load_image(
        sample, max_long_edge=max_long_edge, assume_srgb=(policy == "explicit"), untagged_policy=policy,
    )
    if reference_pixels.shape != sample_pixels.shape:
        raise ValueError(
            f"Images differ in shape after decode: reference {reference_pixels.shape[1]}x{reference_pixels.shape[0]}, "
            f"sample {sample_pixels.shape[1]}x{sample_pixels.shape[0]}"
        )
    return summarize_delta_e2000(reference_pixels, sample_pixels)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reality-first-photo delta-e",
        description=(
            "CIEDE2000 between two encoded-sRGB images, or every pair in a reference set. "
            "Default gates are placeholders and do not score film likeness."
        ),
    )
    parser.add_argument("--reference", type=Path, help="Encoded-sRGB reference image. Not used with --reference-set.")
    parser.add_argument("--sample", type=Path, help="Encoded-sRGB sample image. Not used with --reference-set.")
    parser.add_argument("--reference-set", type=Path, help="Directory or reference-set.json. See docs/REFERENCE_SET.md.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON. Reference sets always print JSON.")
    parser.add_argument("--report-only", action="store_true", help="Print the summary and do not apply a pass/fail gate.")
    parser.add_argument("--mean-max", type=float, help=f"Fail if the mean CIEDE2000 is above this. Default placeholder: {PLACEHOLDER_MEAN_MAX}.")
    parser.add_argument("--p95-max", type=float, help=f"Fail if the 95th percentile is above this. Default placeholder: {PLACEHOLDER_P95_MAX}.")
    parser.add_argument("--max-long-edge", type=int, default=0, help="Decode size. Both images in a pair must still match. Default 0 keeps full size.")
    from ..local_cli import add_color_policy_arguments

    add_color_policy_arguments(parser)
    args = parser.parse_args(argv)
    try:
        from ..local_cli import untagged_policy_from_flags

        if args.reference_set is not None and (args.reference is not None or args.sample is not None):
            raise ValueError("Use either --reference-set or --reference with --sample, not both")
        if args.reference_set is None and (args.reference is None or args.sample is None):
            raise ValueError("delta-e needs --reference and --sample, or --reference-set")
        policy = untagged_policy_from_flags(assume_srgb=args.assume_srgb, strict_color=args.strict_color)
        role = "not_applied" if args.report_only else (
            "placeholder" if args.mean_max is None and args.p95_max is None else "user"
        )
        mean_max = None if args.report_only else args.mean_max
        p95_max = None if args.report_only else args.p95_max
        if args.reference_set is not None:
            from .reference_set import evaluate_reference_set

            summary = evaluate_reference_set(
                args.reference_set,
                max_long_edge=args.max_long_edge,
                policy=policy,
                mean_max=mean_max,
                p95_max=p95_max,
                role=role,
                report_only=args.report_only,
            )
            print(json.dumps(summary, indent=2, allow_nan=False), flush=True)
        else:
            summary = apply_delta_e_gate(
                _load_pair(args.reference, args.sample, args.max_long_edge, policy),
                mean_max=PLACEHOLDER_MEAN_MAX if mean_max is None and not args.report_only else mean_max,
                p95_max=PLACEHOLDER_P95_MAX if p95_max is None and not args.report_only else p95_max,
                role=role if not args.report_only else "not_applied",
            )
            if args.json:
                print(json.dumps(summary, indent=2, allow_nan=False), flush=True)
            else:
                print(f"pixels: {summary['pixels']}", flush=True)
                print(f"mean: {summary['mean']:.6f}", flush=True)
                print(f"median: {summary['median']:.6f}", flush=True)
                print(f"p95: {summary['p95']:.6f}", flush=True)
                print(f"max: {summary['max']:.6f}", flush=True)
                print(f"passed: {summary['passed']}", flush=True)
                print(summary["note"], flush=True)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if summary.get("passed") is False:
        return 2
    return 0
