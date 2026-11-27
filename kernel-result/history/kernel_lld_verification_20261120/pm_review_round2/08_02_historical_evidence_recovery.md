# 08.02 · 历史执行证据恢复

**HISTORICAL_EXECUTION_EVIDENCE_UNAVAILABLE**。本次取得准确的 ARMv7l 成功构建日志、生成配置、构建根标识、依赖保留记录和发布元数据。匹配构建的链接子进程 argv、历史 PATH 和 Kbuild 命令文件在本次授权范围内仍未取得。静态因果分析可继续。 [结构化结果](08_02_historical_evidence_recovery.json)

| 调查范围 | 本次结果 | 证据 |
| --- | --- | --- |
| 固定快照 build.xml、源项目 manifest、公开 builddata 和 ARMv7l success 日志目录 | 标准目标含 ARMv7l。Base 固定为 20261119.042539。目录列出了 linux-rpi 和 linux-tizen-modules 的成功日志。快照目录未索引这两个作业的命令文件、根文件系统、额外 verbose trace 或 shell 环境 | [RBS 构建信息](../evidence/repository/publication-build.out) · [源项目版本](../evidence/repository/manifest.out) · [公开数据目录](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [成功日志目录](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
| 精确主内核和树外作业成功日志 | 主内核作业使用 scratch.armv7l.27，树外使用 scratch.armv7l.0。两者由 qb-build-host-01 运行，有明确的工具包保留清单和 QEMU binfmt 注册。日志展开 SPEC shell 和部分递归 make，链接为 quiet LD、LD [M]。未命中展开的链接器 argv 或真实 PATH/LD 赋值 | [主内核构建根摘录](evidence/recovery/kernel-buildroot-excerpts.txt) · [树外构建根摘录](evidence/recovery/external-buildroot-excerpts.txt) · [原始主内核日志](../evidence/build/linux-rpi-armv7l.out) · [原始外部模块日志](../evidence/build/linux-tizen-modules-armv7l.out) |
| 发布产物归档 | 读取第一轮选中的内核、devel、devel-debuginfo、树内模块、树外模块五个 RPM 成员表。只在 devel 找到生成的 .config、include/config/auto.conf、include/generated/compile.h。所查五包未出现 .vmlinux.cmd、.vmlinux.o.cmd、.vmlinux.unstripped.cmd、压缩引导目录 .vmlinux.cmd 或任何 .ko.cmd。原打包 rsync 参数明确排除 *.cmd | [devel 实测成员表](evidence/recovery/rpm-command-record-members-arm-rpi4-linux-kernel-devel-6.12.80-0.armv7l.out) · [原打包日志 L14237](../evidence/build/linux-rpi-armv7l.out#L14237) |
| 本机路径 | 对历史日志给出的两条准确 BUILD_ROOT 和 /home/abuild/rpmbuild 仅执行 stat，均不存在于当前主机。第一轮本地 GBS 同 release 候选的 builder、2026-08-26 时间和 Build ID 均与目标不同，保留排除记录 | [stat 回执](evidence/recovery/exact-local-build-roots.cmd.json) · [stat 原始输出](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [旧候选排除](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
| 公开 profiling 与额外目录 | 精确快照的 ARMv7l result_meta.json 返回 HTTP 200，只含汇总时间、成功计数和空 DeployUrl。三个定向试探 builddata/buildinfo/、builddata/buildroots/、builddata/artifacts/ 均 HTTP 404。结果仅适用于这些公开地址 | [profiling 目录](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [profiling 汇总](evidence/recovery/profiling-result-meta.out) · [buildinfo](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [buildroots](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [artifacts](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
| 历史工具链清单 | exact Base RPM primary 的压缩和解压摘要均匹配 repomd。可与两个原始作业的保留版本关联。已复用原生 LLVM RPM，另取一个必要的加速 RPM 并核验两个历史路径 | [历史包选择](evidence/recovery/base-selected-packages.json) · [历史链接器路径](08_06_historical_linker_resolution.md) |

查询限定在已公开的精确 RBS 快照、已封存产物和两条本机准确路径。历史日志给出的 worker 名称用于身份关联。本轮未尝试连接该 worker 或私有 OBS，也未扫描其他主机。私有历史归档如仍存在，实际可用性有待具备访问权限的原构建方确认。

可离线复核 RPM 成员、原始日志匹配和构建根记录。默认复用本包已保存的 HTTP 回执。需要重新执行同范围的四项公开查询时传入 --probe-public。 [定向恢复脚本](scripts/recover_historical_execution.py)
