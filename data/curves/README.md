# Digitized Kodak chart samples

These CSV files are pixel readings made by `scripts/digitize_kodak_curves.py` from rendered pages of two Kodak Alaris datasheets. They are not numeric tables released by the manufacturer. They are not evidence that a picture from this project matches either film.

The PDF and the rendered page are not stored here. Spectral-sensitivity curves were not digitized: on the published page they cross, sit on a grid, and are interrupted by labels, and the automatic trace did not stay on the ink. No numbers were invented for that chart.

| File | Document | Chart | What was traced |
| --- | --- | --- | --- |
| `kodak_portra_400_characteristic.csv` | E-4050, January 2025, revised 1-25 | Status M characteristic curves | Blue, green and red density. The flat toe under the B/G/R labels is missing. |
| `kodak_portra_400_spectral_dye_density.csv` | same | Diffuse spectral dye density | Midscale neutral and minimum density, until the curves meet. The long-wavelength rise after that is missing. |
| `kodak_ektar_100_characteristic.csv` | E-4046, January 2025, revised 1/25 | Status M characteristic curves | Same limits as the Portra characteristic file. |
| `kodak_ektar_100_spectral_dye_density.csv` | same | Diffuse spectral dye density | Same limits as the Portra dye-density file. |

Each CSV header records the publication, the PDF sha256 that was read, the page, the axis box in pixels, the scale per pixel, and an error estimate of about two pixels. At the render scale used by the script that is roughly 0.02 in log exposure or wavelength-axis units and about 0.02 in density.

`warm-negative-400` uses a logistic fit to the Portra green Status M curve, with layer spacing from the blue and red curves. `neutral-negative-100` does the same for Ektar. The dye-density samples were not turned into the dye matrix, because the trace stops where the two curves meet. Both recipes stay `unverified`.
