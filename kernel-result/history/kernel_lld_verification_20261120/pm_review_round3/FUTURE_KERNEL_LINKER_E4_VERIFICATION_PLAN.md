# 下一次正常构建的 E4 取证计划

目标是在一次可归因的正常构建中，对主内核、ARM 包装器和模块按目标记录**实际成功执行的链接器、参数和输出**。优先验证 kdbus/kdbus.o 与 kdbus/kdbus.ko 两条独立事件。新构建只能证明自身，20261120 的历史证据等级维持原判。

| 证据 | 采集点 | 用途和限制 |
| --- | --- | --- |
| V=1 日志 | RPM %build 的实际 make 调用，保留相同架构、构建根、LLVM 及其他参数 | 保存展开的 recipe 和时序。单凭名字为 ld 或 ld.lld 的命令无法识别实际文件。 [Kbuild 文档](https://docs.kernel.org/6.12/kbuild/kbuild.html) |
| 目标 .cmd 及响应文件 | 链接后、SDK rsync 排除和清理前，从对象构建树保留当前作业的 .cmd | 关联目标与完整 recipe。记录时间和 SHA256，区分缓存命中和本次执行。kdbus.mod 等响应文件保存实际内容、路径和摘要。 [Kbuild 保存命令的规则](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |
| 有效变量和查找上下文 | 同一次构建的顶层、实际调用链接器的子进程 | 记录 LD、CC、LLVM、LLVM_IAS、CROSS_COMPILE、MAKEFLAGS、MAKEOVERRIDES、PATH、cwd、容器和 rootfs 标识。保留 Make 的 origin、flavor。PATH 的静态解析用于交叉核对。 |
| 实际成功 exec | 构建进程树内限定 execve/execveat，或 runner 已授权的等效 exec 记录 | 保存时间、进程和父链、命名空间、cwd、被解析路径、原始 argv、调用返回和进程退出码。区分 ENOENT 等失败尝试与成功启动。 |
| 链接器文件、版本及 NEVRA | 实际 build root 内确认执行的 ELF 及解释器或 wrapper 链 | 用执行时的已打开文件对象，或等效的不可变构建根，核对 inode/设备号及实际 ELF SHA256。记录 symlink 目标、包装器摘要、工具 RPM NEVRA、RPM 的 SHA256 和版本报告。command -v 的解析记录作为补充。 |
| 输出和打包关系 | 每个 link 后，strip/BTF、签名或压缩前后，以及最终 RPM | 保存链接 argv 的输出路径、文件 SHA256 和 GNU Build ID。给文件变化步骤记录输入输出摘要，最终核对 RPM 成员路径及 SHA256。 |

目标表至少包含中间 kdbus/kdbus.o、最终 kdbus/kdbus.ko。在有完整内核构建的作业追加 vmlinux.o、最终 vmlinux、arch/arm/boot/compressed/vmlinux 及交付模块。常见记录路径分别为 kdbus/.kdbus.o.cmd、kdbus/.kdbus.ko.cmd、.vmlinux.o.cmd、.vmlinux.cmd 和 arch/arm/boot/compressed/.vmlinux.cmd。以目标真实对象目录为准。 [中间规则](../pm_review_round2/evidence/kernel/source/scripts/Makefile.build#L432) · [最终规则及保存命令](../pm_review_round2/evidence/kernel/source/scripts/Makefile.modfinal#L36)

## 执行与验收顺序

1. 在下一次计划内且获准采集的构建中记录作业 ID、Tizen 快照、架构、源提交、源和 devel RPM 摘要、Kbuild 配置、工具包 manifest 与采集器版本。使用新输出目录，确认 kdbus 目标确实生成实际链接事件。
2. runner 具备所需权限时，只观测指定构建进程树的 exec。采用 strace 可从 -f 和限定 execve、execveat 开始，保留时间戳和完整参数，检测参数截断，同时保留进程退出。对并行构建按 PID、父链和目标路径配对。等效的 runner 事件采集器需提供相同字段及采集完整性。
3. 在 exec-stop 或其他可靠时点把成功执行的文件绑定到构建命名空间。存在 RBS binfmt/QEMU 或 wrapper 时，记录启动入口、解释器与执行的 guest 或 accelerated 文件链，单独确认 /proc/PID/exe 是否指向模拟器。缺少实际链接器 SHA256 或仍有多种映射时，该目标保留 E3。 [已知两种历史候选](../pm_review_round2/08_06_historical_linker_resolution.json)
4. 用同一作业的 V=1 记录、.cmd 与 exec 交叉核验路径、文件摘要和 NEVRA。把成功执行写入的 kdbus.o 关联到最终 kdbus.ko、strip 后成员、二进制 RPM 及发布文件 SHA256。主 ELF 的 zImage 与 devel/debug 分支另保存重算 Build ID 的摘要关系。
5. 每个目标单独出具证据。记录 build ID、revision、目标路径、成功 exec ID、真实 argv、工具绝对路径与 SHA256、.cmd/响应文件 SHA256、目标字节和 RPM 成员。缺少 exec、截断、缓存或 wrapper 歧义时，保留该目标原证据等级。

## 开销和定向构建决策

先从一个常规 kdbus 作业验证采集链。只跟踪 exec 和必要进程树边界，按目标路径和 -o 参数建立索引，限定范围的原 trace 压缩留存。只记录允许的环境字段和必要路径。利用已有未采集作业的 wall time、CPU、I/O 数据比较，将压缩后体积一同纳入扩大范围的决策。实际开销尚未测量。

现有工程验收已经归档，无需额外重编 kdbus。若 PM 要求提前验证补丁或采集新作业的直接证据，另行批准定向构建计划：

- 输入为准确的 linux-tizen-modules-source、候选一行 diff、匹配 ARMv7l/AArch64 非 RT devel SDK、相应 LLVM/GNU 工具和原构建宏。在隔离构建根采集基线与候选。GCC 和显式 Clang+BFD 要选择对应配置及工具。
- 已封存 ARMv7l 外置作业全程约 139 秒，含准备、非 RT/RT 和打包。非 RT 主 build 约为日志 78 秒至 105 秒。该样本仅提供已有构建根场景的量级，环境准备、双架构对照和审核另计。 [实际日志](../evidence/build/linux-tizen-modules-armv7l.out)
- PM 需决定是否早于常规作业运行、工具链与架构矩阵，以及 runner 采集权限。回归检查实际对象与模块链接、strip/打包关系、加载前的 ELF/vermagic 和配置匹配。新证据只支持新作业。
