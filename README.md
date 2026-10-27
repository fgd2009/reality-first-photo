# Reality First Photo

Compare an input reference, natural normalization, your own LUT and their combination **offline on your computer**. Source images stay unchanged; recorded LUT fingerprints, strengths and color decisions let you repeat the recipe you choose.

Version **0.1.0a4** is a **Python command-line preview** for people comfortable with a terminal, supported RGB images and encoded-sRGB 3D CUBE LUTs.

[中文说明](README.zh-CN.md) · [Color contract](docs/COLOR_CONTRACT.md) · [Validation](VALIDATION.md) · [MIT license](LICENSE)

![Static three-column synthetic demo: Input, Normalized, and Normalized + warm LUT](docs/images/synthetic-comparison.png)

*Three-column static demo made from generated gradients, a color chart and shapes: **Input → Normalized (0.6) → Normalized + warm LUT (0.5)**. The warm LUT is an original simple transform. No photographs or commercial presets are shown.*

[Short demo recording plan](docs/DEMO.md) — a plan only; no video has been published.

## Quick start: see the result

Requires **Python 3.12 or newer**. In a POSIX shell, install from GitHub and generate the demo, check its inputs, then create a four-way comparison:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install https://github.com/fgd2009/reality-first-photo/archive/refs/heads/main.zip
reality-first-photo demo --output first-look
reality-first-photo check --input first-look/input --lut first-look/demo_warm.cube --format png
reality-first-photo compare --input first-look/input --output first-compare --lut first-look/demo_warm.cube --normalize-strength 0.6 --lut-strength 1
```

Open **`first-look/comparison.png`** for the static three-column demo. Open **`first-compare/index.html`** where local-file browsing is permitted for the four-route report and individual PNG links. Choose fresh output directories; existing output is never overwritten. No Git checkout or test tools are needed, and the installed commands work outside a source checkout.

Installation downloads dependencies. Image processing stays local without telemetry, model calls, account login or uploads. The CLI does not invoke an external EXIF helper or read personal preference stores.

**Preview boundaries:** you choose a preferred result; the tool does not score images or select a winner. Evidence covers synthetic inputs and the checks in [VALIDATION.md](VALIDATION.md), not real-photo quality or physical film accuracy. Independent user trials have not been completed. RAW, a full GUI and native app installers are outside this preview; cross-platform behavior and actual browser appearance remain unverified. See the [support limits](#supported-inputs-and-limits) and [browser-check status](docs/TROUBLESHOOTING.md#pending-manual-html-visual-check).

## Compare four processing routes

The quick-start commands reuse the demo's generated inputs and original warm LUT.

`check` really decodes the inputs and reports ready, blocked and ignored entries with ICC decisions. It writes no files and does not extract EXIF through an external helper; add `--json` for a machine-readable report on stdout. Match the intended format, preview size and explicit sRGB assumption. A check does not lock files or guarantee they remain unchanged for the later run.

**Open `first-compare/index.html` in your browser** to compare four PNG previews for each input:

| Route | Processing |
| --- | --- |
| Original / input reference | Decode, convert to working sRGB and resize as requested, then export PNG; this is not a source-file copy. |
| Normalized | Apply normalization to the decoded working-space pixels. |
| LUT only | Apply the selected LUT to the decoded working-space pixels without normalization. |
| Normalized + LUT | Normalize first, then apply the selected LUT. |

Each route starts independently from the same decoded input before PNG quantization; the reference PNG is not fed back into another route. The comparison does not select a best result. Use the image links to open/save individual exports and expand the details to inspect recipe strengths, actual normalization operations and ICC decisions. The default normalization strength is 0.6, LUT strength is 1 and preview long edge is 2048; adjust those with `--normalize-strength`, `--lut-strength` and `--max-long-edge`. Comparison output is always **8-bit PNG with the working sRGB ICC**.

For your own images, replace `--input` and `--lut` with local paths, and choose a new output directory. `compare` requires a supported LUT. RAW and unknown or unsupported ICC inputs remain rejected; `--assume-srgb` is only a deliberate declaration for untagged pixels already known to be encoded sRGB.

Input symlinks (including links inside an input folder), existing output paths and outputs inside the input tree are rejected. Supported input names/content and LUT bytes are checked between routes and before completion; a detected change leaves a failed report without a success page. This is change detection, not an immutable file snapshot.

The local report consists of `index.html`, `compare.json` and the four image folders. It contains input filenames and hashes, LUT metadata and derived images; the tool does not upload it. Keep the folder together so its relative image links continue to work. The command does not launch a browser or start a server. Successful completion requires `compare.json` to say `complete`; a forced stop can leave an HTML file before that final checkpoint, so the page's existence alone is insufficient.

Python callers can use `reality_first_normalization.compare.run_comparison(source, output, lut_path, ...)` with `Path` arguments. It returns 0 on success, 2 on a processing failure, or 130 on cancellation; invalid preflight options/paths raise `ValueError` or `OSError` before creating output.

### Export the route you choose

After comparing, choose a route yourself and rerun the original inputs through the standard export command with the **exact strengths, LUT, preview size and color assumption recorded in your report**. For example, only if you chose the combined route from the example above:

```sh
reality-first-photo --input first-look/input --output chosen-tiff --lut first-look/demo_warm.cube --normalize-strength 0.6 --lut-strength 1 --max-long-edge 2048 --format tiff
```

For normalization alone, omit the LUT; for LUT only, set normalization strength to zero; for the input reference, do both. Use your actual comparison strengths if they differ from the example. TIFF is 16-bit while comparison PNGs are 8-bit; do not feed the exported reference PNG back into the pipeline. See the [route mapping and recovery guide](docs/TROUBLESHOOTING.md#export-the-route-you-chose).

## Process your own images

```sh
reality-first-photo --input /path/to/tagged-images --output /path/to/new-output --lut /path/to/your.cube --normalize-strength 0.6 --lut-strength 1 --format tiff
```

Use an appropriately licensed LUT authored for **encoded sRGB**. Normalization runs before the LUT; the LUT's own table defines the look, without a later style replacement. Set `--normalize-strength 0` to apply the LUT without normalization. Omit `--lut` for normalization alone. Both strengths accept values from 0 to 1; `--lut-strength 0` blends out the LUT but still validates a supplied file. A missing LUT is an error.

The default preview long edge is 2048 pixels. Choose `--max-long-edge 0` explicitly for full size. Decoding happens before resizing; large-image memory use and performance have not been validated.

Choose a **new output directory** for each run. Existing directories are rejected, and the output cannot be inside an input folder. Folder input searches recursively for JPEG, PNG and TIFF files. Known RAW extensions cause the whole run to fail before creating output; other extensions are ignored. Each processing run writes a `manifest.json` with its status, completed files, input hashes and color decisions. Each item also records `normalization.applied` and `normalization.operations`, including the actual `exposure_scale` and `white_balance_gains_rgb` when normalization runs. These are calculated processing parameters, not photo-quality scores. Failed or cancelled runs retain partial output and record the active/failed relative filename and processing stage; fix the cause and restart into another new directory. Abrupt termination can leave a `running` or missing final record, which must be treated as incomplete. Validation includes injected interruptions and real Linux SIGINT/SIGTERM signals at a controlled processing checkpoint; physical keyboard and GUI behavior remain unverified.

## If a command stops

| Message or situation | Next step |
| --- | --- |
| Output directory already exists | Pick a new directory, for example `--output first-look-2`. Existing output is preserved. |
| A new input has missing or invalid ICC | Re-export as tagged RGB sRGB in a trusted color-managed tool. Use `--assume-srgb` only for untagged pixels you know are already encoded sRGB; it cannot bypass an invalid ICC. |
| CUBE LUT not found | Correct the `--lut` path to your own supported CUBE file. For the standard image-processing command, omit `--lut` only if you want normalization alone; `compare` requires it. |

Use the [troubleshooting guide](docs/TROUBLESHOOTING.md) for read-only checks, status interpretation and the pending synthetic HTML visual checklist. Actual browser appearance remains unverified in the managed development environment: local-file navigation was blocked with `ERR_BLOCKED_BY_ADMINISTRATOR`. Do not bypass that policy; structural HTML tests are not visual browser validation.

## Supported inputs and limits

| Input or operation | Preview behavior |
| --- | --- |
| RGB8 JPEG and PNG | Valid RGB ICC profiles are converted to working sRGB through LittleCMS. Animated/multi-frame images, including APNG, are rejected. |
| TIFF | Uncompressed, single-page, interleaved RGB only; 8/16-bit integer or bounded float32 samples. |
| High-depth TIFF ICC | Requires the exact bundled working ICC, or an untagged image with an explicit sRGB assumption. Arbitrary high-depth ICC conversion is unavailable. |
| Untagged input | Rejected unless `--assume-srgb` explicitly declares that its pixels are encoded sRGB. This option cannot bypass an invalid embedded ICC. |
| Resizing and output | Float32 channel resizing; 16-bit TIFF or 8-bit PNG/JPEG output, all with the working ICC. JPEG is lossy. |
| LUT | Red-fastest 3D CUBE, trilinear interpolation, finite positive domain widths and output nodes in [0,1]. Default domain and `DOMAIN_MIN`/`DOMAIN_MAX` are supported. Unknown directives, 1D/combined tables and `LUT_3D_INPUT_RANGE` are rejected; no inferred log/HDR transforms. |

RAW/DNG, grayscale, CMYK, alpha/color-key transparency, 16-bit PNG, compressed or multi-page TIFF, packed TIFF depths and non-default TIFF orientation are rejected. A full GUI, commercial presets and native app installers are outside this preview. Real photographs, real RAW, commercial LUTs, physical film accuracy and cross-platform behavior have not been validated.

## Development and validation

```sh
git clone https://github.com/fgd2009/reality-first-photo.git
cd reality-first-photo
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]' build
python -m pytest -q tests
python -m build
```

The existing `--input` / `--output` command remains available for image processing. From a source checkout, `python -m examples.generate_demo demo-assets` still generates the original synthetic inputs and LUTs without processing them.

The [CI workflow](.github/workflows/ci.yml) runs the candidate tests on Ubuntu with Python 3.12, builds the package, installs its wheel in a separate environment and runs the complete demo and four-way comparison outside the source checkout. It does not publish to PyPI. See [VALIDATION.md](VALIDATION.md) for the current executed checks and remaining limits; historical results from a larger recovery tree are not additional test coverage for this repository.

The [roadmap](ROADMAP.md) starts with reliable end-to-end use, then a [voluntary local tryout](docs/TRYOUT.md). Its small-group learning gates are proposed criteria, not collected user results. No unsolicited outreach or automatic best-image choice is part of this work.

## License and dependencies

The original project code and demonstration generator are released under the [MIT license](LICENSE), copyright 2026 fgd2009. Dependencies retain their own licenses. The generated working ICC has its own permissive notice; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Supplying a LUT does not change that LUT's ownership or license.
