# 06 · Repository → Runtime 身份映射

**EXACT_MATCH，适用于运行主内核的 Build ID 和完整 notes。** 仓库内核 RPM 通过 RPM 元数据校验，发布启动镜像通过独立发布 SHA256SUMS 校验。两个通道的 zImage 字节一致。gzip 解出的 raw Image 含有与设备完全相同的 84 字节 notes 和同一完整 banner。 [机器可读身份记录](06_identity_verification.json) · [启动分区比对](evidence/repository/image-profile-verification.json) · [notes 逐字节比对](evidence/kernel_binary/byte-comparison.json)

| 链路 | 结果 | 证据 |
| --- | --- | --- |
| 快照 → Kernel RPM | 仓库 SHA256 一致，arm-rpi4-linux-kernel-6.12.80-0.armv7l.rpm | [02_repository_identity.json](02_repository_identity.json) |
| Kernel RPM → 发布启动分区 | EXACT_SHA256 · 2b26465ef90455092cb6671bc2a6a967edfe8f5e7233894b70eaee0564b68601 | [evidence/repository/image-profile-verification.json](evidence/repository/image-profile-verification.json) |
| zImage → raw Image → 运行主内核 | EXACT_MATCH · 99ba05b664f7ece7686ab5f087bf54680bb172e6，完整 notes 同字节 | [evidence/kernel_binary/byte-comparison.json](evidence/kernel_binary/byte-comparison.json) |
| 开发及调试 ELF → raw Image | 同一构建的发布后 ELF。差异为 20 个 GNU ID 字节 | [03_kernel_binary_analysis.md](03_kernel_binary_analysis.md) |
| 已安装内核 RPM NEVRA / install time / owner | UNVERIFIABLE · 活动 DB 无条目，/boot 未暴露启动文件 | [evidence/runtime/pinned-rpm-device-queries.out](evidence/runtime/pinned-rpm-device-queries.out) |
| 模块 RPM → 发布分区 → 设备已安装 | 发布分区 59/59，设备 59/59 SHA256 匹配 | [05_kernel_module_analysis.md](05_kernel_module_analysis.md) |
| 设备文件 → 设备已加载模块 | 11/11 GNU Build ID 匹配 | [05_loaded_module_mapping.csv](05_loaded_module_mapping.csv) |

运行 Image BUILD_ID 为 tizen-unified-toolchain_20261120.082536_tizen-headed-armv7l。发布 boot profile 使用独立 boot 和 modules 分区。会话可读取独立的只读模块挂载，启动卷文件未暴露，设备 /boot/zImage 的 SHA256 和活动 DB 中的安装时间、RPM 所有权无法实测。RPM header 的 BuildTime 为 epoch 0。实际编译时间由内核 banner、生成头和构建日志关联。 [发布清单](02_repository_inventory.md) · [设备挂载](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
