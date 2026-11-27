# 08.03 内核链接器选择

**非实时 RPi4 ARMv7l 的 vmlinux、ARM decompressor、vmlinux.o 及树内模块最终链接均达到 E3。** 证据所支持的链接器家族及版本为 LLD 22.1.8。本次构建的完整 argv、实际执行路径和目标 .cmd 未取得，E4 为 0。变量展开根据对应源码及实际参数推导。 [规则矩阵](08_03_linker_rule_matrix.csv) · [原始代码、变量和日志](08_03_linker_variable_trace.json) · [链接器候选](08_06_historical_linker_resolution.md)

## Tizen 构建和源码绑定

规格文件来自该快照的 rpi4-linux-kernel-6.12.80-0.src.rpm。SPEC 第 14 行的 VCS 为 platform/kernel/linux-rpi#42aeefac58edeb081aff440f0b60be71cbe49755。SRPM 内的 SPEC、manifest 与第一轮保存的原件逐字节核对。Kbuild、ARM Makefile、.config 和 auto.conf 从同批 arm-rpi4-linux-kernel-devel-6.12.80-0.armv7l 的解包流按成员提取，保留原始行号、成员路径、偏移及 SHA256。正式日志记录同一次构建写出 SRPM、kernel RPM、modules RPM 与 devel RPM（15249、15251、15253、15255 行）。分析采用的是这份 Tizen 打补丁后的规则。 [SRPM SPEC](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [逐文件绑定](evidence/kernel/kernel-source-binding.json) · [完整官方日志](../evidence/build/linux-rpi-armv7l.out) · [原始行号的日志片段](evidence/kernel/linux-rpi-armv7l-excerpts.txt)

## 变量传递链

| 环节 | 已观察证据及静态推导 |
| --- | --- |
| SPEC 与宏展开 | SPEC 4–11、190–198 行选择 ARM 和 RPi4，并在 LLVM 工具链分支导出 LLVM=1。官方日志 1672–1681 行记录 RPM preamble 的 CC/CXX、MAKEFLAGS += -k、SPEC 的 LLVM=1 和 arm-rpi4 循环值。SPEC 228–242 行对应日志 2682、2687、3371 行的合并配置、olddefconfig 与正式 make。构建的 -j8 来自日志 10 行的 _smp_mflags。 |
| O 与递归 make | 实际非 RT 入口为日志 3371 行的 make O=build/arm-rpi4 -j8，3372 行切入对应输出目录。顶层 Makefile 180–189 行将显式 O 应用于 KBUILD_OUTPUT，223–225 行用 -C 和 -f 递归回源码 Makefile。顶层 593 行导出已选择的 LD、CC。vmlinux_o、vmlinux 与 modfinal 用各自的 -f 脚本继续。 |
| LLVM、LD、CROSS_COMPILE | 顶层 Makefile 423–428、478–495 行以 LLVM 是否非空选分支。LLVM=1 既无路径语义也无版本后缀语义，默认展开 LD=ld.lld。CROSS_COMPILE 在此处的非 LLVM 分支组成 GNU 命令名。LLVM=0 也非空，按该源码仍进入 LLVM 分支。历史正式命令未显式传 LD、CROSS_COMPILE 或 LLVM_PREFIX/SUFFIX。 |
| CC 与 LLVM_IAS | 标准 GNU make 优先级下，RPM 日志的环境 CC 会被 LLVM 分支中的 Makefile CC=clang 覆盖，命令行赋值或 -e 可改变优先级。scripts/Makefile.clang 4、15–29 行选择 ARM target。LLVM_IAS=0 只影响汇编器与 GNU 工具路径参数。匹配配置实际记录 CONFIG_CC_IS_CLANG=y、CONFIG_CLANG_VERSION=220108、CONFIG_AS_IS_LLVM=y。ARM 的四条链接路径使用 LD。 |
| 配置探测 | scripts/Kconfig.include 39–59 行检查工具并把 $(LD) 传给 ld-version.sh。脚本 22–57 行执行 --version 并区分 GNU ld、gold 和 LLD，init/Kconfig 47–61 行生成标志。归档 .config 和 auto.conf 均显示 CONFIG_LD_IS_LLD=y、CONFIG_LLD_VERSION=220108、CONFIG_LD_VERSION=0。这是当次配置阶段的探测结果。 |
| MAKEFLAGS 和覆盖条件 | preamble 添加 -k，顶层 Makefile 49 行再加 -rR。现有 quiet 日志未展开继承的完整 MAKEFLAGS、MAKEOVERRIDES、GNUMAKEFLAGS 或 PATH。GNU make 将命令行变量传给子 make。已核对的历史命令、实际配置和正常构建规则均未提供触发二次 LD override 的条件。 |
| ARM 架构 | arch/arm/Makefile 13–17、44–52 行增加链接选项及字节序。252–258、295–302 行选择 zImage 路线。对应 ARM devel 树未提供 Makefile.postlink。arch/arm/boot/compressed/Makefile 修改本目标 flags，调用继承的通用 ld 规则。 |

[顶层 Makefile](evidence/kernel/source/Makefile) · [Clang/IAS](evidence/kernel/source/scripts/Makefile.clang#L23) · [配置探测](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [LD 版本脚本](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [生成配置](evidence/kernel/source/.config#L5) · [GNU make 变量优先级](https://www.gnu.org/software/make/manual/html_node/Overriding.html) · [GNU make 递归选项](https://www.gnu.org/software/make/manual/html_node/Options_002fRecursion.html)

## 四个实际目标

| 目标 | 规则及原始代码位置 | 实际日志关联 | 产物关联 |
| --- | --- | --- | --- |
| vmlinux.o | 顶层 1161–1162，scripts/Makefile.vmlinux_o 50–65 将 vmlinux.a 与库通过 $(LD) -r 写入 $@ | 7940 行 AR vmlinux.a，7941 行 LD vmlinux.o，7942、7945 行跟随提取及 modpost | 该中间输出在同次构建的后续阶段消耗。历史 vmlinux.o 文件未保留。 |
| vmlinux | 顶层 1178–1181，scripts/Makefile.vmlinux 25–34 把 LD 和 flags 传入链接脚本。脚本 31、77–103、272 行把传入的 LD 用于 ARM 最终输出 | 7951、7958 行是临时 kallsyms 链接。7962 行是最终 LD vmlinux，随后生成 System.map | CONFIG_LTO_NONE=y 使最终输入走 vmlinux.a 和库。vmlinux 经 OBJCOPY 进入 boot Image，Task 7 关联发布及设备 notes。 |
| ARM decompressor | arch/arm/boot/Makefile 53–60 通过独立构建规则生成 compressed/vmlinux，再 OBJCOPY 到 zImage。压缩目录 Makefile 148–153 调用 if_changed,ld，scripts/Makefile.lib 333–334 执行 $(LD) $(ld_flags) | 8141 行记录 compressed/vmlinux 链接，8143、8145 行 OBJCOPY 和 zImage ready，14011 行安装，15251 行写出 kernel RPM | devel wrapper 与发布 zImage 的文件承载 SHF_ALLOC 范围经 Task 7 比对。 |
| 52 个树内 .ko | 顶层 1886–1888 调用独立 modfinal。scripts/Makefile.modfinal 36–40、59–64 行以 $(LD) -r、module.lds 和对象生成完整 .ko，再做 BTF | 每个目标均对应早期 CC/LD .o、CC .mod.o、最终 LD [M] .ko、BTF、安装和 strip | 52 条完整路径与发布 RPM 和设备 SHA256 一致。 |

[原始 vmlinux.o 配方](evidence/kernel/source/scripts/Makefile.vmlinux_o#L50) · [最终 vmlinux 配方](evidence/kernel/source/scripts/Makefile.vmlinux#L25) · [链接脚本](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [ARM 解压器](evidence/kernel/source/arch/arm/boot/compressed/Makefile#L148) · [模块 final](evidence/kernel/source/scripts/Makefile.modfinal#L36) · [逐模块](08_04_in_tree_modules.md) · [Build ID 复核](08_07_build_id_postprocessing_review.md)

## GNU BFD 路径

日志的历史构建根保留了 binutils，其已知程序名包括 ld、ld.bfd 和 target-prefixed ld 路径。实际传递的普通目标 LD 由 LLVM 分支构造为 **ld.lld**。两份匹配的历史 package payload 中，/usr/bin/ld.lld 与 /emul/usr/bin/ld.lld 分别解析到 ARM 及 x86-64 的 LLD 22.1.8 ELF，第六项审查在两者未发现 BFD wrapper。ARM 选项、目标后链接步骤和 .ko 目标 Kbuild 文件均未提供指向另一个 linker 的选择。clang 的链接特例只用于 UML，该 ARM 规则直接执行 LD。基于可绑定的构建链，GNU BFD 缺少一条合理的最终链接路线。 [历史二进制证据](08_06_historical_linker_resolution.md) · [ARM 直接执行的条件分支](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

历史 PATH 排序、完整继承变量和实际执行路径仍不可恢复。要让 BFD 与现有记录同时成立，需要另行假设配置后更换 LD 或 PATH、未记录的目标覆盖、额外的 ld.lld 同名文件或二进制替换。已核对的实际命令、Kconfig 探测、匹配 Tizen 规则和已知候选均不支持这些假设。E3 证明这条受支持的工程路径，原 LLD_CONFIRMED 和 E4 均没有变化。 [完整变量记录](08_03_linker_variable_trace.json)
