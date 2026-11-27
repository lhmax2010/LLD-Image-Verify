# Phase 13 · 最终收益复核与运行验收

**PM Review · 2026-11-27 · LLD-KERNEL-001**

本修改定位为 **LLVM LLD Adaptation & Binary Size Optimization**。PM 批准 Phase 12 阶段性验收，并接受该 `kdbus` 场景已测到的构建代价。工程问题保持 **CLOSED_ENGINEERING**。本轮复核确认本地 A/B E4、单行改动因果、文件尺寸与真实 GCC/BFD 兼容性。目标地址响应的设备与新 QB 平台及镜像均不匹配，运行验收待部署，**Product Merge Readiness = PENDING**。 [PM 原任务](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [产品验收矩阵](PRODUCT_MERGE_GATE_MATRIX.csv) · [结构化结果](PHASE13_FINAL_ACCEPTANCE_SUMMARY.json)

## Phase 12 证据复核

- **源码与冻结输入。** 从实际构建源码和日志复核每组的 53 个成员，唯一差异是 `kernel/Makefile` 删除 `LD = ${CROSS_COMPILE}ld`。响应文件、19 个有序输入、两个共同最终元数据对象及两个 SDK 文件逐件校验 SHA-256。重放的中间对象与各自 A/B 逐字节一致。用 A 的 `kdbus.mod.o` 和 `.module-common.o` 冻结最终 LLD 输入，隔离 B 组 modpost 中同一集合 154 个 CRC 对的排序差异。 [本轮核对记录](evidence/review/audit.json) · [冻结清单](../phase12_controlled_benchmark/evidence/replay/frozen-inputs.json) · [重放记录](../phase12_controlled_benchmark/evidence/replay/link-replay.json)
- **实际 E4。** A 中间执行 GNU BFD 2.43，B 中间执行 LLVM LLD 22.1.8，两组最终均执行 LLD。四条记录各自核对成功 `execve`、实际 executable 路径及 SHA-256、完整 argv、`exit_group(0)`、Kbuild `.cmd` 以及输出文件路径与 SHA-256。该 E4 适用于本地受控作业，历史 QB 评级与缺失边界沿用 Phase 11。 [原始执行跟踪](../phase12_controlled_benchmark/evidence/build/selected) · [历史直接证据说明](../kernel_lld_verification_20261125/11C_INTERMEDIATE_DIRECT_EVIDENCE.md)
- **环境边界。** 使用目标 LLVM SDK、匹配 Clang/LLD 22.1.8 加速负载和 pahole 1.29。固定 Base 依赖遇到 HTTP 404，A/B 共用已恢复的只读 Tizen ARM 用户空间、GNU Make 4.4.1、旧 qemu-accel 的 BFD 2.43 及 ABI 匹配 libbpf 1.6.2-1.1。两组沿用非 RT 入口、BTF 与 Kbuild strip，记录相同的 depmod 告警。完整历史 QB 构建根和 RPM 包装流程的等价性未建立。 [Phase 12 环境说明](../phase12_controlled_benchmark/PHASE12_LLD_BENEFIT_REPORT.md) · [依赖获取状态](../phase12_controlled_benchmark/evidence/toolchain/base-inputs.json) · [证据包完整性](evidence/review/phase12-bundle.out)

## 中间和最终文件归因

| 范围 | BFD 中间链接（Bytes） | LLD 中间链接（Bytes） | 差额 |
| --- | ---: | ---: | ---: |
| `kdbus.o` 整个文件 | 2,505,192 | 1,998,564 | −506,628（−20.22%） |
| `.text` | 67,428 | 67,428 | 0 |
| `.data` / `.rodata` | 48 / 1,256 | 48 / 1,256 | 0 |
| `.bss` | 0 | 0 | 0，逻辑尺寸均为 29 |
| `.debug_info` / `.debug_line` | 992,223 / 92,391 | 992,223 / 92,391 | 0 |
| `.debug_str` | 601,961 | 95,814 | −506,147 |
| `.symtab` / `.strtab` / `.shstrtab` | 14,592 / 7,683 / 523 | 12,960 / 9,215 / 741 | −1,632 / +1,532 / +218 |
| `.ARM.attributes` | 50 | 54 | +4 |
| ELF header / section headers | 52 / 2,240 | 52 / 2,240 | 0 |
| 零值对齐填充 / 其余布局字节 | 35 / 1 | 59 / 0 | +24 / −1 |
| strip 后 `kdbus.ko` | 162,584 | 161,292 | −1,292（−0.79%） |

两份 `.debug_str` 均为 `SHF_MERGE|SHF_STRINGS`、条目单位 1 字节。BFD 中间对象有 50,290 个非空物理字符串，其中 7,179 个不同值。LLD 物理存储恰为同一组 7,179 个不同值，去掉的 43,111 个重复条目正好合计 506,147 Bytes，未依赖额外后缀折叠。其他 `.debug_*` 和 `.rel.*` / `.rela.*` 总尺寸差均为零，某些 DWARF 引用和重定位记录的原始编码有变化。去掉的 101 个中间映射符号与 1 个局部 `.note.GNU-stack` 节符号合计解释 `.symtab` 的 −1,632 Bytes。其余节变化包含 `.comment` −396、四个常量或字符串节合计 −230。节载荷净减少 506,651 Bytes，物理间隙净增加 23 Bytes，和整个文件精确对平。 [逐节及物理布局 CSV](INTERMEDIATE_SIZE_ATTRIBUTION.csv) · [字节范围与字符串详表](evidence/review/intermediate-layout.json)

真实 A/B 和冻结重放均得到最终文件 −1,292 Bytes。最终差额为 81 个局部 ARM `$d` 数据映射符号各 16 Bytes，加上 `.ARM.attributes` 多 4 Bytes。BFD map 复核了 101 个中间新增标记，最终 81 个均可归到该集合，75 个有唯一输入对象，6 个常量合并后有多个等价候选。两个最终 ELF 的 ARM/Thumb/Data 有效边界相同。发布形式 A/B 分别与历史旧、新 QB 的模块逐字节一致。历史构建是否实际切换链接器仍由其各自证据评级约束。 [中间标记复验](evidence/review/mapping-intermediate-review.json) · [最终标记复验](evidence/review/mapping-stripped-review.json) · [静态 ABI 与归一反汇编](../phase12_controlled_benchmark/ARM_MAPPING_SYMBOL_ANALYSIS.md)

506,628 Bytes 是单个中间文件的磁盘体积差。最终模块节省 1,292 Bytes，本地同参数单文件 XZ 减少 312 Bytes。历史双 QB 的 RPM XZ 负载差为 432 Bytes，范围涉及两个发布包。Debuginfo RPM 是否减少尚无对应独立构建证据，I/O、整包构建资源、设备常驻内存均未测量。 [压缩对照](../phase12_controlled_benchmark/evidence/packaging/compression.json) · [运行内存机制](../phase12_controlled_benchmark/RUNTIME_MEMORY_FEASIBILITY.md)

## 构建代价、兼容性与产品边界

Phase 12 的 160 次测量及 28 条摘要逐行复算一致。保留默认 wall time 中位数增加 **+6.231 ms（显示值之差，+110.33%）** 及 Peak RSS 增加 **+45,648 KiB（+592.83%）**。Phase 13 的等八核补测覆盖 BFD 与 LLD 默认、1、2、4、8 线程共 288 条。LLD 单线程比本轮 LLD 默认快 13.82%，输出字节一致，RSS 略增，耗时与 RSS 仍高于 BFD。线程设置的影响已测量，创建、同步和内部分配等细分开销仍无 profiling 归因。高并发下应关注多个链接器进程同时达到峰值的容量风险。 [性能与置信区间](LINKER_THREAD_PERFORMANCE_REPORT.md)

三个真实 GCC/BFD C/D 对均用 `tizen-unified-dev_20261120.082616` 的 Raspberry Pi 4 ARMv7l 非 RT GCC SDK，Linux 提交 `42aeefac58edeb081aff440f0b60be71cbe49755`，release `6.12.80-arm-rpi4-v7l`。覆盖 ARM 原生工具负载、精确发布版 x86-64 加速器以及显式 GNU binutils 目录前缀。三组都是该目标的工具链路径覆盖，每对七个安装形式模块逐字节一致，345 个导入 CRC 匹配对应 SDK。已检查的静态 ABI 未发现回归。 [三组 GCC/BFD 原报告](../phase12_controlled_benchmark/GCC_COMPATIBILITY_REPORT.md) · [核验原始报告状态](evidence/review/audit.json)

新 QB 的启动、59 模块身份与运行、错误回归及功能验证保留待项。PM 已接受本例构建代价，产品合入仍以正确部署及获授权的运行验收为准。 [运行报告](RUNTIME_REGRESSION_REPORT.md) · [Kernel Owner 英文技术说明](KERNEL_OWNER_FINAL_JUSTIFICATION.md) · [复验步骤](REPRODUCE.md)
