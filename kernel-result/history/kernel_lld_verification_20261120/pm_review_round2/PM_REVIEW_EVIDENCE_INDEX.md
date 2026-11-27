# PM Review 证据索引

本包针对 20261120.082536、standard/armv7l、RPi4 非 RT。第一轮归档原址为 /local-user/lss/kernel_lld_check/kernel_lld_verification_20261120。round1 下是通过原 SHA256 校验的证据副本，原目录保留。未复制的完整镜像、大 RPM、已解包 ELF 等原件可用保留索引中的相对路径和 SHA256 从第一轮归档定位。 [原报告](../KERNEL_LLD_VERIFICATION_REPORT.md) · [原归档 SHA256](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [保留与省略清单](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

| 复核主题 | 使用文件 |
| --- | --- |
| 总结和关闭条件 | [正式报告](PM_REVIEW_ROUND2_REPORT.md) · [结构化汇总](PM_REVIEW_ROUND2_SUMMARY.json) · [Gate 矩阵](PM_REVIEW_GATE_MATRIX.csv) |
| 第一轮归档校验 | [SHA256 与命令索引](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [原命令](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [完整离线复跑](evidence/round1-offline-replay.out) · [退出码](evidence/round1-offline-replay.cmd.json) · [核心输出精确匹配](evidence/round1-replay-output-comparison.json) · [新增交叉审计](08_01_evidence_integrity_review.json) |
| 与发布快照绑定的日志 | [完整日志 SHA256、来源 URL、原始路径和行数](evidence/ORIGINAL_BUILD_LOG_INDEX.json) · [主内核全文](../evidence/build/linux-rpi-armv7l.out) · [树外作业全文](../evidence/build/linux-tizen-modules-armv7l.out) · [树外源码作业](evidence/external/source-provider-buildlog.out) · [59 条带原始行号的摘录](evidence/module-final-link-excerpts.txt) |
| 源码和 Kbuild | [内核变量](08_03_linker_variable_trace.json) · [规则](08_03_linker_rule_matrix.csv) · [内核源码/规则来源](08_03_kernel_linker_selection.md) · [树内 52 目标](08_04_in_tree_modules.csv) · [树外 7 目标](08_05_out_of_tree_modules.csv) |
| 历史命令和链接器文件 | [有界搜索](08_02_historical_evidence_recovery.md) · [历史候选](08_06_historical_linker_resolution.md) · [真实 binutils ld/ld.bfd](evidence/external/historical-binutils-resolution.json) · [工具输入下载信息及摘要](evidence/PM_TOOL_INPUTS.json) |
| Build ID 与设备关联 | [后处理报告](08_07_build_id_postprocessing_review.md) · [逐段和 CRC](BUILD_ID_COMPARISON.json) · [原 runtime notes](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [六项身份匹配](08_09_identity_review.json) |
| 原有分类与证据等级 | [逐目标 59 行](MODULE_LINKER_EVIDENCE_MATRIX.csv) · [独立分母与统计](08_08_evidence_levels.json) · [加载模块 Build ID](../05_loaded_module_mapping.csv) |

## 复跑

轻量包解压后，在包含本索引的目录执行：

    sha256sum -c --quiet BUNDLE_SHA256SUMS
    python3 -B scripts/check_pm_bundle.py

原归档完整输入由工作区保留。默认在工作区的 pm_review_round2 内，或者从轻量包执行并显式传入原归档：

    python3 -B scripts/replay_round1_view.py check --base /local-user/lss/kernel_lld_check/kernel_lld_verification_20261120
    python3 -B scripts/replay_round1_view.py replay /local-user/lss/kernel_lld_check/kernel_round1_offline_recheck --base /local-user/lss/kernel_lld_check/kernel_lld_verification_20261120

此入口将新增 PM 子目录排除在第一轮封存的文件覆盖检查之外，原归档文件和脚本本身不改写。replay 将归档复制到临时视图，并在给定的新目录调用第一轮离线入口。

带完整输入的交叉复核用 audit_round1.py、review_build_id.py 和 stage_portable_evidence.py 的 --base 参数。具体实际调用与退出状态见各任务的 .cmd.json。证据等级和表格生成器读取已检查的任务矩阵：

    python3 -B scripts/write_pm_report.py

源代码和工具包取证脚本分别在内核、树外和历史可执行文件报告末尾列出。历史工具 RPM 须按已记录 URL 和 SHA256 获取，在工作区交付目录可直接用 artifacts 的留存文件。包内验证入口离线检查 tar 内容、矩阵、日志和证据路径。
