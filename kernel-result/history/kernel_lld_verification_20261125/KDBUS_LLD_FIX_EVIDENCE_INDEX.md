# LLD-KERNEL-001 · 证据索引与独立复核

在 `kernel_lld_verification_20261125/` 下运行命令。Phase 11 原始回执用同名 `.cmd.json`、`.out`、`.err` 记录 argv、时间、退出状态、stdout、stderr。HTTP 抓取另存响应头，部分管道保留各进程状态。搜索目标不存在、授权检查失败或路径未发布时，保留相应原始退出状态。构建输出自带日志行号锚点。 [PM 原始任务](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

| 阶段 | 审核入口 | 关键数据和原始依据 |
| --- | --- | --- |
| 11A | [预检](11A_PREFLIGHT.md) | [QB 身份](11A_QB_IDENTITY.json)、[RPM 清单](11A_RPM_INVENTORY.csv)、[新 manifest](evidence/repository/manifest.out)、[新内核日志](evidence/build/linux-rpi-armv7l.out)、[新模块日志](evidence/build/linux-tizen-modules-armv7l.out)、[源码提供包日志](evidence/build/linux-tizen-modules-source-armv7l.out) |
| 11B | [补丁纳入](11B_PATCH_INCLUSION_REPORT.md) | [源码来源](11B_SOURCE_PROVENANCE.json)、[实物差异](11B_SOURCE_DIFF.patch)、[旧 Makefile](../kernel_lld_verification_20261120/pm_review_round2/evidence/external/source/Makefile)、[新 Makefile](evidence/reproduction/inputs/20261125.130358/Makefile)、[Phase 10 独立 Git 核验](../phase10_kdbus_sandbox/evidence/remote-object-verification.json) |
| 11C | [直接执行证据](11C_INTERMEDIATE_DIRECT_EVIDENCE.md) | [命令数据](11C_INTERMEDIATE_LINK_COMMANDS.json)、[quiet 日志中间目标](evidence/build/linux-tizen-modules-armv7l.out#L505) |
| 11D | [中间链接因果分析](11D_INTERMEDIATE_LINKER_CAUSAL_ANALYSIS.md) | [变量与源码规则](11D_LINKER_VARIABLE_TRACE.json)、[规则矩阵](11D_LINKER_RULE_MATRIX.csv)、[包装 RPM 写入](evidence/build/linux-tizen-modules-armv7l.out#L746) |
| 11E | [Make 复现](11E_BEFORE_AFTER_REPRODUCTION.md) | [原始变量与模拟调用](11E_MAKE_VARIABLE_TRACE.json)、[实验结果](11E_REPRODUCTION_RESULTS.csv)、[实验回执](evidence/reproduction/before-after.cmd.json) |
| 11F | [二进制兼容性](11F_MODULE_BINARY_COMPARISON.md) | [ABI 汇总](11F_MODULE_ABI_SUMMARY.json)、[节大小](11F_MODULE_SIZE_COMPARISON.csv)、[符号](11F_MODULE_SYMBOL_DIFF.csv)、[重定位](11F_MODULE_RELOCATION_DIFF.csv) |
| 11G | [启动与模块覆盖](11G_KERNEL_LLD_REGRESSION_REPORT.md) | [59 个模块的清单比对](11G_MODULE_INVENTORY_DIFF.csv)、[清单与包校验原始数据](evidence/binary/module-inventory-metadata.json) |
| 11H | [运行验收](11H_RUNTIME_VERIFICATION.md) | [设备身份](11H_RUNTIME_IDENTITY.json)、[原始 SDB 输出](evidence/runtime/identity-device.out)、[命令与退出码](evidence/runtime/identity-device.cmd.json) |

## 完整性与归档

`SHA256SUMS` 覆盖本轮目录中的常规文件。`SHA256SUMS_REUSED_INPUTS` 列出独立存放的旧 QB 与 Phase 10 输入，包含复用的旧 Kernel SRPM。证据包保留本轮发布元数据、下载 RPM、构建日志、脚本、结果及所需的精选旧基线。归档包含省去重复下载的旧 Kernel SRPM，旧输入摘要表与 `11A_RPM_INVENTORY.csv` 记录其路径和摘要。仓库仅定位的新内核镜像、核心 debuginfo 参考发布摘要。证据包旁的 `.sha256` 用于校验整个压缩包。含目标 Phase 10 ref 的独立 Git bundle 保存提交数据与历史，不包含 Git 配置或认证材料。 [新 QB RPM 清单](11A_RPM_INVENTORY.csv) · [Phase 10 Git ref](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

在原工作区验证所有输入与结果：

    sha256sum -c --quiet SHA256SUMS
    sha256sum -c --quiet SHA256SUMS_REUSED_INPUTS
    sha256sum -c KDBUS_LLD_FIX_EVIDENCE_BUNDLE.tar.gz.sha256
    python3 -B scripts/verify_qb_review.py --verify-bundle

解包时使用空目录。三个顶层目录分别承载新 QB 范围、旧 QB 精选输入和 Phase 10 精选证据。在独立解包副本运行 `python3 -B scripts/verify_qb_review.py --unpacked`，验证归档所含成员及关键交叉关系。解包后可直接核对复用的旧 Kernel SRPM 及其他旧输入。

## 离线复跑

用独立副本运行会改写派生 CSV、JSON 和运行回执的脚本。依赖 Python 3、GNU binutils 中的 `readelf`、RPM 工具及 Git。Make 隔离实验使用随包保存的 x86_64 GNU Make 4.4.1。命令由各阶段文档给出，下面是三项主要入口。

1. **改动、配置、日志、ABI 统计核对**。摘要脚本独立核对单行源码差异、QB 身份、E3 记录、发布模块文件摘要、实际模块计数、模拟实验数与设备运行状态。 [核验脚本](scripts/verify_qb_review.py)
2. **Make 变量复跑**。使用旧新 RPM 中提取的 Makefile、归档的 Kbuild 规则和精确记录版本的 GNU Make。 [11E 命令](11E_BEFORE_AFTER_REPRODUCTION.md)
3. **原始包到模块 ELF 复跑**。脚本验证新仓库 primary/filelists、RPM 摘要和 RPM 内每个模块摘要，再生成清单、readelf 记录、节、符号与重定位对照。 [11F 命令](11F_MODULE_BINARY_COMPARISON.md)

从便携归档复跑 11B Git 对照时，先在解包副本（Phase 11 目录）恢复专用本地 checkout：

    git clone --branch sandbox/liushanshan/lld       "$(pwd)/evidence/preflight/phase10-sandbox.bundle" ../phase10_kdbus_sandbox/checkout
    python3 -B scripts/qb_build_support.py source

此 Git 操作读取本地 bundle。原工作区已有 Phase 10 checkout，可直接运行源码核对脚本。实际设备阶段的复核以归档身份数据为输入，另行获取新运行数据需要确认部署和设备访问授权。 [设备原始身份](11H_RUNTIME_VERIFICATION.md)
