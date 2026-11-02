# Reference set

A reference set is a directory of image pairs. `delta-e --reference-set` prints one JSON object and exits 2 if any pair fails its gate. The tool does not upload the directory.

```text
my-set/
  reference-set.json
  items/
    chart-a/
      reference.png
      sample.png
```

`reference-set.json`:

```json
{
  "format": "reality-first-reference-set-v1",
  "license": "Say who may use these images. This file does not grant a license.",
  "thresholds": {"mean_max": 10.0, "p95_max": 20.0, "role": "placeholder"},
  "items": [
    {"id": "chart-a", "reference": "items/chart-a/reference.png", "sample": "items/chart-a/sample.png"}
  ]
}
```

`format` must be `reality-first-reference-set-v1`. `license` must be non-empty. Paths are relative to the JSON file, must stay inside the directory, and must not contain `..`. Images are decoded with the same reader as export, then compared with CIEDE2000 in encoded sRGB. Shapes must match.

If `thresholds` is omitted, the command uses the placeholder gates: mean ≤ 10 and 95th percentile ≤ 20. Those numbers are round stand-ins. Passing them does not mean a picture matches a film stock. `--mean-max` and `--p95-max` override the file and set the role to `user`. `--report-only` prints measurements and sets `passed` to null. A role of `film-match` is rejected.

Do not put scans or datasheet figures in this repository unless their license is already cleared in [CALIBRATION_SOURCES.md](CALIBRATION_SOURCES.md). A personal set stays on your machine.
