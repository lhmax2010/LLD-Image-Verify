# Phase 12F/G · 真实 GCC/BFD 构建兼容性

**`GCC_REAL_BUILD = PASS`，`GCC_COMPATIBILITY = PASS`。** 使用匹配的 GCC Kernel SDK 对原始 Makefile（C）和修复 Makefile（D）执行真实外部模块构建与同配置 Kbuild strip。中间 `kdbus.o` 与最终 `kdbus.ko` 分别记录到 GNU BFD 2.43 的成功执行。每对控制组的 7 个安装模块逐字节一致。Phase 11 的 GNU Make 模拟为独立结果。 [机器可读判定](evidence/gcc/status.json) · [Phase 11 模拟记录](../kernel_lld_verification_20261125/11E_BEFORE_AFTER_REPRODUCTION.md)

## SDK、源码和执行环境

- SDK 来自 Tizen GCC QB `tizen-unified-dev_20261120.082616`，RPi4 ARMv7l 非 RT，Kernel Release `6.12.80-arm-rpi4-v7l`。Kernel source revision 为 `42aeefac58edeb081aff440f0b60be71cbe49755`，与 Phase 11 的 LLVM 目标相同。RPM 由发布元数据校验，SDK 包含 GCC/BFD 配置、generated headers、`Module.symvers`、Kbuild helper 和同包 `vmlinux`。GCC SDK 的 `.config` 记录 `CONFIG_CC_IS_GCC=y`、`CONFIG_LD_IS_BFD=y` 与 `CONFIG_MODVERSIONS=y`，`compile.h` 记录 GCC 14.2.0 和 GNU ld 2.43。 [发布的 GCC QB](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Dev/tizen-unified-dev_20261120.082616/) · [RPM 元数据](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [GCC 构建日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [SDK 身份](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
- GCC QB 的 wrapper 为 `46316fa8f9dd0d0d51726ad5fbe299daa2d16af6`。沿用该分支的非 RT wrapper 入口与七个模块宏。使用原始 provider `25797e8af7ed95a5783bbe84c11959560aaf7e92` 的精确 RPM 载荷，C 组保留 `LD = ${CROSS_COMPILE}ld`，D 组删除这一行。源文件路径和摘要对照仅该 Makefile 变化。每对使用相同 guest 工作路径、SDK、CPU affinity、`-j2`、工具链和后处理。 [wrapper SPEC](evidence/gcc/wrapper/linux-tizen-modules.spec) · [源码清单摘要](evidence/gcc/source-manifests.json)
- 隔离 ARM 环境使用只读本地 GBS root 作基础，关键工具和 SDK 以匹配 RPM 载荷覆盖。原生 ARM payload 通过 QEMU 用户态运行，使用匹配发布的 `gcc-14.2.0-1.6.armv7l` 与 `binutils-2.43-1.6.armv7l`。另用该 GCC QB 的精确 `qemu-accel-x86_64-armv7l-0.4-1.1` 验证实际加速路径。归档了 RPM 来源、实际 ELF 摘要、构建回执、成功 `execve`、进程退出和对象摘要。 [原生探针](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [原生工具哈希](evidence/gcc/tool-hashes.json) · [加速探针](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [加速 ELF 哈希](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

| C/D 控制 | 中间与最终链接器 | C/D 结果 |
| --- | --- | --- |
| QB 默认 GNU 工具选择，关闭 accelerator，QEMU 执行 ARM payload | 匹配包的 `/usr/bin/ld`，BFD 2.43 | 构建、BTF、strip 均通过，两组各 7 个安装模块逐字节一致 |
| QB 默认 GNU 工具选择，启用发布 payload accelerator | 实际运行 `/emul/usr/bin/ld`，BFD 2.43 | 构建、BTF、strip 均通过，两组各 7 个安装模块逐字节一致 |
| 显式目标 GNU `CROSS_COMPILE` 目录前缀 | `/usr/armv7l-tizen-linux-gnueabi/bin/ld`，BFD 2.43 | 构建、BTF、strip 均通过，两组各 7 个安装模块逐字节一致 |

前缀对照使用发行包提供的 ARM GNU Binutils 目录和指向匹配 GCC 包的本地驱动别名。未设置 `LD` 或 `LLVM`，两个实际链接步骤均遵循该前缀。执行记录限于本次独立构建，对应归档的 argv、输入、输出及进程退出状态。 [原生 C](evidence/gcc/builds/C/linker-execution.json) · [原生 D](evidence/gcc/builds/D/linker-execution.json) · [加速 C](evidence/gcc/builds/C-accel/linker-execution.json) · [加速 D](evidence/gcc/builds/D-accel/linker-execution.json) · [前缀 C](evidence/gcc/builds/C-prefix/linker-execution.json) · [前缀 D](evidence/gcc/builds/D-prefix/linker-execution.json)

## ELF 和 ABI 对比

每对的 ordered object 输入摘要、中间 `kdbus.o`、未 strip 和已 strip 的 `kdbus.ko` 摘要相同。两组经 GNU objdump 归一化的指令和重定位输出相同。各组 7 个安装 ELF 均通过 ARM ELF32 ET_REL、模块符号与版本检查。每组 345 个导入 CRC 匹配该 GCC SDK，其中 kdbus 153 个。kdbus 每组 2,352 条重定位在该对字节相同的模块间一致。ELF 全文件一致覆盖 SHF_ALLOC 内容、节布局、ARM flags、符号、隐式 addend 和模块元数据。kdbus 的完整 vermagic 匹配同 GCC QB 已发布 RPM 的原始模块。 [同一 SDK 模块链接脚本](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [原生 ABI](evidence/gcc/builds/C-prefix/abi.json) · [加速 ABI](evidence/gcc/builds/C-accel/abi.json) · [已发布 GCC 模块 vermagic](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

三种配对环境内的安装 kdbus 大小均为 150,032 Bytes。原生与精确加速环境之间的整体 SHA-256 不同，两环境所选 compiler 与 linker payload 不同，比较范围为各自单变量 C/D 内。原生 compiler 版本字符串末尾为 `1.6`，SDK 和加速 compiler 版本字符串末尾为 `1.1`。原生运行双方保留相同 compiler 字符串警告，完整记录在 stderr。双方的 zlogger 帧大小警告和隔离安装目录的 depmod 元数据警告均保留。探路构建曾选旧 GBS 加速 payload，后续对照用匹配发布的 payload 重跑。 [原生编译 stderr](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [安装 stderr](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [探路跟踪](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## 复验方法

在 Phase 12 目录内执行。脚本只在本轮工作树准备源代码、新建隔离挂载及构建外部模块。需要可读且能运行 ARM 用户态的 Tizen GBS root、`bwrap`、`strace`、RPM 工具和 Python 3.11+。两组命令有相同 guest 入口。RPM 打包和设备运行属于其他验收范围。 [RPM 获取脚本](scripts/gcc_inputs.py) · [构建与追踪脚本](scripts/gcc_build.py) · [证据核对脚本](scripts/gcc_compare.py)

```sh
python3 -B scripts/gcc_inputs.py
python3 -B scripts/gcc_build.py prepare
for lane in C D; do
  python3 -B scripts/gcc_build.py build --lane "$lane"
  python3 -B scripts/gcc_build.py build --lane "$lane" --cross-prefix
  python3 -B scripts/gcc_build.py build --lane "$lane" --with-accel --cpus 12-13
done
python3 -B scripts/gcc_compare.py
```
