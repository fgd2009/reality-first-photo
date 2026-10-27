# Voluntary local tryout

This is a blank guide for a future voluntary trial, not a record of completed trials or a sent invitation. No participants, outcomes or testimonials are implied. Recruitment and outreach are not automated; do not contact people without authorization.

The aim is to learn whether a person can complete the documented local flow and decide whether any result is useful. The software does not select a best image. A preference for the input reference, no preference, a failed attempt or deciding not to continue are valid outcomes.

## Your choice and your data

Participation is optional. Skip any question or stop at any point. Start with the bundled synthetic demo; using your own supported images or LUT later is entirely optional and stays local.

**Do not send photographs, derived images, EXIF, private paths, credentials or full logs. Do not paste `compare.json` or processing manifests:** they include filenames, hashes and other local details. The trial needs only the short, redacted observations below. Keep source files, LUTs and report folders on your own machine and choose whether to share any feedback.

Sharing feedback does not grant permission to publish a quote, identity or image. Any public use of feedback must be agreed separately. No tracking, upload or telemetry is introduced for this trial.

## Try the flow

1. Run the complete README quick start **once** ([English](../README.md#quick-start-see-the-result) / [中文](../README.zh-CN.md#快速开始先看到结果)). It already installs the preview and runs `demo`, `check` and `compare`. If you have completed it, use those existing results; do not rerun into `first-look` or `first-compare`. Record the version if readily available; do not send your environment configuration.
2. Open the existing `first-look/comparison.png` and identify the three labeled columns. The images are synthetic, not photographs or proof of photographic quality.
3. Check that the quick start's input check reported ready, then inspect the existing `first-compare/compare.json` locally and confirm its status is `complete`. If either step failed or remained incomplete, use the [recovery guide](TROUBLESHOOTING.md) before continuing; do not count existing files alone as success.
4. In an environment that permits normal local-file viewing, open the existing `first-compare/index.html`. Find the four variants, open an exported PNG and inspect the recipe details. The input reference is decoded, color-managed/resized sRGB PNG, not a copy of the original file.
5. Decide whether any route is useful for a task you care about. “None” and “not enough evidence” are welcome; a synthetic demonstration alone may be insufficient to judge your photo workflow.

For a new attempt, use a fresh working directory or change output names and every dependent input/report path consistently. If installation, processing or viewing stops, record the step and a redacted error category; do not bypass browser/administrator restrictions or weaken ICC checks. A blocked report view is a blocked view, not successful visual validation.

The current managed development environment has not visually verified the HTML in a browser: local navigation returned `ERR_BLOCKED_BY_ADMINISTRATOR`. This guide does not ask you to reproduce or work around that restriction.

## Optional feedback template

Copy only the fields you want to answer. Leave unknown answers blank; do not invent a result. No name, contact details, filename or private path is needed.

```text
Version / public commit, if known:
Platform and Python version, if comfortable sharing (no device identifiers):

Installation: completed independently / completed with help / stopped / not attempted
Demo and comparison.png: completed independently / completed with help / stopped / not attempted
Read-only input check: completed independently / completed with help / stopped / not attempted
Four-way compare command: completed independently / completed with help / stopped / not attempted
Local report and individual PNG: viewed independently / viewed with help / blocked / not attempted

Where I needed help or stopped (step and a short description; remove private details):
Error category, if any (for example installation / output exists / ICC / LUT / local viewing):

Preferred route: input reference / normalized / LUT only / normalized + LUT / mixed / none / unsure
Why, in one sentence:
Would I adopt any exported result for a task of my own? yes / no / unsure
What task or unmet need, in general terms (no client or private project names):

Have I returned for another task? yes / no / not yet
If yes, what made me return? (A short general description, no images or paths):
One change that would make the next attempt easier:
```

The final repeat-use question is optional follow-up evidence, not a requirement to make a second attempt. “Would adopt” records stated intent; it must not be counted as observed repeat use.

## How to interpret the feedback

Keep actual independent, assisted, failed, declined and unknown outcomes separate. Do not count a maintainer-run demonstration as a participant completing the task. Do not turn missing answers into positive responses or omit stopped attempts to improve a success rate.

The [roadmap](../ROADMAP.md) proposes exploratory gates of 4/5 independent completions and 3/5 choosing a result they would adopt. **No such results have been collected or established by this document.** A group of five provides directional feedback, not a market-size estimate, statistical validation or a quality endorsement. Use the reasons and failure points to choose a small next change.

## 中文简要与反馈

这是未来自愿试用的空白模板，不代表已经招募、联系或完成任何试用。可跳过问题、随时停止；先用自带合成图，自己的照片和 LUT 是否使用由本人决定，并留在本机。

**不要发送照片、派生图、EXIF、私人路径、凭据、完整日志或 JSON 报告。** 仅按意愿分享去除私人信息的简短文字。反馈不等于同意公开姓名、引用或图像；不得主动群发或伪造参与者。

只将 [README 快速开始](../README.zh-CN.md#快速开始先看到结果)的整段命令运行**一次**，它已完成安装、demo、check 和 compare；如果已经完成，直接使用现有结果，不再向同名 `first-look` / `first-compare` 重跑。随后打开已有 `comparison.png`，确认先前 check 就绪、`compare.json` 状态为 `complete`，再在允许本地文件访问的环境查看已有 `index.html` 和导出 PNG。失败或未完成时按[故障恢复说明](TROUBLESHOOTING.md)处理；新一轮尝试需新工作目录，或一致更新输出名称及所有依赖路径。遇到管理员/浏览器限制就记录“受阻”，不绕过；原图参考也经过解码、ICC 转换和缩放，不是源文件副本。

可只反馈以下几项：

- 版本；安装、demo、check、compare、查看报告分别是独立完成、需帮助、受阻还是未尝试。
- 卡在哪一步、简短错误类别；不要粘贴含私人信息的原始日志。
- 偏好原图参考、仅归一化、仅 LUT、组合、混合选择、都不选或不确定，以及原因。
- 是否愿意在自己的任务中采用某个导出结果：是 / 否 / 不确定；这只是意向，不是实际重复使用。
- 是否已自愿再次使用：是 / 否 / 尚未；最希望改善的一件事。

“4/5 独立完成、3/5 愿意采用”只是尚未达成或验证的探索性门槛，不是当前事实、照片质量背书或统计结论。保留失败、协助、退出和未知结果，不把自动对比当成自动选优。
