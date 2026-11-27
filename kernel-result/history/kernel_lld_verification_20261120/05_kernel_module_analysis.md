# 05 · Kernel Module LLD 覆盖

范围为 6.12.80-arm-rpi4-v7l。仓库模块来自 arm-rpi4-linux-kernel-modules（52 个）及 linux-tizen-modules-rpi4（7 个）。设备在 /usr/lib/modules/6.12.80-arm-rpi4-v7l 读取 59 个文件，逐文件 SHA256 验证传输。两边均为未压缩 ARM ELF32 little-endian ET_REL，vermagic 全部匹配。逐文件同时保留原始和 ELF 哈希。 [逐文件清单](05_kernel_module_inventory.csv) · [设备采集清单](evidence/runtime/installed-modules.json)

| 类别 | 仓库 | 设备已安装 |
| --- | --- | --- |
| 模块文件总数 | 59 | 59 |
| 成功解析 | 59 | 59 |
| LLD_CONFIRMED | 0 | 0 |
| LLD_INDICATED | 59 | 59 |
| BFD_CONFIRMED | 0 | 0 |
| BFD_INDICATED | 0 | 0 |
| OTHER_LINKER | 0 | 0 |
| CONFLICTING_EVIDENCE | 0 | 0 |
| UNKNOWN | 0 | 0 |
| PARSE_FAILED | 0 | 0 |
| Confirmed LLD Coverage | 0.00% (0/59) | 0.00% (0/59) |
| LLD Evidence Coverage | 100.00% (59/59) | 100.00% (59/59) |
| ELF Parsing Coverage | 100.00% (59/59) | 100.00% (59/59) |
| ELF 自带链接器标记 | 0 | 0 |
| 匹配 quiet 链接记录 | 59 | 59 |

分母包括各来源目标 release 的全部普通模块文件路径。两边都没有重复路径、同名模块、同字节副本或模块文件符号链接。设备 /lib 和 /usr/lib 指向同一物理树，计一次。内建驱动及辅助文件排除。 [统计和排除项](05_kernel_module_coverage.json)

设备 59/59 个文件的路径和原始 SHA256 精确匹配仓库包。活动 RPM DB 报告的模块 owner 数为 0。已发布模块分区的 59/59 个文件另与仓库 RPM 匹配。 [RPM owner 回执](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [发布分区验证](evidence/repository/image-profile-verification.json)

每个模块均有自己的 LD [M]、INSTALL、RPM 写出及构建成功回执。结合该构建的 LLVM=1、开发包配置及 Kbuild 的 $(LD) 规则逐项判定 LLD_INDICATED。设备结论通过逐文件路径和 SHA256 关联。每个模块 ELF 自身缺少链接器标记，历史最终链接器 executable 和 argv 也均缺失。表中 100% 表示有 LLD 迹象的证据覆盖率，最终链接确认覆盖率为 0%。 [逐目标日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [逐文件结构化证据](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

主 /proc/modules 快照列出 11 个加载模块，其中 11/11 个 sysfs GNU Build ID 与已安装 ELF 匹配。早期快照中有 10 个。 [加载模块映射](05_loaded_module_mapping.csv) · [主快照](evidence/runtime/loaded-list.out) · [sysfs notes](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
