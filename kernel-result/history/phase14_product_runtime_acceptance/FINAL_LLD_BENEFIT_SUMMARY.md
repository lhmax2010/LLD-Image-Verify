# 最终 LLD 收益与代价归档

目标修改为 `platform/kernel/linux-tizen-modules-source` 的 `1c26a4781d7813abd9ab2fb4c3fad35c52ec8fc8`，移除外部 Makefile 的 `LD = ${CROSS_COMPILE}ld`。受控构建确认 `kdbus.o` 从 GNU BFD 2.43 切换到 LLVM LLD 22.1.8，两组最终链接均使用 LLD，限定于本地 Raspberry Pi 4 ARMv7l 非 RT 构建配置。 [Phase 12 实际构建](../phase12_controlled_benchmark/CONTROLLED_BUILD_MATRIX.csv) · [Phase 13 复核](../phase13_final_acceptance/PHASE13_FINAL_ACCEPTANCE_REPORT.md)

| 量测项 | BFD 中间链接 | LLD 中间链接 | 结果 |
| --- | ---: | ---: | --- |
| `kdbus.o` | 2,505,192 Bytes | 1,998,564 Bytes | **减少 506,628 Bytes（20.22%）** |
| `.debug_str` | 601,961 Bytes | 95,814 Bytes | **重复字符串贡献减少 506,147 Bytes，占净尺寸减少约 99.91%** |
| strip 后 `kdbus.ko` | 162,584 Bytes | 161,292 Bytes | **减少 1,292 Bytes（0.79%）** |
| 最终模块中 ARM 数据映射符号 | 183 | 102 | **减少 81 个冗余符号** |
| 默认 Link Time 中位数 | 5.647 ms | 11.878 ms | **增加 6.231 ms（显示值差，+110.33%）** |
| 默认 Linker Peak RSS 中位数 | 7,700 KiB | 53,348 KiB | **增加 45,648 KiB（+592.83%）** |

真实 A/B 与同对象、同最终 LLD 的冻结重放均复现最终文件差。已检查的 ARM 区域边界、机器代码、重定位语义与静态 ABI 保持兼容。三组真实 GCC/BFD A/B 通过，每组七个安装形式模块逐字节一致。范围是对应 Tizen RPi4 ARMv7l 非 RT GCC SDK 的三个工具链路径。 [中间对象归因](../phase13_final_acceptance/INTERMEDIATE_SIZE_ATTRIBUTION.csv) · [ELF 与映射证据](../phase12_controlled_benchmark/ARM_MAPPING_SYMBOL_ANALYSIS.md) · [GCC/BFD 报告](../phase12_controlled_benchmark/GCC_COMPATIBILITY_REPORT.md)

原 160 条测量及配对 95% 置信区间复算一致。在独立八核补测中，`--threads=1` 相对同轮 LLD 默认配置缩短 **13.82%** wall time，输出逐字节一致。该补测的单线程 LLD 仍慢于 BFD 且 Peak RSS 更高。线程设置的影响已测量，内部具体开销的归因仍未确认。优先按具体工作负载审视全局推广，构建并发时需考虑峰值叠加。 [链路性能及范围](../phase13_final_acceptance/LINKER_THREAD_PERFORMANCE_REPORT.md)

PM 接受该 `kdbus` 场景的构建代价，改动按链接器适配和二进制尺寸优化归档。**Runtime Memory Benefit = NOT_MEASURED**。整包构建吞吐、其他 Tizen RPM 与设备常驻内存收益均未在这次对照中量化。 [Phase 13 正式决定](PM_PHASE13_FINAL_DECISION.md)
