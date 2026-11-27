# 链接器耗时、峰值 RSS 与线程补测

**Phase 12 原始性能结论复算通过。** 默认配置下，LLVM LLD 22.1.8 的 wall time 中位数由 5.647 ms 增至 11.878 ms，按报告显示值相差 **+6.231 ms**。用未舍入的中位数相减为 +6.2303685 ms，按原统计定义增 **110.33%**。中位 Peak RSS 由 7,700 增至 53,348 KiB，相差 **+45,648 KiB（+592.83%）**。负收益均纳入 PM 验收。 [Phase 12 原 CSV](../phase12_controlled_benchmark/LINKER_BENCHMARK_SUMMARY.csv) · [本轮复算记录](evidence/review/audit.json)

## 原测量与置信区间

原 160 条有效记录含两个 profile，各为 40 个 BFD/LLD 配对。每个配对有相同 profile、相同 pair ID 及位置 1、2。沿用原 seed 20261126、nearest-rank P95 和 4,000 次有放回重采样。对每次重采样保留 BFD/LLD 的块配对，计算两组中位数，以 BFD 中位数为分母，取 2.5%、97.5% 分位。全部 28 条统计行复算一致。默认线程的 wall time 增幅 95% CI 为 +101.35% 至 +116.02%，RSS 为 +589.30% 至 +594.51%。单 CPU 显式单线程对照仍增加 102.86% wall time 和 590.18% RSS。两个原 profile 分别使用 CPU 4–7 和 CPU 4，未计时探测的 BFD 工作者数均为 0。LLD 默认创建 5 个工作线程，显式单线程创建 0 个。 [原设计](../phase12_controlled_benchmark/evidence/benchmark/design.json) · [原始样本](../phase12_controlled_benchmark/LINKER_BENCHMARK_RAW.csv) · [逐行复算实现](scripts/review_phase12.py)

## 相同八核资源下的六组补测

复用同一 19 个输入对象及顺序、响应文件、工具 executable 和原生计时器。六组共享 CPU 0–7，对应八个单独、同最高标频的核心，使用同一目标路径和文件系统。选项差异为实际链接器或 LLD 的 `--threads`。每模式 6 次预热和 48 次有效测量，共 **288 条**。每块含六种模式，各模式在每个位置出现次数相同，块内顺序随机化。RSS、缺页、CPU 时间来自子进程 `wait4`，频率、负载、输出哈希与线程诊断在计时范围之外。区间为同块配对的 pointwise 95% bootstrap，不能外推跨宿主或跨时段差异。 [设计与命令](evidence/threads/design.json) · [CPU 拓扑](evidence/threads/host.out) · [原始数据](evidence/threads/measurements.csv)

| 模式 | 工作线程创建数¹ | Wall 中位数 ms | Wall P95 ms | Peak RSS 中位数 KiB | User / System 中位数 ms | Minor / Major 缺页中位数 | 输出 Bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GNU BFD 2.43 | 0 | 5.835 | 8.614 | 7,596 | 2.968 / 3.149 | 1,013 / 0 | 2,505,192 |
| LLD 默认 | 8 | 12.920 | 16.614 | 46,952 | 11.865 / 5.854 | 2,158.5 / 0 | 1,998,564 |
| LLD `--threads=1` | 0 | 11.134 | 13.075 | 47,580 | 7.537 / 3.968 | 2,071.5 / 0 | 1,998,564 |
| LLD `--threads=2` | 2 | 13.318 | 16.634 | 47,424 | 9.252 / 5.857 | 2,145 / 0 | 1,998,564 |
| LLD `--threads=4` | 4 | 13.584 | 16.346 | 47,236 | 10.631 / 6.267 | 2,129 / 0 | 1,998,564 |
| LLD `--threads=8` | 8 | 12.934 | 17.852 | 46,980 | 11.455 / 6.410 | 2,160 / 0 | 1,998,564 |

¹ 独立、未计时的成功 `clone/clone3` 工作线程创建数，主线程另计。 [统计与两种基准置信区间](evidence/threads/summary.csv) · [线程和输出散列](evidence/threads/design.json)

`--threads=1` 相对本轮 LLD 默认缩短 **1.786 ms（13.82%，95% CI 7.62% 至 20.33%）**，RSS 中位数增加 **628 KiB（1.34%）**。单线程 LLD 的 wall time 仍比同轮 BFD 高 90.82%，RSS 高 526.38%。`--threads=2/4/8` 的 wall time 相对 LLD 默认区间均跨零。五种 LLD 模式的所有样本都与归档 LLD 输出逐字节一致，SHA-256 为 `e5b8c3d1bcb0b9ddc180c842269c435ffc95840831ad75c313ba3f42682b7c99`，因此代码、符号、重定位、映射和文件大小保持一致。 [逐样本哈希](evidence/threads/measurements.csv)

## 原因判断与规模化风险

同输入、同资源下，仅限制 LLD 工作线程数就改变了 wall time，并可从未计时诊断确认创建线程的差别。这支持本例小负载存在可调的线程相关代价。线程创建、同步、任务并行各自占用多少仍为 **HYPOTHESIS**。单线程仍有明显耗时与 RSS 差距，观察结果无法按 ELF 解析、内部分配或调试处理分别归因。宿主 `perf_event_paranoid=4`，采样计数权限探测失败。调试字符串合并与输出尺寸已证实，其执行时间贡献未测量。 [采样能力探测](evidence/threads/perf-capability.err) · [ELF 布局核算](evidence/review/intermediate-layout.json)

这是一项小规模链接的本机结果，默认策略保持原状。若扩展到并发构建或更多小链接，进程峰值 RSS 和启动成本可能叠加为吞吐量或内存容量风险。大型目标的并行收益以及整包构建吞吐量需以对应工作负载测量。
