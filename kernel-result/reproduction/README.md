# 离线技术复核

从 `kernel-result/` 执行以下命令。Python 脚本读取已公开数据，校验清单并重新计算统计和证据关联。

    sha256sum -c --quiet SHA256SUMS
    python3 -B reproduction/review_archive.py

复核覆盖 160 条原始性能记录、28 条汇总及配对置信区间、288 条线程数据、逐区物理尺寸对账、映射符号、四条 LLVM 对照 E4 执行链、真实 GCC/BFD 三组模块摘要和新 QB 的 59 项设备 RPM 对照。代码来自历史阶段的纯统计函数。离线命令只读取归档数据。

## 历史方法及输入

- [初始验证方法](../history/kernel_lld_verification_20261120/VERIFICATION_METHOD.md) 包含 RPM 元数据、ELF、Kbuild 和设备身份的原流程。
- [Round 3 Make 复现](../history/kernel_lld_verification_20261120/pm_review_round3/KDBUS_MINIMAL_REPRODUCTION.md) 配有 [隔离最小输入和脚本](../history/kernel_lld_verification_20261120/pm_review_round3/reproducer)。这些实验说明变量优先级，历史直接执行评级依赖各自证据。
- [Phase 11 Make 复现](../history/kernel_lld_verification_20261125/11E_BEFORE_AFTER_REPRODUCTION.md) 保留两个 QB 的 Makefile 和实际脚本。工具按报告中标注的版本从实际发行依赖恢复。
- [Phase 12 受控重放方法](../history/phase12_controlled_benchmark/REPRODUCE.md) 保留构建、ELF、链接跟踪、GCC 与统计脚本。完整构建及实际冻结重放需要原生工具负载、相应公共 SDK、Tizen 用户空间及同哈希输入对象。它们通过工作区原档或可信发布源准备。
- [Phase 13 线程、归因和审核方法](../history/phase13_final_acceptance/REPRODUCE.md) 的新实测命令依赖对应冻结对象。对已有样本的统计可直接用本页离线入口复算。
- [Phase 14 运行报告](../history/phase14_product_runtime_acceptance/PHASE14_RUNTIME_REGRESSION_REPORT.md) 保留原始身份记录、发布对照和只读方法。设备采集脚本接受调用者提供的授权 SDB serial。

历史完整性脚本可能引用原始 RPM、二进制、摘要和路径。这些引用指向当时的完整本地归档。公开副本的校验边界见 [公开归档说明](../REVIEW_LIMITATIONS.md)。
