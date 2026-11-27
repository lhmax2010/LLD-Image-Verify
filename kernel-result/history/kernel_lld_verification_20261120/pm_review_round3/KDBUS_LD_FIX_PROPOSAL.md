# LLD-KERNEL-001 · kdbus LD 修复候选

**推荐 Option A。** 删除 `platform/kernel/linux-tizen-modules-source` 的顶层 `Makefile:2` 一行，让对象构建沿用目标 SDK 的 Kbuild 链接器。候选针对源码提供项目的 revision `25797e8af7ed95a5783bbe84c11959560aaf7e92`，来自与目标构建匹配的 `linux-tizen-modules-source-11.0.0-0.armv7l.rpm`。打包项目 `platform/kernel/linux-tizen-modules` 的 SPEC `L159` 将该来源复制到 `./kernel`。 [候选补丁](KDBUS_LD_FIX_CANDIDATE.patch) · [原始 Makefile](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [源码、SPEC、日志和 manifest 行号](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## 为什么一行足够

真实赋值是 `LD = ${CROSS_COMPILE}ld`。源码顶层 `Makefile:42–49` 的三个独立入口只递归调用目标内核的 `modules`、`modules_install`、`clean`，未直接引用 `LD`。对象构建的 `scripts/Makefile.build:41` 则包含整个外部 Makefile。在 GNU Make 默认优先级下，普通文件赋值覆盖从顶层 Kbuild `Makefile:593` 导出的环境 `LD`，该变量继续传给下层递归对象构建。`kdbus/Makefile:1–22` 定义 19 个组成对象，`scripts/Makefile.build:432–443` 用实际有效的 `$(LD) ... -r` 合并 `kdbus.o`。 [编号源码](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [GNU Make 环境变量优先级](https://www.gnu.org/software/make/manual/html_node/Environment.html) · [GNU Make 递归变量](https://www.gnu.org/software/make/manual/html_node/Variables_002fRecursion.html)

SDK 顶层 `Makefile:423–428,478–495` 在非空 `LLVM` 下选择 `$(LLVM_PREFIX)ld.lld$(LLVM_SUFFIX)`，在空 `LLVM` 下选择 `$(CROSS_COMPILE)ld`。`LLVM=0` 在这份 Makefile 中仍是非空。保留顶层选择可兼容路径前缀、版本后缀和调用方在命令行显式设置的 `LD`。最终 `kdbus.ko` 由顶层 `Makefile:1886–1888` 另起的 `scripts/Makefile.modfinal:36–40` 链接，独立收取顶层导出的 `LD`。 [SDK 规则与日志 L612/L636](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [GNU Make 命令行优先级](https://www.gnu.org/software/make/manual/html_node/Overriding.html)

## 四种方案

| 方案和优先级 | 修改位置及规模 | 递归与独立外部模块行为 | 主要回归风险 |
| --- | --- | --- | --- |
| **A · 首选** 删除外部源中的 `LD` 赋值 | 实现源码顶层 `Makefile:2`，删除 1 行 | 对象子 make 继承 SDK `LD`，最终子 make 和独立 `make KERNELDIR=…` 的 goals、参数及安装行为维持现有规则 | 低。所有使用该共享外部源码的合成对象将采用各自 SDK 已选的 linker。任何依赖原隐式覆盖的调用方应改用明确、受支持的工具参数 |
| **B · 低优先级** 把现有赋值限制在空 `LLVM` | 同一位置新增两行条件护栏，保留原赋值。条件形如 `ifeq ($(LLVM),)` … `endif` | 非空 LLVM 使用继承值。空 LLVM 的对象 make 仍重算前缀，两个递归链接阶段有再次分离的可能 | 中。让项目继续维护一套重复工具选择规则。仅按 `LLVM=1` 分支还会漏掉路径或后缀模式。这个方案限定为保留原 GNU 兼容路径的备选 |
| **C · 应急备选** 由 RPM 入口显式传 `LD` | 包装项目 SPEC `L267、L271` 至少改两个构建调用。另需约 2–4 行表达受支持的工具策略。统一传给 clean 和 install 时修改全部 6 个 RPi4 调用 | 写成 make 命令行变量，通过 `MAKEFLAGS` 传至递归流程，优先于普通赋值。只在 RPM `%build` 中 export 一个环境变量不足以抵消外部赋值。独立模块使用者没有自动收到包级规则 | 中。包内外默认行为继续分叉。硬编码 `ld.lld` 会绕过 SDK 的前缀、后缀和混合模式选择，值必须来自明确的包工具策略 |
| **D · 结构性备选** 把 Kbuild 声明移到独立 `Kbuild` | 源码两文件。示例拆法保留 L1、空行和 L42–49，删除原 Makefile 39 行，在新 `Kbuild` 增加 L4–40 的 37 行，不迁移 LD。另改打包 SPEC 两处 `find ... -name Makefile` | 当前 SDK 的 `Kbuild.include:65` 优先选择 `Kbuild`。外层保留独立 goals，内部继承 SDK linker。需要同时更新旧 SDK 兼容验证和打包流程 | 中。移动编译标志后，原 SPEC `L234、L262` 对 `Makefile` 的 Clang 参数清理会漏掉新 `Kbuild`。这个选项适合随后整理共享构建文件 |

## 工具链和平台兼容性

| 方案 | GCC + GNU | Clang + GNU BFD | Clang + LLD | ARMv7l、AArch64 与 `CROSS_COMPILE` |
| --- | --- | --- | --- | --- |
| A | 空 `LLVM` 下沿用 SDK 的 `$(CROSS_COMPILE)ld`，普通 GNU 路径与原设置相同 | 保留调用方有效的命令行 `LD=<GNU BFD>`，例如采用 LLVM 工具集并显式选择 GNU 链接器。最终和中间阶段使用同一选择 | 保留 `LLVM=1`、目录、版本后缀以及显式 LLD 路径 | 对两种架构交由各自 SDK 选工具。GNU 仍使用前缀。全 LLVM 分支不自行给 LLD 再加 GNU 前缀。Clang 外部汇编按 SDK 的 `LLVM_IAS=0` 分支继续使用工具前缀 |
| B | 保留原源码的 GNU 前缀式赋值 | 显式命令行 `LD` 优先。空 LLVM 场景中的环境值可能在对象 make 被覆盖 | 若条件正确识别空值与非空值，则保留顶层 LLD 选择 | 仍要解释每个 SDK 导出值与源码重算 `CROSS_COMPILE` 的差异。未来 Kbuild 逻辑变化可能使两者分叉 |
| C | 包装层须明确尊重 GCC 的 GNU 工具选择 | 包装层须能选择实际目标 GNU BFD，否则可能强制成 LLD | 包装层须传入 SDK 对应的名称、前缀或完整路径 | ARMv7l 与 AArch64 必须分别解析工具值并贯穿各自构建调用。只写常量或只追加一个 GNU 前缀的覆盖风险较大 |
| D | Kbuild 拆分完整后同 A | 同 A，显式选项保持有效 | 同 A，同时要更新 SPEC 的 Clang 参数清理目标 | 双架构及各共享模块都需确认外部入口、声明和参数保持兼容。核对旧 SDK 的 Kbuild 优先级 |

匹配 SPEC `L245–272` 对 RPi4 覆盖 ARM 和 AArch64，选用架构对应的 SDK 目录，包含 non-RT 与 RT 并开启 `BUILD_kdbus=m`。其他 AArch64 板卡分支将 `BUILD_kdbus=n`，但仍共用这份源 Makefile。本次结论来自封存的 ARMv7l 非 RT SDK，AArch64 和其他 SDK 的兼容性是源码评估。混合 toolchain 仍需满足各自 SDK 的配置、ABI、BTF 和链接选项。 [实际 SPEC 与 SDK 选项](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## 验证和 PM 决策

候选 patch 已在有 Round 2 SHA256 绑定的原 Makefile 独立副本上执行 `patch --dry-run --batch --fuzz=0 -p1`，退出 0，无 offset 或 fuzz，副本前后 SHA256 相同。补丁仅用于评审。 [dry-run 输出](evidence/fix-proposal/patch-dry-run.out) · [工具、输入/输出摘要和退出状态](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [候选生成与 dry-run 脚本](scripts/verify_kdbus_candidate.py)

当前工程关闭和修复评审不需要单独重编 kdbus。若 PM 决定继续做产品回归，优先把候选交给源码提供项目，在下一次正常构建同时保留复合对象和最终模块的链接实录。独立复验优先检查 ARMv7l Clang+LLD，再按实际受支持的平台和配置验证 AArch64、GNU 与显式 Clang+BFD 流程，并核对独立外部模块入口。实际构建结果可证明新运行的行为，20261120 历史中间链接依然需要该次原作业的证据。
