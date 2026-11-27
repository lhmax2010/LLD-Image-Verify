# Tizen 内核 LLD 验证复跑

本目录固定到 Tizen Unified Toolchain 20261120.082536、RPi4 ARMv7l 非 RT、6.12.80-arm-rpi4-v7l 和授权 SDB 序列号 private-address-02:26101。其他快照、设备及 RT/ARM64 需要重新审定输入和匹配规则。

## 入口

从本目录执行以下命令。复跑输出目录必须为不存在的路径，原证据目录保持可独立校验。预留至少 3 GiB 工作空间。

    bash verify.sh check
    bash verify.sh replay ../kernel_lld_replay_20261120
    bash verify.sh capture ../kernel_lld_device_recheck_20261120
    bash verify.sh refresh ../kernel_lld_full_recheck_20261120

- **check** 核对原始包、分析输出、报告 SHA256 和各验收结论的关系，全程离线。
- **replay** 使用归档设备与发布证据重算 RPM、配置、ELF、模块和报告。输入包和启动镜像仍按归档 metadata 和 SHA256SUMS 核验。
- **capture** 从已授权的指定设备重新读取 banner、notes、RPM、模块文件和加载清单，再与归档的精确快照重算。模块加载状态是时点记录。
- **refresh** 在 capture 基础上重新请求固定快照的仓库、目标 RPM、boot profile、boot archive 和原始构建日志。考虑快照的网络可达性；下载或目标身份校验失败时脚本返回非零并保留回执。历史 Base 包和上游脚本继续用已归档并校验的版本。

Linux 主机需有 Bash、Python 3.12（HTML 渲染用 markdown-it-py）、GNU coreutils/binutils、rpm、rpm2cpio、cpio、file、tar、gzip、xz、zstd、debugfs。发布 FAT 镜像读取使用 mcopy。本证据包自带已解包的 mtools，若主机已安装 mcopy，脚本优先使用该工具。现场命令需要 curl、现有 SDB 可执行文件及已授权设备。工具路径和版本见 [原始工具清单](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)。

## 核验步骤

1. **设备。** 读取 SDB 设备列表，锁定序列号。用设备 IP 和 DT 型号复核。读取 /proc/version、boot banner、/etc/os-release、/proc/cmdline 和 RPM DB。以小端 ELF notes 记录读取 /sys/kernel/notes，用设备 SHA256 验证传输。读取实际 /proc/modules 快照后，对其中每个模块读取 sysfs GNU Build ID。 [运行报告](01_runtime_kernel.md) · [采集命令](scripts/runtime-read-plan.json) · [采集器](scripts/capture_runtime.py) · [解析器](scripts/parse_runtime.py)
2. **仓库。** 先读 packages、debug、source 的 repomd、primary 和 filelists，验证 compressed/open checksum，再定位准确 release 和模块所属包。检查 RPM 的 metadata SHA256、RPM header/payload 摘要和签名状态。对发布 boot.img 和 modules.img 分别用 mcopy、debugfs 读取，逐文件比较发布分区和 RPM 摘要。 [仓库分析](02_repository_inventory.md) · [仓库脚本](scripts/repository.py) · [发布分区脚本](scripts/repository_image.py)
3. **内核静态。** 用 rpm2cpio 解码 newc，按类型和路径选择常规文件；解包过程拒绝绝对路径、越界路径和重复成员。运行 file、readelf。检查上游 extract-vmlinux 与 extract-ikconfig 输出及其退出结果，另验 ARM 头和 gzip 成员得到 raw Image。直接比较设备 notes 字节，以 ELF PT_LOAD 的 LMA 对齐核对 SHF_ALLOC 文件内容，并以 .gnu_debuglink CRC32 绑定 sidecar。 [二进制分析](03_kernel_binary_analysis.md) · [分析脚本](scripts/analyze_artifacts.py) · [段比较](scripts/compare_kernel_bytes.py)
4. **构建证据。** 核对实际 .config、auto.conf、compile.h、utsrelease.h、utsversion.h。用该快照的完整日志把 quiet 输出、精确路径、时间和 RPM 写出关联。检查 Kbuild 的 LLVM 规则、打包排除 .cmd 规则、历史 Base 包和旧 GBS 记录排除理由。 [构建报告](04_build_command_analysis.md) · [配置提取](scripts/collect_build_rpm_evidence.sh) · [日志解析](scripts/build_log_evidence.py)
5. **模块。** 从全部匹配 release 的包和设备物理目录扫描 .ko、.ko.gz、.ko.xz、.ko.zst。设备归档用 tar 写 stdout 并以 base64 传输，逐个对照在设备即时计算的 SHA256。主机按需解压，保留载体和 ELF 各自的 SHA256。readelf 核验架构、类型、Build ID、.comment 和 .modinfo。比较路径、SHA256 与实时 Build ID；目录别名只计一次，文件符号链接单列。 [逐模块 CSV](05_kernel_module_inventory.csv) · [加载模块](05_loaded_module_mapping.csv)
6. **判定。** ELF 标记或逐目标构建证据可以支持 LLD_INDICATED。已和产物绑定的历史最终链接命令与其 linker 身份才允许升级为 CONFIRMED。vermagic、clang 版本和缺失标记均不能判定最终 linker。由全部独立正常模块文件构成分母，PARSE_FAILED 和 UNKNOWN 保留在分母。 [模块统计](05_kernel_module_coverage.json)
7. **自检。** 校验清单覆盖所有常规文件、模块计数和哈希、运行 notes 和仓库完整链路。COMMANDS.jsonl 汇总原始采集和验证命令、工作目录、UTC 时间、退出状态和 stdout/stderr。预检部分命令记录了归档移动前的工作目录；文件按本包相对路径读取。 [命令索引](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [SHA256SUMS](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [自检结果](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

脚本可独立运行。单独运行会改写所在副本的证据和统计；复跑或现场采集建议从 verify.sh 新建副本。自检回执在清单封存之后写出，清单自身以及自检的三份回执不参与自校验。mtools 的辅助符号链接未纳入 SHA256SUMS，使用的 mcopy 实体目标及原始 deb 文件已纳入。对工作区执行普通文件校验也可用 sha256sum -c --quiet SHA256SUMS。

原始数据和方法仅用于本次可审计比较。设备无授权的 SDB 连接会退出。现场设备结果若偏离本次基线，部分断言会失败并保留证据，需根据原始输出重新定级。
