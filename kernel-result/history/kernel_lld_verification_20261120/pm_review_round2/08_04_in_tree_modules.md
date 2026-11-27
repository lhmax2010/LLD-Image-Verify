# 08.04 树内模块

**52/52 为 E3，0/52 为 E4。** 每个模块都有匹配的 .o、.mod.o、最终 .ko、BTF、INSTALL、STRIP、RPM 写出及完成记录。逐路径对应第一轮已解析的 ELF 清单及仓库文件和设备文件，重新读取归档文件计算的两组 SHA256 均相同。原 LLD_INDICATED 为 52，LLD_CONFIRMED 仍为 0。 [52 行逐模块矩阵](08_04_in_tree_modules.csv) · [逐条审计 JSON](evidence/kernel/in-tree-event-audit.json) · [复算输出](evidence/kernel/rule-audit.out)

- **作用域** 官方日志 3371–8156 行使用 build/arm-rpi4，匹配其下 52/52 个实际相对路径。排除有同名目标的独立 arm-rpi4-rt 区间。最终 RPM 路径由完整 release 和模块路径识别。 [日志及行号](evidence/kernel/linux-rpi-armv7l-excerpts.txt)
- **配方** 对应目录的 Kbuild/Makefile 有 obj-m 或配置为 m 的 obj-$(CONFIG_…) 条目。每个目标均有历史 .o 产出、.mod.o 编译及最终 LD [M] .ko。scripts/Makefile.modfinal 36–40、59–64 行以继承的 $(LD) -r 和 scripts/module.lds 产出 .ko，随后执行 BTF。也标为 LD [M] 的早期 .o 只记作中间合并。 [模块规则](evidence/kernel/source/scripts/Makefile.modfinal#L36) · [逐目标配置](08_04_in_tree_modules.csv)
- **覆盖和预编译** 对 52 个模块所在目录及其父目录提取 devel 的全部 Makefile/Kbuild，扫描 LD、LLVM、PATH、MAKEFLAGS 等赋值及显式 ld、ld.bfd 调用。没有模块专属的替代最终配方。从该 SRPM 的源码 tar 和九份补丁扫描相关目录中的 .o、.a、.so、.ko 及 shipped 后缀，没有相关预编译对象路径。结论范围是列出的源目录、成员名、补丁和可见最终规则。 [源码范围和哈希](evidence/kernel/kernel-source-binding.json) · [范围成员清单](evidence/kernel/raw-source-scoped-member-list.txt)
- **发布链** 14124–14235 行记录完整匹配的 52 个非 RT INSTALL、STRIP。scripts/Makefile.modinst 43–89 行选择 kernel/，INSTALL 使用 cp，INSTALL_MOD_STRIP=1 触发 strip --strip-debug。15253 行写出 arm-rpi4-linux-kernel-modules-6.12.80-0.armv7l.rpm，15275 行记录完成。与设备的 SHA256 对比基于最终 RPM payload，构建机原始未 strip 的 .ko 未留存。 [安装规则](evidence/kernel/source/scripts/Makefile.modinst#L43) · [完整日志](../evidence/build/linux-rpi-armv7l.out) · [52 行矩阵](08_04_in_tree_modules.csv)

E3 依赖逐个目标规则、实际配置、独立的非 RT 最终链接日志及模块摘要链。两种已知的 ld.lld 候选均为同版 LLD。历史完整 argv、.cmd 和实际执行路径仍未取得。结论适用于树内最终 .ko，对外置模块和各输入 .o 不作传递判定。 [规则因果链](08_03_kernel_linker_selection.md) · [两种历史可执行文件](08_06_historical_linker_resolution.md)
