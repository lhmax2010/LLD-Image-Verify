# LLD-KERNEL-001 · kdbus 中间链接根因

**准确来源为 platform/kernel/linux-tizen-modules-source @ 25797e8af7ed95a5783bbe84c11959560aaf7e92 的顶层 Makefile 第 2 行。** 源码提供 RPM 将它安装到 /usr/src/linux-tizen-modules-source/Makefile。包装 SRPM 的 SPEC L159 将其复制到 ./kernel/Makefile，日志 L509 记录了该复制。SPEC L262 只移除特定 Clang 警告选项，保留第 2 行的 LD 赋值。 [真实 Makefile](../pm_review_round2/evidence/external/source/Makefile#L2) · [包装 SPEC](evidence/source/external/linux-tizen-modules.spec#L159) · [源 RPM 记录](evidence/source/source-rpm-pinned-row.json)

    LD = ${CROSS_COMPILE}ld

该行采用普通递归赋值 =，命中时 origin 为 file，flavor 为 recursive，展开取引用时的 CROSS_COMPILE 值。该行没有 export 或 override。顶层外部 wrapper 的 L42–49 只调用子 make，不在本层执行 LD，历史子 make argv L576 无显式 LD。它引入风险的入口是同一个文件在 **Kbuild Makefile.build 子进程中再次被 include**。 [外层配方](../pm_review_round2/evidence/external/source/Makefile#L42) · [历史递归命令](../evidence/build/linux-tizen-modules-armv7l.out#L576)

## 作用域与优先级

1. 日志 L565–566 记录 LLVM=1。SDK 的 Makefile L423–428 处理可选前后缀，L478–496 据此选取 ld.lld，L593 显式 export LD 和 CROSS_COMPILE。整个 historical PATH、原始环境变量及 make override 状态没有留存。 [目标 SDK](../pm_review_round2/evidence/kernel/source/Makefile#L478) · [历史日志](../evidence/build/linux-tizen-modules-armv7l.out#L565)
2. Makefile.build L41 include 外部 Makefile 前，LD 来自父进程的环境。普通文件赋值优先于默认环境优先级，使本作用域的变量变为递归表达式。原来从环境导入的 LD 默认继续导出，递归子 make 接收父作用域展开后的字符串。Makefile.build L484–488 进入 kdbus 子目录，L432–443 用 LD 运行组合对象链接。确切 kdbus Makefile 的 19 个对象和历史日志 L612 绑定此阶段。 [include](../pm_review_round2/evidence/kernel/source/scripts/Makefile.build#L41) · [归并规则](../pm_review_round2/evidence/kernel/source/scripts/Makefile.build#L432) · [复合对象组](evidence/source/external/kdbus/Makefile) · [GNU Make 优先级和递归](https://www.gnu.org/software/make/manual/make.html)
3. 顶层 modules 依赖 modpost，再独立启动 Makefile.modfinal（L1886–1888）。modpost 即使读取外部 Makefile，其子进程中的 LD 赋值也不回流到顶层。modfinal L9–18 读取配置、公共规则和 MODORDER，L36–40 使用继承自顶层的 LD。它没有 include 外部 Makefile，且对象构建子进程与它不是父子关系。历史 L636 绑定最终 kdbus.ko。 [两个子流程的边界](../pm_review_round2/evidence/kernel/source/Makefile#L1886) · [modpost include](../pm_review_round2/evidence/kernel/source/scripts/Makefile.modpost#L118) · [最终规则](../pm_review_round2/evidence/kernel/source/scripts/Makefile.modfinal#L36) · [历史 .ko 记录](../evidence/build/linux-tizen-modules-armv7l.out#L636)

| 赋值或输入 | 对本案的影响 |
| --- | --- |
| LD = … | 本案实际源码。默认优先级高于环境，低于命令行赋值 |
| LD := … | 立即展开且仍是普通文件赋值。仅把 = 改为 := 不消除覆盖 |
| LD ?= … | 只在 LD 未定义时赋值。对象子进程继承已有 LD，本模型中保留 ld.lld。GNU Make 内建的默认 LD 也可算作已定义 |
| override LD = … | 显式提高本地优先级。不是本案源码，亦不能从本地取值推断所有递归子进程的 argv |
| export LD | 规定对子进程的环境传递，不单独改变赋值优先级。顶层 SDK 有实际 export |
| 命令行 LD | 通常由 MAKEFLAGS/MAKEOVERRIDES 传播并压过普通赋值。单纯环境 LD 默认不能阻止覆盖。-e 是另一个优先级分支 |

## 隔离实验中的基准观测

| 作用域 | origin | flavor | value | 展开 |
| --- | --- | --- | --- | --- |
| 顶层 Kbuild 选定 LD | file | recursive | $(LLVM_PREFIX)ld.lld$(LLVM_SUFFIX) | ld.lld |
| Makefile.build include 前 | environment | recursive | ld.lld | ld.lld |
| Makefile.build include 后 | file | recursive | ${CROSS_COMPILE}ld | ld |
| kdbus 子进程的中间归并 | environment | recursive | ld | ld |
| 独立 modpost | file | recursive | ${CROSS_COMPILE}ld | ld |
| 顶层直接启动的 modfinal | environment | recursive | ld.lld | ld.lld |

历史作业保留 Make 4.4.1。独立实验使用 GNU Make 4.3，模拟 LLVM=1，取空的 CROSS_COMPILE 且没有命令行 LD。源规则、GNU Make 语义和实验相互支持，表中 origin 和展开值属于实验。 [实测输出](evidence/reproducer/historical_shape_control.out) · [完整 trace](KDBUS_LINKER_VARIABLE_TRACE.json)

历史 ARMv7l binutils 2.43-1.8 保留在作业环境，原 RPM 文件和 newc inode 验证表明 /usr/bin/ld 和 /usr/bin/ld.bfd 是同一 BFD ELF 的硬链接。若中间命令为裸 ld 且解析到该文件，GNU BFD 路径成立。带 CROSS_COMPILE 时，规则会请求对应前缀工具。实际历史前缀、PATH 和执行记录缺失，判定为 BFD_PATH_POSSIBLE。 [历史作业依赖](../evidence/build/linux-tizen-modules-armv7l.out#L437) · [历史 ld/ld.bfd](../pm_review_round2/evidence/external/historical-binutils-resolution.json) · [目标证据结果](KDBUS_HISTORICAL_INTERMEDIATE_LINK.md)

覆盖来自树外源码顶层 Makefile，因此模式可影响同一 include 作用域内任何使用 LD 的组合目标。该批其余六个目标只在此阶段编译单一对象，匹配 SDK 未启用触发单对象额外链接的 Clang LTO。本次已观测的中间归并风险定位到 kdbus.o。 [目标构建绑定](../pm_review_round2/evidence/external/target-bindings.json) · [同类检查](KERNEL_LINKER_OVERRIDE_AUDIT.md)
