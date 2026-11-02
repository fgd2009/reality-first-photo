"""Read characteristic and dye-density curves from two Kodak datasheet PDFs.

The PDFs are downloaded into a cache outside the repository. Rendered pages and
the PDFs are not written into the tree. Outputs are CSV samples under
data/curves/. Those samples are this project's pixel readings, not a numeric
table published by Kodak.

Requires pypdfium2 (Apache-2.0 / PDFium). It is not a runtime dependency:

    python -m pip install pypdfium2
    python scripts/digitize_kodak_curves.py

The axis boxes were measured on a scale-3 render of the PDFs whose sha256 is
checked below. If Kodak replaces a file, the sha256 check stops the script
instead of writing a mis-registered curve.
"""
from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "curves"
CACHE = Path("/tmp/reality-first-photo-kodak-pdf")
SCALE = 3

# sha256 of the PDFs fetched on 2026-11-02. Filled after the first download
# if empty; the committed script pins the values once known.
EXPECTED_SHA256 = {
    "e4050": "70b15171673c5d01505f58ace448995ad72acbe5e401d1966563a61ac0712838",
    "e4046": "38a41d47ad006cd563793033f83c8f9ef6cdd3c8300695c31facfc71d368f8db",
}

DOCUMENTS = {
    "e4050": {
        "url": "https://www.kodakprofessional.com/sites/default/files/2025-07/e4050.pdf",
        "publication": "E-4050",
        "revision": "January 2025, revised 1-25",
        "title": "KODAK PROFESSIONAL PORTRA 400 Film",
        "stem": "kodak_portra_400",
        "page": 4,
        "charts": {
            "characteristic": {
                "box": (248, 314, 793, 858),
                "x": (-4.0, 1.0),
                "y": (0.0, 4.0),
                "x_name": "log_exposure_lux_seconds",
                "y_name": "status_m_density",
                "curves": ("status_m_blue", "status_m_green", "status_m_red"),
                "note": "Top curve is blue Status M (B), then green, then red. The flat toe under the B/G/R labels is not included.",
            },
            "spectral_dye_density": {
                "box": (1076, 316, 1621, 858),
                "x": (400.0, 700.0),
                "y": (0.0, 2.5),
                "x_name": "wavelength_nm",
                "y_name": "diffuse_spectral_density",
                "curves": ("midscale_neutral", "minimum_density"),
                "note": "Upper curve is midscale neutral, lower is minimum density. Sampling stops where the two curves meet; the long-wavelength rise after that is not included.",
            },
        },
    },
    "e4046": {
        "url": "https://www.kodakprofessional.com/sites/default/files/2025-07/e4046.pdf",
        "publication": "E-4046",
        "revision": "January 2025, revised 1/25",
        "title": "KODAK PROFESSIONAL EKTAR 100 Film",
        "stem": "kodak_ektar_100",
        "page": 4,
        "charts": {
            "characteristic": {
                "box": (245, 326, 793, 874),
                "x": (-3.0, 2.0),
                "y": (0.0, 4.0),
                "x_name": "log_exposure_lux_seconds",
                "y_name": "status_m_density",
                "curves": ("status_m_blue", "status_m_green", "status_m_red"),
                "note": "Top curve is blue Status M (B), then green, then red. The flat toe under the B/G/R labels is not included.",
            },
            "spectral_dye_density": {
                "box": (1074, 320, 1622, 868),
                "x": (400.0, 700.0),
                "y": (0.0, 2.5),
                "x_name": "wavelength_nm",
                "y_name": "diffuse_spectral_density",
                "curves": ("midscale_neutral", "minimum_density"),
                "note": "Upper curve is midscale neutral, lower is minimum density. Sampling stops where the two curves meet; the long-wavelength rise after that is not included.",
            },
        },
    },
}


def main() -> None:
    import pypdfium2 as pdfium

    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    for key, doc in DOCUMENTS.items():
        pdf_path = _download(key, doc["url"])
        digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        expected = EXPECTED_SHA256[key]
        if expected and digest != expected:
            raise SystemExit(f"{key} sha256 {digest} does not match pinned {expected}")
        print(f"{key} sha256 {digest}")
        page = pdfium.PdfDocument(pdf_path)[doc["page"] - 1]
        image = page.render(scale=SCALE).to_pil().convert("L")
        ink = np.asarray(image) < 110
        clean = _drop_long_lines(ink)
        for chart_name, chart in doc["charts"].items():
            samples = _trace(clean, chart["box"], len(chart["curves"]))
            width = chart["box"][2] - chart["box"][0]
            if len(samples) < 0.55 * width:
                print(f"SKIP {doc['stem']} {chart_name}: only {len(samples)} columns traced")
                continue
            path = OUT / f"{doc['stem']}_{chart_name}.csv"
            _write_csv(path, doc, chart_name, chart, samples, digest)
            print(f"wrote {path.name} columns {len(samples)}")


def _download(key: str, url: str) -> Path:
    dest = CACHE / f"{key}.pdf"
    if not dest.is_file():
        request = urllib.request.Request(url, headers={"User-Agent": "reality-first-photo-digitize"})
        with urllib.request.urlopen(request, timeout=60) as response:
            dest.write_bytes(response.read())
    return dest


def _drop_long_lines(ink: np.ndarray) -> np.ndarray:
    clean = ink.copy()
    height, width = clean.shape
    for y in range(height):
        row = clean[y]
        x = 0
        while x < width:
            if not row[x]:
                x += 1
                continue
            end = x
            while end < width and row[end]:
                end += 1
            if end - x > 50:
                clean[y, x:end] = False
            x = end
    for x in range(width):
        column = clean[:, x]
        y = 0
        while y < height:
            if not column[y]:
                y += 1
                continue
            end = y
            while end < height and column[end]:
                end += 1
            if end - y > 50:
                clean[y:end, x] = False
            y = end
    return clean


def _clusters(clean: np.ndarray, x: int, y0: int, y1: int) -> list[float]:
    ys = np.flatnonzero(clean[y0:y1, x]) + y0
    if len(ys) == 0:
        return []
    groups: list[float] = []
    acc = [int(ys[0])]
    previous = int(ys[0])
    for raw in ys[1:]:
        y = int(raw)
        if y - previous <= 5:
            acc.append(y)
        else:
            if len(acc) >= 2:
                groups.append(float(np.mean(acc)))
            acc = [y]
        previous = y
    if len(acc) >= 2:
        groups.append(float(np.mean(acc)))
    return groups


def _trace(clean: np.ndarray, box: tuple[int, int, int, int], count: int) -> list[tuple[int, list[float]]]:
    x0, y0, x1, y1 = box
    seed = None
    tracks: list[float] = []
    for x in range(x0 + (x1 - x0) // 3, x0 + 2 * (x1 - x0) // 3):
        found = _clusters(clean, x, y0 + 2, y1 - 2)
        if len(found) == count:
            seed = x
            tracks = sorted(found)
            break
    if seed is None:
        return []

    def step(current: list[float], x: int) -> list[float] | None:
        found = _clusters(clean, x, y0 + 2, y1 - 2)
        nxt: list[float] = []
        used: set[int] = set()
        for track in current:
            best = None
            best_distance = 1e9
            for index, value in enumerate(found):
                if index in used:
                    continue
                distance = abs(value - track)
                if distance < best_distance:
                    best_distance = distance
                    best = index
            if best is None or best_distance > 16:
                return None
            used.add(best)
            nxt.append(found[best])
        return nxt

    left: list[tuple[int, list[float]]] = []
    current = list(tracks)
    for x in range(seed - 1, x0 + 4, -1):
        nxt = step(current, x)
        if nxt is None:
            break
        current = nxt
        left.append((x, list(current)))
    right: list[tuple[int, list[float]]] = [(seed, list(tracks))]
    current = list(tracks)
    for x in range(seed + 1, x1 - 4):
        nxt = step(current, x)
        if nxt is None:
            break
        current = nxt
        right.append((x, list(current)))
    return list(reversed(left)) + right


def _write_csv(path: Path, doc: dict, chart_name: str, chart: dict, samples: list, pdf_sha256: str) -> None:
    x0, y0, x1, y1 = chart["box"]
    x_min, x_max = chart["x"]
    y_min, y_max = chart["y"]
    # One pixel is the axis scale divided by the inner width or height.
    x_per_px = (x_max - x_min) / (x1 - x0)
    y_per_px = (y_max - y_min) / (y1 - y0)
    lines = [
        f"# source_publication: {doc['publication']}",
        f"# source_title: {doc['title']}",
        f"# source_revision: {doc['revision']}",
        f"# source_url: {doc['url']}",
        f"# source_pdf_sha256: {pdf_sha256}",
        f"# source_page: {doc['page']}",
        f"# chart: {chart_name}",
        "# method: pypdfium2 scale-3 render; dark pixels traced after dropping straight rules longer than 50 px",
        f"# axis_box_px: {x0},{y0},{x1},{y1}",
        f"# x_axis: {chart['x_name']} from {x_min} at x={x0} to {x_max} at x={x1}",
        f"# y_axis: {chart['y_name']} from {y_min} at y={y1} to {y_max} at y={y0}",
        f"# scale_per_pixel: x={x_per_px:.5f} y={y_per_px:.5f}",
        (
            "# reading_error_estimate: about 2 px, so roughly "
            f"{2 * x_per_px:.3f} in x and {2 * y_per_px:.3f} in y, plus any toe clipped by axis labels"
        ),
        f"# curves: {', '.join(chart['curves'])}. {chart['note']}",
        "# disclaimer: Digitized by this project from the published chart. Not a numeric table released by the manufacturer. Not evidence that a picture matches the film.",
        ",".join([chart["x_name"], *chart["curves"]]),
    ]
    for x, ys in samples:
        data_x = x_min + (x - x0) / (x1 - x0) * (x_max - x_min)
        values = []
        for y in ys:
            data_y = y_min + (y1 - y) / (y1 - y0) * (y_max - y_min)
            values.append(f"{data_y:.4f}")
        lines.append(f"{data_x:.4f}," + ",".join(values))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
