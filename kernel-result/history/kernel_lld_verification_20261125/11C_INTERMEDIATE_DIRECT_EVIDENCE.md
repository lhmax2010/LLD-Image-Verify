# 11C 历史中间链接执行记录查验

**HISTORICAL_EXECUTION_EVIDENCE_UNAVAILABLE。** 新 QB 公开的成功 job 日志给出了 Raspberry Pi 4 ARMv7l 非 RT 组合对象 `kdbus/kdbus.o` 的安静模式目标行和后续产物链。原始 `.kdbus.o.cmd`、verbose 完整命令、成功 `execve` 记录、历史 `PATH` 和中间 ELF 均未取得，直接执行证据等级 E4 未建立。 [机器可读结果](11C_INTERMEDIATE_LINK_COMMANDS.json) · [原始成功日志](evidence/build/linux-tizen-modules-armv7l.out)

| 日志行 | 观察结果 |
|---|---|
| 467–470 | 外层进入外部源码，内层针对 `/boot/kernel/devel/kernel-devel-arm-rpi4` 和对应 `M` 目录构建。 |
| 473–504 | 构成 kdbus 的多个输入对象各有独立的 `CC [M]` 行。 |
| 505 | `LD [M]` 的输出路径以 `/kernel/kdbus/kdbus.o` 结尾。 |
| 511、528–530 | 后续记录 MODPOST、`kdbus.mod.o` 编译、`kdbus.ko` 最终链接和 BTF。 |
| 550–551、746、760 | 非 RT `kdbus.ko` 安装并 strip，写出匹配的 `linux-tizen-modules-rpi4-11.0.0-0.armv7l.rpm`，job 正常结束。 |
| 557 起 | 下一段转向 RT SDK，包含同名目标，未用于本结论。 |

组合规则在匹配的新 QB SDK 的 `scripts/Makefile.build` 第 432–444 行，使用 `kdbus/Makefile` 的 `kdbus-y` 组成列表。第 505 行是该组合输出的真实日志；能确认输出目标和成功 job 中的执行顺序，日志级别没有打印可复原的完整参数或已解析的 executable。源码推导的命令模板另载于 11D。 [实际目标定义](../kernel_lld_verification_20261120/pm_review_round3/evidence/source/external/kdbus/Makefile) · [SDK 规则](../kernel_lld_verification_20261120/pm_review_round2/evidence/kernel/source/scripts/Makefile.build) · [11D 工程推导](11D_INTERMEDIATE_LINKER_CAUSAL_ANALYSIS.md)

- 成功日志原文搜索 `.kdbus.o.cmd`、`.kdbus.ko.cmd`、`V=1`、执行跟踪、显式 `LD` 或完整 `ld* -r` 命令，`rg` 退出 1 表示没有命中。两个对应 job 的本地构建根路径均不存在，`stat` 退出 1。 [日志搜索回执](evidence/build/direct-evidence-corrected-log-search.cmd.json) · [路径查验回执](evidence/build/direct-evidence-builder-path-stat.cmd.json) · [路径错误](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
- 检查了新 QB 公开 builddata、ARMv7l succeeded 日志目录、profiling 数据集和已校验的 Unified packages/debug 及对应 Base packages filelists。公开 profiling 目录列出构建时长、依赖关系、硬件资源等统计数据，未列出 job 构建根或执行跟踪。限定架构的发布包 filelists 无 `kdbus.o` 或上述 `.cmd` 成员。 [公开 builddata 索引](evidence/build/builddata-index.out) · [日志索引](evidence/build/armv7l-succeeded-index.out) · [profiling 数据目录](evidence/build/profiling-armv7l-default-index.out) · [校验后的 filelists 搜索](evidence/build/base/repository-filelists-linker-paths.json)

若 PM 需要 E4，可向 QB 归档方索取该非 RT job 的 `.kdbus.o.cmd`、完整 verbose 或成功 `execve` 记录，以及可解析命令的构建根 `PATH` 与目标链接器路径/哈希。必须能关联第 505 行对应的组合对象和第 746 行写出的发布 RPM。
