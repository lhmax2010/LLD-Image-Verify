# Phase 9 · Kernel linker override 定向审计

**本轮范围内有 1 条目标链接的潜在绕过路径。它由外部模块源码 Makefile L2 引入，只能到达已识别的 kdbus.o 中间合并。** 其余命中包括标准 Kbuild 继承路径、宿主/用户态工具和非执行行。未取得可确认 BFD 实际执行的记录。 [153 行判定矩阵](KERNEL_LINKER_OVERRIDE_FINDINGS.csv) · [可复算统计](evidence/audit/findings-summary.json)

## 范围与校验

范围使用 20261120.082536 的 standard/armv7l、非 RT RPi4，匹配 kernel revision 42aeefac58edeb081aff440f0b60be71cbe49755 和外部源码 provider revision 25797e8af7ed95a5783bbe84c11959560aaf7e92。审查 72 份精确内核构建控制文件及 RPM 包装文件，覆盖 52 个树内模块的目录与父目录、ARM 解压器及共用 Kbuild。另审查 9 个从已归档精确 devel CPIO 选择性取得的宿主和用户态工具控制文件，以及外部 provider 的 3 个 Makefile 和独立包装 SPEC。85 个文件的 SHA256、devel RPM SHA256 和完整构建日志 SHA256 均已验证。 [逐文件来源和摘要](evidence/audit/source-scope.json) · [源与日志复核结果](evidence/audit/audit-source-verification.json)

仅读取原 SRPM 已持有字节，遍历 92,413 个 tar 成员头。对目标树内模块目录、ARM 解压器、脚本和工具的明示范围内 5,313 个常规源成员检查对象后缀及 ELF、普通和薄 ar、LLVM bitcode 魔数；对象名的软链接和硬链接也进入候选检测。九份 Tizen 补丁按原 SHA256 核对，筛查作用域内新增的构建控制行，并复核不存在该范围的对象样式改动或二进制 diff marker。外部 provider 55 个包成员及包装 Source0 的 16 个常规文件沿用已封存的对象/归档魔数审查。上述范围内没有预编译对象候选；已发布的 .ko、包内生成的 devel 构建输出和未进入目标构建的其他架构源码不计入该检查。 [原 SRPM 检查范围](evidence/audit/source-object-magic.json) · [补丁控制行](evidence/audit/patch-control-lines.json) · [补丁及外部输入校验](evidence/audit/audit-source-verification.json)

## 判定结果

| 分类 | 条数 | 含义 |
| --- | ---: | --- |
| CONFIRMED_BYPASS | 0 | 需要历史执行身份与受影响的目标绑定 |
| POTENTIAL_BYPASS | 1 | 已有匹配源码、目标规则、日志和 GNU linker 候选支持一条可达路径 |
| SAFE_INHERITANCE | 56 | 该规则透传选定 linker，或使用它执行明确范围的链接 |
| EXPECTED_HOST_TOOL | 26 | 构建期宿主程序和它们的库 |
| FALSE_POSITIVE | 70 | 注释、探测、数据嵌入、非本目标分支及独立用户态工具 |
| 合计 | 153 | 每个源文件逻辑行或补丁新增行单列，同行多个模式合并 |

| 搜索模式 | 候选数 | 如何判定 |
| --- | ---: | --- |
| 显式 ld.bfd | 0 | 目标构建源码无直接拼写命中。历史 binutils 本身提供该文件，作为解析证据单列 |
| 裸 ld 候选 | 12 | 含普通 GNU 分支、宿主默认值、版本探测文字和外部源码覆盖。单凭词法无法识别实际执行 |
| CROSS_COMPILE 后接 ld | 4 | 顶层非 LLVM 分支、工具支持库、独立工具选择和外部源码覆盖均可见 |
| LD 赋值、导出或 allow-override 调用 | 19 | 检查赋值发生的 Make 实例、作用域和后续规则 |
| ld/LD 的 relocatable -r | 6 | 分别识别 vmlinux.o、最终 .ko、通用对象合并以及工具对象合并 |
| 硬编码 linker 路径 | 0 | 已列控制文件无字面绝对 linker 路径。历史构建 PATH 和 execve 仍未留存 |
| 预编译对象文本候选 | 1 | Makefile.lib L386–397 的 incbin 包装生成的 DTB 数据；归档魔数扫描无对象候选 |
| 递归 Make 和工具链传递 | 111 | 含实际调用、工具子树和示例。核对 M=、LLVM、MAKEFLAGS 和 LD 入口 |
| 编译器 driver 选择及共用链接规则 | 1 / 18 | --ld-path 使用当前 LD，常规链接配方也需要追到消费的变量 |

模式计数重叠。CSV 保留前后行号、原始逻辑行、来源、目标和逐行理由。 [原始候选](evidence/audit/raw-candidates.csv) · [判定矩阵](KERNEL_LINKER_OVERRIDE_FINDINGS.csv)

## 关键命中及非等价路径

- **kdbus.o · POTENTIAL_BYPASS。** 外部源码 provider 的 Makefile L2 保存原文 LD = ${CROSS_COMPILE}ld。Makefile.build L41 读取该文件，L485 将工具值带入子目录，L433 以当前 LD 执行 composite -r。日志 L612 对应 kdbus/kdbus.o，已保留的历史 ARM binutils RPM 证实裸 ld 和 ld.bfd 是一个 GNU BFD ELF 的名称。真实 PATH、展开 argv 及执行文件缺失。L636 对应单独的 modfinal 过程和 kdbus.ko。 [外部 Makefile](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [对象规则](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [已绑定日志](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [历史 linker 命名空间](evidence/audit/audit-source-verification.json)
- **内核 target 工具链。** 顶层 Makefile L478–489 的 GNU ld 分支用于 LLVM 为空时。本次展开日志先设置 LLVM=1，非 RT 构建进入 L480 的 ld.lld 选择，L593 继续导出。vmlinux.o、常规 ARM 的 vmlinux 和解压器、最终 .ko 都消费相应继承值。Makefile.build L156 的单对象 LLVM 转换仅在 CONFIG_LTO_CLANG 条件下运行，本次 SDK 的 auto.conf 记录 CONFIG_LTO_NONE=y。未发现另一条能够到达本次内核或模块语义范围的 linker override。 [顶层选择](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [ARM 规则](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [配置](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
- **宿主工具的 LD 解析。** resolve_btfids 的 Makefile L21–26 允许宿主默认 HOSTLD ?= ld，并把它作为自身 libbpf/libsubcmd 子任务的 LD。内核日志同时记录 HOSTLD、DESCEND 和 libsubcmd-in.o；具体历史 HOSTLD 实际程序仍未知。这些构建工具和引入目标 ELF 的 Kbuild 链接流程有不同的 LD 作用域。bpftool bootstrap 使用类似的宿主参数。 [resolve_btfids Makefile](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [bpftool Makefile](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [已绑定日志](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
- **独立 userspace 和数据规则。** 内核 RPM SPEC L235 在进入主要内核 make 前单独运行 perf。tools/perf/Makefile.perf L191 扩展的是 perf 的 LD flags；tools/build/Makefile.build 有供这些工具使用的 -r。Makefile.lib 中 incbin 是 DTC 生成的数据。以上命中未达本次 target linker。 [包装入口](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [perf 规则](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [设备树规则](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## 扩展到 Tizen RPM

建议按发布快照分批处理已归档的 source RPM、宏/依赖和成功构建日志。先静态枚举 linker 选择、带作用域的变量赋值、driver 参数和二进制输入，再由实际展开的架构分支、递归进程边、provider 和目标产物缩小候选。宿主工具和独立用户态程序单列；预编译对象需绑定到消费者和链接输入。对活跃的潜在绕过取得同一构建的实际 executable、argv 和对象摘要再提升为 CONFIRMED_BYPASS。此办法可增量索引新增或改变的源 RPM 并复用相同 SHA256 的源码范围，避免用 grep 命中直接推断迁移覆盖率。

## 复跑

在本报告目录运行以下命令复算已绑定副本。仅使用轻量证据包即可完成此次候选重分类。

    PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/audit_linker_overrides.py --reuse-scan

加入原归档后可重新抽取控制文件、验证精确 RPM 和日志、复查静态候选。输出限于本轮目录。

    PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/audit_linker_overrides.py --base ..
    PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/verify_linker_audit_sources.py --base ..

[扫描脚本](scripts/audit_linker_overrides.py) · [来源验证脚本](scripts/verify_linker_audit_sources.py) · [归档抽取和对象扫描回执](evidence/audit/source-scan.cmd.json) · [候选判定输出](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [85 文件校验输出](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

已在独立临时目录用原归档重新执行完整定向扫描和来源校验，判定矩阵、输入范围、魔数和补丁数据、统计、来源校验与日志摘录共 7 个结果逐字节一致。 [隔离复跑输出](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [命令回执](evidence/audit/replay-audit.cmd.json)
