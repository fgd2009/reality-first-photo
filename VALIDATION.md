# Validation record — 0.1.0a4 CLI preview

Validated on **2026-10-27**, Linux x86_64, Python **3.12.14**. Runtime: NumPy 2.4.6, Pillow 12.2.0, tifffile 2026.5.15. Tests: pytest 9.0.3. Builds: build 1.6.1 and isolated setuptools 84.2.1. Python >=3.12 remains required.

## Scope and acceptance

This bounded stage-1 iteration addresses a batch-workflow gap: a failed image was hard to identify, and ordinary exports did not save progress until the end. It adds read-only `check` diagnosis, atomic progress checkpoints, relative input/stage errors and explicit recovery instructions. The [roadmap](ROADMAP.md) separates reliable operation, voluntary trials, evidence-led interaction choices and later authorized growth. No trial outcomes are claimed.

The existing `demo`, `compare`, Python comparison API and ordinary export flags remain supported. Color algorithms, normalization parameters, LUT interpolation, working ICC policy and supported formats are unchanged. Tests/examples use generated pixels and original synthetic LUTs only. No private photographs, EXIF, private paths, testimonials or third-party presets were obtained or published.

| Check | Result |
| --- | --- |
| Complete regression suite | **159 passed, 0 failed, 0 skipped**, 1.85 seconds |
| Offline audit around the suite | 0 socket/child-process attempts; 0 blocked attempts |
| Source archive and wheel build | Passed; wheel built from source distribution |
| Separate wheel environment | Passed; package imports outside checkout, `pip check` reports no broken requirements |
| Installed workflow | Passed: demo → read-only check → 4-way comparison (12 PNGs) → selected-recipe TIFF export (3 files) |
| Output decoding | RGB8 PNG / RGB16 TIFF, 257×97 synthetic dimensions and exact working ICC checked |
| Read-only diagnosis | Ready/blocked/ignored entries; relative LUT paths; invalid/missing ICC; corrupt and oversized input; RAW, symlinks and name collisions |
| Partial failure / retry | Completed files retained, failing relative input/stage identified; existing output refused unchanged; corrected input succeeds in a new directory |
| Checkpoint write failure | Previous valid JSON remains readable and incomplete; no success result returned |
| Cooperative cancellation | Injected interruption tests plus real Linux SIGINT at a controlled second-decode checkpoint: exit 130, cancelled status, first completed item retained |
| Abrupt termination | Real Linux SIGTERM at that checkpoint: process terminated, prior valid `running` record and first completed item retained |
| Final comparison publication | Complete JSON committed after HTML publication; injected failure/stop before final checkpoint cannot leave a complete overall JSON status |
| Local HTML browser appearance | **Not run this iteration; still unverified.** Prior `file://` navigation was denied with `ERR_BLOCKED_BY_ADMINISTRATOR`; no retry or workaround |

The 159 total includes the previous 113 tests and 46 new diagnosis/recovery cases. Earlier suites overlap; historical totals are not added together. Automated HTML/asset and numerical tests do not establish visual or aesthetic acceptance.

## Diagnosis and recovery contracts

`check` uses the same actual decoder and ICC decisions as export, without exporting, changing inputs or invoking the external EXIF helper. JSON is printed to stdout on request. Unsupported non-image extensions inside a folder are explicitly listed as ignored; known RAW files block the run. Candidate decode failures are collected rather than hiding later files. Optional LUT validation uses the caller's working directory, matching export and comparison. A ready result does not reserve output paths, check available disk space, lock files or promise a later run will succeed. Decoding occurs before resize, so large-image memory/performance remains unverified.

The Pillow excessive-pixel rejection now becomes an actionable handled error. Its safety limit is retained. The test uses only a synthetic oversized PNG header, without allocating the implied image pixels.

Export manifests start at `running`, checkpoint the active relative input and processing stage, and record each completed item. JSON is serialized and written to a new temporary file before atomic replacement. An interrupted or failed write retains the prior checkpoint when possible; disk failure can prevent a final failed/cancelled record. This is not a filesystem transaction or a power-loss guarantee. The program never resumes into an existing output directory.

`complete` in the final JSON is the completion authority. A forced stop between HTML publication and the final comparison checkpoint can leave `index.html` while `compare.json` still says `running`; the HTML now explicitly explains that its existence alone does not prove completion and omits a static overall-success claim. Caught failures/cancellations remove the comparison HTML. A missing or non-complete final record requires review and a fresh output directory.

The installed-package signal harness pauses only a test wrapper at the second image's decode, after the real exporter has saved its checkpoint, then sends an actual OS signal. It verifies Linux process behavior, not a physical keyboard, GUI, every possible interruption instant or another OS. No signal handlers are changed in the product.

## Reproduce

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test,lint]' build
python -m ruff check .
python -m mypy reality_first_normalization
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider tests
python -m build
python3 -m venv /tmp/reality-first-wheel-check
/tmp/reality-first-wheel-check/bin/python -m pip install dist/*.whl
/tmp/reality-first-wheel-check/bin/python -m pip check
python scripts/acceptance.py --python /tmp/reality-first-wheel-check/bin/python
```

Use a fresh verification environment. [The acceptance script](scripts/acceptance.py) creates and removes only its disposable synthetic test tree; it invokes the installed package with isolated Python outside the checkout. Pass the wheel environment to `--python`. An editable install (`pip install -e`) fails this check on purpose, because the imported package then lives inside the source tree. The script verifies diagnosis, comparison, selected-route export, source/LUT hashes, partial failure, repeated-output refusal and a successful new-directory retry. On POSIX it also exercises SIGINT/SIGTERM; elsewhere those signal checks are explicitly not run.

[CI](.github/workflows/ci.yml) runs ruff and mypy in a separate job, and runs the suite, builds the distribution, installs the wheel in a separate environment and runs both the acceptance script and decoded-image checks. The 2026-10-27 result table above records that date's suite. Ruff and mypy are later CI jobs. [GitHub Actions](https://github.com/fgd2009/reality-first-photo/actions) records results for each exact commit. The final local suite disables automatic pytest plugins and bytecode writing; a Python audit hook rejects network/socket and child-process events, with no attempts observed. The separate acceptance harness intentionally launches local test processes. This audit is not a product OS sandbox; installation and package building can use the network.

## Preserved evidence and outstanding acceptance

Existing regressions retain red-fastest CUBE order, float resize precision, actual ICC pixel conversion, high-depth TIFF boundaries, missing LUT errors and unsupported-format rejection. Four routes still start independently from original working pixels before PNG quantization. Manifests retain actual normalization operations and ICC decisions. LUT SHA-256 remains tied to the same bytes parsed, with no stale path-only cache. Comparison checks input/LUT changes between stages; it does not snapshot or lock files.

The HTML uses escaped dynamic text, encoded confined relative image paths, no JavaScript/external assets and a restrictive CSP. Hostile synthetic filenames, link containment and local asset decoding are covered. **Actual browser rendering remains unverified** because the prior managed-browser denial was respected; no alternate browser, port, environment or server was used to bypass it. [Minimal manual steps](docs/TROUBLESHOOTING.md#pending-manual-html-visual-check) describe a future ordinary permitted viewing check, without requesting private photos.

No independent user trial, adoption or repeat-use result is established. The 4/5 and 3/5 roadmap gates are proposals only. Public validation does not establish real-photo aesthetics, physical film accuracy, real RAW behavior, commercial LUT compatibility, arbitrary high-depth ICC conversion, large-image performance, GUI/native installers, Windows/macOS behavior or PyPI publication. The unchanged highlight-rolloff helper has no separate rolloff effect on bounded SDR values. A `py3-none-any` wheel is not cross-platform test evidence.

The baseline 0.1.0a3 at `415735b62cf0b32cf50661a5d3453521a2ec937b` had [successful CI](https://github.com/fgd2009/reality-first-photo/actions/runs/40487306775) and 113 tests. This iteration preserves MIT ownership/licensing and the offline/no-telemetry boundary. Previously denied repository creation, rename and Release attachment upload were not retried. No credentials, account permissions, unrelated repositories, automatic read-only inspection settings or external promotional messages were changed.
