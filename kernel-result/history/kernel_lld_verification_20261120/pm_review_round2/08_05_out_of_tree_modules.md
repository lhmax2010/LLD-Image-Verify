# 08.05 · 树外模块最终链接验证

**树外 7/7 个最终 .ko 达到 E3 ENGINEERING_VERIFIED。原有分类保留 7 个 LLD_INDICATED、0 个 LLD_CONFIRMED。** 树外源码的 LD 覆盖作用于对象构建及其递归子进程。kdbus.o 中间组合链接存在历史 GNU BFD 工具产物可佐证的执行路径，实际使用的中间链接器未知。最终 kdbus.ko 与其他六个最终产物共用独立的 Kbuild 最终链接路径。 [逐模块矩阵](08_05_out_of_tree_modules.csv) · [原始构建日志](../evidence/build/linux-tizen-modules-armv7l.out)

## 输入和构建关联

- 目标二进制 RPM 为 linux-tizen-modules-rpi4-11.0.0-0.armv7l.rpm，Source RPM 为 linux-tizen-modules-11.0.0-0.src.rpm。其 SPEC 和发布 manifest 均记录 platform/kernel/linux-tizen-modules 的 458baad02d812098938663971d1b8560a4813375。%prep 将独立的 /usr/src/linux-tizen-modules-source 复制到 ./kernel。实际日志 L358、L477 和 L509 依次记录依赖进入构建、安装和复制。 [SPEC](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [manifest 绑定与日志行](evidence/external/target-bindings.json)
- 本轮补取固定快照的 ARMv7l linux-tizen-modules-source-11.0.0-0.armv7l.rpm，SHA256 为 b8fdab693b2a21fb263ae9e24c5eb14e20097e12ee4a71681ff8edb8aa93f6b9。RPM VCS 与发布 manifest L488 一致，实际源码修订为 25797e8af7ed95a5783bbe84c11959560aaf7e92。发布的 provider 构建日志 L772 写出同名包。RPM header、payload 摘要及归档 primary/filelists 均已核验。 [provider 校验回执](evidence/external/source-provider-rpm-digests.out) · [provider 发布日志](evidence/external/source-provider-buildlog.out) · [源码内容清单](evidence/external/source-content-inventory.json)
- 检查了源码 provider CPIO 的 55 个成员和包装 SRPM 自有 Source0 的 16 个常规文件。按对象文件后缀及 ELF、普通和薄 ar、LLVM bitcode、嵌套压缩归档魔数检查，未见预编译对象。六个简单对象的 .c 和 kdbus 的 19 个 .c 都有同一次非 RT 构建的独立 CC [M] 记录。 [源码内容检查](evidence/external/source-content-inventory.json) · [编译条目](evidence/external/target-bindings.json)

## LD 传播与覆盖范围

1. **SPEC 到递归入口。** 非 RT RPi4 SPEC L245–268 选 BUILD_*=m，历史日志 L549–566 展开这些设置和 export LLVM=1。L531–538 记录宏导出的 AR=llvm-ar、带 ARM 前缀的 Clang CC/CXX 和 MAKEFLAGS+= -k。-k 继续其他目标，变量优先级不受影响。本日志未保存原有完整 MAKEFLAGS、GNUMAKEFLAGS、MAKEFILES 或 shell PATH。L574–576 的外层及子 make 传 KERNELDIR、M、CFLAGS_MODULE 和 modules，观察到的 argv 无 LD 或 CROSS_COMPILE 显式赋值。INSTALL_MOD_STRIP=1 出现在后续安装路径。 [实际日志 L531–577](../evidence/build/linux-tizen-modules-armv7l.out#L531) · [外层 Makefile](evidence/external/source/Makefile#L42)
2. **SDK 顶层选择。** 日志 L485 安装 arm-rpi4-linux-kernel-devel-6.12.80-0，L576 进入该非 RT SDK。M 设置 KBUILD_EXTMOD（顶层 Makefile L131–148）。LLVM=1 是非空，且不提供路径前缀或版本后缀（L423–428）。按标准 GNU Make 优先级，顶层 Makefile L478–489 选择 LD=ld.lld 与 CC=clang，L593 将两者导出给其直接子进程。Makefile.clang 使用 CROSS_COMPILE 和 LLVM_IAS=0 选择目标参数及汇编实现。ARM Makefile 调整端序和架构 flag。两处源码都未覆盖该最终 LD。 [SDK Makefile](evidence/kernel/source/Makefile#L478) · [ARM Makefile](evidence/kernel/source/arch/arm/Makefile) · [Makefile.clang](evidence/kernel/source/scripts/Makefile.clang)
3. **对象阶段的实际源码覆盖。** 外部源码顶层 Makefile L2 明确将 LD 赋值为 CROSS_COMPILE 加 ld。它没有显式导出，也没有在 L42–43 的包装 make 命令中传参。SDK 启动独立对象构建子进程 scripts/Makefile.build，该进程从环境读到顶层导出的 LD，随后在 L41 通过 include $(kbuild-file) 读取外部 Makefile。GNU Make 的默认优先级允许普通文件赋值覆盖环境值，并继续向下导出最初来自环境的变量。kdbus 子进程沿 L484–488 取得 LD，cmd_ld_multi_m（L432–443）对应 L612 的 LD [M] …/kernel/kdbus/kdbus.o。CROSS_COMPILE 为空时静态展开为 ld。准确历史环境取值未保存。 [外部 Makefile](evidence/external/source/Makefile#L2) · [Kbuild.include](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [Makefile.build](evidence/kernel/source/scripts/Makefile.build#L432) · [GNU Make 变量递归](https://www.gnu.org/software/make/manual/html_node/Variables_002fRecursion.html)
4. **中间 GNU BFD 候选。** L437 记录历史环境保留 binutils-2.43-1.8。对应 ARMv7l RPM 的 header 和 newc 数据表明 /usr/bin/ld 与 /usr/bin/ld.bfd 是同一 inode 的硬链接。其 ELF32 ARM 内容 SHA256 同为 d3fbf8e82e019182675ec373a7af8c046743fde5c00294441f34392a3dd28af9，含 GNU Binutils 2.43 字符串。若历史的中间命令解析到该已存在的 ld，kdbus.o 会使用 GNU BFD。六个简单模块直接从单一 .c 生成 .o，同构建 SDK 的 CONFIG_LTO_NONE=y，CONFIG_LTO_CLANG 未启用，Makefile.build L151–162 的单对象额外链接因而不生效。 [binutils 硬链接证据](evidence/external/historical-binutils-resolution.json) · [对象和最终链接 L612、L636](../evidence/build/linux-tizen-modules-armv7l.out#L612)
5. **最终 .ko 独立进程。** SDK 顶层 modules 在 modpost 完成后直接以 $(MAKE) -f $(srctree)/scripts/Makefile.modfinal 启动最终链接（L1886–1888）。独立的 modpost 子进程会读取外部 Makefile（L118），其执行规则 L133–141 使用 MODPOST，子进程的变量修改止于自身。modfinal 读 auto.conf、Kbuild.include 和 Makefile.lib（L9–13），以 MODORDER 构建 %.ko，执行 $(LD) -r … -T scripts/module.lds -o …（L36–40、L59–63）。该进程没有再次读取外部 Makefile。源码中无预存 .cmd，历史构建前也执行了 clean。SDK 的 CONFIG_LD_IS_LLD=y 提供配套佐证，本次独立树外构建的 LLVM 值有自身日志记录。 [顶层规则](evidence/kernel/source/Makefile#L1886) · [modpost](evidence/kernel/source/scripts/Makefile.modpost#L118) · [modfinal](evidence/kernel/source/scripts/Makefile.modfinal#L36)
6. **工程判定。** 七条最终 LD [M] … .ko 都落在非 RT 构建块，且各有同路径 BTF、INSTALL、STRIP、打包复制和写出包证据。已核验两种已知历史 ld.lld 候选都解析到实际 LLD 22.1.8。观察到的构建参数和最终规则没有提供通过 MAKEFLAGS 的 LD 赋值、make -e、MAKEFILES 或其他覆写路径。源码中的 BFD 候选仅在独立对象构建流程能到达链接规则。历史实际绝对路径、完整环境和最终链接 argv 缺失，因此保留 E3 与 LLD_INDICATED。 [全部事件与 SHA256 关联](evidence/external/target-bindings.json)

## 七个目标

| 模块 | 源码来源 | 最终 LD [M] 行 | INSTALL 行 | Evidence Level |
| --- | --- | --- | --- | --- |
| dm_bow | dm-bow.c | 621 | 647 | E3 |
| extcon_usb_fixed | extcon-usb-fixed.c | 624 | 649 | E3 |
| inform_reboot | inform-reboot.c | 627 | 651 | E3 |
| kdbus | kdbus/Makefile L1–22 选择的 19 个源码对象 | 636 | 657 | E3 |
| logger | logger.c | 630 | 653 | E3 |
| proc_tsm | proc-tsm.c | 633 | 655 | E3 |
| zlogger | zlogger/zlogger.c | 639 | 659 | E3 |

七个目标都满足源码 → CC [M] → LD [M] → INSTALL → SPEC L458–464 → RPM 逐文件 digest → 解出的 payload → 归档设备文件 SHA256 一致。kdbus.o L612 单列为中间对象，模块最终验收引用 kdbus.ko L636。L664 起的 RPi4 RT 构建属于另一输出路径。 [逐模块证据和工程理由](08_05_out_of_tree_modules.csv)

完整历史外部构建日志位于第一轮 evidence/build/linux-tizen-modules-armv7l.out，SHA256 为 41163ea6c43b4f04f1dfcdb4c0997e5d1cb2149f3e14a6c1bf57f65771061b83。本轮保留等字节副本和带原行号的重点片段。复算脚本只读分析归档和现有源码，历史 binutils 项支持用精确 RPM 选择性复算。 [完整日志](../evidence/build/linux-tizen-modules-armv7l.out) · [带行号片段](evidence/external/external-buildlog-lines.txt) · [复算脚本](scripts/inspect_external_payloads.py)
