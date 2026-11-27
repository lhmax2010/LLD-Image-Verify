# Phase 12H · kdbus 运行内存可行性

**`RUNTIME_MEMORY_BENEFIT = NOT_MEASURED`。** 匹配内核启用了 `CONFIG_KALLSYMS_ALL`，部分 ARM 映射符号可进入常驻的 core kallsyms。减少这些符号有机会改变常驻 `MOD_DATA` 的布局，实际分配按内存类型对齐到 4 KiB 页。磁盘 `.symtab` 的差额无法直接推算常驻物理页差额，也没有本轮设备测量。新 QB 的运行回归仍为 `PENDING_NEW_IMAGE_DEPLOYMENT`。 [SDK 配置](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [符号表布局](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [页对齐分配](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [Phase 11 设备身份](../kernel_lld_verification_20261125/11H_RUNTIME_VERIFICATION.md)

## 输入与范围

目标为 Raspberry Pi 4 ARMv7l 非 RT，内核 release `6.12.80-arm-rpi4-v7l`，`platform/kernel/linux-rpi` 修订 `42aeefac58edeb081aff440f0b60be71cbe49755`。直接使用与新 QB 发布摘要相同的旧归档 SRPM，核验 SHA-256，按 SPEC 顺序检查 9 个补丁并重放触及所选源码的补丁。所核对的 10 份最终文件均与相同修订的旧 QB debugsource 对应 RPM 成员逐字节一致。新 QB debugsource 官方路径本轮返回 404。配置来自匹配的新 SDK RPM，逐成员核对了 `.config` 摘要。 [原始输入清单](evidence/runtime/provenance.json) · [源码与补丁规则](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [下载回执](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

关键设置包括 `CONFIG_MODULES=y`、`CONFIG_MODULE_UNLOAD=y`、`CONFIG_KALLSYMS=y`、`CONFIG_KALLSYMS_ALL=y`、`CONFIG_ARM_MODULE_PLTS=y`、`CONFIG_STRICT_MODULE_RWX=y`、`CONFIG_PAGE_SHIFT=12`、`CONFIG_DEBUG_INFO_BTF_MODULES=y`。`CONFIG_MODULE_COMPRESS` 未启用，RPM 的 XZ 是打包传输压缩。该目标按 ARM ELF REL 处理重定位。 [配置摘录](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## 四类大小与内存

| 类别 | 现有观察或推导 | 解释 |
| --- | --- | --- |
| 磁盘 ELF | 已发布 `kdbus.ko` 162,584 → 161,292 Bytes，`.symtab` 14,032 → 12,736 Bytes | 旧、新 QB 文件量测，两者存在工具链修订和构建环境差异 |
| 包压缩 | 同名七模块 RPM 92,412 → 91,980 Bytes，其中 XZ cpio 压缩流 82,852 → 82,420 Bytes，RPM flags 均为 `5T` | 整个实际包的发布差额，包含 cpio 元数据及压缩相互作用 |
| 临时加载内存 | 模块加载器读取完整 ELF，之后释放临时副本。加载及 init 阶段也使用完整符号、字符串和类型表 | 仅按完整 ELF 文件大小和 4 KiB 对齐推算，两版处于同一页数区间。峰值还涉及 init 数据、复制、加载器元数据及其他分配 |
| 常驻模块内存 | 模块初始化完成后切换到 core kallsyms；内存以各 `mod_mem_type` 对齐到页 | 持久符号表可能受映射符号差额影响。实际是否跨越分配页边界、是否影响其他内核分配，待运行证据 |

[旧新包测量与压缩流](evidence/runtime/provenance.json) · [ELF 尺寸数据](../kernel_lld_verification_20261125/11F_MODULE_SIZE_COMPARISON.csv) · [加载临时文件](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [加载成功路径释放原文件](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [切换到 core kallsyms 并延迟释放 init](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## 为什么映射符号可能影响常驻布局

磁盘中的 `.symtab` 未设置 `SHF_ALLOC`。通用加载器逐内存类型排列普通 `SHF_ALLOC` 节，清除 `.modinfo`、`__versions` 的分配标志，并将 per-CPU 节另行分配。随后 `layout_symtab()` 给完整 `.symtab`、`.strtab` 分配临时 `MOD_INIT_DATA`，并为 core 副本在 `MOD_DATA` 中追加 ELF 符号记录、逐符号复制的名称和类型字节。带名称且位于非 init 已分配节的符号满足 `is_core_symbol()`，该规则未按 `$a`、`$t`、`$d` 名称剔除。按地址查找函数时跳过 mapping symbol 属于后续查询行为。 [节区布局规则](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [装载前节标志调整](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [core 选择与完整表布局](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [地址查询](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

匹配 ARM 代码将 `.init*`、`.ARM.extab.init*` 和 `.ARM.exidx.init*` 归为 init。以归档 ELF 结合上述筛选规则，历史新旧差异的 81 条 `$d` 中有 78 条符合 core 保留资格。其余来自 `.modinfo`、`.init.data` 和 `.ARM.extab.init.text`。这是符号筛选模型的计数。ARM 路径通过 ELF REL 的类型、符号索引及指令编码应用重定位，并可在分配前调整 PLT 节大小和对齐。若实际评估内存，需同时核对 PLT、节布局和页级分配。 [ARM init 节判定](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [ARM 重定位](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [ARM PLT 改写](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [静态符号筛选记录](evidence/runtime/published-module-mapping-sample.json)

## 后续测量设计

1. 取得专用 RPi4 ARMv7l 非 RT 设备的部署和模块加载、卸载授权。固定一个 boot kernel、镜像配置、已发布或匹配的 SDK，以及 Phase 12 同构建产生的对照模块。由设备责任人按正常流程安排设备和窗口。
2. 在固定正常模块使用路径与设备条件下交替测量 A/B。记录镜像 BUILD_ID、kernel Build ID、模块文件摘要、`PAGE_SIZE`、依赖状态、冷暖缓存条件及日志。使用可取得的模块分配跟踪记录关联 `kdbus` 的原始文件读入、init 型分配和稳态 allocation。将装载瞬时峰值与 init 回收及 RCU 同步后的稳态分开分析。
3. 读取 `/sys/module/kdbus/coresize`、`initsize`，如配置提供则同时读取 `datasize`。在允许的诊断环境下用模块分配跟踪或 `/proc/vmallocinfo` 交叉核对，另行归类依赖、per-CPU、BTF 和运行分配。稳态核心页差额从实际分配得出，观测波动随结果保留。 [内核报告字段](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

复算静态输入与历史样本可从工作区执行 `python3 -B phase12_controlled_benchmark/scripts/collect_runtime_static.py`。命令仅使用归档 RPM 和 ELF，实际设备测试留待独立授权。 [可复现静态采集](scripts/collect_runtime_static.py) · [采集回执](evidence/runtime/static-input-intake.cmd.json)
