# Reality First Photo roadmap

Build a dependable local workflow, learn from willing users, then choose the next interface from evidence. This is a sequence of decisions, not a promise of dates or features.

## Baseline and current status

This plan starts from **0.1.0a3**. Its [validation record](VALIDATION.md) reports **113 passing tests** at that baseline; that count is not a user-trial result and does not include historical suites again.

| Status | Evidence or boundary |
| --- | --- |
| Completed at the baseline | Offline CLI export, packaged synthetic demo, four-way comparison, local JSON/HTML reports, independent wheel installation and synthetic end-to-end checks. |
| Completed at the baseline | Tested color/provenance contracts and explicit failures for unsupported inputs, changed inputs/LUTs, existing outputs and partial/cancelled runs. See the validation record for the exact scope. |
| Unverified | Actual HTML browser appearance. The managed browser rejected local-file navigation with `ERR_BLOCKED_BY_ADMINISTRATOR`; HTML structure/link checks are not visual browser verification. |
| Unverified | Independent user completion, preferred results, adoption, repeat use, real-photo quality, native Mac interaction and broad platform compatibility. No trial outcomes are recorded by this plan. |
| Not doing in this stage | A full GUI, RAW decoding, commercial LUT bundles, automated best-image selection, cloud processing, telemetry, paid promotion or unsolicited outreach. |

The browser restriction must not be bypassed by changing policy, networking or serving files as a workaround. A future visual check needs an environment where normal local-file viewing is permitted. Until then, retain the limitation explicitly.

Stage 1 now has a bounded reliability focus for the 0.1.0a4 iteration: a read-only `check` that actually decodes inputs, and failure/cancellation records that identify the relative input and processing stage. Retry uses a new directory; abrupt termination remains incomplete. Implementation and executed results belong in [VALIDATION.md](VALIDATION.md), not in this plan as assumed passes. See [recovery guidance](docs/TROUBLESHOOTING.md).

## Stages and acceptance

| Stage | Work and evidence | Acceptance before expanding |
| --- | --- | --- |
| **1. Reliable end-to-end flow — active** | Keep installation → demo → compare → locate/save output understandable and repeatable. Add read-only input/LUT checks and actionable failure-stage records; record the bounded fix and relevant verification. | The documented installed-package flow succeeds on each claimed environment; relevant regression and packaging checks pass; failure/cancellation remains honest and preserves sources/existing outputs. Report viewing is checked in a permitted environment before claiming a visually verified end-to-end flow. |
| **2. Voluntary real-user trial — not started** | Use the [tryout guide](docs/TRYOUT.md) with willing participants. Record independent completion, assistance, comparison preference and reasons; images and private reports remain under each participant's control. | Review a small, explicitly voluntary first group. Exploratory gates: **at least 4 of 5 independently complete the flow**, and **at least 3 of 5 choose an exported result they would adopt in their own workflow**. These are proposed learning gates, **not achieved facts**, statistical proof or evidence of repeat use. |
| **3. Choose the next interaction from evidence — not started** | If recurring friction is selecting files, choosing a LUT or opening results, evaluate lightweight Mac interaction. If repeated tasks concern many images, presets or repeated runs, evaluate batch workflow improvements. Mixed or insufficient evidence means further learning. | Choose one bounded prototype only after documenting the recurring need, existing alternatives and a measurable acceptance task. Test it with the affected willing users. CLI support continues; neither a Mac UI nor batch expansion is preselected. |
| **4. Authorized growth after repeat use — not started** | Look for participants voluntarily returning for another task and describing why. Separate observed repeat use from stated intent. | Only after repeat-use evidence, agree the audience, message and channel for a bounded growth experiment. Contacting people or publishing promotional messages requires explicit authorization; no automated or unsolicited outreach follows from this roadmap. |

For stage 2, “independent” means completing the documented installation, synthetic demo, comparison and finding the outputs without step-by-step maintainer intervention. Assisted attempts, failures, withdrawals and unknown answers remain visible in the record; do not silently remove them to meet a gate. A preferred result may be the input reference, normalization, LUT only, the combined route, or none. Preference is not a product-generated quality score.

Missing a gate means fixing the observed friction or revising the hypothesis, not manufacturing participants, testimonials or successful runs. Passing it permits a small next experiment; it does not establish market demand, photographic quality or retention.

## 中文简要

路线顺序是：**可靠跑通全流程 → 自愿真实用户试用 → 根据证据决定轻量 Mac 交互或批量能力 → 有重复使用证据后再做经授权的增长**。

当前 0.1.0a3 基线已有 CLI、合成 demo、四路 compare、安装/打包及 113 项测试记录；这些不是真实用户试用结果。HTML 的真实浏览器视觉效果仍未验证，因为当前环境阻止了本地文件导航；不修改策略、不改网络、不架服务器绕过。

阶段 1 的 0.1.0a4 范围为只读真实解码检查、明确失败/取消的相对文件与阶段、换新目录重试；强制终止仍按未完成处理。具体实现与验证另记，不在路线图中预先宣称通过。阶段 2 尚未开始：“5 人中至少 4 人独立完成、至少 3 人选出愿意采用的导出结果”只是探索性门槛，**不是已达成成绩**，也不等于重复使用。原图参考、仅归一化、仅 LUT、组合效果或都不选，都是有效反馈；不自动指定最佳。

先记录真实问题，再决定交互方向；不会同时承诺完整 GUI 和批量产品。试用者自愿参与并控制自己的数据，不索取照片、EXIF、私人路径或完整报告，不伪造试用，不主动群发。只有出现重复使用证据且传播动作另获授权后，才开展有限增长实验。
