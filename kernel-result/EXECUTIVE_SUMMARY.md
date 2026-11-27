# Executive summary · LLD-KERNEL-001

**工程状态 CLOSED_ENGINEERING。产品合入准备 PENDING。** PM 已批准 Phase 13 工程验收，并接受这个 `kdbus` 构建场景的实测代价。Phase 14 确认目标新 QB 设备正常启动、59/59 模块与发布 RPM 一致且 `kdbus` 已加载为 `live`。功能回归等待批准的实际用例，Kernel Owner 范围和代价审核待完成。 [正式 PM 决定](history/phase14_product_runtime_acceptance/PM_PHASE13_FINAL_DECISION.md) · [产品门槛](history/phase14_product_runtime_acceptance/PRODUCT_MERGE_FINAL_GATE_MATRIX.csv)

| 指标 | BFD | LLD | 差异 |
| --- | ---: | ---: | ---: |
| `kdbus.o` | 2,505,192 B | 1,998,564 B | −506,628 B（20.22%） |
| strip 后 `kdbus.ko` | 162,584 B | 161,292 B | −1,292 B（0.79%） |
| 默认链接墙钟中位数 | 5.647 ms | 11.878 ms | +6.231 ms（+110.33%） |
| 默认链接进程峰值 RSS 中位数 | 7,700 KiB | 53,348 KiB | +45,648 KiB（+592.83%） |

重复 `.debug_str` 字符串贡献 506,147 B，占中间对象净减少量约 99.91%。最终文件少 81 个冗余 ARM 数据映射符号。三组真实 GCC/BFD 对照通过，各组七个安装形式模块逐字节一致。已检查的 ARM 区域边界、代码、重定位和静态 ABI 保持兼容。 [逐节尺寸归因](history/phase13_final_acceptance/INTERMEDIATE_SIZE_ATTRIBUTION.csv) · [GCC 兼容性](history/phase12_controlled_benchmark/GCC_COMPATIBILITY_REPORT.md)

旧发布 QB 的 `kdbus.o` 保持 `BFD_PATH_POSSIBLE`，新发布 QB 两步链接各为 E3，Phase 12 本地对照有 E4 实际执行证据。相同八核资源补测中，`--threads=1` 比同轮 LLD 默认快 13.82%，产物字节一致，仍较 BFD 慢且使用更多峰值 RSS。性能内部根因与运行内存收益仍未测量或证实。 [性能报告](history/phase13_final_acceptance/LINKER_THREAD_PERFORMANCE_REPORT.md) · [完整技术复核](MASTER_REPORT.md)
