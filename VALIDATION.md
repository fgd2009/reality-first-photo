# Validation record — 0.1.0a3 CLI preview

Validated on **2026-10-27**, Linux x86_64, Python **3.12.14**. Runtime versions remain NumPy 2.4.6, Pillow 12.2.0 and tifffile 2026.5.15; tests use pytest 9.0.3. Package builds use build 1.6.1 and isolated setuptools 84.2.1. Python >=3.12 is required.

## Scope and acceptance

This iteration adds a formal offline `compare` command and Python `run_comparison` function. Each input is exported through four independent recipes: input reference, normalization only, LUT only, and normalization followed by LUT. A local `index.html` and `compare.json` explain the settings and link the PNG exports. No result is scored or selected as best.

The existing export pipeline is reused. No color algorithm, normalization parameter, CUBE interpolation, ICC policy, RAW support or GUI is added or changed. The original `demo` and standard image-processing commands remain supported. Public tests and examples use generated pixels and original synthetic LUTs only; no user photographs, EXIF or private paths were obtained or published for this work.

| Check | Result |
| --- | --- |
| Complete regression suite | **113 passed, 0 failed, 0 skipped**, 1.53 seconds |
| Offline audit around the complete suite | 0 socket/child-process attempts; 0 blocked attempts |
| Source archive and wheel build | Passed; wheel built from source distribution |
| Separate environment wheel installation | Passed; `pip check` found no broken requirements |
| Installed four-way CLI outside checkout | Passed: 3 synthetic inputs, 12 PNG exports, complete JSON and HTML |
| Input and LUT fingerprints | Preserved; all four manifests match the same source hashes and selected LUT bytes |
| Dimensions, export type, ICC | Passed: fixture exports 257×97, RGB8 PNG with exact working ICC |
| Numerical routes and zero strengths | Passed against independent affine LUT equations and corresponding equality cases |
| Output and input path protection | Existing file/dir/link, dangling links, input-tree output aliases and name collisions rejected before output creation |
| HTML structure, escaping and links | Passed for Unicode, quotes, ampersands, angle brackets, spaces, #, ?, %, backslashes and nested duplicate basenames |
| Mid-run changes / partial failure / cancellation | Failed or cancelled JSON retained; no successful index page remains |
| Local browser visual opening | **Blocked by environment policy**: Chromium rejected `file://` navigation with `ERR_BLOCKED_BY_ADMINISTRATOR` |

The 113-test total includes the previous 67 tests and 46 new comparison/provenance regressions. Historical test runs are not added to this total.

## Four-route correctness and provenance

All four routes start independently from the original input, with the same ICC policy, preview size and explicit untagged-sRGB assumption. The input reference is decoded, color-converted/resized working sRGB exported as PNG; it is not a byte-for-byte copy of the source file. Processing uses the working pixels before export quantization, rather than feeding a reference PNG back into another route.

Independent synthetic checks cover normalization-only, LUT-only and normalization-then-LUT output. A separately written affine equation verifies the original warm demonstration LUT within PNG quantization tolerance. With normalization or LUT strength zero, the appropriate pairs become equal. Source hashes, dimensions, per-route normalization operations and ICC decisions are checked.

LUT provenance was repaired without changing its rendering algorithm: the loader now parses and hashes the same bytes, without a stale path-only cache. Tests replace a previously loaded LUT at the same path and change its file after a read; the rendered table and recorded SHA-256 remain tied to the bytes actually parsed.

Comparison fingerprints supported input names/content and LUT bytes between routes and before completion. Tests cover modification, addition, deletion, renaming, a same-content LUT switched to a symlink, and source changes during HTML rendering. Changes fail the comparison instead of claiming that inconsistent outputs belong together. This is detection between stages, not file locking or an immutable snapshot.

## Local report safety

The HTML renderer is a pure function. It requires a complete report, escapes all dynamic text/JSON and separately percent-encodes relative image URLs. Image links must remain beneath their fixed recipe folder and end in PNG. Tests confirm that hostile synthetic names do not create scripts, event handlers, remote URLs, query strings or fragments. The document has a restrictive content-security policy and uses no JavaScript, external fonts, network assets or server.

Only a complete comparison writes the final HTML page; failures and cancellation preserve partial outputs and explicit JSON status. All generated image links are checked against real local output files, and those PNGs are decoded and inspected. Actual browser rendering could not be verified in this managed execution environment because local-file navigation was blocked. No browser policy, network setting or server workaround was used; cross-browser behavior is not claimed.

Reports stay on the user's filesystem and contain filenames, hashes, calculated operations, ICC decisions and derived images. Processing skips external EXIF extraction. There is no upload, telemetry, model call, quality score or automatic best-image choice.

## Reproduce

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]' build
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider tests
python -m build
python -m pip check
reality-first-photo demo --output first-look
reality-first-photo compare --input first-look/input --output first-compare --lut first-look/demo_warm.cube --normalize-strength 0.6 --lut-strength 1
```

The [CI workflow](.github/workflows/ci.yml) runs the complete suite, builds packages, installs the wheel in a separate environment, then runs both the synthetic demo and four-way comparison outside the checkout. It checks complete reports and all 12 comparison exports. [GitHub Actions](https://github.com/fgd2009/reality-first-photo/actions) records the outcome for each exact commit.

The final local suite disabled automatic pytest plugins and bytecode writing. A Python audit hook rejected socket and child-process events; none occurred. This is a test-harness check, not a product OS sandbox. Installing dependencies and building packages can use the network; processing does not.

## Preserved limits and prior evidence

The full suite retains red-fastest CUBE, float-resize precision, TIFF16, real ICC pixel conversion, missing LUT, invalid/unknown ICC and unsupported-format regressions. RAW, alpha/transparency, multi-frame input and other unsupported formats still fail explicitly. Existing source files are read without modification; existing output paths are rejected.

This public validation does not establish photographic quality, physical film accuracy, real RAW behavior, commercial LUT compatibility, arbitrary high-depth ICC conversion, large-image performance, native GUI, Windows/macOS application behavior, native installers, signing or PyPI publication. The existing highlight-rolloff helper has no separate rolloff effect on bounded SDR values; that curve remains unchanged. The `py3-none-any` wheel tag does not prove cross-platform testing.

The previous 0.1.0a2 release at `a065c860e576c73760b138e4e66b6079389d0a15` had [successful CI](https://github.com/fgd2009/reality-first-photo/actions/runs/40479919356), 67 tests and a verified installed demo. Earlier 55-, 32- and 100-test records overlap and are not additive coverage.

The project remains MIT-licensed. Previously denied GitHub Release attachment upload was not retried. No credentials, permissions, other business repositories or external promotional messages were changed.
