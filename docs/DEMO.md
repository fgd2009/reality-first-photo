# A 25-second synthetic walkthrough — recording plan

**Status: storyboard and commands only; no video has been recorded or published.** The README image is an existing static output of the synthetic demo, not a screen recording. It does not prove real-photo quality or HTML browser appearance.

Use only the bundled gradients, chart, shapes and original demonstration LUT. No photograph, EXIF, private filename, commercial preset or participant feedback is needed.

## Prepare a real recording

Install the preview using the [README quick start](../README.md#quick-start-see-the-result), then choose a new scratch directory with no personal files. Use a terminal prompt that does not show a username or private path. Keep notifications and unrelated windows out of the capture. Run the actual installed CLI; do not fabricate terminal output or animate a still image to imply a working UI.

The commands below create a fresh `demo-take` and `compare-take`. If either name already exists, choose new names consistently rather than deleting or overwriting an earlier run.

```sh
reality-first-photo demo --output demo-take
reality-first-photo check --input demo-take/input --lut demo-take/demo_warm.cube --format png
reality-first-photo compare --input demo-take/input --output compare-take --lut demo-take/demo_warm.cube --normalize-strength 0.6 --lut-strength 1
```

Verify `demo-take/demo.json` and `compare-take/compare.json` both say `complete` before recording a successful walkthrough. A file's existence alone is insufficient. `check` must report ready; it checks inputs without exporting. The four comparison folders should each contain three PNGs.

## Shot list

| Time | Capture from a real run | Caption / narration |
| --- | --- | --- |
| 0–4 seconds | Installed terminal; run `demo` and retain the actual completion output. | “Compare normalization and your LUT locally.” |
| 4–9 seconds | Open `demo-take/comparison.png` in a normally permitted image viewer. Keep the synthetic notice and all three column labels visible. | “Synthetic demonstration — no real photographs or film-quality claim.” |
| 9–13 seconds | Actual `check` output for the three synthetic inputs and LUT. | “Check inputs and color decisions before export.” |
| 13–18 seconds | Actual `compare` command and completion output. | “Four routes: input reference, normalization, LUT, or both.” |
| 18–25 seconds | Only if normal local HTML viewing is permitted and has been manually verified: show one synthetic input's four labeled routes, open a PNG link and expand its recipe details. | “You choose. Originals stay intact; recipes and ICC decisions are recorded.” |

This is a **20–30 second editing target, not a speed benchmark**. Actual processing/capture may take longer. Any cut or sped-up segment must be disclosed; never replace error output with successful output. Keep the synthetic label visible or on-screen throughout the image sections.

The static demo has **three columns**, normalization strength **0.6**, and warm LUT strength **0.5**. The separate comparison command above has **four routes**, normalization strength **0.6**, and LUT strength **1**. Label the transition and settings accurately; do not present the three-column image as a four-way HTML screenshot. The input reference is decoded, ICC-converted/resized sRGB, not a byte-for-byte source copy. No route is automatically best.

## Current recording boundary

The managed development browser previously rejected local `file://` viewing with **`ERR_BLOCKED_BY_ADMINISTRATOR`**. HTML visual acceptance is still incomplete. This iteration does not retry that navigation or use another browser, port, environment or server to bypass it.

Until an ordinary permitted manual viewing check is completed, the final HTML shot remains **not recorded**. A separately labeled terminal/image-only clip may stop at the actual command results and state “HTML visual check pending”; it must not claim to demonstrate an inspected browser view. Follow the [manual HTML checklist](TROUBLESHOOTING.md#pending-manual-html-visual-check) and record its real result before claiming the full walkthrough was visually verified.

This document grants no permission to publish private images or post externally. No video file, download button, hosted web app or public user trial is implied. RAW, arbitrary unsupported ICC conversion, cross-platform behavior and photographic aesthetics remain outside the demonstrated claims.

## 中文录制说明

**当前只有分镜与可执行命令，没有录制或发布视频。** README 使用已经生成的静态合成对比图；不能称它为录屏或浏览器视觉验收结果。

先按 README 安装，再在全新的临时工作目录运行上面的三个命令。使用不显示个人用户名和私人路径的终端提示符，不录入通知、无关窗口、私照、EXIF 或商业预设。已有输出目录就换新名字，不覆盖。确认两个 JSON 的状态为 `complete`，并确认检查通过、四路各有三张 PNG 后，才能展示成功流程。

25 秒分镜：**0–4 秒实际 demo 命令 → 4–9 秒带合成标识的三列 PNG → 9–13 秒实际 check 结果 → 13–18 秒实际 compare 命令和结果 → 18–25 秒经允许且人工核验的四路 HTML、图片链接与配方详情**。这是剪辑长度目标，不是运行速度承诺；剪切和加速必须说明，不伪造成功输出。

三列静态演示为归一化 **0.6**、LUT **0.5**；上面的四路 compare 为归一化 **0.6**、LUT **1**，不能混淆。保留“合成演示，不代表实拍效果”的标注，不默认组合路线更好。

此前 `file://` 被管理员策略拒绝，当前最后一段 HTML 镜头仍**未录制、未验收**。不换浏览器、端口、环境或服务器绕过。若仅制作终端/PNG 片段，必须明确标注 HTML 视觉检查待完成，不能称为完整浏览器演示。该制作说明不授权公开私照或对外发帖。
