# Check inputs and recover a run

Use `check` before an export or comparison when an input, LUT or color decision is uncertain. It performs the actual image decode, reports ready/blocked/ignored entries and ICC decisions, and writes no files. It does not extract EXIF through an external helper.

```sh
reality-first-photo check --input first-look/input --lut first-look/demo_warm.cube --format png
reality-first-photo check --input first-look/input --lut first-look/demo_warm.cube --format png --json
```

The second command prints a machine-readable report to stdout; it does not save a report file. `--lut` is optional for a normalization-only check. Use the format, preview size and `--assume-srgb` setting intended for the actual processing run. Names are escaped in the output so unusual characters remain distinguishable.

A successful check describes the files read at that time. It does not export images, lock inputs or guarantee that files will remain unchanged before a later run. It may still decode a full-sized input before resizing, so it is not a cheap filename-only check or a large-image memory guarantee.

## Common recovery steps

| Situation | What to do |
| --- | --- |
| Existing output file, folder or link | Choose a new output path. Do not delete previous output merely to retry; the CLI does not overwrite it. |
| Missing LUT or unsupported CUBE | Correct the path or supply a supported, appropriately licensed encoded-sRGB 3D CUBE. `compare` requires a LUT; ordinary normalization-only export can omit it. |
| Missing ICC | In a trusted color-managed tool, export a tagged RGB sRGB image. Use `--assume-srgb` only if the untagged pixels are already known to be encoded sRGB. |
| Invalid or unsupported ICC | Re-export through a trusted color-managed tool using the [color contract](COLOR_CONTRACT.md). The assumption flag cannot override an invalid embedded profile. |
| RAW, alpha, animation or another unsupported format | Convert to a supported tagged RGB input outside this tool. No RAW decoder or automatic format workaround is added by `check`. |
| Input or LUT changes during processing | Keep the selected files unchanged for the run, then retry into a new directory. Existing partial results are not evidence of a consistent comparison. |
| Local HTML viewing is blocked | Record the browser/environment limitation and stop that viewing check. Do not change policy, proxy/network settings or start a server to bypass it. Exported PNGs can be inspected normally where permitted; that does not count as HTML visual verification. |

## Read the processing status

Processing writes `manifest.json`; comparison also writes `compare.json`. These local records can include relative filenames, hashes and image/ICC decisions. Inspect them locally instead of posting them unredacted.

| Status | Meaning and next action |
| --- | --- |
| `complete` | The recorded processing completed. Comparison success requires `compare.json` to say `complete`; a forced stop can leave HTML before the final checkpoint. A page's existence alone does not prove success. This is not a quality rating or a best-image decision. |
| `failed` | Processing stopped with an error. Use the recorded active/failed relative filename, stage and message to identify the cause; fix it and retry into a new directory. |
| `cancelled` | Cooperative cancellation was recorded. Partial files remain; restart into a new directory if desired. |
| `running`, or no final record after abrupt termination | Treat the run as incomplete. A forced process termination, power loss or similar interruption cannot promise a final checkpoint. The existence of some files does not establish completion. |

Preflight errors may occur before any output directory is created. In that case, use the terminal message or a read-only `check`. The tool does not resume into partial output or overwrite it on retry.

## Export the route you chose

Choose a route by inspecting the comparison, not by assuming the combined route is best. Reprocess the original inputs with the same LUT and strengths. Do not feed the exported reference PNG back into the pipeline.

For the README example (`--normalize-strength 0.6 --lut-strength 1`), map the observed choice to the ordinary export command:

| Chosen route | Ordinary export settings |
| --- | --- |
| Input reference | `--normalize-strength 0`, omit `--lut` |
| Normalized | `--normalize-strength 0.6`, omit `--lut` |
| LUT only | `--normalize-strength 0 --lut first-look/demo_warm.cube --lut-strength 1` |
| Normalized + LUT | `--normalize-strength 0.6 --lut first-look/demo_warm.cube --lut-strength 1` |

If you chose the combined route in that example:

```sh
reality-first-photo --input first-look/input --output chosen-tiff --lut first-look/demo_warm.cube --normalize-strength 0.6 --lut-strength 1 --max-long-edge 2048 --format tiff
```

Use the **actual settings from your report** if they differ. Match `--max-long-edge` and the explicit untagged-sRGB assumption as well. Deliberately changing to full size with `--max-long-edge 0` changes the processing basis and is a new run to inspect. TIFF export is 16-bit; the comparison is 8-bit PNG, so their quantization differs. Neither a larger bit depth nor a selected route establishes photographic quality.

## Pending manual HTML visual check

The managed development browser previously rejected `file://` navigation with **`ERR_BLOCKED_BY_ADMINISTRATOR`**. Actual browser appearance remains **unverified** there. The following is a checklist for a permitted environment, not evidence that these steps have passed:

1. Install the version under review, run the synthetic `demo`, then `check` and `compare` as in the [README](../README.md). Use fresh output directories.
2. If normal local-file access is allowed, open `first-compare/index.html` directly. Confirm three synthetic input groups, each with four labeled routes and the input-reference explanation. Record any missing or unreadable image/text.
3. Open an individual PNG using its link, expand recipe/ICC details, and inspect the layout at a narrow window width. Check that all four routes remain reachable and labels match the displayed outputs. This is a layout/navigation check, not a judgment of real-photo accuracy.
4. Record version/public commit, OS/browser version and passed/failed/blocked for those steps, without private paths or images. If policy blocks local viewing, stop and record blocked; do not substitute a workaround or claim success.

## 中文简要

先用只读 `check` 真实解码输入，查看 ready / blocked / ignored 和 ICC 决策；可加 `--json` 将机器可读结果打印到终端，不生成报告文件、不调用外部 EXIF 工具。检查只说明当时读到的文件，不锁定输入，也不保证之后不会变化。

已有输出路径就换新名称；缺 LUT 修正路径，`compare` 必须有 LUT。无 ICC 时优先在可信工具重新导出带标签的 RGB sRGB；只有已确认无标签像素本来就是编码 sRGB 才用 `--assume-srgb`，不能绕过无效 ICC。RAW 等不支持格式仍拒绝。

失败或取消后，在本地记录中查看相对文件名、处理阶段和原因，再换新目录重试。强制终止后若仍是 `running` 或没有最终记录，应视为未完成；已有部分文件不代表成功。

根据观察选择四路之一，再从原始输入按记录中的实际强度、LUT、尺寸和色彩假设导出 TIFF；不要把预览 PNG 回灌。上表的 0.6 / 1 仅对应 README 示例，不是最佳参数推荐。

浏览器视觉验收仍未完成：当前受管环境曾返回 `ERR_BLOCKED_BY_ADMINISTRATOR`。仅在允许正常本地文件访问的环境执行上面的合成图手动检查；不改策略、不改网络、不架服务器绕过。准确记录通过、失败或受阻，不把 HTML 结构测试写成视觉验收。
