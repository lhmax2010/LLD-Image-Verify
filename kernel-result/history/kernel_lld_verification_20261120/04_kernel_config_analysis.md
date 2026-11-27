# Phase 4 — Kernel Config 验证

**PASS（发布的实际生成配置）**。固定快照的 `arm-rpi4-linux-kernel-devel-6.12.80-0.armv7l.rpm` 带有非实时 ARMv7l RPi4 的完整 `.config`。包头指向 `rpi4-linux-kernel-6.12.80-0.src.rpm`，VCS 与快照 manifest 的 `platform/kernel/linux-rpi#42aeefac58edeb081aff440f0b60be71cbe49755` 一致。生成头文件的 release、builder、工具链、UTS 时间与独立采样的运行时 banner 一致。主内核二进制映射由 Phase 6 建立。[RPM 包头](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [快照 manifest](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [生成头文件](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [运行时 banner](evidence/runtime/banner.out) · [身份映射](06_repository_runtime_mapping.md)

| 选项 | 实际 `.config` | `auto.conf` |
|---|---|---|
| `CONFIG_CC_VERSION_TEXT` | `"clang version 22.1.8"` | `clang version 22.1.8` |
| `CONFIG_CC_IS_CLANG` | `y` | `y` |
| `CONFIG_CLANG_VERSION` | `220108` | `220108` |
| `CONFIG_CC_IS_GCC` | 无条目 | 无条目 |
| `CONFIG_GCC_VERSION` | `0` | `0` |
| `CONFIG_LD_IS_LLD` | `y` | `y` |
| `CONFIG_LLD_VERSION` | `220108` | `220108` |
| `CONFIG_LD_IS_BFD` | 无条目 | 无条目 |
| `CONFIG_LD_VERSION` | `0` | `0` |
| `CONFIG_AS_IS_LLVM` | `y` | `y` |
| `CONFIG_AS_VERSION` | `220108` | `220108` |
| `CONFIG_LTO` | 无条目 | 无条目 |
| `CONFIG_LTO_NONE` | `y` | `y` |
| `CONFIG_LTO_CLANG` | 无条目 | 无条目 |
| `CONFIG_LTO_CLANG_THIN` | 无条目 | 无条目 |
| `CONFIG_LTO_CLANG_FULL` | 无条目 | 无条目 |
| `CONFIG_IKCONFIG` | 显式未启用 | 无条目 |
| `CONFIG_IKCONFIG_PROC` | 无条目 | 无条目 |

`220108` 对应 `22.1.8`。Kconfig 通过 `scripts/ld-version.sh` 调用选定链接器的 `--version` 并解析工具名和版本，BFD 未选中时 `CONFIG_LD_VERSION` 默认是 `0`。Kbuild 使用同一 `LD` 生成 `compile.h` 中的工具链 banner，因此两个输出可以核对构建元数据，最终链接器仍由 Phase 4 链接证据判定。[原始 .config](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [原始 auto.conf](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [带行号和 SHA256 的解析](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [Kconfig](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [ld-version.sh](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

| 来源 | 结果 | 原始证据 |
|---|---|---|
| 运行时 `/proc/config.gz` | 路径不存在 | [设备路径检查](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
| 运行时 `/boot/config-6.12.80-arm-rpi4-v7l` | 路径不存在，`/boot` 目录可列出 | [设备路径检查](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
| Kernel 安装包、模块包、devel Debuginfo 和 Debugsource RPM | 发布清单未显示目标生成 `.config` 或 `config-6.12.80-*` | [匹配的 RPM 配置路径](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
| Kernel Development RPM | 完整 `.config`、`auto.conf` 和生成头文件 | [devel 路径清单](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
| Source RPM | SPEC 和补丁记录基础配置及 `olddefconfig`，属于构建意图 | [SPEC](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [源包成员](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [基础 defconfig](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
| Kernel 内嵌配置 | 对仓库 `zImage` 运行版本固定的 `extract-ikconfig` 退出 1 并返回 “Cannot find kernel config”。与 `CONFIG_IKCONFIG` 显式未启用一致 | [提取命令](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [原始 stderr](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
| 对应 GBS 工作目录 | 本机找不到原构建路径。同版本的 8 月构建已凭 builder、时间与 Build ID 排除 | [原路径检查](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [排除证据](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
