# LLD-KERNEL-001 · kdbus.o 历史中间链接证据

**判定为 BFD_PATH_POSSIBLE，历史实际链接器未确认。** 适用范围为固定快照 tizen-unified-toolchain_20261120.082536 的 standard/armv7l 非 RT RPi4 外置模块作业。完整发布日志 SHA256 为 41163ea6c43b4f04f1dfcdb4c0997e5d1cb2149f3e14a6c1bf57f65771061b83，与前两轮封存记录一致。 [机器可读判定](KDBUS_HISTORICAL_INTERMEDIATE_LINK.json) · [完整日志](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [带行号摘录](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

| 搜索范围 | 观察 |
| --- | --- |
| 作业日志与目标范围 | L612 是非 RT 的 quiet LD [M] …/kdbus/kdbus.o，L636 是独立的最终 kdbus.ko，L657–658 安装并剥离该 .ko。L664 之后是另一段 RT 构建，L709 与 L733 对应该段同名目标。日志中未发现针对 L612 的展开 argv、原始 .kdbus.o.cmd 或进程跟踪。 [日志 L612](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [摘录](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
| 目标 RPM、源码 RPM 与归档索引 | 使用现有精确 RPM 文件头查询非 RT 目标包、构建 SPEC 源码 RPM 和源码 provider RPM。检查已封存 packages、debug、source 下的 primary 与 filelists 及归档路径，均未找到目标 .kdbus.o.cmd、可单独检查的 kdbus.o（含压缩或调试副本），或对应 kernel-module 的 kdbus.ko 调试陪件。 [目标 RPM 文件摘要](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [源码 RPM 内容](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [provider 内容](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [索引查询结果](KDBUS_HISTORICAL_INTERMEDIATE_LINK.json) |
| debuginfo | L775–777 将已安装的 *.ko 复制到打包树，L784 调用 find-debuginfo，L807–808 报告空 debugsource 文件列表。精确 armv7l 调试元数据的 kdbus-test.debug 属于 tests-debuginfo 中的用户态测试工具，源码 debugsource 中匹配测试目录或头文件。均无法约束目标中间对象。 [打包日志 L775–808](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [调试索引候选](KDBUS_HISTORICAL_INTERMEDIATE_LINK.json) |
| 发布最终 ELF | 非 RT kdbus.ko 与 RPM 文件摘要及前轮留存设备文件的 SHA256 同为 1186ce63d4c7c5f995fd0099becfe8834d52da35939d285f5c0bd9d62042a576。GNU Build ID 为 b85657c98fa68ebf43a90520861cd8f461c0abad，.comment 只记录 clang version 22.1.8，未找到 .gnu_debuglink 或调试段。该 Build ID 和编译器标识属于最终交付对象，不能识别上游一次 -r 合并的可执行文件。 [ELF 输出](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [readelf 诊断](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
| 历史执行记录 | 沿用 Round 2 已核实的精确 buildroot 缺失、私有 worker 归档不可取得、公开 buildinfo/buildroots/artifacts 探测 404、profiling 仅含聚合结果。当前轮没有重探这些位置、联系设备或下载 RPM。 [已封存搜索结论和回执索引](../pm_review_round2/08_02_historical_evidence_recovery.json) |

历史 L437 记录构建环境保留 binutils-2.43-1.8.armv7l。该 RPM 中 /usr/bin/ld 与 /usr/bin/ld.bfd 的 inode 均为 952，两者为同一 ARM GNU BFD ELF 的硬链接，SHA256 为 d3fbf8e82e019182675ec373a7af8c046743fde5c00294441f34392a3dd28af9。真实外部模块 Makefile L2 的普通赋值 LD = ${CROSS_COMPILE}ld 在前缀为空时产生命令名 ld，历史包由此提供有依据的 BFD 候选。日志没有记录该目标生效的 CROSS_COMPILE、最终 argv 或原进程的 PATH。若存在高优先级的有效 LD=ld.lld，LLVM 也会是可行的替代机制，历史证据未显示该覆盖实际发生。 [binutils 原包证据](../pm_review_round2/evidence/external/historical-binutils-resolution.json) · [真实 Makefile](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [Kbuild 中间链接规则](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [历史 LLD 候选](../pm_review_round2/08_06_historical_linker_resolution.json)

从 Round 3 目录执行下列命令可复验本项。脚本读取封存输入，输出新增的查询回执、校验结果与报告数据。

    PYTHONDONTWRITEBYTECODE=1 LC_ALL=C python3 -B scripts/check_kdbus_history.py --archive-root ..

[复验脚本](scripts/check_kdbus_history.py) · [执行回执](evidence/history/targeted-search.cmd.json) · [输出](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
