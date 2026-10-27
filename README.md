# Reality First Photo

An offline command-line preview for natural image normalization and your own SDR CUBE LUTs. Version **0.1.0a3** imports supported RGB images, converts them to encoded sRGB, applies bounded exposure/white-balance and tone/color normalization, then applies your selected LUT at an explicit strength. Export as sRGB PNG, JPEG or 16-bit TIFF.

This is an early CLI preview, not a complete photo editor or a calibrated physical-film emulator.

[中文说明](README.zh-CN.md) · [Color contract](docs/COLOR_CONTRACT.md) · [Validation](VALIDATION.md) · [MIT license](LICENSE)

## Quick start: see the result

Requires **Python 3.12 or newer**. These commands use a POSIX shell and install the current preview from GitHub; no Git checkout or test tools are needed. The tested environment is recorded in [VALIDATION.md](VALIDATION.md); Windows and native application packaging are not validated.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install https://github.com/fgd2009/reality-first-photo/archive/refs/heads/main.zip
reality-first-photo demo --output first-look
```

**Open `first-look/comparison.png` in your image viewer.** Its three labeled columns show **Input**, **Normalized** and **Normalized + warm LUT** for a gradient, a color chart and geometric shapes. Normalization strength is 0.6; the final column applies the original warm demo LUT at strength 0.5 after that normalization.

These are **synthetic images, not photographs**. The warm LUT is a simple original affine transform, not a named film stock or commercial look. This comparison demonstrates the processing steps; it does not establish professional photo quality or physical film accuracy.

![Synthetic gradient, color chart and shapes shown as Input, Normalized, and Normalized + warm LUT](docs/images/synthetic-comparison.png)

*Original synthetic demonstration only; no photographs or commercial presets.*

The command works from any directory after installation. It prints the result paths and creates `input/`, `normalized/`, `styled/`, two original CUBE files, `comparison.png` and `demo.json` inside the new `first-look` folder. The two export folders each include three PNGs and a processing manifest. If `first-look` already exists, choose a different name, such as `--output first-look-2`; the demo never overwrites it.

Installation downloads Python dependencies. Image processing runs locally without telemetry, model calls, API keys, account login or network access. The CLI does not invoke an external EXIF helper or read personal preference stores. No photographs, third-party LUTs or XMP presets are included.

## Compare four processing routes

After the demo above, reuse its synthetic inputs and original warm LUT:

```sh
reality-first-photo compare --input first-look/input --output first-compare --lut first-look/demo_warm.cube --normalize-strength 0.6 --lut-strength 1
```

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

The local report consists of `index.html`, `compare.json` and the four image folders. It contains input filenames and hashes, LUT metadata and derived images; the tool does not upload it. Keep the folder together so its relative image links continue to work. The command does not launch a browser or start a server, and only a completed comparison produces the HTML report.

Python callers can use `reality_first_normalization.compare.run_comparison(source, output, lut_path, ...)` with `Path` arguments. It returns 0 on success, 2 on a processing failure, or 130 on cancellation; invalid preflight options/paths raise `ValueError` or `OSError` before creating output.

## Process your own images

```sh
reality-first-photo --input /path/to/tagged-images --output /path/to/new-output --lut /path/to/your.cube --normalize-strength 0.6 --lut-strength 1 --format tiff
```

Use an appropriately licensed LUT authored for **encoded sRGB**. Normalization runs before the LUT; the LUT's own table defines the look, without a later style replacement. Set `--normalize-strength 0` to apply the LUT without normalization. Omit `--lut` for normalization alone. Both strengths accept values from 0 to 1; `--lut-strength 0` blends out the LUT but still validates a supplied file. A missing LUT is an error.

The default preview long edge is 2048 pixels. Choose `--max-long-edge 0` explicitly for full size. Decoding happens before resizing; large-image memory use and performance have not been validated.

Choose a **new output directory** for each run. Existing directories are rejected, and the output cannot be inside an input folder. Folder input searches recursively for JPEG, PNG and TIFF files. Known RAW extensions cause the whole run to fail before creating output; other extensions are ignored. Each run writes a `manifest.json` with its status, completed files, input hashes and color decisions. Each item also records `normalization.applied` and `normalization.operations`, including the actual `exposure_scale` and `white_balance_gains_rgb` when normalization runs. These are calculated processing parameters, not photo-quality scores. Failed or cancelled runs retain partial output; restart into another new directory. Cancellation is covered by injected `KeyboardInterrupt` tests, not physical keyboard or GUI validation.

## If a command stops

| Message or situation | Next step |
| --- | --- |
| Output directory already exists | Pick a new directory, for example `--output first-look-2`. Existing output is preserved. |
| A new input has missing or invalid ICC | Re-export as tagged RGB sRGB in a trusted color-managed tool. Use `--assume-srgb` only for untagged pixels you know are already encoded sRGB; it cannot bypass an invalid ICC. |
| CUBE LUT not found | Correct the `--lut` path to your own supported CUBE file. For the standard image-processing command, omit `--lut` only if you want normalization alone; `compare` requires it. |

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

## License and dependencies

The original project code and demonstration generator are released under the [MIT license](LICENSE), copyright 2026 fgd2009. Dependencies retain their own licenses. The generated working ICC has its own permissive notice; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Supplying a LUT does not change that LUT's ownership or license.
