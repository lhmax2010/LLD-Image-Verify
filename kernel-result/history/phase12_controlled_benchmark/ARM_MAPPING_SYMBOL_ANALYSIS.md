# Phase 12D/G · ARM 映射符号、大小与静态二进制对比

按 Arm AAELF32 比较 `$a` ARM、`$t` Thumb、`$d` data 的半开区间。检查符号绑定、类型、尺寸、起始边界、同地址重复及重定位引用。已知纯数据节可以省略起始标记。 [Arm AAELF32 5.5.5](https://github.com/ARM-software/abi-aa/blob/main/aaelf32/aaelf32.rst#mapping-symbols)

| 比较 | 文件大小旧 → 新（Bytes） | 差额 | 映射符号 a/t/d 旧 → 新 |
| --- | ---: | ---: | --- |
| historical-qb | 162,584 → 161,292 | -1,292 | 122/0/183 → 122/0/102 |
| controlled-intermediate | 2,505,192 → 1,998,564 | -506,628 | 122/0/203 → 122/0/102 |
| controlled-unstripped | 2,071,276 → 2,069,984 | -1,292 | 122/0/183 → 122/0/102 |
| controlled-stripped | 162,584 → 161,292 | -1,292 | 122/0/183 → 122/0/102 |
| frozen-intermediate | 2,505,192 → 1,998,564 | -506,628 | 122/0/203 → 122/0/102 |
| frozen-unstripped | 2,071,276 → 2,069,984 | -1,292 | 122/0/183 → 122/0/102 |
| frozen-stripped | 162,584 → 161,292 | -1,292 | 122/0/183 → 122/0/102 |
| gcc-intermediate | 2,935,264 → 2,935,264 | +0 | 114/0/191 → 114/0/191 |
| gcc-unstripped | 3,029,212 → 3,029,212 | +0 | 114/0/196 → 114/0/196 |
| gcc-stripped | 150,032 → 150,032 | +0 | 114/0/177 → 114/0/177 |

真实 Makefile A/B 的发布形式分别为 162,584 与 161,292 Bytes，与两份对应历史 QB 的 SHA-256 分别完全一致。在已验证的受控环境中，单行改动的 1,292 Bytes 减少可归因。历史 QB 的链接器执行仍沿用原证据评级。 [冻结输入、输出及命令](evidence/replay/link-replay.json)

固定对象重放中，BFD 路径的 `$d` 为 203 → 183 → 183，LLD 路径为 102 → 102 → 102，顺序为中间对象、未 strip 模块、已 strip 模块。纯中间链接差额为 101 个标记，固定的最终 LLD 处理消除其中 20 个，来自 .ARM.exidx（18）、.ARM.exidx.exit.text（1）和 .ARM.exidx.init.text（1）。strip 对两侧的 81 个差额无影响。 [中间链接 ELF](evidence/elf/frozen-intermediate.json) · [最终 ELF](evidence/elf/frozen-stripped.json)

GNU BFD map 的映射参考对象与普通重放的中间 ELF 摘要一致。`$d` 多出的 101 条逐一指向原来没有该标记的纯数据输入节起点，均由 BFD 在中间链接添加。两侧原始的 102 条代码内数据映射保持。最终多出的 81 条均追踪至这些 BFD 添加的记录，75 条具备唯一对象来源，6 条合并常量具有多个候选来源，分别位于 .rodata.cst16（4）与 .rodata.cst8（2）。 [逐符号来源](evidence/elf/frozen-stripped.json)

中间 ELF 的主要差额来自 `.debug_str` 合并，另有常量、字符串节布局和符号表变化。数据与调试 REL 站点对目标字符串或固定宽度合并记录归一化后等价，未发现未解释的站点变化。中间 ELF flags 从 0x05000000 变为 0x05000200，LLD 路径显式编码 soft-float。两侧最终 ELF 均为 0x05000200，匹配目标 SDK。 [节大小 CSV](ELF_SIZE_COMPARISON.csv) · [中间 ELF 校验](evidence/elf/frozen-intermediate.json)

GCC C/D 的中间 ELF、未 strip 模块及已安装模块两两逐字节一致，最终模块 153/153 满足目标 SDK CRC。GCC SDK 脚本在两侧均生成一个 BYTE(0) 的 .plt 占位字节。GNU objdump 报告该位置越界，LLVM 额外显示一个 unknown 字节。两侧共同解码的 16,450 个指令无位置或操作码差异。 [GCC 构建与静态证据](GCC_COMPATIBILITY_REPORT.md) · [逐项证据](evidence/elf/gcc-stripped.json)

## historical-qb

历史发布对照为 OBSERVED_NOT_ATTRIBUTED。两份发布包的原始中间对象及工具执行记录缺失。 [Phase 11 ELF 报告](../kernel_lld_verification_20261125/11F_MODULE_BINARY_COMPARISON.md) · [Arm 属性默认值](https://github.com/ARM-software/abi-aa/blob/main/addenda32/addenda32.rst#default-values-for-public-tags)

节文件字节差额为`.ARM.attributes` +4、`.symtab` -1,296。节载荷 -1,292 Bytes，节表 +0 Bytes，文件其余布局 +0 Bytes。 [逐节 CSV](ELF_SIZE_COMPARISON.csv)

符号总数 876 → 795，LOCAL 565 → 484、GLOBAL 311 → 311、WEAK 0 → 0。移除的映射符号为同类连续区间内标记 62、纯数据节可省略起始标记 15、同地址重复 4。涉及 15 个节，执行节类别边界变化 0 处，两侧映射符号重定位引用均为 0/0。 [完整标记与区间](evidence/elf/historical-qb.json)

执行节字节变化为无。SHF_ALLOC 原字节变化为.note.gnu.build-id、__versions。重定位 2,972 → 2,972，原始差额无，归一化未解释差额无。SDK CRC 为 left PASS 154/154、right PASS 154/154。复核项无。 [接口、属性、布局和重定位证据](evidence/elf/historical-qb.json)

GNU 与 LLVM 反汇编在各自旧新对照中的规范化一致性为 [True, True]。两工具解析指令位置交集为 [16789, 16789]，交集编码冲突为 [0, 0]。助记符别名保留在两套原始日志。 [GNU 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [LLVM 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## controlled-intermediate


节文件字节差额为`.ARM.attributes` +4、`.comment` -396、`.debug_str` -506,147、`.rodata.cst16` -48、`.rodata.cst8` -8、`.rodata.str` -76、`.rodata.str1.1` -98、`.shstrtab` +218、`.strtab` +1,532、`.symtab` -1,632。节载荷 -506,651 Bytes，节表 +0 Bytes，文件其余布局 +23 Bytes。 [逐节 CSV](ELF_SIZE_COMPARISON.csv)

符号总数 911 → 809，LOCAL 602 → 500、GLOBAL 309 → 309、WEAK 0 → 0。移除的映射符号为同类连续区间内标记 83、纯数据节可省略起始标记 18。涉及 18 个节，执行节类别边界变化 0 处，两侧映射符号重定位引用均为 0/0。 [完整标记与区间](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

来源匹配状态为LINK_MAP_UNIQUE 101。唯一关联的输入对象分布为util.o 6、queue.o 4、reply.o 4、pool.o 7、policy.o 4、domain.o 4、notify.o 3、node.o 5、names.o 6、metadata.o 4、message.o 6、match.o 8、item.o 3、handle.o 5、fs.o 7、endpoint.o 5、connection.o 7、bus.o 5、main.o 8。GNU BFD map 的参考 ELF 与无 map 的重放结果摘要相同。最终模块的来源关联结合节内容或合并记录内容，详情保留多候选。 [逐符号来源](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

执行节字节变化为无。SHF_ALLOC 原字节变化为.data、.rodata.cst16、.rodata.cst32、.rodata.cst8、.rodata.str、.rodata.str1.1、__bug_table。重定位 73,663 → 73,663，原始差额regular_site_bytes_changed 3、debug_site_bytes_changed 65,036、regular_identity_deltas 446，归一化未解释差额无。SDK CRC 为 left NOT_CHECKED 0/0、right NOT_CHECKED 0/0。复核项无。 [接口、属性、布局和重定位证据](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

GNU 与 LLVM 反汇编在各自旧新对照中的规范化一致性为 [True, True]。两工具解析指令位置交集为 [16789, 16789]，交集编码冲突为 [0, 0]。助记符别名保留在两套原始日志。 [GNU 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [LLVM 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## controlled-unstripped


节文件字节差额为`.ARM.attributes` +4、`.symtab` -1,296。节载荷 -1,292 Bytes，节表 +0 Bytes，文件其余布局 +0 Bytes。 [逐节 CSV](ELF_SIZE_COMPARISON.csv)

符号总数 904 → 823，LOCAL 593 → 512、GLOBAL 311 → 311、WEAK 0 → 0。移除的映射符号为同类连续区间内标记 62、纯数据节可省略起始标记 15、同地址重复 4。涉及 15 个节，执行节类别边界变化 0 处，两侧映射符号重定位引用均为 0/0。 [完整标记与区间](evidence/elf/controlled-unstripped.json)

来源匹配状态为LINK_MAP_UNIQUE 75、LINK_MAP_MULTIPLE 6。唯一关联的输入对象分布为util.o 4、queue.o 3、reply.o 3、pool.o 6、policy.o 3、domain.o 3、notify.o 2、node.o 4、names.o 4、metadata.o 3、message.o 4、match.o 6、item.o 2、handle.o 4、fs.o 6、endpoint.o 4、connection.o 5、bus.o 3、main.o 6。GNU BFD map 的参考 ELF 与无 map 的重放结果摘要相同。最终模块的来源关联结合节内容或合并记录内容，详情保留多候选。 [逐符号来源](evidence/elf/controlled-unstripped.json)

执行节字节变化为无。SHF_ALLOC 原字节变化为.note.gnu.build-id、__versions。重定位 75,099 → 75,099，原始差额无，归一化未解释差额无。SDK CRC 为 left PASS 154/154、right PASS 154/154。复核项无。 [接口、属性、布局和重定位证据](evidence/elf/controlled-unstripped.json)

GNU 与 LLVM 反汇编在各自旧新对照中的规范化一致性为 [True, True]。两工具解析指令位置交集为 [16789, 16789]，交集编码冲突为 [0, 0]。助记符别名保留在两套原始日志。 [GNU 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [LLVM 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## controlled-stripped


节文件字节差额为`.ARM.attributes` +4、`.symtab` -1,296。节载荷 -1,292 Bytes，节表 +0 Bytes，文件其余布局 +0 Bytes。 [逐节 CSV](ELF_SIZE_COMPARISON.csv)

符号总数 876 → 795，LOCAL 565 → 484、GLOBAL 311 → 311、WEAK 0 → 0。移除的映射符号为同类连续区间内标记 62、纯数据节可省略起始标记 15、同地址重复 4。涉及 15 个节，执行节类别边界变化 0 处，两侧映射符号重定位引用均为 0/0。 [完整标记与区间](evidence/elf/controlled-stripped.json)

来源匹配状态为LINK_MAP_UNIQUE 75、LINK_MAP_MULTIPLE 6。唯一关联的输入对象分布为util.o 4、queue.o 3、reply.o 3、pool.o 6、policy.o 3、domain.o 3、notify.o 2、node.o 4、names.o 4、metadata.o 3、message.o 4、match.o 6、item.o 2、handle.o 4、fs.o 6、endpoint.o 4、connection.o 5、bus.o 3、main.o 6。GNU BFD map 的参考 ELF 与无 map 的重放结果摘要相同。最终模块的来源关联结合节内容或合并记录内容，详情保留多候选。 [逐符号来源](evidence/elf/controlled-stripped.json)

执行节字节变化为无。SHF_ALLOC 原字节变化为.note.gnu.build-id、__versions。重定位 2,972 → 2,972，原始差额无，归一化未解释差额无。SDK CRC 为 left PASS 154/154、right PASS 154/154。复核项无。 [接口、属性、布局和重定位证据](evidence/elf/controlled-stripped.json)

GNU 与 LLVM 反汇编在各自旧新对照中的规范化一致性为 [True, True]。两工具解析指令位置交集为 [16789, 16789]，交集编码冲突为 [0, 0]。助记符别名保留在两套原始日志。 [GNU 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [LLVM 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## frozen-intermediate


节文件字节差额为`.ARM.attributes` +4、`.comment` -396、`.debug_str` -506,147、`.rodata.cst16` -48、`.rodata.cst8` -8、`.rodata.str` -76、`.rodata.str1.1` -98、`.shstrtab` +218、`.strtab` +1,532、`.symtab` -1,632。节载荷 -506,651 Bytes，节表 +0 Bytes，文件其余布局 +23 Bytes。 [逐节 CSV](ELF_SIZE_COMPARISON.csv)

符号总数 911 → 809，LOCAL 602 → 500、GLOBAL 309 → 309、WEAK 0 → 0。移除的映射符号为同类连续区间内标记 83、纯数据节可省略起始标记 18。涉及 18 个节，执行节类别边界变化 0 处，两侧映射符号重定位引用均为 0/0。 [完整标记与区间](evidence/elf/frozen-intermediate.json)

来源匹配状态为LINK_MAP_UNIQUE 101。唯一关联的输入对象分布为util.o 6、queue.o 4、reply.o 4、pool.o 7、policy.o 4、domain.o 4、notify.o 3、node.o 5、names.o 6、metadata.o 4、message.o 6、match.o 8、item.o 3、handle.o 5、fs.o 7、endpoint.o 5、connection.o 7、bus.o 5、main.o 8。GNU BFD map 的参考 ELF 与无 map 的重放结果摘要相同。最终模块的来源关联结合节内容或合并记录内容，详情保留多候选。 [逐符号来源](evidence/elf/frozen-intermediate.json)

执行节字节变化为无。SHF_ALLOC 原字节变化为.data、.rodata.cst16、.rodata.cst32、.rodata.cst8、.rodata.str、.rodata.str1.1、__bug_table。重定位 73,663 → 73,663，原始差额regular_site_bytes_changed 3、debug_site_bytes_changed 65,036、regular_identity_deltas 446，归一化未解释差额无。SDK CRC 为 left NOT_CHECKED 0/0、right NOT_CHECKED 0/0。复核项无。 [接口、属性、布局和重定位证据](evidence/elf/frozen-intermediate.json)

GNU 与 LLVM 反汇编在各自旧新对照中的规范化一致性为 [True, True]。两工具解析指令位置交集为 [16789, 16789]，交集编码冲突为 [0, 0]。助记符别名保留在两套原始日志。 [GNU 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [LLVM 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## frozen-unstripped


节文件字节差额为`.ARM.attributes` +4、`.symtab` -1,296。节载荷 -1,292 Bytes，节表 +0 Bytes，文件其余布局 +0 Bytes。 [逐节 CSV](ELF_SIZE_COMPARISON.csv)

符号总数 904 → 823，LOCAL 593 → 512、GLOBAL 311 → 311、WEAK 0 → 0。移除的映射符号为同类连续区间内标记 62、纯数据节可省略起始标记 15、同地址重复 4。涉及 15 个节，执行节类别边界变化 0 处，两侧映射符号重定位引用均为 0/0。 [完整标记与区间](evidence/elf/frozen-unstripped.json)

来源匹配状态为LINK_MAP_UNIQUE 75、LINK_MAP_MULTIPLE 6。唯一关联的输入对象分布为util.o 4、queue.o 3、reply.o 3、pool.o 6、policy.o 3、domain.o 3、notify.o 2、node.o 4、names.o 4、metadata.o 3、message.o 4、match.o 6、item.o 2、handle.o 4、fs.o 6、endpoint.o 4、connection.o 5、bus.o 3、main.o 6。GNU BFD map 的参考 ELF 与无 map 的重放结果摘要相同。最终模块的来源关联结合节内容或合并记录内容，详情保留多候选。 [逐符号来源](evidence/elf/frozen-unstripped.json)

执行节字节变化为无。SHF_ALLOC 原字节变化为.note.gnu.build-id。重定位 75,099 → 75,099，原始差额无，归一化未解释差额无。SDK CRC 为 left PASS 154/154、right PASS 154/154。复核项无。 [接口、属性、布局和重定位证据](evidence/elf/frozen-unstripped.json)

GNU 与 LLVM 反汇编在各自旧新对照中的规范化一致性为 [True, True]。两工具解析指令位置交集为 [16789, 16789]，交集编码冲突为 [0, 0]。助记符别名保留在两套原始日志。 [GNU 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [LLVM 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## frozen-stripped


节文件字节差额为`.ARM.attributes` +4、`.symtab` -1,296。节载荷 -1,292 Bytes，节表 +0 Bytes，文件其余布局 +0 Bytes。 [逐节 CSV](ELF_SIZE_COMPARISON.csv)

符号总数 876 → 795，LOCAL 565 → 484、GLOBAL 311 → 311、WEAK 0 → 0。移除的映射符号为同类连续区间内标记 62、纯数据节可省略起始标记 15、同地址重复 4。涉及 15 个节，执行节类别边界变化 0 处，两侧映射符号重定位引用均为 0/0。 [完整标记与区间](evidence/elf/frozen-stripped.json)

来源匹配状态为LINK_MAP_UNIQUE 75、LINK_MAP_MULTIPLE 6。唯一关联的输入对象分布为util.o 4、queue.o 3、reply.o 3、pool.o 6、policy.o 3、domain.o 3、notify.o 2、node.o 4、names.o 4、metadata.o 3、message.o 4、match.o 6、item.o 2、handle.o 4、fs.o 6、endpoint.o 4、connection.o 5、bus.o 3、main.o 6。GNU BFD map 的参考 ELF 与无 map 的重放结果摘要相同。最终模块的来源关联结合节内容或合并记录内容，详情保留多候选。 [逐符号来源](evidence/elf/frozen-stripped.json)

执行节字节变化为无。SHF_ALLOC 原字节变化为.note.gnu.build-id。重定位 2,972 → 2,972，原始差额无，归一化未解释差额无。SDK CRC 为 left PASS 154/154、right PASS 154/154。复核项无。 [接口、属性、布局和重定位证据](evidence/elf/frozen-stripped.json)

GNU 与 LLVM 反汇编在各自旧新对照中的规范化一致性为 [True, True]。两工具解析指令位置交集为 [16789, 16789]，交集编码冲突为 [0, 0]。助记符别名保留在两套原始日志。 [GNU 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [LLVM 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## gcc-intermediate


节文件字节差额为无。节载荷 +0 Bytes，节表 +0 Bytes，文件其余布局 +0 Bytes。 [逐节 CSV](ELF_SIZE_COMPARISON.csv)

符号总数 812 → 812，LOCAL 504 → 504、GLOBAL 308 → 308、WEAK 0 → 0。移除的映射符号为无。涉及 0 个节，执行节类别边界变化 0 处，两侧映射符号重定位引用均为 0/0。 [完整标记与区间](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

执行节字节变化为无。SHF_ALLOC 原字节变化为无。重定位 76,660 → 76,660，原始差额无，归一化未解释差额无。SDK CRC 为 left NOT_CHECKED 0/0、right NOT_CHECKED 0/0。复核项无。 [接口、属性、布局和重定位证据](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

GNU 与 LLVM 反汇编在各自旧新对照中的规范化一致性为 [True, True]。两工具解析指令位置交集为 [16450, 16450]，交集编码冲突为 [0, 0]。助记符别名保留在两套原始日志。 [GNU 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [LLVM 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## gcc-unstripped


节文件字节差额为无。节载荷 +0 Bytes，节表 +0 Bytes，文件其余布局 +0 Bytes。 [逐节 CSV](ELF_SIZE_COMPARISON.csv)

符号总数 834 → 834，LOCAL 524 → 524、GLOBAL 310 → 310、WEAK 0 → 0。移除的映射符号为无。涉及 0 个节，执行节类别边界变化 0 处，两侧映射符号重定位引用均为 0/0。 [完整标记与区间](evidence/elf/gcc-unstripped.json)

执行节字节变化为无。SHF_ALLOC 原字节变化为无。重定位 78,072 → 78,072，原始差额无，归一化未解释差额无。SDK CRC 为 left PASS 153/153、right PASS 153/153。复核项无。 [接口、属性、布局和重定位证据](evidence/elf/gcc-unstripped.json)

GNU 与 LLVM 反汇编在各自旧新对照中的规范化一致性为 [True, True]。两工具解析指令位置交集为 [16450, 16450]，交集编码冲突为 [0, 0]。助记符别名保留在两套原始日志。 [GNU 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [LLVM 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## gcc-stripped


节文件字节差额为无。节载荷 +0 Bytes，节表 +0 Bytes，文件其余布局 +0 Bytes。 [逐节 CSV](ELF_SIZE_COMPARISON.csv)

符号总数 764 → 764，LOCAL 454 → 454、GLOBAL 310 → 310、WEAK 0 → 0。移除的映射符号为无。涉及 0 个节，执行节类别边界变化 0 处，两侧映射符号重定位引用均为 0/0。 [完整标记与区间](evidence/elf/gcc-stripped.json)

执行节字节变化为无。SHF_ALLOC 原字节变化为无。重定位 2,352 → 2,352，原始差额无，归一化未解释差额无。SDK CRC 为 left PASS 153/153、right PASS 153/153。复核项无。 [接口、属性、布局和重定位证据](evidence/elf/gcc-stripped.json)

GNU 与 LLVM 反汇编在各自旧新对照中的规范化一致性为 [True, True]。两工具解析指令位置交集为 [16450, 16450]，交集编码冲突为 [0, 0]。助记符别名保留在两套原始日志。 [GNU 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [LLVM 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## 覆盖与复验

未执行配对 RPM 打包。文件大小结论覆盖同等后处理且 strip 后的已安装模块 ELF。

两份最终 ELF 的二进制差异按内容与布局分别复核。REL 使用站点原字节或相同重定位源节字节，RELA 核对显式 addend。可解析的合并节引用以目标记录内容和已知站点信息复核。版本 CRC 以名称与数值配对，原始表排列与 Build ID 属于已记录的元数据差异。

[一键复核](scripts/review_arm_elf.sh) · [ELF 对比脚本](scripts/compare_arm_elf.py) · [报告脚本](scripts/render_arm_elf_report.py) · [输入描述符](evidence/elf/resolved-inputs.json) · [ABI 和大小机器结果](evidence/elf/status.json)
