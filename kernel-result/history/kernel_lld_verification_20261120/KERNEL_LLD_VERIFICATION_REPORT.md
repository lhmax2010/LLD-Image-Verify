# Tizen Linux Kernel LLD Migration Verification

**总体 CONDITIONAL_PASS，暂不关闭验收。** 目标 Raspberry Pi 4 正在运行 6.12.80-arm-rpi4-v7l，构建元数据和关联产物支持 Clang 22.1.8 / LLD 22.1.8。发布启动产物与运行主内核 notes 精确匹配。主内核及全部模块的历史最终链接命令仍缺失。

## Executive Summary

1. **编译器** 独立读取的 /proc/version 记录 Clang 22.1.8。发布生成配置和调试 ELF 也记录 Clang。 [运行证据](01_runtime_kernel.md) · [配置](04_kernel_config_analysis.md)
2. **链接器** /proc/version 及 boot banner 记录 LLD 22.1.8。发布配置选择 LLD。经字节关系绑定的主内核及 ARM 解压器 debuginfo 均有同版本 .comment 标记。 [ELF 分析](03_kernel_binary_analysis.md)
3. **最终链接证据** 精确构建日志观察到 vmlinux、ARM 解压器和 59 个 .ko 的链接步骤。日志省略 executable 与 argv，发布开发包排除 .cmd，调试 ELF 标记也可能从输入继承。历史包存在 /usr/bin/ld.lld 和 /emul/usr/bin/ld.lld 两种候选路径。主内核最终链接独立验证保持 CONDITIONAL_PASS。 [命令和证据缺口](04_build_command_analysis.md)
4. **身份** EXACT_MATCH。仓库 RPM 和发布 boot 镜像内的 zImage SHA256 相同。raw Image 与目标设备共享 GNU Build ID 99ba05b664f7ece7686ab5f087bf54680bb172e6 和完整 84 字节 notes。设备启动文件哈希和活动 RPM 所有权仍不可得。 [身份关联](06_repository_runtime_mapping.md)
5. **模块全量** 仓库 59 个，设备 59 个。两边都解析成功、逐文件 SHA256 全匹配。各有 59 个 LLD_INDICATED，0 个 LLD_CONFIRMED，证据覆盖率 100%，最终链接确认覆盖率 0%。 [模块统计](05_kernel_module_analysis.md)
6. **GNU BFD** 对目标内核和模块的现有证据均无 BFD 命中。最终 argv 缺失限制了残留排除结论。 [模块统计](05_kernel_module_coverage.json) · [构建日志分析](04_build_command_analysis.md)
7. **UNKNOWN / PARSE_FAILED** 仓库与设备均为 0 / 0。模块 ELF 自带链接器证据为 0 个，LLD_INDICATED 来自逐目标构建记录、配置和字节关联。运行时主快照的 11/11 个模块 Build ID 与已安装文件对应。 [逐文件证据](05_kernel_module_inventory.csv) · [运行映射](05_loaded_module_mapping.csv)
8. **验收** A、C、E 通过，B、D 有条件通过。PM 应优先复查本次构建的完整命令和执行路径缺口，再评估是否可关闭验收。 [机器可读汇总](KERNEL_LLD_VERIFICATION_SUMMARY.json)

## Verification Matrix

| Verification Item | Expected | Actual | Status | Evidence | Confidence |
| --- | --- | --- | --- | --- | --- |
| Device Identity | private-address-02 / RPi4 | private-address-02:26101 · Raspberry Pi 4 Model B Rev 1.5 | PASS | [查看](01_runtime_kernel.md) | 高 |
| Kernel Architecture | ARMv7l | armv7l / ELF32 ARM little-endian | PASS | [查看](03_kernel_binary_analysis.md) | 高 |
| Kernel Compiler | Clang 22.1.8 | Clang 22.1.8，独立读取 banner 和配置 | PASS | [查看](evidence/runtime/banner.out) | 高，构建元数据 |
| Kernel Linker | LLD 22.1.8 | LLD 22.1.8，banner、配置、关联调试 ELF | PASS | [查看](03_kernel_binary_analysis.md) | 高，有多源迹象 |
| Kernel Final Link | 直接证明 LLD | quiet LD、构建规则、关联 ELF 标记 | CONDITIONAL_PASS | [查看](04_build_command_analysis.md) | 中 |
| Kernel Config | LLD enabled | CONFIG_LD_IS_LLD=y，CONFIG_LLD_VERSION=220108 | PASS | [查看](04_kernel_config_analysis.md) | 高，发布生成配置 |
| Repository Identity | 匹配目标发布快照 | 目标 RPM、发布 SHA256SUMS、运行镜像 BUILD_ID 对应 | PASS | [查看](02_repository_inventory.md) | 高 |
| Kernel Binary Identity | 对应运行内核 | EXACT_MATCH，GNU Build ID 和 84 字节 notes | PASS | [查看](06_repository_runtime_mapping.md) | 高 |
| Device RPM identity | 可读的 NEVRA、install time、owner | UNVERIFIABLE | INCONCLUSIVE | [查看](01_runtime_kernel.md) | 高，数据库查询 |
| Module ELF Parsing | 100% 全量 | 仓库 59/59，设备 59/59 | PASS | [查看](05_kernel_module_coverage.json) | 高 |
| Module LLD Coverage | 全量确认 | LLD_INDICATED 仓库 59/59，设备 59/59。两组 LLD_CONFIRMED 均 0 | CONDITIONAL_PASS | [查看](05_kernel_module_analysis.md) | 中 |
| BFD Residual | 无 GNU BFD 残留 | 未发现 BFD 证据，历史最终 argv 缺失 | INCONCLUSIVE | [查看](05_kernel_module_analysis.md) | 中 |
| Runtime Boot | 目标设备已启动 | SDB 已授权，读取运行内核和启动日志 | PASS | [查看](01_runtime_kernel.md) | 高 |

## Acceptance Status

| Gate | 范围 | 状态 | 结论与限制 | 证据 |
| --- | --- | --- | --- | --- |
| A | 目标设备及运行时工具链 | PASS | private-address-02:26101，Clang 22.1.8 / LLD 22.1.8，运行记录独立采集。 | [查看](01_runtime_kernel.md) |
| B | Kernel 最终链接 | CONDITIONAL_PASS | 主内核和解压器有 LLD 证据，历史最终 argv 和实际 executable 缺失。 | [查看](04_build_command_analysis.md) |
| C | Repository ↔ Runtime 身份 | PASS | EXACT_MATCH，适用于发布启动产物与运行主内核 notes。设备 RPM DB 和启动文件哈希不可得。 | [查看](06_repository_runtime_mapping.md) |
| D | Kernel Module 覆盖 | CONDITIONAL_PASS | 两组完整扫描。仓库 59/59、设备 59/59 有 LLD 证据，最终链接均为 0 个确认。 | [查看](05_kernel_module_analysis.md) |
| E | 证据完整性 | PASS | JSON、CSV、SHA256、覆盖率复算和证据路径通过脚本自检。 | [查看](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) |

## Findings & Risks

BLOCKER 0 · MAJOR 2 · MINOR 2 · INFO 1

### F-01 · MAJOR

历史主内核、vmlinux.o 和 ARM 解压器完整链接命令缺失。

- **受影响产物** vmlinux、vmlinux.o、arch/arm/boot/compressed/vmlinux
- **原始证据** 精确快照日志 L7962、L8141 及打包排除 .cmd 的 L14237。 [查看证据](evidence/build/linux-rpi-armv7l.out)
- **根因** 已确认日志采用 quiet Kbuild，开发包打包排除 .cmd。
- **影响** 独立的最终链接器验收仍有缺口。
- **建议** 向该次构建的维护者请求已有的原始 .vmlinux*.cmd、解压器 .cmd 或 verbose 日志。

### F-02 · MAJOR

59 个独立模块均具备逐目标 LLD 迹象，历史最终链接命令均缺失。

- **受影响产物** 52 个内核树内模块和 7 个树外模块
- **原始证据** 每个输出的 LD [M]、INSTALL、RPM 写出、LLVM=1 和构建成功原始记录。 [查看证据](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
- **根因** 已确认所有交付模块 ELF 均无可识别链接器标记。quiet 日志省略 argv。
- **影响** Confirmed LLD Coverage 为 0%，无匹配的原始 argv 可用于排除构建工具覆盖或解析异常。
- **建议** 向归档维护者请求这两次构建已有的 59 条最终 .ko 命令及链接器路径。

### F-03 · MINOR

设备的活动 RPM 数据库缺少目标包，启动卷在会话中不可读。

- **受影响产物** 设备 Kernel RPM NEVRA、安装时间、文件所有权及启动卷 zImage
- **原始证据** 目标 RPM 查询无记录，/boot 为空，设备模块为独立只读挂载。 [查看证据](evidence/runtime/pinned-rpm-device-queries.out)
- **根因** 独立分区结构已确认。具体镜像部署操作未观察。
- **影响** 无法实测活动 RPM NEVRA、install time 或设备启动文件 SHA256，运行内核的 notes 仍与发布产物精确匹配。
- **建议** 如验收要求明确包含设备启动卷哈希和 RPM 记录，请索取现有部署清单或只读证据。

### F-04 · MINOR

RPM 与 repo 元数据可做摘要校验，发布签名无法核验。

- **受影响产物** 目标二进制及源码 RPM、repomd.xml
- **原始证据** rpm -Kv 校验摘要通过。探测的签名、密钥端点返回 404。 [查看证据](02_repository_inventory.md)
- **根因** 本次验证未取得可用发布签名和可信密钥。
- **影响** 完整性有校验链支持，发布签名层的来源认证未建立。
- **建议** 如 PM 要求签名级来源证明，请索取对应快照的可信签名和发布密钥。

### F-05 · INFO

开发和调试 ELF 的 GNU Build ID 经过发布后处理。

- **受影响产物** devel vmlinux、vmlinux.debug 与 zImage 的 raw Image
- **原始证据** 发布后 ID bac659039ce25486da3473a6da562dc0e7fd1eea。逐字节比较证明唯一变化是 .notes 内的 20 字节。 [查看证据](evidence/kernel_binary/byte-comparison.json)
- **根因** 构建日志确证运行 find-debuginfo.sh --build-id-seed，字节结果与 Build ID 重算一致。
- **影响** 应在启动 raw Image 端应用设备 Build ID 比对。
- **建议** PM 可复核记录中的唯一差异窗口及两组 debuglink CRC。

## Reproduction 与自检

执行主机为 Ubuntu 24.04.5 LTS，x86_64。可用工具包含 SDB 4.2.36、GNU readelf 2.42、RPM 4.18.2、Python 3.12.3。现场开始时间 2026-11-25T00:49:13-08:00（America/Los_Angeles），banner 采集时间 2026-11-25T08:48:58.060706+00:00（UTC）。准确运行时间和退出状态见每条回执。 [环境](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [工具清单](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [命令及退出状态](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

- 下载列表、URL、大小、签名和校验状态以仓库清单为准。包含发布启动 tar、元数据、构建日志和上游脚本。 [RPM 清单](02_kernel_rpm_inventory.csv) · [启动发布数据](evidence/repository/image-profile-verification.json) · [输入和输出 SHA256](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
- 设备操作限于面向授权序列号的 SDB 查询及 stdout 文件流读取。RPM 查询、解包、二进制分析和文件写入在主机完成。 [运行回执](evidence/runtime) · [命令索引](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
- 离线回放和重新采集的入口、方法、证据定位和计算口径见复跑文档。 [验证方法与脚本](VERIFICATION_METHOD.md)
- 证据路径、JSON/CSV 一致性、分类分母、模块映射、SHA256 和最终链接声明由主机脚本自检。 [最终自检](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## 阶段交付

- [00 预检查](00_preflight.md) · [01 运行内核](01_runtime_kernel.md) · [02 RPM 仓库](02_repository_inventory.md)
- [03 静态分析](03_kernel_binary_analysis.md) · [04 配置](04_kernel_config_analysis.md) · [04 构建命令](04_build_command_analysis.md)
- [05 模块覆盖](05_kernel_module_analysis.md) · [06 身份映射](06_repository_runtime_mapping.md)
