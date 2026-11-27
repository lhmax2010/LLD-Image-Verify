# Tizen Kernel LLD Migration · PM Review Round 2

**严格验收总体仍为 CONDITIONAL_PASS。按 PM 提议的最终链接工程条件，Gate B 和 D 均为 PASS。** 目标为 tizen-unified-toolchain_20261120.082536 的 Raspberry Pi 4 ARMv7l 非 RT 内核。主内核和 ARM 解压器最终链接为 E3，52 个树内与 7 个树外最终 .ko 均为 E3。没有取得历史 E4。建议 PM 批准所列最终链接范围的工程关闭，保留严格验收的直接执行缺口，并单独跟踪树外 kdbus.o 中间合并的链接器。最终关闭由 PM 决定。

## 审阅问题处理结果

| 问题 | 本轮结果 |
| --- | --- |
| 第一轮证据能否复算 | 原归档 1,937 项 SHA256、497 条回执通过。完整离线复跑退出 0，四份关键输出 SHA256 与第一轮一致。59 条发布与设备模块字节链、11 个运行 Build ID 独立复核通过。 [完整性审计](08_01_evidence_integrity_review.md) |
| 历史命令能否取回 | HISTORICAL_EXECUTION_EVIDENCE_UNAVAILABLE。公开成功日志、生成配置、Build Root 元数据和工具依赖可追溯。有限搜索未取得该构建的原 .cmd、完整 argv、历史 PATH 或 execve 路径。 [搜索范围及结果](08_02_historical_evidence_recovery.md) |
| 具体可能使用哪个链接器 | 历史原生 ARM ELF 和加速 x86-64 ELF 均解析为 LLD 22.1.8。实际绝对执行路径仍未识别。历史 binutils 的 ld/ld.bfd 支持下述中间阶段例外。 [历史可执行文件](08_06_historical_linker_resolution.md) |
| Build ID 是否能解释 | 历史 RPM 宏用 VERSION-RELEASE 形成 seed，真实日志执行 debugedit 流程。映射到 raw Image 的 32 个主 ELF 段只有 .notes 内 20 字节不同，完整 84 字节 runtime notes 匹配，两组 debuglink CRC 正确。 [段与后处理](08_07_build_id_postprocessing_review.md) |
| 身份 Exact 的范围 | zImage 文件、notes 和 59 个模块文件是 EXACT_MATCH。发布内核到当前运行身份整体为 STRONG_MATCH。设备启动文件和活动 RPM DB 仍为 UNVERIFIABLE。 [六项身份关系](08_09_identity_review.md) |

## 连接最终链接证据

| 目标 | 证据等级 | 有效 linker | 范围 | 
| --- | --- | --- | --- | 
| vmlinux.o | E3 | LLD 22.1.8 | relocatable kernel object | 
| vmlinux | E3 | LLD 22.1.8 | kernel final ELF | 
| arch/arm/boot/compressed/vmlinux | E3 | LLD 22.1.8 | ARM decompressor final ELF | 
| 52 in-tree .ko | E3 | LLD 22.1.8 | module final relocatables | 

主内核源自匹配的 Tizen SRPM/SPEC 和开发包中实际使用的 Kbuild。观测到的 LLVM=1、无显式 LD 覆盖的非 RT make 调用、配置探测、源码规则、四类成功 quiet 目标以及产物提供最终链接闭环。已知两种历史 ld.lld 解析均落到同版本 LLD。通过匹配配置、构建参数、实际递归路径和 RPM 结果，没有找到这些最终链接的合理 GNU BFD 路径。剩余的不确定性是未留存的原始执行路径及参数。 [内核变量传递](08_03_kernel_linker_selection.md) · [52 行树内模块](08_04_in_tree_modules.csv)

7 个树外模块用单独的打包 SPEC、独立的源码提供 RPM 和自己的构建日志。源码包装 Makefile 的 LD 赋值会进入 Makefile.build 对象构建作用域。kdbus/kdbus.o 的中间合并存在 GNU BFD 合理路径，历史 ARM binutils RPM 中的 ld 与 ld.bfd 经包记录和 inode 比对指向同一个 BFD ELF。kdbus.ko 的最终链接在顶层 Kbuild 单独启动的 Makefile.modfinal 子流程中，和同批另外六个最终 .ko 使用顶层选择的 ld.lld。中间合并的实际 executable 无法确认。 [树外作用域和全部 7 模块](08_05_out_of_tree_modules.md) · [树外矩阵](08_05_out_of_tree_modules.csv)

## 模块覆盖率

| 指标 | 仓库模块 | 设备模块 | 树内模块 | 树外模块 | 
| --- | --- | --- | --- | --- | 
| Original Confirmed LLD Coverage | 0/59（0%） | 0/59（0%） | 0/52（0%） | 0/7（0%） | 
| Original LLD Evidence Coverage | 59/59（100%） | 59/59（100%） | 52/52（100%） | 7/7（100%） | 
| E4 Direct Execution Coverage | 0/59（0%） | 0/59（0%） | 0/52（0%） | 0/7（0%） | 
| E3 Engineering Verified Coverage | 59/59（100%） | 59/59（100%） | 52/52（100%） | 7/7（100%） | 
| E3 + E4 Engineering Acceptance Coverage | 59/59（100%） | 59/59（100%） | 52/52（100%） | 7/7（100%） | 

E1、E2 和 UNKNOWN 在两组最终模块中均为 0。每个 E3 有自己的构建和安装路径、RPM 写出日志、payload 与设备 SHA256 和规则推导理由。旧分类在仓库与设备两边均为 59/59 LLD_INDICATED 和 0/59 LLD_CONFIRMED。两边 59/59 ELF 解析通过，59/59 文件匹配。未发现已确认的 BFD Module。 [59 行证据](MODULE_LINKER_EVIDENCE_MATRIX.csv) · [等级定义与分母](08_08_evidence_levels.md)

## 严格与工程验收

| Gate | 严格验收 | 工程验收 | 依据 | 
| --- | --- | --- | --- | 
| A | PASS | PASS | 认可独立采集的目标设备、Clang 22.1.8 / LLD 22.1.8 banner。 [查看](../01_runtime_kernel.md) | 
| B | CONDITIONAL_PASS | PASS | 主内核和 ARM 解压器最终链接均达到 E3。无实录 argv 或 .cmd。 [查看](08_03_linker_rule_matrix.csv) | 
| C | PASS | PASS | 发布内核到运行内核为 STRONG_MATCH，独立 notes 与模块文件为 EXACT_MATCH。保留设备卷和 RPM DB 限制。 [查看](08_09_identity_review.md) | 
| D | CONDITIONAL_PASS | PASS | 59 个最终 .ko 的发布/设备摘要、解析和证据闭环。kdbus.o 独立中间步骤有合理 BFD 候选。 [查看](MODULE_LINKER_EVIDENCE_MATRIX.csv) | 
| E | PASS | PASS | 第一轮归档验证、离线复跑、独立日志和装载 notes 核查通过。 [查看](08_01_evidence_integrity_review.md) | 

审阅应优先确认工程关闭是否只覆盖主内核、ARM 解压器及最终 .ko。若目标进一步要求所有中间链接也使用 LLD，现有 kdbus.o 证据仍需原作业的命令记录，或由 PM 决定其处理方式。发布签名可用性、设备启动文件 SHA256 和活动 RPM DB 均沿用已记录限制。本轮未重新编译、刷机、重启或联系设备。 [证据索引与复跑](PM_REVIEW_EVIDENCE_INDEX.md)
