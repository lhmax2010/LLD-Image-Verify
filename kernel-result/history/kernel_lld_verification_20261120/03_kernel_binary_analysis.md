# 03 · 内核二进制静态验证

已校验的 7 个目标二进制 RPM 在主机解包。arm-rpi4-linux-kernel-6.12.80-0.armv7l.rpm 提供 /boot/zImage。开发和调试 RPM 各提供主内核和 ARM 解压器 ELF。清单保留 SHA256、路径、工具输出和退出状态。 [二进制清单](03_kernel_binary_inventory.csv) · [结构化证据](03_kernel_linker_evidence.json)

| 输入 | 类型 | GNU Build ID | 链接器证据 |
| --- | --- | --- | --- |
| /boot/zImage | ARM little-endian zImage，经 gzip 解出 raw Image | 99ba05b664f7ece7686ab5f087bf54680bb172e6（raw Image notes） | 版本字符串 LLD 22.1.8 |
| devel vmlinux | ELF32 / little-endian / ARM / ET_EXEC | bac659039ce25486da3473a6da562dc0e7fd1eea | 无 .comment |
| devel vmlinux.debug | ELF32 / little-endian / ARM / ET_EXEC | bac659039ce25486da3473a6da562dc0e7fd1eea | Linker: LLD 22.1.8 |
| devel compressed/vmlinux | ELF32 / little-endian / ARM / ET_EXEC | 无 | 无 .comment |
| devel compressed/vmlinux.debug | ELF32 / little-endian / ARM / ET_EXEC | 无 | Linker: LLD 22.1.8 |

- Linux stable v6.12.80 对应提交 00d7934ffcc35e65b113ba4991c8a3338bd85fc1。脚本原件、tag 和 SHA256 已归档。extract-vmlinux 退出 0，stdout 为空，stderr 报找不到 ELF。extract-ikconfig 退出 1，stdout 为空。 [tag 核对](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [脚本 SHA256](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [extract-vmlinux stderr](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
- 校验 ARM zImage magic 后，在 0x8249 解出一个通过 gzip 校验、带目标 banner 的 raw Image。大小 41,721,980 字节，SHA256 为 1bcb98939e19276f8a4de3ab82425f119856005d388680fdb2847d42bdda1171。GNU Build ID note 位于 0x1b609f0，完整运行时 notes 位于 0x1b609c0。 [raw Image](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [设备 notes](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
- 按 ELF PT_LOAD 的 LMA 对齐，主内核 31/32 个有文件内容的 SHF_ALLOC 段逐字节一致。唯一差异为 .notes 中的 20 字节 Build ID。ARM 解压器 6/6 个段一致。未映射范围的非零字节数均为 0。两个 debug sidecar 均经 .gnu_debuglink 文件名和 CRC32 验证，主内核对同时共享发布后的 Build ID。 [逐字节比较](evidence/kernel_binary/byte-comparison.json)
- 日志先 stage zImage，后执行 find-debuginfo.sh --build-id-seed 6.12.80-0。该历史 rpm-build 的 find-debuginfo 实现向 debugedit 传入重新计算选项和 seed，确认发布处理可解释唯一差异。 [发布日志](evidence/build/linux-rpi-armv7l.out#L14459) · [历史脚本回执](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [debugedit 官方项目](https://sourceware.org/debugedit/)
- 两个已绑定的调试 ELF 都在 .comment+0x16 记录 Linker: LLD 22.1.8，在 .comment+0x1 记录 Clang。raw Image 中是构建 banner。其他字节命中按偏移保留，未确定来源的命中保持未知。 [主内核 readelf](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [解压器 readelf](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [LLVM 标记实现](https://llvm.googlesource.com/llvm-project/+/refs/heads/main/lld/ELF/SyntheticSections.cpp)
- .comment 可以保留输入对象或部分链接的标记。构建日志观察到 vmlinux 和 ARM 解压器的 quiet 链接步骤。结合已验证的 Kbuild 默认选择，两者均有 LLD 迹象，最终链接保持 CONDITIONAL_PASS。 [构建证据](04_build_command_analysis.md)
