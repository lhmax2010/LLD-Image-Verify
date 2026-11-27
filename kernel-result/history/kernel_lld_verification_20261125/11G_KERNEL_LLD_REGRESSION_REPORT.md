# 11G · 新 QB ARMv7l RPi4 非 RT Kernel LLD 覆盖回归检查

**`PASS_SCOPED_REGRESSION_CHECK`。** 新 QB 匹配的 SDK 启用 LLVM LLD。新构建日志覆盖非 RT 主内核、ARM 解压器和七个树外模块的链接目标。两份目标模块 RPM 实测共有 59 个 `.ko`，均通过基本 ELF 解析。检查覆盖对应源码规则、配置、发布日志和模块 payload。主内核与解压器的独立二进制解析、历史链接器执行追踪和新镜像 runtime 未纳入本阶段结论。 [机器可读检查结果](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [QB 身份与 RPM 记录](11A_QB_IDENTITY.json)

## 内核配置与链接规则

内核源码 revision 为 `42aeefac58edeb081aff440f0b60be71cbe49755`，新旧相同。与新 non-RT 目标匹配的 SDK RPM 通过仓库 SHA-256 检查，`compile.h`、`.config`、`kernel.release` 和下表所用规则文件全部逐成员核对 RPM header 摘要。`compile.h` 报告 `clang version 22.1.8, LLD 22.1.8`，`UTS_MACHINE=arm`。`.config` 为 `CONFIG_CC_IS_CLANG=y`、`CONFIG_LD_IS_LLD=y`、`CONFIG_LLD_VERSION=220108`，未启用 `CONFIG_LD_IS_BFD`。`kernel.release` 为 `6.12.80-arm-rpi4-v7l`。 [SDK 解包记录](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [RPM 成员摘要](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [配置](../kernel_lld_verification_20261120/pm_review_round2/evidence/kernel/source/.config) · [编译元数据](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

| 目标 | 新 QB 规则与日志 |
| --- | --- |
| `vmlinux` | 内核 `%build` 日志第 1677 行导出 `LLVM=1`，第 3350 行进入 `O=build/arm-rpi4`。SDK 顶层 `Makefile` 第 480、593 行选择并导出 `LD=$(LLVM_PREFIX)ld.lld$(LLVM_SUFFIX)`。顶层第 1180–1181 行调用 `scripts/Makefile.vmlinux`，其第 28–34 行传入 `$(LD)` 到 `link-vmlinux.sh`。后者在 ARM 路径用 `${LD}` 链接。日志第 7922、7943 行分别记录 `LD vmlinux.o`、`LD vmlinux`。 |
| ARM 解压器 `arch/arm/boot/compressed/vmlinux` | `arch/arm/boot/compressed/Makefile` 第 148–152 行调用 `if_changed,ld`，`scripts/Makefile.lib` 第 333–334 行的 `cmd_ld` 使用 `$(LD)`。日志第 8113 行记录解压器链接，第 8116、8118 行记录生成 `zImage`。第 8143 行开始 RT 构建，观察点均位于该分隔线之前。 |
| 七个树外 `.ko` 最终链接 | 外部 RPM 日志第 458 行导出 `LLVM=1`，第 469–470 行调用并进入匹配的 non-RT SDK。SDK `scripts/Makefile.modfinal` 第 36–40、60–61 行以 `$(LD) -r` 实现 `.ko` 最终链接。日志第 514、517、520、523、526、529、532 行的七个 `LD [M]` 目标与外部 RPM 里的七个相对模块路径逐项一致，第 746 行记录目标 RPM 写出。 |

[内核日志](evidence/build/linux-rpi-armv7l.out) · [树外构建日志](evidence/build/linux-tizen-modules-armv7l.out) · [SDK 顶层 Kbuild](../kernel_lld_verification_20261120/pm_review_round2/evidence/kernel/source/Makefile) · [内核链接脚本](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [ARM 解压器规则](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [模块链接规则](../kernel_lld_verification_20261120/pm_review_round2/evidence/kernel/source/scripts/Makefile.modfinal)

上述已检查的活跃规则和非 RT 日志未出现新的显式 GNU BFD 选择。顶层的非 LLVM `$(CROSS_COMPILE)ld` 分支保留。内核日志可见 `bpf_obj_new_impl` 等 BTF 编码及 `resolve_btfids` 警告，同样的四类警告和各自次数在旧日志均存在。新日志继续记录 `zImage` 成功与内核、模块、开发 RPM 写出。日志中的安静 `LD` 标签观察到构建目标，证据等级由对应目标的独立因果链评估，本阶段未沿用旧 QB 的 E3。 [内核和模块目标行及警告计数](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [新 QB 源码核对](11B_SOURCE_PROVENANCE.json)

## 模块覆盖

| 发布模块组 | 旧 QB | 新 QB | 新 ELF 解析通过 | SHA-256 改变 |
| --- | ---: | ---: | ---: | ---: |
| 树内 `arm-rpi4-linux-kernel-modules` | 52 | 52 | 52 | 52 |
| 树外 `linux-tizen-modules-rpi4` | 7 | 7 | 7 | 1 |
| 合计 | 59 | 59 | 59 | 53 |

从新 QB `repomd` 追溯并检查 `primary` 与 `filelists` 的压缩及开放摘要。筛选 `armv7l` 且在 `/lib/modules/6.12.80-arm-rpi4-v7l/` 发布 `.ko` 的全部 RPM，得到两个匹配载体。RPM 整包 SHA-256 与 `primary` 一致，模块路径与独立 `filelists` 一致，解包成员逐一通过 RPM header SHA-256。59 个新模块均为 ARM ELF32 little-endian 可重定位 ELF，均有可读取的 Build ID，对应目录与 `vermagic` 的 release 一致。全量新旧规范路径集合相同，无新增、移除或路径重命名。树内组做了基础解析和 inventory/hash 比对，完整符号、重定位和 ABI 比较集中于七个树外模块。 [覆盖差异 CSV](11G_MODULE_INVENTORY_DIFF.csv) · [仓库选择、各载体和 payload](evidence/binary/module-inventory-metadata.json) · [七个树外模块的 ELF 变化](11F_MODULE_BINARY_COMPARISON.md)

可在当前目录按 11F 的两条命令复验。新内核 image 与主内核 debuginfo 的 RPM 在本阶段按仓库身份、文件列表及成功日志关联，实际发布主内核和解压器二进制尚待直接核验。 [复验步骤](11F_MODULE_BINARY_COMPARISON.md#基线与复验) · [范围与结论](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
