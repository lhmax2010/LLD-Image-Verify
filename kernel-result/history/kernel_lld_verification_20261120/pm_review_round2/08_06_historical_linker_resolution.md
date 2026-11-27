# 08.06 · 历史链接器可执行文件解析

**Linker family = LLD，version = 22.1.8，actual executable path = UNRESOLVED。** 两个历史 ARMv7l 作业都保留相同版本的 clang-accel 与原生 llvm RPM。两个文件均从历史 Base 的原包读取，架构和版本观察来自 ELF，不依赖当前分析主机的链接器。 [结构化结果](08_06_historical_linker_resolution.json) · [主内核包清单](evidence/recovery/kernel-buildroot-excerpts.txt) · [树外包清单](evidence/recovery/external-buildroot-excerpts.txt)

| 历史候选路径 | 所属 RPM / RPM 架构 | Payload 类型 / ELF 架构 | SHA256 与版本 |
| --- | --- | --- | --- |
| /usr/bin/ld.lld | llvm-22.1.8-1.6.armv7l / armv7l，源 llvm-22.1.8-1.6.src.rpm | 相对符号链接 lld。目标 /usr/bin/lld 是 ARM ELF32 little endian PIE、动态链接，解释器 /lib/ld-linux.so.3。通用 LLD 驱动 ELF | 文件 SHA256 6148726c811fc3b3a41791bc0ee27c68106a686b5f2041879423f42bdcb9212d，原始版本标识 LLD 22.1.8。 [RPM 文件记录](evidence/recovery/native-rpm-file-headers.out) · [ELF 读取](evidence/recovery/native-readelf.out) · [版本字串](evidence/recovery/accelerated-strings-version.out) |
| /emul/usr/bin/ld.lld | clang-accel-x86_64-armv7l-0.4-1.1.armv7l / armv7l，源 qemu-accel-0.4-1.1.src.rpm | 常规 ELF64 x86-64 little endian PIE，解释器 /emul/usr/lib64/ld-linux-x86-64.so.2。与同包 /emul/usr/bin/lld 的字节相同，包 inode 和提取 inode 均不同。两个常规文件，无 shell wrapper 或符号链接 | 文件 SHA256 9ecd1893b14dd19d8ffb8b582e48c1a4f1019b45019e1851e227c55b9ba57405，原始版本标识 LLD 22.1.8。 [RPM 文件记录](evidence/recovery/accelerated-rpm-file-headers.out) · [ELF 读取](evidence/recovery/accelerated-readelf.out) · [版本字串](evidence/recovery/accelerated-strings-version.out) |

- 原生 RPM SHA256 为 1cfda9694d06cb45ae468f843bc35ec7165b317ce2282802226b324123f422c0。加速 RPM SHA256 为 d93bd3069d25ed9c6c71d5483833c7106a9ab0c5b3960fe873510241b15e15bc，大小 151112237 字节。二者与 Base 主索引和 RPM ELF 文件摘要核对。已记录 digest 检查，RPM 的发行签名信任另行处理。 [原封存依赖记录](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [Base primary 校验及候选](evidence/recovery/base-selected-packages.json) · [原生包摘要](evidence/recovery/native-rpm-digest.out) · [加速包摘要](evidence/recovery/accelerated-rpm-digest.out)
- 两个日志均在 x86_64 builder 上为 ARM 构建，记录 binfmt 注册和 qemu-linux-user 包，路径及 ELF 架构支持 ARM 原生执行与 x86-64 加速两种角色。无法恢复原 shell PATH、QEMU 重定向状态及实际 execve，因此实际选中的候选路径保持空值。加速包的查询到的安装脚本仅包含 ldconfig 和注释。 [历史路径缺口](08_02_historical_evidence_recovery.md) · [加速包 scriptlet](evidence/recovery/accelerated-rpm-scripts.out)
- 两个保留包的已验证 ld.lld 均为 LLD。已保留 binutils 提供 ld 与 ld.bfd 名称，Base primary 中的同名 ld.lld 声明来自 LLVM 与 accel。其余已索引 ld.lld 提供者有独立路径或不同 accel 包名，两份日志均无这些提供者的保留/安装匹配。因果检查仍要按每个最终链接规则验证命令名是否保持 ld.lld，并处理实际的局部 LD 赋值。单靠路径相同或工具包并存无法给出 E4。 [命名空间比较](evidence/recovery/base-selected-packages.json) · [Kernel 规则](08_03_kernel_linker_selection.md) · [树外规则](08_05_out_of_tree_modules.md)

复跑使用第一轮封存目录中的 Base metadata、原生 LLVM RPM 和目标日志，及当前复核获取的单个加速 RPM。在 Round 1 目录外指定 scratch。若该 RPM 尚未存在，可以用 --fetch-accelerator 取回。脚本不会运行两个 ELF，也不会安装 RPM。 [验证脚本](scripts/inspect_historical_linker.py)
