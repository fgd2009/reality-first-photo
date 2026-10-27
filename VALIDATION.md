# Validation record — 0.1.0a1 CLI preview

Current validation: **2026-10-27**, Linux x86_64, Python **3.12.14**. A new virtual environment installed the pinned dependencies from `pyproject.toml`: NumPy 2.4.6, Pillow 12.2.0, tifffile 2026.5.15 and pytest 9.0.3. The build frontend was build 1.6.1; isolated package builds used setuptools 84.2.1.

## Current results

| Check | Result |
| --- | --- |
| Candidate regression suite | **55 passed, 0 failed, 0 skipped**, 0.59 seconds |
| Offline test audit | No socket or child-process attempts; 0 blocked attempts |
| Clean editable installation and dependency consistency | Passed; `pip check` reported no broken requirements |
| Source distribution and wheel build | Passed; wheel built from the source distribution |
| Separate virtual environment wheel installation | Passed; `pip check` reported no broken requirements |
| Installed command outside the source tree | Passed; 15 exports from 3 generated images |
| Export dimensions, sample depth and ICC | Passed: 257×97; uint16 TIFF / uint8 PNG and JPEG; exact working ICC |
| Input SHA-256 before and after export | Unchanged for all 3 inputs |
| ZIP path/entry review and common secret-pattern scan | Passed; no traversal, symlinks, encrypted entries or matched secret patterns |
| GitHub repository creation | Blocked: the authenticated integration returned `GraphQL: Resource not accessible by integration (createRepository)` |
| Remote push / exact remote commit / public CI | Not run: repository creation was denied; a follow-up metadata read still returned HTTP 404 |

The regression run disabled automatic pytest plugin loading and bytecode writing. A Python audit hook rejected socket and child-process events; none occurred. This describes the test harness, not a product-level OS sandbox. Installation/build downloaded dependencies; CLI processing contains no telemetry, network or model-call implementation.

The uploaded source archive was `release_candidate.zip`, 53,054 bytes, SHA-256 `8f12a99143c62335f7e8ee1d17fc012750cb153a4e7306391131e7c024297ab8`. macOS ZIP sidecar metadata was excluded from the publication tree. Only original code, documentation, tests, the generated working ICC and the original demonstration generator are included. No real photographs, commercial LUT/XMP assets, private configuration or credentials are included.

GitHub identity was verified as `fgd2009`, and the intended target was `fgd2009/reality-first-photo`. This is a publication-permission blocker, not a failed code check. No repository or release was created by this attempt. The local source commit and built artifacts are ready for publication when a repository can be created through an authorized account or app. No credential, permission-scope or network configuration changes were attempted.

## Regression scope

The suite verifies red-fastest CUBE ordering against an independent flat-row scalar trilinear reference (error <2e-6), non-default/narrow domains, title whitespace and comments, and strict rejection of malformed or unsupported CUBE directives. It covers missing LUTs, explicit strengths 0/0.5/1, normalization, default preview resizing and explicit full size.

Precision checks retain 2048 distinct levels when resizing a 4096-level ramp, and retain 4096 levels through TIFF16 within 1/65535. A generated linear RGB ICC with the same name and primaries as the working ICC transforms code 128 to encoded sRGB near 188; the test checks actual pixel conversion and the output ICC, rather than profile relabelling.

Input checks cover missing/broken ICC, explicit sRGB assumption, high-depth profile restrictions, alpha/color-key transparency, multi-frame PNG, format/extension mismatches, packed depths, compressed TIFF and RAW rejection. Mixed RAW folders fail before export. Existing output directories are never overwritten; repeated import to a new directory succeeds. Cancellation is injected as `KeyboardInterrupt`, not tested with a physical keyboard.

Three release fixes were made during this review: unsupported CUBE directives now fail instead of being ignored, multi-frame images fail instead of silently selecting the first frame, and known RAW files in a mixed input folder fail before output is created. The existing normalization parameters and red-fastest interpolation were retained.

## Installed-wheel synthetic exports

The console entry point was executed in a separate virtual environment, from outside the source checkout. Inputs were original generated gradients, a color chart and geometry. Five batches exported three files each:

- Identity LUT with normalization off → TIFF16.
- Normalization strength 0.6 without a LUT → TIFF16.
- Normalization 0.6 then original affine-warm LUT at strength 0.5 → TIFF16, PNG and JPEG.

All 15 files and their manifests were inspected. Identity TIFF16 maximum error was **0.0** for the generated 8-bit inputs. Using the normalization-only TIFF output and an independent affine equation for the warm LUT, maximum error was **1.4496070801839345e-5** for TIFF16 (within 2/65535) and **0.001962615396353094** for PNG (within 1/255 + 1/65535). JPEG dimensions, depth and ICC were checked; JPEG is lossy and has no pixel-identity claim. All source hashes remained unchanged.

## Reproduce

From a source checkout with Python >=3.12:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]' build
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider tests
python -m build
python -m pip check
python -m examples.generate_demo demo
reality-first-photo --input demo/input --output out-identity --lut demo/identity.cube --normalize-strength 0 --format tiff
reality-first-photo --input demo/input --output out-warm --lut demo/demo_warm.cube --normalize-strength 0.6 --lut-strength 0.5 --format png
```

The [CI workflow](.github/workflows/ci.yml) also installs the built wheel into a separate environment and runs a synthetic export outside the checkout.

## Limits and historical evidence

Not validated: real photographs or RAW, commercial LUTs/XMP, physical film accuracy, arbitrary high-depth ICC conversion, large-image memory/performance, native GUI, macOS/Windows application behavior, native installers, signing or PyPI publication. The `py3-none-any` wheel tag describes package contents, not a cross-platform test result. The existing highlight-rolloff helper produces no separate rolloff effect on bounded SDR values; this preview does not claim such an effect or change its curve.

The supplied candidate previously recorded 32 passing tests on macOS Python 3.13.4. That is historical evidence only. A separate larger recovery tree's 100-test result overlaps the candidate and is **not added** to the current 55 tests.
