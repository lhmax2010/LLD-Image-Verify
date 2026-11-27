# Round 3 证据索引与复跑

| 事项 | 证据 |
| --- | --- |
| PM 签发范围 | [原指令](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [关闭记录](KERNEL_LLD_ENGINEERING_ACCEPTANCE.md) · [JSON](KERNEL_LLD_ENGINEERING_ACCEPTANCE.json) |
| 匹配的已封存输入 | [Round 2 汇总](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [来源 SHA256 与原相对路径](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [上一轮完整性](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
| 精确源码和真日志 | [外部 Makefile L2](../pm_review_round2/evidence/external/source/Makefile#L2) · [SPEC](evidence/source/external/linux-tizen-modules.spec) · [外置构建日志 L612](../evidence/build/linux-tizen-modules-armv7l.out#L612) · [源码和日志绑定](KDBUS_LINKER_VARIABLE_TRACE.json) |
| 最小 Make 实验 | [复跑说明](KDBUS_MINIMAL_REPRODUCTION.md) · [实验脚本](reproducer/run.py) · [场景 argv 和退出码](evidence/reproducer/cases.json) · [结果 CSV](KDBUS_REPRODUCTION_RESULTS.csv) |
| 历史 kdbus.o | [取证报告](KDBUS_HISTORICAL_INTERMEDIATE_LINK.md) · [历史 enum](KDBUS_HISTORICAL_INTERMEDIATE_LINK.json) |
| 候选修复 | [方案](KDBUS_LD_FIX_PROPOSAL.md) · [补丁](KDBUS_LD_FIX_CANDIDATE.patch) · [dry-run 回执](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
| 通用扫描 | [受限范围和结论](KERNEL_LINKER_OVERRIDE_AUDIT.md) · [逐项分类](KERNEL_LINKER_OVERRIDE_FINDINGS.csv) |
| E4 计划 | [未来正常作业的取证办法](FUTURE_KERNEL_LINKER_E4_VERIFICATION_PLAN.md) · [总报告](PM_REVIEW_ROUND3_REPORT.md) |

轻量包内含报告、源文件与日志证据、复跑脚本和清单。原 RPM 仍在前两轮中，未复制到压缩包。目标历史检查和候选检查脚本需要相邻的原归档，具体参数见各报告末尾。独立复跑 Make 模型只需要轻量包和 GNU Make、Python 3。

在解包后的 pm_review_round3 目录执行：

    sha256sum -c --quiet BUNDLE_SHA256SUMS
    python3 -B scripts/check_round3_bundle.py
    python3 -B reproducer/run.py --output /path/to/new-experiment

实验结果的临时路径会变化。对比 case、stage、origin、flavor、raw_ld、effective_ld 及 mocked_argv 即可复核实际观测口径。旁路分类规则及审计脚本见 [寻找同模式](KERNEL_LINKER_OVERRIDE_AUDIT.md)。
