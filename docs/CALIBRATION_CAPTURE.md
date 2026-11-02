# 校准拍摄指南

一页纸。目的是让你自己产生一对参考图，放进 reference set 之后跑 `delta-e`。这不能证明结果像某款商业胶片。默认色差门槛只是占位数字。

## 拍什么

1. 用一张常见的 24 色色卡。如果打印 [Wikimedia 的色卡 PDF](https://commons.wikimedia.org/wiki/File:Color_Checker.pdf)，那份文件是 CC BY-SA 4.0：使用时要署名，改过的版本也要使用相同许可。不要把该 PDF 放进本仓库。
2. 灯光固定。日光或同一盏连续光即可。不要中途换灯、换白平衡或让人走过色卡。
3. 胶片机对色卡对焦、曝光正常，拍一张。用同一灯光，再用数码机拍一张，白平衡设成与灯光一致。记下胶片名称、曝光、灯光和冲扫店。没有数码机时，第二张可以是你信任的扫描原件，但两张必须是你有权使用的。
4. 按平常流程冲洗。扫描时如果软件允许，关掉自动校色，记下扫描软件、分辨率，以及文件有没有嵌入 ICC。

## 做成参考集

5. 导出两张编码 sRGB 的 PNG，尺寸一致。`reference.png` 是你认定的参考（通常是数码原图或未套配方的扫描）。`sample.png` 是待比较的图（例如本工具 `--film` 的导出）。
6. 建一个目录，写入 `reference-set.json`，格式见 [REFERENCE_SET.md](REFERENCE_SET.md)。`license` 写成这组图实际的许可，例如“作者本人拍摄，仅供自己验收”。
7. 运行：

```sh
reality-first-photo delta-e --reference-set /path/to/my-set
```

退出码 0 表示没有越过当前门槛，2 表示越过了。JSON 里的 `passed` 是门槛结果，不是胶片相似度。门槛不合适就在 JSON 里改 `thresholds`，或加上 `--mean-max` 和 `--p95-max`。`--report-only` 只打印数值。

图留在你的电脑上。这个工具不会上传它们。
