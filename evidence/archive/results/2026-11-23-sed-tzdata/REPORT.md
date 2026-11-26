# sed 和 tzdata 的历史链接器验证

QB 1234653 和新版 Unified `20261120.082536` 的 aarch64、armv7l 镜像都已验证。**每轮新增 12 个 GNU ld.bfd 2.43 确证实例，原有 70 个待确认实例减至 58 个。** [新旧结果汇总](updated-counts.json)

| 包 | 镜像内目标 | 每轮实例 | 结果 |
| --- | --- | ---: | --- |
| `sed` | `/usr/bin/sed` 及 recovery 中的副本 | 8 | GNU ld.bfd 2.43 |
| `tzdata` | `/usr/sbin/zdump`、`/usr/sbin/zic` | 4 | GNU ld.bfd 2.43 |

每轮 12 个实例对应 6 份不同的 ELF。两轮合计 7 份，因为旧轮和新版的 aarch64 `sed` 分别为 `4.1c-1.6` 和 `4.1c-1.7`，完整哈希不同。两轮的 `tzdata` 源 RPM 均为 `2026d-1.1`。ICU 中的同名 `zic` 是另一个目标，仍在待确认清单里。 [新版逐实例](latest-confirmed.tsv) · [旧版逐实例](qb1234653-confirmed.tsv)

## 证据链

1. 从原始构建日志定位四组架构和快照对应的 SRPM。SRPM 和发布 RPM 的 VCS 都与镜像清单对应的源提交匹配。运行时 RPM 与补入的 compiler-rt RPM 均按发布仓库 repodata 核对完整 SHA256。逐目标从运行时 RPM 提取 ELF，与镜像文件的完整 SHA256 对账，12 组全部匹配。
2. 使用相同的目标文件和日志中的最终 Clang 链接参数，分别指定 `-fuse-ld=bfd` 和 `-fuse-ld=lld`。实际链接输出分别显示 GNU Binutils 2.43 和 LLD 22.1.8。
3. 以原 RPM 拆分调试信息的方式处理重放 ELF。比较时只清零 `.gnu_debuglink` 中 4 字节的调试文件 CRC。12 组 GNU ld.bfd 产物全部匹配镜像 ELF，LLD 对照 0 组匹配。报告同时保留各版本的完整 SHA256，便于核对调试校验值导致的差异。 [逐目标重放矩阵与原始日志](replay-matrix.tsv)

`sed` 的正式链接使用 PGO。重放在每个环境中运行原训练测试套件，均通过 **57 项测试**，各生成 **185 份 raw profile**，数量与对应 QB 日志一致。旧构建根缺少 compiler-rt，从对应 Base 发布仓库补入 22.1.8。历史日志中的三个架构与快照组合所见 RPM release 与对应发布仓库不同。两种链接器的最终对照在每个环境中都使用同一个重建的 profile 和同一批对象，GNU ld.bfd 重放仍达到除调试 CRC 外的字节一致。 [PGO 训练与构建输入](sed-pgo.tsv)

## 更新后的统计

每轮 10,875 个实例中，**6,892 个确认为 LLD，140 个确认为 GNU ld，58 个证据不足**。其余分类的原始数值见机器可读汇总。58 个待确认实例由 23 个 Base 实例和 35 个 Unified 预编译语音实例组成，单轮按 SHA256 去重为 42 份，两轮合计 43 份。 [新版剩余目标](latest-remaining.tsv) · [旧版剩余目标](qb1234653-remaining.tsv) · [复跑方法和命令](../../METHODS.md#8-重放-sed-和-tzdata-的发布链接)
