# Phase 12I · ARMv7l 重定位链接的推广边界

**`GENERALIZATION_POTENTIAL = TARGETED_RESEARCH_ONLY`。** 优先考虑实际对 ARM32 `ET_REL` 产物执行 `ld -r`，并在最终交付物保留符号表的 RPM。相同类别的输出仍需实际复测至最终 strip 或打包环节。

## 机制与有限样本

Arm AAELF32 把 `$a`、`$t`、`$d` 定义为 ARM、Thumb 和数据区间的起点。纯数据节可省略映射符号，具有字面量池或 ARM/Thumb 切换的混合节需要保留正确边界。有效的比较基于按节和地址归一后的类型区间、重定位及适用的 BE8 要求，单独计数无法判断边界是否完整。 [Arm AAELF32 §5.5.5](https://github.com/ARM-software/abi-aa/blob/main/aaelf32/aaelf32.rst#mapping-symbols)

上游 GNU Binutils 2.43 的 ARM ELF 后端 `elf32_arm_output_arch_local_syms()` 会为满足条件且没有映射的非空输入节在节起点写入 `$d`。同类输入数据节合并后，输出可能保留多个连续数据标记。LLD 22.1.8 的 ARM 代码还会收集并排序可执行节中的映射符号以处理 BE8。对小端样本，应通过相同输入和链接输出判定差额究竟来自 BFD 补生成、LLD 去重、编译器输入差异，还是最终后处理。 [GNU BFD ARM 2.43 源码](https://github.com/RTEMS/sourceware-mirror-binutils-gdb/blob/binutils-2_43-branch/bfd/elf32-arm.c#L16918-L16977) · [LLVM LLD 22.1.8 ARM 处理](https://github.com/llvm/llvm-project/blob/llvmorg-22.1.8/lld/ELF/Arch/ARM.cpp#L998-L1067)

已核对同批原始七模块 RPM 的历史样本。旧、新 `kdbus.ko` 的 `$d` 为 183 → 102，`$a` 都是 122，`$t` 均为 0。81 个减少的 `$d` 均来自非可执行节，可执行节中按节、值和类别比较的映射多重集合一致。已发布 `kdbus.ko` 在 Phase 11 实际打包处理后仍有差异，另外六个同包模块的已发布 ELF 逐字节相同。旧、新发布 Base 快照、工具链 RPM 版本及构建环境存在差异，样本提供候选线索。 [逐模块样本](published-module-mapping-sample.json) · [Phase 11 ELF 比对](../../../kernel_lld_verification_20261125/11F_MODULE_BINARY_COMPARISON.md) · [环境对照](../../../kernel_lld_verification_20261125/11A_PREFLIGHT.md)

Phase 12 的本地 A/B 使用相同 LLVM SDK 和构建入口，七个 `modules_install` + strip 产物中也只有 `kdbus.ko` 变化，另外六个 SHA-256 一致。两个作业日志唯一的 `LD [M] ... .o` 中间目标都是 `kdbus/kdbus.o`。改善机会集中在该样本实际触发了中间复合链接的目标。当前对照覆盖一个 RPM 组件族。 [受控样本及作业关联](controlled-seven-module-sample.json) · [A 作业](../build/A-build.out#L114) · [B 作业](../build/B-build.out#L114)

## 后续定向筛选

1. 从确有 ARMv7l `ld -r` 命令的构建日志小范围选择另外一两个候选 RPM，优先有多输入对象的 Kbuild 模块或多阶段重定位链接。检查实际链接器和日志确认，记录架构、端序、GCC 配置要求及最终交付的 ELF 类型。
2. 在固定源码、工具链和宿主环境中，只替换中间链接器，锁定输入对象、顺序、链接脚本及响应文件。用相同最终链接、strip 和压缩条件比较。归档中间对象、未 strip 结果、发布形式和 RPM 的尺寸，符号归属及归一的区间、重定位和反汇编结果。
3. 优先量化保留局部符号表的产物。若打包规则移除相关局部符号，中间对象差异可能在交付环节消失。需要保留 ARM/Thumb/Data 边界、正常通过 ABI/GCC 回归且具有足够测量收益时，可再交 Kernel Owner 评审。结果按候选单独记录，保持本轮仅限定向样本。

从工作区运行 `python3 -B phase12_controlled_benchmark/scripts/collect_runtime_static.py` 复算归档样本。已有本地 A/B 构建输出时，以上命令带 `--controlled-sample` 复算同批模块比较。 [复验脚本](../../scripts/collect_runtime_static.py)
