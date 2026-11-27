# Tizen Kernel LLD · PM Review Round 3

**工程验收已正式归档并关闭。严格验收维持 CONDITIONAL_PASS，LLD-KERNEL-001 继续开放。** PM 批准 vmlinux、ARM 解压器与 59 个最终 .ko 的工程验收，并单独批准 vmlinux.o 的 E3。仓库与设备均保留原 LLD_CONFIRMED 0/59、LLD_INDICATED 59/59、E3 59/59、E4 0/59。完整中间链接覆盖仍为 NOT_VERIFIED。 [正式工程验收归档](KERNEL_LLD_ENGINEERING_ACCEPTANCE.md) · [PM 决定原文](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## LLD-KERNEL-001

**历史判定为 BFD_PATH_POSSIBLE。** 精确源码为 platform/kernel/linux-tizen-modules-source @ 25797e8af7ed95a5783bbe84c11959560aaf7e92 的顶层 Makefile 第 2 行：

    LD = ${CROSS_COMPILE}ld

历史构建的顶层 Kbuild 按 LLVM=1 选择并导出 ld.lld。Makefile.build 子进程读取外部 Makefile，普通文件赋值覆盖环境 LD，传给组合对象子进程。L612 记录 kdbus.o 中间合并。独立 modfinal 子进程继承顶层选择，L636 对应 kdbus.ko。历史 binutils 中 ld 和 ld.bfd 为同一 GNU BFD ELF 的硬链接，但未取得 L612 的命令记录、中间对象、对应调试文件或执行跟踪。交付 .ko 的编译器标记和 Build ID 无法识别上游合并使用的链接器。 [作用域根因](KDBUS_LD_OVERRIDE_ROOT_CAUSE.md) · [定向历史取证](KDBUS_HISTORICAL_INTERMEDIATE_LINK.md)

隔离实验在 GNU Make 4.3 下通过 21 个场景，记录 147 条变量观测、42 条 mock argv。模拟的历史参数形状观测到中间 ld、最终 ld.lld。历史作业为 GNU Make 4.4.1，实验只验证作用域机制。 [原始输入与复跑](KDBUS_MINIMAL_REPRODUCTION.md) · [实验 CSV](KDBUS_REPRODUCTION_RESULTS.csv)

## 候选及范围审计

推荐 **Option A**，在源码项目顶层 Makefile 删除一行 LD 赋值，由已经选择工具链的 Kbuild 提供 LD。已在封存副本通过零模糊 dry-run，模拟矩阵验证 ARMv7l/AArch64 的 GCC 前缀选择、LLVM 模式和显式 Clang+BFD 覆盖。真实模块构建与 ABI 兼容性仍待正常作业验证。独立用户若过去依赖隐式覆盖链接器，需在调用方显式选择对应内核 SDK 的工具链。 [四种方案及兼容性](KDBUS_LD_FIX_PROPOSAL.md) · [候选一行 diff](KDBUS_LD_FIX_CANDIDATE.patch)

本轮受限审计记录 153 条命中。其中 1 条为支持 kdbus.o 的合理风险，0 条为确认的绕行。已获取目标源码中未发现第二条同类可达旁路。主机构建规则和不参与目标链接的路径分别记录，后续可先对各 RPM 的构建入口及确切目标做筛选。 [审计范围与分布](KERNEL_LINKER_OVERRIDE_AUDIT.md) · [逐项结果](KERNEL_LINKER_OVERRIDE_FINDINGS.csv)

## 是否需要新的构建

已批准范围的关闭不需要单独重编 kdbus。提前构建只有在 PM 需要尽早验证候选或为新作业取得 E4 时有价值。建议在下次正常构建中保留目标 .cmd、V=1、成功 exec 与执行文件的 RPM NEVRA 和 SHA256，追踪中间对象到发布 RPM 的每次文件变化。新作业的证据只适用于该作业。PM 需决定何时安排一行候选的真实回归验证，以及是否另行批准定向构建和执行跟踪。 [未来 E4 及成本计划](FUTURE_KERNEL_LINKER_E4_VERIFICATION_PLAN.md)

Round 2 归档的 SHA256 和便携包校验通过。本轮只复用现有包、源码和日志，运行隔离的 Make 实验和候选 dry-run。未重编、重刷、重启、访问设备或写入产品源码。 [前轮校验回执](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [复算与输入索引](PM_REVIEW_ROUND3_EVIDENCE_INDEX.md) · [机器可读汇总](PM_REVIEW_ROUND3_SUMMARY.json)
