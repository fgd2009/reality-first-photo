# Parametric film model

Status: synthetic tests only. No bundled recipe has been compared with a scanned negative, print or slide. A passing test shows that the code matches this document, not that a picture looks like a commercial stock.

## 中文概要

这一版在编码 sRGB 工作像素上加了一条可选的胶片模型，顺序是：

1. 按 IEC 61966-2-1 把编码 sRGB 变回线性光，当作相对曝光的代理，不是相机场景线性数据。
2. 用一条可调的 Hurter–Driffield 特性曲线把 log10 曝光变成光学密度。
3. 用 3×3 矩阵把 RGB 曝光分到青、品红、黄三层，再用另一组 3×3 染料吸收和 Beer–Lambert 定律得到透过率。
4. `negative-print` 再走一次相纸；`reversal` 把曲线补成“曝光越多、染料越少”。
5. 颗粒加在染料密度上，种子可复现。halation 是高光多余曝光的高斯扩散，发生在特性曲线之前。

五套配方的常数是本项目自选的整数级参数，再在这个模型内部把中灰调到接近中性。没有数字化任何厂商曲线，也没有读取 SpektraFilm / SpektraLab 的代码、LUT 或配置。名称里的 50、100、200、400 只是速度档标签，不是测得的 ISO 感光度。效果未经真实样本验证。

## What the code actually does

The interpreter id is `parametric-hd-beer-lambert-v1` (`reality_first_normalization/film/version.py`). A recipe whose `model_version` differs is rejected. Every run records that id, the recipe file SHA-256, a canonical-JSON SHA-256 of the interpreted parameters, the strength, the user seed and, when grain runs, a per-image seed.

Input and output are encoded sRGB in [0, 1], the existing working space. Out-of-range finite values are clipped. The pipeline does not change the ICC policy.

### 1. Encoded sRGB to relative exposure

IEC 61966-2-1 inverse transfer:

- if `C <= 0.04045`, linear = `C / 12.92`
- otherwise linear = `((C + 0.055) / 1.055) ^ 2.4`

Relative exposure is `linear * 2^exposure_ev / scene_mid_gray`. Bundled recipes use `scene_mid_gray = 0.18`, the ordinary photographic middle-gray reference, not an ISO speed measurement. This linearization is display-referred. It is not a raw sensor reconstruction.

### 2. Characteristic curve

Optical density follows a logistic of a warped log exposure. At the midpoint the slope is the recipe `gamma` (density per log10 exposure). `asymmetry > 0` lengthens the toe and shortens the shoulder; the warp derivative at the midpoint is 1, so gamma is unchanged. The warp is an original smooth skew, `u * exp(asymmetry * tanh(u / skew_softness))`. It is not a digitized manufacturer H&D plot.

Log exposure is floored at `1e-6` before `log10`. The reversal process stores the same increasing curve and uses the complement `d_min + d_max - D` as the dye that remains.

### 3. Layers, dyes and Beer–Lambert

`sensitivity.layer_order` is fixed: cyan (red-sensitive), magenta (green-sensitive), yellow (blue-sensitive). That stack order is the standard integral tripack described by Hunt and by Evans, Hanson and Brewer. The 3×3 matrix is a stand-in for spectral sensitivity overlap. Its entries are round numbers chosen here. They are not status-M dye densities from a data sheet.

Integral density is `A @ analytical_density`, plus a constant orange-mask or base density. Transmittance is `10^(-D)`, clipped so `D` stays in `[0, 8]`. That is the decadic form of the Beer–Lambert law.

`negative-print` feeds that transmittance to a second paper stage with its own exposure, balance, sensitivity, curve and dyes. The balance is the model's analogue of a printing filter pack. Bundled balances were solved so an encoded gray near 0.46 lands near a chosen gray inside this model. That is internal calibration, not a measured printer.

### 4. Grain

Noise is added to analytical dye density before the absorption matrix. Its standard deviation is

`strength * max(D, 0)^exponent * window`

`window` is 1 when `midtone_emphasis` is 0, and `4 s (1-s)` when emphasis is 1, with `s` the position between `d_min` and `d_max`. `strength` is the deviation at density 1 when the window is 1. It is an illustrative scale, not a measured RMS granularity.

The random stream is NumPy `Generator(PCG64)` seeded from `SeedSequence` of a SHA-256 mix of the model version, the user seed and the sample id (the CLI uses the input SHA-256). Repeating a result requires the same NumPy random algorithm. This project pins NumPy 2.4.6. A future NumPy change can change the grain even when the seed is unchanged; the manifest records `numpy` and `rng` so that is visible.

### 5. Halation

Highlight exposure above `threshold` is multiplied by `gain_rgb` and spread with a normalized separable Gaussian whose sigma is `sigma_fraction` times the long edge. The spread is added back onto the exposure before the characteristic curve. Sigma is reduced when the kernel would be wider than the reflect pad. A one-pixel image does not spread. The Gaussian is a phenomenological spread function, not a measured film-base point-spread function. Red gain is higher than blue gain in the bundled recipes because residual halation is described as redder in the photographic textbooks cited below; the gains themselves are not measurements.

### 6. CUBE export and comparison

`film-lut` evaluates the pointwise model, with grain and halation off, on an encoded-sRGB lattice of size 2..64. The file is red-fastest Adobe Cube order, the same order the existing loader expects. A `.provenance.json` file records the recipe hash and states that spatial effects were omitted. `--film-color-only` uses that same pointwise path on images.

`compare --film` writes four routes: input reference, normalization only, film, and normalization plus film. A LUT is optional and, when present, is applied after the film on the last two routes. Without `--film`, the original four LUT routes are unchanged. The HTML page says the film model is unverified.

### 7. CIEDE2000 scaffold

`reality_first_normalization.metrics.delta_e` converts encoded sRGB to CIE L\*a\*b\* with the IEC primaries and D65, then evaluates CIEDE2000. `reality-first-photo delta-e` prints mean, median, p95 and max. `threshold` is always null. The command does not decide whether two images look like the same film. The unit test checks the published Sharma, Wu and Dalal pairs to four decimal places. Those pairs test the formula. They are not a film trial.

## Sources

These sources justify the shape of the model. They are not a license to copy tables, and this repository does not copy tables from them.

- Hurter, F. and Driffield, V. C. (1890). Photochemical investigations and a new method of determination of the sensitiveness of photographic plates. *Journal of the Society of Chemical Industry*, 9. Density versus log exposure.
- Mees, C. E. K. and James, T. H., eds. (1977). *The Theory of the Photographic Process*, 4th ed. Macmillan. Sensitometry, Selwyn granularity, Nutting's relation of density to grain number, and halation from reflection at the base.
- Selwyn, E. W. H. (1935). A theory of graininess. *The Photographic Journal*, 75, 571–580. Granularity scaling with aperture. The implementation uses the density-domain idea, not a copied granularity table.
- Hunt, R. W. G. (2004). *The Reproduction of Colour*, 6th ed. Wiley. Integral versus analytical density, unwanted dye absorptions, the orange mask, and negative-positive versus reversal.
- Evans, R. M., Hanson, W. T. and Brewer, W. L. (1953). *Principles of Color Photography*. Wiley. The cyan/magenta/yellow tripack.
- IUPAC. Beer–Lambert law. *Compendium of Chemical Terminology*. <https://goldbook.iupac.org/terms/view/B00626>
- IEC 61966-2-1 and the ICC sRGB registry. Transfer function and primaries. <https://registry.color.org/rgb-registry/srgb>
- ISO 5. Photography — Density measurements. Definition of optical density as `-log10` transmittance. The standard is paywalled; no tables were copied.
- CIE 142-2001 and ISO/CIE 11664-6. CIEDE2000. Implementation corners follow Sharma, G., Wu, W. and Dalal, E. N. (2005). The CIEDE2000 color-difference formula: implementation notes, supplementary test data, and mathematical observations. *Color Research & Application*, 30(1), 21–30. <https://doi.org/10.1002/col.20070>. Pairs: <https://hajim.rochester.edu/ece/sites/gsharma/ciede2000/>. Their MATLAB and spreadsheet were not copied; only the published numeric pairs are used as a test oracle.
- Dainty, J. C. and Shaw, R. (1974). *Image Science*. Academic Press. Spread functions and granularity as linear imaging ideas. The Gaussian here is not their measured data.

Manufacturer data sheets were not digitized. Using one later would require reading that sheet's license first and recording the URL and the license in the recipe.

## What was not taken from other film tools

SpektraFilm is GPL-3.0, its film configuration data is CC BY-SA 4.0, and its LUTs have their own restrictions. SpektraLab is a fork whose license was not reviewed, because this work did not open that project's code, data or LUTs. Nothing in this module was transcribed from either project. The names appear in the README only as an acknowledgement that those tools encouraged an open, offline film-simulation tool.

## RAW is still unsupported

Pillow, NumPy and tifffile do not decode camera RAW. `rawpy` 0.28.0 is MIT ([rawpy license](https://github.com/letmaik/rawpy/blob/main/LICENSE)) but it wraps LibRaw, which is LGPL-2.1 ([LICENSE.LibRaw](https://github.com/letmaik/rawpy/blob/main/LICENSE.LibRaw)). The project currently distributes only MIT/BSD dependencies. LibRaw's LGPL obligations on a wheel, and the GPL demosaic packs that rawpy wheels exclude ([rawpy on PyPI](https://pypi.org/project/rawpy/)), are an author decision, not a silent dependency. A RAW path would also need a written decode contract: demosaic, white balance, camera matrix and transfer. The color contract already refuses to invent that from output primaries. No real RAW file was used here.

## Author choices still open

- The five recipes can be retuned after real paired scans exist. Until then `verification` must stay `unverified`; the loader rejects any other status.
- A likeness gate needs a threshold the author chooses. CIEDE2000 does not supply one, and this change does not invent a pass/fail number.
- Grain reproducibility is tied to NumPy 2.4.6's PCG64. Bumping NumPy should be treated as a grain change.
- Whether `--film` should grow separate grain and halation switches, beyond `--film-color-only`, is undecided.
