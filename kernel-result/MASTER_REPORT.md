# Kernel LLD 最终技术报告 · LLD-KERNEL-001

## 1. Executive Summary

修改定位为 **LLVM LLD Adaptation & Binary Size Optimization**。PM 批准 Phase 13 工程验收并接受本例构建性能代价。Phase 14 的目标 QB 只读运行检查通过。功能回归仍待获批准用例，Kernel Owner 审核和产品合入均待完成。 [执行摘要](EXECUTIVE_SUMMARY.md) · [PM 正式决定](history/phase14_product_runtime_acceptance/PM_PHASE13_FINAL_DECISION.md)

## 2. 背景、范围和初始 Kernel 验证

范围为 Raspberry Pi 4 ARMv7l 非 RT，Kernel Release `6.12.80-arm-rpi4-v7l`。Phase 1–7 绑定旧 QB `20261120.082536` 的发布 RPM、启动产物和设备身份，审查 Clang/LLD、Kbuild、主内核、ARM 解压器以及 52 个树内和 7 个树外模块。旧设备的 59 个模块文件逐一匹配发布，据此裁定身份和覆盖。Phase 8/9 将已确认的主构建及模块最终链接范围和缺失的历史直接执行证据分别归档。 [初始报告](history/kernel_lld_verification_20261120/KERNEL_LLD_VERIFICATION_REPORT.md) · [旧 QB 身份映射](history/kernel_lld_verification_20261120/06_repository_runtime_mapping.md) · [Phase 8 复审](history/kernel_lld_verification_20261120/pm_review_round2/PM_REVIEW_ROUND2_REPORT.md) · [Phase 9 工程验收](history/kernel_lld_verification_20261120/pm_review_round3/KERNEL_LLD_ENGINEERING_ACCEPTANCE.md)

## 3. kdbus 链接器覆盖根因与修复

旧外部模块 Makefile 中的 `LD = ${CROSS_COMPILE}ld` 可以覆盖顶层 Kbuild 从 LLVM 模式导出的链接器选择，影响 `kdbus.o` 中间组合链接。最终模块链接另走 `Makefile.modfinal`，在对应路径继续继承 Kbuild 的 `LD`。删除这一行，使 GNU 或 LLVM 配置都由 Kbuild 选择链接器。历史旧 QB 缺实际中间命令，评级保持 `BFD_PATH_POSSIBLE`。Round 3 的 21 个隔离实验复现覆盖机制。 [根因](history/kernel_lld_verification_20261120/pm_review_round3/KDBUS_LD_OVERRIDE_ROOT_CAUSE.md) · [最小复现](history/kernel_lld_verification_20261120/pm_review_round3/KDBUS_MINIMAL_REPRODUCTION.md) · [覆盖审计](history/kernel_lld_verification_20261120/pm_review_round3/KERNEL_LINKER_OVERRIDE_AUDIT.md) · [补丁设计](history/kernel_lld_verification_20261120/pm_review_round3/KDBUS_LD_FIX_PROPOSAL.md)

| 本地受控配置 | 中间 `kdbus.o` | 最终 `kdbus.ko` |
| --- | --- | --- |
| LLVM 原 Makefile | GNU BFD 2.43 | LLVM LLD 22.1.8 |
| LLVM 删除覆盖 | LLVM LLD 22.1.8 | LLVM LLD 22.1.8 |
| 真实 GCC 原始与修复 | GNU BFD 2.43 | GNU BFD 2.43 |

实际修复提交为 `1c26a4781d7813abd9ab2fb4c3fad35c52ec8fc8`，Change-Id 为 `Ic0b9efb5c514bb6e18dbc270aa269211ec514375`，父提交为 `25797e8af7ed95a5783bbe84c11959560aaf7e92`。归属 `platform/kernel/linux-tizen-modules-source`，推送至 `refs/heads/sandbox/liushanshan/lld`。Phase 10 保存认证之后的独立远程取回和内容校验，Gerrit 网页当时要求登录。 [提交报告](history/phase10_kdbus_sandbox/KDBUS_LD_FIX_SUBMISSION_REPORT.md) · [远程核验](history/phase10_kdbus_sandbox/evidence/remote-object-verification.json) · [候选补丁](history/kernel_lld_verification_20261120/pm_review_round3/KDBUS_LD_FIX_CANDIDATE.patch) · [实际最终差异](history/phase10_kdbus_sandbox/evidence/remote-fetched-diff.out)

## 4. Phase 11 新 QB 工程验收

新发布 `20261125.130358` 的 manifest、源码 RPM、源码提供包、SPEC 与构建作业证明了补丁纳入。源码提供载体的 53 个文件中只更改根 Makefile。新 QB 的 `kdbus.o` 与 `kdbus.ko` 分别达到 E3，顶层实际作业选择 LLVM 模式并使用匹配工具链，原 BFD 覆盖路径已消除。46 次隔离复现通过，59/59 模块 ELF 解析通过，2,972 条 kdbus 重定位核对等价，各版七个树外模块合计 356 个导入 CRC 与对应 SDK 匹配。PM 批准工程关闭，严格验收为 `CONDITIONAL_PASS`。 [新 QB 验证](history/kernel_lld_verification_20261125/KDBUS_LLD_FIX_QB_VERIFICATION_REPORT.md) · [Kbuild 因果链](history/kernel_lld_verification_20261125/11D_INTERMEDIATE_LINKER_CAUSAL_ANALYSIS.md) · [59 模块清单](history/kernel_lld_verification_20261125/11G_MODULE_INVENTORY_DIFF.csv) · [PM 决定](history/phase11_pm_final_acceptance/PM_PHASE11_FINAL_ACCEPTANCE.md)

## 5. Phase 12 单变量构建、实际 E4 与冻结重放

A/B 使用同一新 LLVM SDK、同样的 53 个准备源码路径及同一已恢复 Tizen 环境。唯一源码差异是该一行 Makefile。四个链接阶段关联成功 `execve`、可执行路径及 SHA-256、完整 argv、退出码和输出文件摘要。实际 A 的组合链接执行 BFD，B 执行 LLD，两组最终均执行 LLD。冻结响应文件与 19 个有序输入对象逐一同哈希。固定共同最终元数据、链接脚本、BTF 及 strip 后复现尺寸变化。A/B 发布形式模块恰与各自旧、新 QB 文件 SHA-256 一致。直接执行证明适用于这次受控本地作业。 [构建矩阵](history/phase12_controlled_benchmark/CONTROLLED_BUILD_MATRIX.csv) · [链接执行与产物摘要](history/phase12_controlled_benchmark/evidence/build/controlled-builds.json) · [原始目标跟踪](history/phase12_controlled_benchmark/evidence/build/selected) · [冻结输入](history/phase12_controlled_benchmark/evidence/replay/frozen-inputs.json) · [重放映射](history/phase12_controlled_benchmark/evidence/replay/link-replay.json)

## 6. Phase 13 尺寸归因、调试字符串与 ARM 映射

| 量测 | BFD | LLD | 净额 |
| --- | ---: | ---: | ---: |
| `kdbus.o` | 2,505,192 B | 1,998,564 B | −506,628 B（20.22%） |
| `.debug_str` | 601,961 B | 95,814 B | −506,147 B |
| 中间其余文件差异 | | | −481 B |
| strip 后 `kdbus.ko` | 162,584 B | 161,292 B | −1,292 B（0.79%） |

中间 `.debug_str` 的 50,290 个非空物理字符串仅有 7,179 个不同值，LLD 保存这 7,179 个值一次。节载荷净减少 506,651 B，间隙净增加 23 B。ELF 表头尺寸和 `.bss` 的文件占用保持原值。最终模块 `.symtab` 少 81 条 16 B 的冗余局部 `$d`，`.ARM.attributes` 多 4 B 的默认属性显式编码。BFD map 将 101 个额外中间标记定位到非可执行输入节贡献的起点。最终保留的 81 个差额有 75 个唯一对象归属，6 个映射到常量折叠后等价候选。已验证 ARM/Thumb/Data 有效区域边界一致。 [完整尺寸 CSV](history/phase13_final_acceptance/INTERMEDIATE_SIZE_ATTRIBUTION.csv) · [文件布局与调试字符串](history/phase13_final_acceptance/evidence/review/intermediate-layout.json) · [映射归属](history/phase13_final_acceptance/evidence/review/mapping-stripped-review.json) · [完整分析](history/phase12_controlled_benchmark/ARM_MAPPING_SYMBOL_ANALYSIS.md)

## 7. 链接耗时、内存代价与线程补测

| Phase 12 默认线程中位数 | BFD 2.43 | LLD 22.1.8 | 差异 |
| --- | ---: | ---: | ---: |
| Link Time | 5.647 ms | 11.878 ms | +6.231 ms（显示值之差，+110.33%） |
| Peak RSS | 7,700 KiB | 53,348 KiB | +45,648 KiB（+592.83%） |

160 条有效样本按两个资源配置各 40 个配对归档。95% CI 使用 4,000 次同块配对 bootstrap 的中位数比值，28 条原始摘要已按原口径复算。默认 wall time 回归区间为 +101.35% 至 +116.02%，RSS 为 +589.30% 至 +594.51%。Phase 13 相同八核补测含 288 个样本，覆盖 BFD、LLD 默认及显式线程 1/2/4/8。`--threads=1` 比同轮 LLD 默认快 13.82%，输出字节一致，但仍比 BFD 慢且 RSS 更高。内部开销分项仍是待验证假设。峰值 RSS 与启动代价需要按并发构建规模审视。PM 只接受本例代价。 [原 160 条数据](history/phase12_controlled_benchmark/LINKER_BENCHMARK_RAW.csv) · [原置信区间](history/phase12_controlled_benchmark/LINKER_BENCHMARK_SUMMARY.csv) · [线程原数据](history/phase13_final_acceptance/evidence/threads/measurements.csv) · [线程统计与设计](history/phase13_final_acceptance/LINKER_THREAD_PERFORMANCE_REPORT.md)

## 8. GCC/BFD 与静态 ABI

三组真实 C/D 使用相应 Tizen Unified Dev `20261120.082616` 的 Raspberry Pi 4 ARMv7l 非 RT GCC SDK。覆盖 ARM 工具负载、发布版加速器和显式 GNU binutils 前缀。每组七个安装形式模块逐字节一致，每次构建 345 个导入 CRC 匹配 SDK。已检查的 LLVM 最终 ELF 代码、符号接口、映射、重定位语义与 ABI 保持兼容。构建配置范围为单一板型和内核变体下三种工具链路径。 [GCC 报告](history/phase12_controlled_benchmark/GCC_COMPATIBILITY_REPORT.md) · [实际 GCC 执行记录](history/phase12_controlled_benchmark/evidence/gcc/builds) · [ELF、符号及重定位](history/kernel_lld_verification_20261125/11F_MODULE_ABI_SUMMARY.json)

## 9. Phase 14 Runtime Verification 与产品门槛

更正后的目标设备确认 Raspberry Pi 4 ARMv7l 非 RT、Image BUILD_ID `tizen-unified-toolchain_20261125.130358_tizen-headed-armv7l`、运行 Kernel Build ID `8d5da0f28ffc7a57a290127a26fc17cbbd103558`。发布内核 RPM 解压启动载荷中的完整 notes 与 banner 和设备相符。系统为 `running`，零失败单元。52 个树内与 7 个树外模块全部匹配新发布 RPM 成员摘要。`kdbus` 安装 SHA 与已加载 Build ID 均匹配发布，状态 `live`，当前可读内核日志无对应加载或符号错误，kernel journal 存在读取权限限制。当前无已批准且可执行的功能用例，功能回归仍待执行。 [运行报告](history/phase14_product_runtime_acceptance/PHASE14_RUNTIME_REGRESSION_REPORT.md) · [设备—RPM 文件对照](history/phase14_product_runtime_acceptance/evidence/module-runtime-to-rpm.csv) · [内核发布绑定](history/phase14_product_runtime_acceptance/evidence/release/kernel-identity.json)

| 最终 PM 决策项 | 状态 |
| --- | --- |
| Phase 12 evidence review / Phase 13 acceptance | PASS / PASS |
| LLD-KERNEL-001 | CLOSED_ENGINEERING |
| Patch causality / static ABI | MEASURED_AND_ATTRIBUTED / PASS |
| GCC compatibility | PASS_RPI4_ARMV7L_NON_RT |
| Build performance trade-off | ACCEPTED_FOR_KDBUS |
| Runtime regression | PARTIAL_PASS_FUNCTIONAL_PENDING |
| Functional regression | NOT_RUN_NO_APPROVED_CASE_AVAILABLE |
| Runtime memory benefit | NOT_MEASURED |
| Kernel Owner trade-off acceptance | PENDING_OWNER_REVIEW |
| Product merge readiness | PENDING |

产品合入待获批准的功能回归、测试期日志结果，以及 Kernel Owner 确认 GCC 覆盖和构建代价。 [最终产品矩阵](history/phase14_product_runtime_acceptance/PRODUCT_MERGE_FINAL_GATE_MATRIX.csv) · [Kernel Owner 审核请求](history/phase14_product_runtime_acceptance/KERNEL_OWNER_INTEGRATION_REQUEST.md)

## 10. 证据限制和后续研究

旧、新历史 QB 缺对应直接 E4 执行记录。部分固定 Base 依赖不可用，本地对照使用同一恢复用户空间和较早 BFD 加速负载。整包吞吐、Debuginfo RPM 体积差、设备常驻内存，以及其他 RPM 的优化普适性仍待各自测量。后续可针对具备实际 ARM 部分链接和符号表保留的有限候选分析体积与构建容量，保留匹配的功能与运行证据。 [公开限制及源缺口](REVIEW_LIMITATIONS.md) · [推广边界](history/phase12_controlled_benchmark/evidence/runtime/generalization.md) · [完整证据索引](EVIDENCE_INDEX.md)
