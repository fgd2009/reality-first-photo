# Reality First Photo

**0.1.0a2 离线命令行预览版**：导入受支持的 RGB 图像，转换到编码 sRGB，先进行有边界的自然曝光、白平衡及影调/色彩归一化，再按明确强度应用用户自己的 SDR CUBE LUT，导出 sRGB PNG、JPEG 或 16 位 TIFF。

这是早期 CLI 预览，不是完整照片编辑器，也不宣称经过标定的真实胶片复现。

[English](README.md) · [色彩契约](docs/COLOR_CONTRACT.md) · [验证记录](VALIDATION.md) · [MIT 许可](LICENSE)

## 快速开始：先看到结果

要求 **Python ≥3.12**。下列命令使用 POSIX shell，直接从 GitHub 安装当前预览，不需要 Git 仓库副本或测试工具。实际验证环境见 [VALIDATION.md](VALIDATION.md)，Windows 和原生应用安装包尚未验证。

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install https://github.com/fgd2009/reality-first-photo/archive/refs/heads/main.zip
reality-first-photo demo --output first-look
```

**用图像查看器打开 `first-look/comparison.png`。** 三列分别标为 **Input（原图）**、**Normalized（归一化）**、**Normalized + warm LUT（归一化后加暖色 LUT）**，展示渐变、色卡和几何图形。归一化强度为 0.6；最后一列在此基础上以 0.5 强度应用原创暖色示例 LUT。

这些都是**合成图，不是真实照片**。暖色 LUT 是简单原创仿射变换，不代表某个胶片品牌或商业风格。对比图只演示处理步骤，不构成专业照片效果或物理胶片准确性的背书。

![原创合成渐变、色卡和几何图形的原图、归一化、归一化后加暖色 LUT 对比](docs/images/synthetic-comparison.png)

*仅为原创合成演示，不包含真实照片或商业预设。*

安装后可以在任意目录运行此命令。程序打印结果路径，并在新的 `first-look` 文件夹内创建 `input/`、`normalized/`、`styled/`、两个原创 CUBE 文件、`comparison.png` 和 `demo.json`。两个导出文件夹分别包含三张 PNG 和处理记录。如果 `first-look` 已存在，请换一个名称，例如 `--output first-look-2`；演示不会覆盖已有目录。

安装过程需要下载 Python 依赖；图像处理在本地完成，没有遥测、模型调用、API 密钥、账号登录或网络请求。CLI 不调用外部 EXIF 工具，也不读取个人偏好。仓库不包含真实照片、第三方 LUT 或 XMP 预设。

## 处理自己的图像

```sh
reality-first-photo --input /path/to/tagged-images --output /path/to/new-output --lut /path/to/your.cube --normalize-strength 0.6 --lut-strength 1 --format tiff
```

使用具有适当授权、面向**编码 sRGB**制作的 LUT。归一化先执行，之后由用户 LUT 的表格定义效果，不再套用另一种风格。将 `--normalize-strength` 设为 `0` 可跳过归一化；省略 `--lut` 则只归一化。两个强度参数均为 0 到 1；`--lut-strength 0` 不混入 LUT 效果，但仍检查已指定的 LUT 文件。LUT 缺失会明确报错。

默认预览长边为 2048 像素。用 `--max-long-edge 0` 明确保留原尺寸；解码发生在缩放之前，大图内存占用和性能尚未验证。

每次运行都需选择**新的输出目录**；已有目录会被拒绝，输出也不能位于输入文件夹内部。文件夹输入会递归查找 JPEG、PNG、TIFF；如发现已知 RAW 扩展名，整次运行会在创建输出前报错；其他扩展名会被忽略。`manifest.json` 记录运行状态、完成文件、输入哈希和色彩决策。每个文件还记录 `normalization.applied` 和 `normalization.operations`；执行归一化时，后者包含实际的 `exposure_scale` 与 `white_balance_gains_rgb`。这些是计算得到的处理参数，不是照片质量评分。失败或取消时保留部分输出，重新运行请另选目录。取消测试使用注入的 `KeyboardInterrupt`，没有验证实体键盘或 GUI。

## 遇到错误时

| 提示或情况 | 下一步 |
| --- | --- |
| 输出目录已经存在 | 换用新目录，例如 `--output first-look-2`，已有输出会保留。 |
| 新输入缺少 ICC，或 ICC 无效 | 在可信色彩管理工具中重新导出带标签的 RGB sRGB。仅当无标签像素已确认是编码 sRGB 时使用 `--assume-srgb`；它不能绕过损坏的 ICC。 |
| 找不到 CUBE LUT | 更正 `--lut` 路径，指向自己的受支持 CUBE 文件。只有希望仅做归一化时才省略 `--lut`。 |

## 支持范围与限制

| 输入或操作 | 当前预览行为 |
| --- | --- |
| RGB8 JPEG、PNG | 通过 LittleCMS 将有效 RGB ICC 转换至工作 sRGB；拒绝动画和多帧图像，包括 APNG。 |
| TIFF | 仅无压缩、单页、逐像素 RGB；支持 8/16 位整数或范围受限的 float32。 |
| 高位深 TIFF 的 ICC | 仅接受与内置工作 ICC 完全相同的配置，或无 ICC 且显式声明为 sRGB 的数据；不支持任意高位深 ICC 转换。 |
| 无 ICC 输入 | 默认拒绝；只有确认像素已是编码 sRGB 时，才使用 `--assume-srgb`。该参数不能绕过损坏的内嵌 ICC。 |
| 缩放与导出 | float32 分通道缩放；导出 16 位 TIFF 或 8 位 PNG/JPEG，均附工作 ICC。JPEG 为有损格式。 |
| LUT | 红轴最快的 3D CUBE，三线性插值、有限正域宽、输出节点位于 [0,1]；支持默认域和 `DOMAIN_MIN`/`DOMAIN_MAX`；拒绝未知指令、1D/组合表和 `LUT_3D_INPUT_RANGE`，不自动推断 log/HDR 转换。 |

RAW/DNG、灰度、CMYK、alpha/透明色键、16 位 PNG、压缩或多页 TIFF、打包位深 TIFF、非默认 TIFF 方向均会被拒绝。完整 GUI、商业预设和原生应用安装包不在本预览范围内。尚未验证真实照片、真实 RAW、商业 LUT、物理胶片准确性或跨平台行为。

## 开发与验证

```sh
git clone https://github.com/fgd2009/reality-first-photo.git
cd reality-first-photo
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]' build
python -m pytest -q tests
python -m build
```

原有 `--input` / `--output` 图像处理命令继续可用。在源码目录运行 `python -m examples.generate_demo demo-assets`，仍可只生成原始合成图和示例 LUT，不执行处理。

[CI 工作流](.github/workflows/ci.yml) 使用 Ubuntu / Python 3.12 运行当前候选测试，构建软件包，在独立环境安装 wheel，并从源码目录之外运行完整演示；不会自动发布到 PyPI。当前执行结果和未验证项见 [VALIDATION.md](VALIDATION.md)。历史大型恢复副本的测试数不计入此仓库覆盖数。

## 许可

原创项目代码与演示生成器以 [MIT 许可](LICENSE)发布，版权归 2026 fgd2009。依赖保留各自许可证；生成的工作 ICC 保留其自由使用声明，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。用户提供的 LUT 仍受其自身许可约束。
