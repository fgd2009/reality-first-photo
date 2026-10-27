# Reality First Photo

An offline command-line preview for natural image normalization and your own SDR CUBE LUTs. Version **0.1.0a1** imports supported RGB images, converts them to encoded sRGB, applies bounded exposure/white-balance and tone/color normalization, then applies your selected LUT at an explicit strength. Export as sRGB PNG, JPEG or 16-bit TIFF.

This is an early CLI preview, not a complete photo editor or a calibrated physical-film emulator.

[中文说明](README.zh-CN.md) · [Color contract](docs/COLOR_CONTRACT.md) · [Validation](VALIDATION.md) · [MIT license](LICENSE)

## Quick start

Requires **Python 3.12 or newer**. These commands use a POSIX shell. The tested environment and exact checks are recorded in [VALIDATION.md](VALIDATION.md); Windows and native application packaging are not validated.

```sh
git clone https://github.com/fgd2009/reality-first-photo.git
cd reality-first-photo
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'

python -m examples.generate_demo demo
reality-first-photo --input demo/input --output out-identity --lut demo/identity.cube --normalize-strength 0 --format tiff
reality-first-photo --input demo/input --output out-warm --lut demo/demo_warm.cube --normalize-strength 0.6 --lut-strength 0.5 --format png
```

Installation downloads Python dependencies. Image processing runs locally without telemetry, model calls, API keys, account login or network access. The CLI does not invoke an external EXIF helper or read personal preference stores.

The demo generator creates three original synthetic images (a gradient, a color chart and geometric shapes) and two original demonstration LUTs. The warm LUT is a simple affine transform, not a named film stock or commercial look. No photographs, third-party LUTs or XMP presets are included.

## Process your own images

```sh
reality-first-photo --input /path/to/tagged-images --output /path/to/new-output --lut /path/to/your.cube --normalize-strength 0.6 --lut-strength 1 --format tiff
```

Use an appropriately licensed LUT authored for **encoded sRGB**. Normalization runs before the LUT; the LUT's own table defines the look, without a later style replacement. Set `--normalize-strength 0` to apply the LUT without normalization. Omit `--lut` for normalization alone. Both strengths accept values from 0 to 1; `--lut-strength 0` blends out the LUT but still validates a supplied file. A missing LUT is an error.

The default preview long edge is 2048 pixels. Choose `--max-long-edge 0` explicitly for full size. Decoding happens before resizing; large-image memory use and performance have not been validated.

Choose a **new output directory** for each run. Existing directories are rejected, and the output cannot be inside an input folder. Folder input searches recursively for JPEG, PNG and TIFF files. Known RAW extensions cause the whole run to fail before creating output; other extensions are ignored. Each run writes a `manifest.json` with its status, completed files, input hashes and color decisions. Failed or cancelled runs retain partial output; restart into another new directory. Cancellation is covered by injected `KeyboardInterrupt` tests, not physical keyboard or GUI validation.

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
python -m pytest -q tests
python -m pip install build
python -m build
```

The [CI workflow](.github/workflows/ci.yml) runs the candidate tests on Ubuntu with Python 3.12, builds the package, installs its wheel in a separate environment and exercises synthetic export. It does not publish to PyPI. See [VALIDATION.md](VALIDATION.md) for the current executed checks and remaining limits; historical results from a larger recovery tree are not additional test coverage for this repository.

## License and dependencies

The original project code and demonstration generator are released under the [MIT license](LICENSE), copyright 2026 fgd2009. Dependencies retain their own licenses. The generated working ICC has its own permissive notice; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Supplying a LUT does not change that LUT's ownership or license.
