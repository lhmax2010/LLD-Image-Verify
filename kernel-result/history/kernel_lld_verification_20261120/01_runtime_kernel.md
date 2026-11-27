# 01 · Runtime Kernel Verification

已通过固定序列号的授权 SDB 会话独立采集目标设备。运行内核、构建版本元数据和仓库身份分别核验。阶段 A 通过。最终链接和仓库身份见 [04 构建](04_build_command_analysis.md) 与 [06 身份](06_repository_runtime_mapping.md)。

| 验证项 | 状态 | 实际结果 | 证据 |
| --- | --- | --- | --- |
| 设备身份 | PASS | private-address-02:26101，Raspberry Pi 4 Model B Rev 1.5。SDB 列表有 2 个已授权会话，设备侧 IP 复核通过。 | [查看](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
| 当前内核 | PASS | 6.12.80-arm-rpi4-v7l / armv7l，Fri Nov 20 09:22:45 UTC 2026，abuild@qb-build-host-01。 | [查看](evidence/runtime/banner.out) |
| 工具链版本元数据 | PASS | Clang 22.1.8 / LLD 22.1.8，来自 /proc/version 与启动日志。 | [查看](evidence/runtime/banner.out) |
| 镜像 BUILD_ID | PASS | tizen-unified-toolchain_20261120.082536_tizen-headed-armv7l | [查看](evidence/runtime/banner.out) |
| 内核 GNU Build ID | PASS | 99ba05b664f7ece7686ab5f087bf54680bb172e6 | [查看](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
| 运行配置文件 | INCONCLUSIVE | /proc/config.gz 和 /boot/config-6.12.80-arm-rpi4-v7l 在本次会话缺失。 | [查看](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
| 活动 RPM 数据库 | INCONCLUSIVE | 查询 1229 条记录。目标包无条目。设备内核 RPM NEVRA、Source RPM、Build Time、Install Time 和文件 owner 不可确认。 | [查看](evidence/runtime/pinned-rpm-device-queries.out) |
| 已安装模块 | PASS | 59 个唯一模块路径，extra/ 下 7 个。118 次 RPM owner 查询找到 0 个文件归属。 | [查看](evidence/runtime/installed-modules.json) |
| 加载模块主快照 | PASS | 11 个加载模块，11 个取得 GNU Build ID，早期快照 10 个。 | [查看](evidence/runtime/loaded-modules.json) |

- **证据读取** 记录 uname -a、uname -r、uname -m、/proc/version、/etc/os-release、/proc/cmdline 和 boot banner。设备内路由表显示目标 IP 为本机地址。DT 型号和兼容性字符串来自设备。 [启动与版本原文](evidence/runtime/banner.out) · [设备 IP](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [设备树](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
- **运行 notes** 使用 ARM 小端 ELF note 布局和 4 字节对齐。恢复 84 字节。设备 SHA256 和恢复字节均为 a6b307af55ad01ae5fd722ad86700411ac629297fe5cb77b4eb995021d8fb8f7。 [notes 原件](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [解析](01_runtime_kernel.json)
- **设备文件限制** /boot 可列目录，当前会话未暴露启动分区文件。活动 RPM DB 中 /boot 的 owner 只是目录所属包。/usr/lib/modules 为独立只读挂载，/lib/modules 指向同一模块树。启动文件 SHA256、目标 RPM 的安装时间和文件所有权缺少设备侧记录。 [挂载、权限及目录归属](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [可读取性](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [活动 RPM 查询](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
- **模块采集** tar 流经 base64 传输，只在主机落盘。59 个文件经路径、类型、大小与设备端 SHA256 核验。归档 SHA256 为 958377d8584b37e08e68fae6cccf616ed7e29580593ae0d405004e4cce5f95e6。 [设备文件回执](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [归档](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [RPM owner](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
- **加载模块** 主快照和相邻 lsmod 均保留。该设备在读操作间的状态可能变化，按主快照分别读取模块 notes。 [主快照](evidence/runtime/loaded-list.out) · [lsmod](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [模块 notes](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

[结构化结果](01_runtime_kernel.json) · [采集方法](VERIFICATION_METHOD.md) · [实际命令及退出状态](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
