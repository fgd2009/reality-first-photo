"""Render a completed four-way comparison as a self-contained local HTML page."""
from __future__ import annotations

from html import escape
import json
from pathlib import PurePosixPath
from urllib.parse import quote


_RECIPE_IDS = ("original", "normalized", "lut_only", "normalized_lut")


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def _json(value: object) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Comparison report must contain finite JSON data") from exc
    return escape(rendered, quote=True)


def _image_url(output: object, recipe_id: str) -> str:
    """Validate a literal POSIX path before encoding it as a relative URL."""
    if not isinstance(output, str) or not output or "\x00" in output:
        raise ValueError("Comparison image output must be a relative PNG path")
    parts = output.split("/")
    if (
        len(parts) < 2
        or parts[0] != recipe_id
        or any(part in ("", ".", "..") for part in parts)
        or PurePosixPath(output).is_absolute()
        or PurePosixPath(output).suffix.lower() != ".png"
    ):
        raise ValueError(f"Comparison image must stay inside {recipe_id}/ and end in .png")
    # A backslash is a filename character in this POSIX contract, not a separator.
    # Encoding also prevents #, ?, %, quotes and non-ASCII names becoming URL syntax.
    return escape(quote(output, safe="/"), quote=True)


def render_comparison_html(report: dict) -> str:
    """Render completed report data only; never read inputs or write output."""
    if not isinstance(report, dict) or report.get("status") != "complete":
        raise ValueError("Only a complete comparison report can be rendered")
    if report.get("kind") != "four_way_comparison" or report.get("format") != "png":
        raise ValueError("Expected a four_way_comparison report with PNG previews")
    recipes = report.get("recipes")
    if not isinstance(recipes, list) or len(recipes) != len(_RECIPE_IDS):
        raise ValueError("Comparison report requires exactly four recipes")
    if any(not isinstance(recipe, dict) for recipe in recipes):
        raise ValueError("Invalid comparison recipe")
    if any(recipe.get("id") not in _RECIPE_IDS for recipe in recipes):
        raise ValueError("Unknown comparison recipe")
    recipe_by_id = {recipe["id"]: recipe for recipe in recipes}
    if set(recipe_by_id) != set(_RECIPE_IDS):
        raise ValueError("Comparison recipe IDs must be unique")
    items = report.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Comparison report requires at least one input")
    lut = report.get("lut")
    if not isinstance(lut, dict):
        raise ValueError("Comparison report requires LUT metadata")

    # Validate JSON and every image path before constructing any report markup.
    metadata = {key: value for key, value in report.items() if key != "items"}
    metadata_json = _json(metadata)
    _json(items)
    rows = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("variants"), dict):
            raise ValueError("Invalid comparison input or variants")
        cards = []
        for recipe_id in _RECIPE_IDS:
            recipe = recipe_by_id[recipe_id]
            variant = item["variants"].get(recipe_id)
            if not isinstance(variant, dict):
                raise ValueError(f"Missing comparison variant: {recipe_id}")
            src = _image_url(variant.get("output"), recipe_id)
            label = _text(recipe.get("label", recipe_id))
            name = _text(item.get("input_name", ""))
            if recipe_id == "original":
                explanation = (
                    "Input reference: decoded, ICC-converted/resized sRGB PNG; "
                    "not a source-file copy."
                )
            else:
                explanation = (
                    f"Normalization strength: {_text(recipe.get('normalize_strength'))}. "
                    f"LUT strength: {_text(recipe.get('lut_strength'))}. "
                    f"LUT applied: {_text(recipe.get('lut_applied'))}."
                )
            details = _json({
                "recipe": recipe,
                "input_sha256": item.get("input_sha256"),
                "normalization": variant.get("normalization"),
                "color": variant.get("color"),
            })
            cards.append(
                '<figure class="variant">'
                f"<figcaption><h3>{label}</h3><p>{explanation}</p></figcaption>"
                f'<a href="{src}"><img src="{src}" alt="{label}: {name}" loading="lazy"></a>'
                f'<p><a href="{src}" download>Open or save this PNG</a></p>'
                "<details><summary>Recipe, normalization and ICC decisions</summary>"
                f"<pre>{details}</pre></details></figure>"
            )
        rows.append(
            '<section class="input">'
            f"<h2>{_text(item.get('input_name', ''))}</h2>"
            f'<p class="dimensions">{_text(item.get("width"))} × '
            f'{_text(item.get("height"))} pixels per preview</p>'
            '<div class="grid">' + "".join(cards) + "</div></section>"
        )

    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta http-equiv="Content-Security-Policy" '
        'content="default-src \'none\'; img-src \'self\'; style-src \'unsafe-inline\'; '
        'base-uri \'none\'; form-action \'none\'">\n'
        "<title>Reality First — Four-way comparison</title>\n"
        "<style>"
        ":root{color-scheme:light;font-family:system-ui,sans-serif;color:#182220;background:#f5f4ef}"
        "*{box-sizing:border-box}body{margin:0;padding:32px 24px}main{max-width:1800px;margin:auto}"
        "h1{font-size:2rem;margin:0 0 12px}h2{font-size:1.2rem;overflow-wrap:anywhere}"
        "h3{font-size:1rem;margin:0 0 8px}p{line-height:1.55}header{max-width:1000px}"
        ".note{color:#45504c}.input{margin-top:36px;border-top:1px solid #c9d0ca;padding-top:16px}"
        ".dimensions{font-size:.9rem;color:#45504c}.grid{display:grid;"
        "grid-template-columns:repeat(4,minmax(240px,1fr));gap:16px;overflow-x:auto;padding-bottom:8px}"
        ".variant{margin:0;padding:16px;background:#fff;border:1px solid #d7ddd7;border-radius:8px}"
        "figcaption{min-height:120px}figcaption p{font-size:.85rem;color:#45504c}"
        "img{display:block;width:100%;height:auto;background:#e8ebe6}"
        "a{color:#245c46}a:focus-visible,summary:focus-visible{outline:3px solid #b77524;outline-offset:3px}"
        "details{margin:12px 0}summary{cursor:pointer;line-height:1.4}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.78rem;line-height:1.5}"
        "footer{margin-top:36px;font-size:.9rem;color:#45504c}"
        "</style>\n</head>\n<body><main><header>"
        "<h1>Four-way comparison</h1>"
        '<p class="note">Compare the same input and selected LUT across four recipes. '
        "No result is selected or rated as best.</p>"
        f"<p>LUT: <strong>{_text(lut.get('name', ''))}</strong></p>"
        "<p>This private local report contains input filenames, hashes and derived images. "
        "The tool does not upload it. Keep the report folder together when moving it.</p>"
        "<details><summary>Report settings and LUT fingerprint</summary>"
        f"<pre>{metadata_json}</pre></details></header>"
        + "".join(rows)
        + "<footer>PNG previews are 8-bit encoded sRGB with the working ICC. "
        "Normalization parameters record calculations, not photo-quality scores. "
        "The input reference has been decoded, color-managed and resized as requested."
        "</footer></main></body></html>\n"
    )
