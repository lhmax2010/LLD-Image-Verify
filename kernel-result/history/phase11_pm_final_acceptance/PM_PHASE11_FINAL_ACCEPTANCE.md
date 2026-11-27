# Phase 11 PM 最终验收决定

归档日期 2026-11-26。适用范围为 Tizen Unified Toolchain 新 QB `20261125.130358`，Raspberry Pi 4 ARMv7l 非 RT，Kernel Release `6.12.80-arm-rpi4-v7l`。

## 正式决定

| 验收项 | PM 批准结论 |
| --- | --- |
| Phase 11 Engineering Acceptance | **PASS** |
| LLD-KERNEL-001 Engineering Status | **CLOSED** |
| 新 QB 补丁纳入 | **PATCH_INCLUDED**，提交 `1c26a4781d7813abd9ab2fb4c3fad35c52ec8fc8` |
| `kdbus.o` 中间链接 | LLVM LLD 22.1.8，**E3** |
| `kdbus.ko` 最终链接 | LLVM LLD 22.1.8，**E3** |
| 原 `LD` 覆盖 | **REMOVED** |
| GNU BFD 执行路径 | 在本次已观察的构建配置下未发现其他合理路径 |
| Static ABI Compatibility | **PASS** |
| Strict Acceptance | **CONDITIONAL_PASS**，保留本次构建历史 E4 直接执行证据缺口 |
| Product Merge Readiness | **PENDING** |

本决定记录 PM 对工程范围的关闭批准。提交来自 `platform/kernel/linux-tizen-modules-source` 的 `sandbox/liushanshan/lld`。新 QB 的 manifest、RPM 源码及构建日志共同确认补丁纳入。两步链接的 E3 结论来自各自的 Kbuild 规则与作业证据。 [原始验证报告](../kernel_lld_verification_20261125/KDBUS_LLD_FIX_QB_VERIFICATION_REPORT.md) · [源码纳入证据](../kernel_lld_verification_20261125/11B_PATCH_INCLUSION_REPORT.md) · [链接因果分析](../kernel_lld_verification_20261125/11D_INTERMEDIATE_LINKER_CAUSAL_ANALYSIS.md)

## 核准归档的量化结果

| 检查 | 结果 |
| --- | --- |
| Kernel Module ELF 解析 | 59/59 通过，52 个树内模块与 7 个树外模块 |
| Makefile 对比实验 | 46 次通过 |
| `kdbus.ko` 重定位 | 2,972 条通过等价性核对 |
| 树外模块导入 CRC | 新旧 QB 各 356 个，均匹配各自 SDK |
| 同包其他六个树外模块 | 逐字节一致 |

| `kdbus.ko` 量测项 | 旧 QB（Bytes） | 新 QB（Bytes） | 差值（Bytes） | 降幅 |
| --- | ---: | ---: | ---: | ---: |
| 文件 | 162,584 | 161,292 | −1,292 | 0.79% |
| `.symtab` | 14,032 | 12,736 | −1,296 | 9.24% |
| `.text` | 67,428 | 67,428 | 0 | 0% |
| `.rodata` | 1,256 | 1,256 | 0 | 0% |
| `.data` | 52 | 52 | 0 | 0% |
| `.bss` | 29 | 29 | 0 | 0% |

文件变化由少 81 条局部 ARM `$d` 映射符号及多 4 Bytes 的 `.ARM.attributes` 显式默认属性编码解释。降幅按旧 QB 大小计算。新旧 QB 的 Base 快照、工具链 RPM 发行号和构建环境存在差异，这组发布对比无法隔离单行修改的贡献。运行内存与性能收益未测量。 [ELF 与静态 ABI 详表](../kernel_lld_verification_20261125/11F_MODULE_BINARY_COMPARISON.md) · [模块覆盖](../kernel_lld_verification_20261125/11G_KERNEL_LLD_REGRESSION_REPORT.md) · [Makefile 复现](../kernel_lld_verification_20261125/11E_BEFORE_AFTER_REPRODUCTION.md)

## 剩余工作

1. **新 QB Runtime Regression**。状态为 `PENDING_NEW_IMAGE_DEPLOYMENT`，Phase 11 只读检查识别到的设备仍运行旧 QB。
2. **真实 GCC/BFD Build Regression**。真实构建为 `PENDING`，GCC/BFD 的 Makefile 模拟已通过。
3. **后续正常构建的 E4 Evidence Collection**。等待既有发布流程中的正常构建，归档实际链接器、完整参数和成功执行记录。该证据对应其具体作业。

本次 PM 归档到此结束。刷机、新构建和正式产品分支合入均需另行授权。原始 Phase 11 报告及证据包作为验收依据保留。 [剩余测试计划](PRODUCT_MERGE_REMAINING_TEST_PLAN.md) · [Kernel Owner 英文说明](KERNEL_OWNER_CHANGE_JUSTIFICATION.md) · [机器可读决定](PM_PHASE11_FINAL_ACCEPTANCE.json) · [原始证据索引与复验入口](../kernel_lld_verification_20261125/KDBUS_LLD_FIX_EVIDENCE_INDEX.md)
