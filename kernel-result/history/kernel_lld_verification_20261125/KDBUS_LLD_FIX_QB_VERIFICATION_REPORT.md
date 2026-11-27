# LLD-KERNEL-001 · 新 QB 修复验收

**PM Review · 2026-11-25 · Raspberry Pi 4 ARMv7l 非 RT**

新 QB 确实包含 Phase 10 的单行修复。发布证据支持 **`kdbus.o` 中间链接和 `kdbus.ko` 最终链接都使用 LLVM LLD 22.1.8，分别达到 E3**。旧 Makefile 引入的 GNU BFD 旁路已消除。在新 QB 实际记录的构建配置下，没有发现其他合理的 BFD 路径。工程验收为 **PASS**。严格验收为 **CONDITIONAL_PASS**，缺少 E4 历史执行证据。建议 PM 按 E3 工程标准关闭 LLD-KERNEL-001，产品合入验收仍为 **PENDING**。 [验收矩阵](KDBUS_LLD_FIX_GATE_MATRIX.csv) · [链接因果链](11D_INTERMEDIATE_LINKER_CAUSAL_ANALYSIS.md)

## QB 与修复身份

| 项 | 旧 QB | 新 QB |
| --- | --- | --- |
| 发布 | `tizen-unified-toolchain_20261120.082536` | `tizen-unified-toolchain_20261125.130358` |
| 内核 | `6.12.80-arm-rpi4-v7l` | `6.12.80-arm-rpi4-v7l` |
| SDK 工具版本 | Clang 22.1.8 / LLD 22.1.8 | Clang 22.1.8 / LLD 22.1.8 |
| 模块实现提交 | `25797e8af7ed95a5783bbe84c11959560aaf7e92` | `1c26a4781d7813abd9ab2fb4c3fad35c52ec8fc8` |
| 模块包装提交 | `458baad02d812098938663971d1b8560a4813375` | 同左 |
| Linux 内核提交 | `42aeefac58edeb081aff440f0b60be71cbe49755` | 同左 |
| 树外模块 RPM SHA-256 | `ee434f5a9545811fa060f3dfc3b45be7bd4e3e0a09cb5d9b9c2e810d32dd87aa` | `92a3a372dd9ead740720f209918c27a88f04329c3a2a45d62c4196762954a2de` |

目标仓库为 `platform/kernel/linux-tizen-modules-source`，修复来自 `sandbox/liushanshan/lld`。以 Phase 10 独立远程验证的确切提交为基准，核对了新 QB manifest、SRPM、源码提供 RPM、SPEC 和实际构建日志中的准备步骤。新旧源码提供 RPM 的 53 个可比较载荷文件中，只有 `Makefile` 发生变化，精确删除 `LD = ${CROSS_COMPILE}ld`。构建中没有补回该行，没有发现其他有效 LD 覆盖或显式 BFD 调用。发布模块包与旧包 NEVRA 相同，发布摘要不同，新任务独立记录了目标模块和写包步骤。Gate A 为 **PASS**。本轮 Gerrit SSH 认证未通过，分支最新 HEAD 沿用 Phase 10 已归档的独立远程验证记录作为修复提交依据，当前发布的纳入情况通过新 QB 的实物独立核对。 [源版本与包身份](11A_QB_IDENTITY.json) · [源码与 SPEC](11B_PATCH_INCLUSION_REPORT.md) · [单行差异](11B_SOURCE_DIFF.patch)

## 中间与最终链接

- **中间 `kdbus/kdbus.o`，E3。** 新非 RT 包装作业第 458 行设置 `LLVM=1`，匹配的顶层 Kbuild 选取并导出 `ld.lld`。修复后的外部 Makefile 继承该变量，匹配的 `scripts/Makefile.build` 用 `$(LD) ... -r` 链接组合对象。构建日志第 505 行记录该目标，后续成功进入 modpost、模块最终链接和第 746 行的 RPM 写入。匹配工具链 RPM 的 native 与 accelerator 候选都验证为 LLD 22.1.8。GNU binutils 提供的 `ld`/`ld.bfd` 没有占用这条作业选择的 `ld.lld`。 [构建日志](evidence/build/linux-tizen-modules-armv7l.out#L458) · [规则与路径核对](11D_INTERMEDIATE_LINKER_CAUSAL_ANALYSIS.md)
- **最终 `kdbus/kdbus.ko`，E3。** 单独核对了匹配 SDK 的 `scripts/Makefile.modfinal`、顶层继承的 `LD`、第 529 行最终目标和第 746 行写包记录，校验了发布 RPM 内的 `kdbus.ko`。 [最终链接位置](evidence/build/linux-tizen-modules-armv7l.out#L529) · [目标规则矩阵](11D_LINKER_RULE_MATRIX.csv)
- **直接执行证据缺口。** 历史公开日志为 quiet 输出，发布范围内未找到匹配的 `.kdbus.o.cmd`、中间 ELF、完整 argv 或成功 execve。历史完整 PATH 和选中的 LLD 可执行文件绝对路径、SHA-256 未恢复。E3 因果链依据实际包和日志，E4 留待与目标产物关联的实际执行记录。旧 QB 的中间链接历史仍为 `BFD_PATH_POSSIBLE`。 [直接证据检索](11C_INTERMEDIATE_DIRECT_EVIDENCE.md) · [命令记录状态](11C_INTERMEDIATE_LINK_COMMANDS.json)

## 变量复现与 GCC

用两个 QB 实际提供的 Makefile，在同一新 Base、同一源 revision、同为 4.4.1 的 x86_64 GNU Make 上运行 21 个旧实验场景及两个补充场景。共 **46 次实验、322 条变量观测、92 条模拟链接调用**。常规 ARMv7l/AArch64 LLVM 模式下，旧中间规则解析为 GNU `ld` 或交叉前缀 `ld`，新规则解析为 `ld.lld`，最终规则始终保留顶层选择。GCC 交叉前缀、显式 BFD/LLD、LLVM 工具目录前缀和版本后缀均保留。GCC/BFD 兼容性模拟为 **PASS**，真实 GCC/BFD 构建为 **PENDING**。 [实验方法和复跑命令](11E_BEFORE_AFTER_REPRODUCTION.md) · [原始变量矩阵](11E_MAKE_VARIABLE_TRACE.json)

## 静态二进制与覆盖回归

新 QB 在目标 release 下发布 **52 个树内和 7 个树外模块**，59 个均可解析，清单无新增、删除或重命名。52 个树内模块和 `kdbus.ko` 的原始摘要有变化，另外六个树外模块逐字节相同。Kernel 主构建与 ARM 解压器规则、静态配置及本次任务日志的覆盖边界见 11G。 [覆盖检查](11G_KERNEL_LLD_REGRESSION_REPORT.md) · [完整清单](11G_MODULE_INVENTORY_DIFF.csv)

| `kdbus.ko` 大小（字节） | 旧 | 新 | 差值 |
| --- | ---: | ---: | ---: |
| 文件 | 162584 | 161292 | −1292 |
| `.text` | 67428 | 67428 | 0 |
| `.rodata` | 1256 | 1256 | 0 |
| `.data` | 52 | 52 | 0 |
| `.bss` | 29 | 29 | 0 |
| `.init.text` | 160 | 160 | 0 |
| `.exit.text` | 48 | 48 | 0 |
| `.modinfo` | 221 | 221 | 0 |
| `.symtab` | 14032 | 12736 | −1296 |
| `.strtab` | 7692 | 7692 | 0 |
| `.ARM.attributes` | 50 | 54 | +4 |

文件大小差额可由 `.symtab` 少 81 个 16 字节的局部 ARM `$d` 映射符号、`.ARM.attributes` 多 4 字节解释。新增的显式 R9/V6 与 FP exceptions/Unused 对应 Arm ABI 默认值 0。全局、弱符号、导入、导出和模块元数据在检查范围一致。2,972 条重定位的位点、类型和目标一致，重定位来源节的原始字节一致。七个树外模块有 356 个记录的导入 CRC，含 kdbus 的 154 个，均匹配各自 SDK 的 `Module.symvers`。Gate D 静态为 **PASS**。 [二进制详表](11F_MODULE_BINARY_COMPARISON.md) · [节级 CSV](11F_MODULE_SIZE_COMPARISON.csv) · [Arm ABI 属性](https://github.com/ARM-software/abi-aa/blob/main/addenda32/addenda32.rst#the-procedure-call-related-attributes)

旧、新内核源码版本和 SDK `.config` 一致，Base QB、Clang/LLVM 包 release、accelerator、GNU binutils、make 及构建主机存在变化。大小结果适用于本对发布产物，无法从该对照单独归因于 Makefile 一行修改。 [配置与干扰变量](11A_PREFLIGHT.md)

## 运行、严格验收与产品合入

- 只读 SDB 身份检查显示 Raspberry Pi 4 仍运行旧 QB `20261120.082536`。新 QB 运行状态为 **PENDING_NEW_IMAGE_DEPLOYMENT**。部署获授权后，首先用镜像 BUILD_ID、内核 Build ID 和 kdbus 包 SHA-256 核对新镜像身份，再核对正常启动、既有模块加载状态、加载错误和已部署模块与发布包的对应。 [设备身份](11H_RUNTIME_VERIFICATION.md)
- 产品合入前还需匹配产品配置的真实 GCC/BFD 模块构建，以及新镜像上的运行回归。如果 PM 要求严格 B Gate，需取得与目标发布关联的成功链接执行记录，包含实际 executable 路径、摘要、版本、argv、输出对象和 RPM 关联。今后的归档应保留这些记录，历史新 QB 的严格证明仍存在该缺口。 [验收矩阵](KDBUS_LLD_FIX_GATE_MATRIX.csv)
- 新旧归档分开校验。新 QB 未下载的完整镜像 RPM 和核心 debuginfo 已记录发布身份与摘要。限定范围内未发现可下载的匹配模块专用 debuginfo。主内核与 ARM 解压器以匹配 SDK、规则和日志核验，发布镜像二进制未独立解析。原始命令、输出、退出码、重放步骤与输入摘要见证据索引。 [证据索引](KDBUS_LLD_FIX_EVIDENCE_INDEX.md)

本轮结论提交 PM Review。LLD-KERNEL-001 的最终关闭与产品合入由 PM 决定。
