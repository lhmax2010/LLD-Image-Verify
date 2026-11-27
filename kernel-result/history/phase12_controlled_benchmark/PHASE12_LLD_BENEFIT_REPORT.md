# Phase 12 · LLD 受控收益与产品兼容性

**PM Review · Raspberry Pi 4 ARMv7l 非 RT · Kernel 6.12.80-arm-rpi4-v7l**

删除外部 Makefile 的 `LD` 赋值，在本地受控构建中把 `kdbus.o` 的中间链接器从 GNU BFD 2.43 切换到 LLVM LLD 22.1.8。两组 `kdbus.ko` 最终链接仍为 LLD，实际执行证据达到 **E4**。固定对象重放复现最终文件减少 **1,292 Bytes（0.79%）**。本工作负载的 LLD 中间链接同时出现**构建耗时与进程峰值 RSS 回归**。运行内存收益未测量，产品合入状态为 **PENDING**。 [汇总 JSON](PHASE12_LLD_BENEFIT_SUMMARY.json) · [构建矩阵](CONTROLLED_BUILD_MATRIX.csv)

## 12A/B · 构建可行性与单变量对照

新 QB 的匹配 LLVM SDK RPM 通过发布 SHA-256，保存配置、generated headers、`Module.symvers`、`vmlinux`、BTF helper 和模块链接脚本的摘要。实际 ARMv7l 编译使用新 QB 的 Clang/LLD 22.1.8 加速负载，pahole 1.29 来自同一 Unified QB。当前固定 LLVM Base 中多项 RPM URL 返回 404，因此复用只读 Tizen ARM 构建根。本地使用已归档的旧 qemu-accel BFD 2.43、GNU Make 4.4.1 和 ABI 匹配的 libbpf 1.6.2-1.1。两组共用这些已冻结的依赖、工具、CPU 4、`-j1`、路径、变量、宏和 strip 规则。关键信息见记录中的实际路径及摘要。 [主机与进程跟踪探测](evidence/preflight/host.out) · [SDK 摘要](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [固定 Base 获取诊断](evidence/toolchain/base-inputs.json) · [版本探测](evidence/build/probe-ready.out) · [BFD 载体](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

两组都沿用包装 SPEC 的非 RT 入口 `make -C kernel KERNELDIR=...` 与 `modules_install INSTALL_MOD_STRIP=1`。源文件清单逐项核对，唯一变化为 `kernel/Makefile` 删除 `LD = ${CROSS_COMPILE}ld`。执行追踪显示 A 实际转到 `/emul/usr/bin/ld`，B 实际转到 `/emul/usr/bin/lld`，两组最终链接均转到 `/emul/usr/bin/lld`。两组在相同 guest 路径构建，复合对象的响应文件、对象顺序及各对象 SHA-256 逐一相同。四次目标链接都保留成功 exec、完整 argv、退出码、可执行文件摘要以及对应输出。Phase 12 的 E4 仅覆盖这些本地作业。历史 QB 的直接执行证据仍未恢复。 [受控构建与产物](evidence/build/controlled-builds.json) · [实际跟踪和 Kbuild 命令](evidence/build/selected)

两组都完成模块构建、BTF 后处理与 strip。`modules_install`记录同样的 depmod 缺失告警，七个目标文件仍已生成。未重现完整 RPM 包装流程。本地发布形式的 A、B `kdbus.ko` 分别与旧、新 QB 发布文件的 SHA-256 完全相同，另外六个同批 strip 后模块在 A/B 中逐字节一致。 [A 退出记录](evidence/build/A-build.cmd.json) · [B 退出记录](evidence/build/B-build.cmd.json) · [七模块对照](evidence/runtime/controlled-seven-module-sample.json)

## 12C/D/G · 因果、尺寸和正确性

重放冻结实际中间链接参数和响应文件顺序，两个链接器使用同一份 19 个输入对象。中间链接命令只切换可执行文件及独立输出路径，诊断用 `-Map` 另跑并核对输出逐字节相同。重放得到的两个中间对象分别和原 A、B 构建逐字节相同。最终使用同一 LLD、链接脚本、A 的 `kdbus.mod.o` 与 `.module-common.o`、BTF 处理和 strip。实际 B 组 modpost 生成的 154 个名称/CRC 对顺序变化，冻结最终输入消除了这项中间结果诱发的顺序差异。冻结版 LLD 最终文件与实际 B 的 SHA-256 有别，大小和静态核对结论一致。 [冻结输入](evidence/replay/frozen-inputs.json) · [命令与最终结果](evidence/replay/link-replay.json)

| 产物 | BFD 中间链接（Bytes） | LLD 中间链接（Bytes） | 差值（Bytes） |
| --- | ---: | ---: | ---: |
| `kdbus.o` | 2,505,192 | 1,998,564 | −506,628（−20.22%） |
| 未 strip `kdbus.ko` | 2,071,276 | 2,069,984 | −1,292（−0.06%） |
| `--strip-debug` 后 `kdbus.ko` | 162,584 | 161,292 | −1,292（−0.79%） |
| 同参数单文件 XZ（本地） | 48,312 | 48,000 | −312 |

中间尺寸差以 `.debug_str` 变化为主。最终文件差额是 `.symtab` 少 81 条 16 字节的局部 `$d`（−1,296 Bytes）与 `.ARM.attributes` 多两条默认值的显式编码（+4 Bytes）。最终模块的 81 个差异标记全部位于非可执行数据节，保留所有已核对的有效区域边界。Arm 规范允许纯数据节省略映射符号。冻结重放的 BFD map 将中间对象多出的 101 个 `$d` 全部定位到原本无对应标记的非可执行输入节贡献起点。最终文件的 81 个差异均来自该集合，其中 75 个可唯一归到输入对象，另 6 个在合并折叠后出现多个等价候选。对照 ELF 的代码字节、GNU/LLVM 归一反汇编、模块符号接口、版本 CRC 和最终重定位语义通过。中间对象的 ARM 标志、SHF_MERGE 引用及调试重定位编码有变化，已按目标值及加数语义核对。 [映射符号与正确性](ARM_MAPPING_SYMBOL_ANALYSIS.md) · [ELF 尺寸表](ELF_SIZE_COMPARISON.csv) · [Arm AAELF32](https://github.com/ARM-software/abi-aa/blob/main/aaelf32/aaelf32.rst#mapping-symbols)

本地同样的 strip 处理两侧均去除 1,908,692 Bytes，最终大小差早于 strip。单文件 XZ 只度量相同压缩选项下的 `.ko`。历史发布 RPM XZ 负载差值为 −432 Bytes，考虑完整 RPM 的其他字段和打包条件，归类为 `OBSERVED_NOT_ATTRIBUTED`。单行因果结论适用于这次受控构建和重放，历史构建过程仍按原有证据评级。 [等条件后处理](evidence/packaging/compression.json) · [历史打包和内存分析](RUNTIME_MEMORY_FEASIBILITY.md)

## 12E · 中间链接耗时和进程 Peak RSS

同一 x86-64 宿主、实际原生加速链接器、相同冻结对象与文件系统。每个配置每个链接器 5 次预热，40 次有效测量，配对随机顺序。默认选项两组共享 CPU 4–7，额外对照共享 CPU 4，且 LLD 显式 `--threads=1`。额外未计时追踪中，默认 BFD 创建 0 个工作线程，LLD 创建 5 个，单线程对照均为 0。计时区间为原生子进程启动至退出，包含加载与写输出的成本。strace、ELF 分析及摘要核对在计时区间外。原始 CSV 记录每个样本的频率快照、负载、wall/user/system、RSS、缺页、退出码及输出文件大小。置信区间为 4,000 次配对 bootstrap 的相对中位数差。 [测量设计](evidence/benchmark/design.json) · [原始 CSV](LINKER_BENCHMARK_RAW.csv) · [统计 CSV](LINKER_BENCHMARK_SUMMARY.csv)

| 配置 | 指标 | BFD 中位数 | LLD 中位数 | LLD 相对增幅（95% CI） |
| --- | --- | ---: | ---: | ---: |
| 默认线程 | Wall time | 5.647 ms | 11.878 ms | +110.33%（+101.35% 至 +116.02%） |
| 默认线程 | Peak RSS | 7,700 KiB | 53,348 KiB | +592.83%（+589.30% 至 +594.51%） |
| 单 CPU / 单线程 | Wall time | 5.108 ms | 10.362 ms | +102.86%（+99.91% 至 +110.24%） |
| 单 CPU / 单线程 | Peak RSS | 7,756 KiB | 53,530 KiB | +590.18%（+587.06% 至 +593.65%） |

两种资源配置下的 wall time 和 Peak RSS 都是 **REGRESSION**。CPU 频率随运行变化，置信区间只覆盖本次同宿主配对采样的不确定性。初次 Python 子进程计时使 BFD 的 RSS 达到明显的启动内存下限，已归档该轮记录。正式结果由低占用原生 `fork/wait4` 计时器重测，进程峰值适用于本次链接工作负载。 [初测记录](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [原生计时器](scripts/bench_timer.c) · [重测回执](evidence/benchmark/native-benchmark.cmd.json)

## 12F · 真实 GCC/BFD 构建兼容性

使用与目标匹配的 GCC/BFD RPi4 ARMv7l 非 RT Kernel SDK。C/D 在同一配置下执行真实模块构建，原与修复 Makefile 两侧均使用实际 GNU BFD 完成中间与最终链接，并验证模块 ELF、符号、重定位和版本 CRC。在精确 GCC QB 用户空间工具链的加速路径和原生 ARM 工具对照中，C/D 各自的七个已 strip 模块逐字节一致。加速对照每组 345 个导入 CRC 匹配 GCC SDK，其中 kdbus 有 153 个。此项为真实构建结果。Phase 11 的模拟结果独立保留。 [GCC/BFD 报告](GCC_COMPATIBILITY_REPORT.md)

## 12H/I · 运行内存与推广

匹配 ARM kernel loader 对临时完整符号表和持久 core kallsyms 采用不同分配策略。部分减少的映射符号满足 core kallsyms 的保留条件，实际常驻页变化仍受类型筛选、字符串表范围、其他节布局和 4 KiB 页对齐影响。运行内存为 `NOT_MEASURED`，新 QB 运行回归仍待部署。 [运行内存静态依据与测试设计](RUNTIME_MEMORY_FEASIBILITY.md)

推广结论为 `TARGETED_RESEARCH_ONLY`。可定向调查存在多输入 ARMv7l 重定位链接并保留符号表的 RPM。一例文件尺寸收益不足以推断其他包有相同结果，本例还实测了时间和峰值 RSS 回归。 [有限样本及筛选方案](evidence/runtime/generalization.md) · [Kernel Owner 英文摘要](KERNEL_OWNER_BENEFIT_SUMMARY.md)

本轮结果提交 PM Review。产品合入准备状态为 **PENDING**，等待新 QB 运行回归及产品决策。 [复验命令与证据包范围](REPRODUCE.md)
