# 可用校准数据源

本仓库不下载、不收录下面任何曲线、光谱或扫描。清单只说明链接、许可和能不能拿来用。许可没核对清楚的，标成待核，不把文件放进来。SpektraFilm / SpektraLab 的代码和数据不在此列，也不会被复制。

判定日期：2026-11-02。页面能打开只说明链接当时可访问，不是对曲线数值的授权。

## 可以自己用，但不要放进这个 MIT 仓库

| 来源 | 链接 | 许可（已看过的文字） | 格式 | 状态 |
| --- | --- | --- | --- | --- |
| Wikimedia Commons 上的色卡 PDF | <https://commons.wikimedia.org/wiki/File:Color_Checker.pdf> | CC BY-SA 4.0。署名，且衍生作品要用相同或兼容许可。 | PDF | 页面已打开，许可栏已核对。可以自己打印来拍，不要把 PDF 收进本仓库。 |
| Chromaxion 光谱库 | <https://www.chromaxion.com/spectral-library.html> | 页面写明：个人、科研和教学可自由使用；再分发必须署名 Robin Myers / Chromaxion；未经书面许可不得出售。 | SpectraShop 文本 | 许可页已核对。该“不得出售”与 MIT 可出售的分发方式冲突，所以不收录。 |
| raw.pixls.us 样张 | <https://raw.pixls.us/> | 上传表单要求作者以 CC0 投入公有领域。2017 年的站点说明写过：从 rawsamples.ch 带进来的旧文件是 CC-BY-NC-SA，不是 CC0。 | 各相机 RAW | 站点说明已核对。单个文件必须看它自己的 License 列。NC 文件不能放进本仓库。本仓库的测试 DNG 不是这里的文件。 |

## 明确不能并入

| 来源 | 链接 | 原因 |
| --- | --- | --- |
| SpektraFilm 及其 darktable 数据包 | <https://github.com/darktable-org/darktable-spektrafilm> | 数据是 CC BY-SA 4.0。ShareAlike 不能收进这个 MIT 树。按作者要求，不读取、不拷贝。 |
| BabelColor ColorChecker 表 | <https://github.com/colour-science/colour/blob/develop/GRANTS> | 许可信只给了 Colour 项目的开发者，没有给本仓库。 |
| butcherg/ssf-data | <https://github.com/butcherg/ssf-data> | CC BY-NC-SA 4.0，而且是数码相机光谱，不是胶片。NC 不能并进 MIT。 |

## 厂商手册：曲线在册上，摘录尚未获许可

这些 PDF 能看到特性曲线或光谱敏感度图。看到的版权行没有给出把数字抄进软件的许可，所以数值一张都没有抄。

| 手册 | 链接 | 已看到的版权 | 状态 |
| --- | --- | --- | --- |
| Fujifilm Professional Film Data Guide | <https://asset.fujifilm.com/www/us/files/2020-03/3ab271f46f8d71c7e4c91bcedb7de050/ProfessionalFilmDataGuide.pdf> | COPYRIGHT © 2005 FUJI PHOTO FILM CO., LTD. | 文件可打开。未见再使用许可。待厂商授权后才能数字化。 |
| Kodak E-77（1980 彩色胶片数据册，第三方扫描） | <https://photomemorabilia.co.uk/Colour_Darkroom/MFisher/Kodak_%20Color_Films_E77_DataBook_Sep1980.pdf> | © Eastman Kodak Company, 1980 | 这是第三方站点上的扫描，不是柯达授予本项目的许可。不使用。 |
| Kodak VISION Color Print Film 2383/3383 | <https://www.kodak.com/content/products-brochures/Film/KODAK-VISION-Color-Print-Film-2383-3383-data-sheet.pdf> | 本次打开该 PDF 超时，没有核对版权页 | 待核。未摘录。 |

NIST 的光谱反射服务是校准业务，不是可下载的 CC0 数据集：<https://www.nist.gov/programs-projects/spectral-reflectance-and-transmittance>。

## 本项目已自行数字化的两份手册

2026-11-02 下载了下面两份 PDF，只在内存和临时目录里渲染第 4 页，没有把 PDF 或曲线图放进仓库。读取脚本是 `scripts/digitize_kodak_curves.py`。采样点在 `data/curves/`。

| 手册 | 链接 | 版本 | 本项目做了什么 |
| --- | --- | --- | --- |
| Portra 400，E-4050 | <https://www.kodakprofessional.com/sites/default/files/2025-07/e4050.pdf> | January 2025，revised 1-25。PDF sha256 `70b15171673c5d01505f58ace448995ad72acbe5e401d1966563a61ac0712838`。© 2025 Kodak Alaris Inc. | 读了 Status M 特性曲线和染料密度曲线的一部分。光谱敏感度曲线交叉、带网格和文字，自动跟踪没有留在墨线上，所以没有写那张图的数字。 |
| Ektar 100，E-4046 | <https://www.kodakprofessional.com/sites/default/files/2025-07/e4046.pdf> | January 2025，revised 1/25。PDF sha256 `38a41d47ad006cd563793033f83c8f9ef6cdd3c8300695c31facfc71d368f8db`。© 2025 Kodak Alaris Inc. | 同上。用户给的 imaging.kodakalaris.com 链接会跳到另一份文件；这里用的是 kodakprofessional.com 上的 2025 年版。 |

这些 CSV 是本项目从印刷曲线上读的坐标，不是厂商发布的数值表，也不表示渲染结果与该胶片一致。估计误差大约 2 个像素，见每个 CSV 的头部。`warm-negative-400` 用了 E-4050 的特性曲线拟合，`neutral-negative-100` 用了 E-4046。染料密度曲线在两线相遇之后没有读全，所以没有拿它改染料矩阵。

## 现在就能用的参考

在厂商许可弄清之前，参考数据应来自你自己拍的色卡。步骤见 [CALIBRATION_CAPTURE.md](CALIBRATION_CAPTURE.md)，目录格式见 [REFERENCE_SET.md](REFERENCE_SET.md)。
