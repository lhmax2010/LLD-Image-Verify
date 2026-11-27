# 08.07 · Build ID 后处理复核

**PASS。** 用 RPM header 的单文件 SHA256 绑定五个已解包成员。从 kernel RPM 的 /boot/zImage 验证 ARM 头后，在偏移 0x8249 解出通过 gzip 校验的 41,721,980 字节 raw Image。从原始设备 hexdump 重建 84 字节 notes，并核对设备报告与归档字节。 [独立复核输出](evidence/build-id/recheck.out) · [机器可读对比](BUILD_ID_COMPARISON.json) · [独立分析脚本](scripts/review_build_id.py)

| 对象 | 位置或结果 | 
| --- | --- | 
| 主 ELF PT_LOAD 所导出的基址 | 0xc0008000 | 
| .notes VMA / LMA | 0xc1b689c0 / 0xc1b689c0 | 
| .notes ELF 文件 / raw Image 偏移 | 0x18789c0 / 0x1b609c0 | 
| 20 字节窗口 ELF / raw 文件偏移 | 0x1878a00 / 0x1b60a00，.notes 内 [64,84) | 
| 原始 GNU Build ID | 99ba05b664f7ece7686ab5f087bf54680bb172e6 | 
| 后处理 GNU Build ID | bac659039ce25486da3473a6da562dc0e7fd1eea | 
| 84 字节 Runtime Notes SHA256 | a6b307af55ad01ae5fd722ad86700411ac629297fe5cb77b4eb995021d8fb8f7 | 
| 主内核 / ARM 解压器 debuglink CRC32 | c7324c98 / 6b4eab11 | 

每个有文件内容的非空 SHF_ALLOC 段均验证 PT_LOAD 的 VMA、文件偏移及大小。用 LMA = p_paddr + sh_addr − p_vaddr 和最低目标 LMA 映射到 flat binary。主内核 32 个段中 31 个相同，唯一差异为 .notes 内的 20 字节，raw 中未映射的区间均为零。ARM 解压器的 6 个映射段均一致。**唯一差异的范围限于所比较的映射段。** ELF 头、非装载段、SHT_NOBITS 和 sidecar 的 DWARF 在范围之外。 [完整映射和窗口](BUILD_ID_COMPARISON.json)

日志 L14011 先安装 zImage，L14459 执行 find-debuginfo.sh --build-id-seed 6.12.80-0，L14579 和 L14853 分别处理解压器和主 ELF。原 Base rpm 宏 L182–189 在 _unique_build_ids 开启时展开 %{VERSION}-%{RELEASE}，L556 默认开启，符合实际执行参数。同一 Base 的 rpm-build 脚本 L445–448 将 -i 和 seed 交给 debugedit。 [历史日志](../evidence/build/linux-rpi-armv7l.out#L14459) · [RPM 宏](evidence/build-id/historical-rpm-macros.out#L189) · [打包脚本](evidence/build-id/historical-find-debuginfo.sh.txt#L445)

重算 ID 更改 .notes，包装流程还处理 DWARF 并从 stripped ELF 移除或分离 .comment。两个 stripped ELF 均无 .comment。各自通过 .gnu_debuglink 文件名和 CRC32 验证的 sidecar 保留非装载 .comment，记录 clang version 22.1.8 与 Linker: LLD 22.1.8。sidecar 标记仍可能从早期链接输入继承。 [stripping 规则](evidence/build-id/historical-find-debuginfo.sh.txt#L248) · [sidecar 标记及 CRC](BUILD_ID_COMPARISON.json)
