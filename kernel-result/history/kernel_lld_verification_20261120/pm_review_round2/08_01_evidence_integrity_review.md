# 08.01 · 第一轮证据完整性复核

**PASS。** 离线入口先读取并独立复核第一轮 1937 条 SHA256 和 497 条命令回执，再复制到独立工作目录复跑。进程退出 0。原目录保留第一轮文件。模块覆盖、加载映射、身份和最终结构化报告的复跑输出均与原件 SHA256 一致。 [原索引](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [原命令索引](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [复跑 stdout](evidence/round1-offline-replay.out) · [复跑回执](evidence/round1-offline-replay.cmd.json) · [复跑逐文件比较](evidence/round1-replay-output-comparison.json)

- **候选范围** 重算 filelists 的压缩与展开摘要，精确 release 下有两个二进制 .ko 包，共 59 个目标。93 条候选和 10 个选中条目的 CSV、JSON 和 RPM 摘要一致。RPM header 文件摘要、已解包 payload、发布模块分区及设备文件四处一致。树外源码提供 RPM 属本轮新增因果证据。 [仓库清单](../02_kernel_rpm_inventory.csv) · [逐项交叉审计](08_01_evidence_integrity_review.json)
- **最终目标绑定** 59 个 quiet LD 事件的完整目标名均以 .ko 结束。相同 LD [M] 标签下的 .o 行单独处理。逐条核对同一日志的 LLVM=1、目标范围、最终 .ko 路径、安装路径、RPM 写出和成功结束。树外 7 条均有各自构建的工具链设置与 .ko 事件。 [原索引](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [作用域复核](08_05_out_of_tree_modules.md)
- **重复与遗漏** 正式 payload 中模块名、basename 和构建路径键均无重复。外置 RT 构建中的同名目标位于明确排除范围。kdbus/kdbus.o 与 kdbus/kdbus.ko 分开。仓库 filelists、RPM header、日志、解包清单及设备路径集合闭合，未发现匹配分母的静默遗漏。 [59 行原始关联](08_01_evidence_integrity_review.json)
- **运行证据** 对 11 个原始 sysfs hexdump 重建头部和 GNU Build ID，逐个验证 note SHA256，再与设备模块 ELF 和 /proc/modules 行比对，11/11 一致。 [sysfs 原文](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [加载清单](../05_loaded_module_mapping.csv)
- **快照绑定** 使用 build.xml ID、Base ID、standard/armv7l、成功日志精确下载 URL、manifest revision 和完整日志 SHA256 绑定。发布签名可用性保留第一轮限制。 [发布 build.xml](../evidence/repository/publication-build.out) · [源码 manifest](../evidence/repository/manifest.out) · [原始日志索引](evidence/ORIGINAL_BUILD_LOG_INDEX.json)
