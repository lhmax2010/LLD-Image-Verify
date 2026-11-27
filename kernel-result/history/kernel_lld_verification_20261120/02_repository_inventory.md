# Phase 2 · Repository 与 Kernel RPM 定位

**采集与校验结果 PASS**。固定快照 `tizen-unified-toolchain_20261120.082536` 可通过主机访问。RPM 库发布 `packages/`、`debug/` 和 `source/` 三个子库。包索引包含 `armv7l`、`aarch64`、`x86_64`、`riscv64` 与 `noarch`。发布文件记录了 Base 快照 `tizen-base-toolchain_20261119.042539`。此次定位只使用指定 Unified 快照的 RPM。 [HTTPS 发布目录](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/) · [主机 HTTP 证据](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [标准仓库目录](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [发布 build.xml](evidence/repository/publication-build.out)

## 元数据和校验边界

- `packages` 的 `repomd.xml` 返回 HTTP 200。 Primary 和 filelists 的压缩及解压后校验值全部匹配。分离签名及密钥探测分别为 HTTP 404 和 404。 [repomd.xml](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
- `debug` 的 `repomd.xml` 返回 HTTP 200。 Primary 和 filelists 的压缩及解压后校验值全部匹配。分离签名及密钥探测分别为 HTTP 404 和 404。 [repomd.xml](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
- `source` 的 `repomd.xml` 返回 HTTP 200。 Primary 和 filelists 的压缩及解压后校验值全部匹配。分离签名及密钥探测分别为 HTTP 404 和 404。 [repomd.xml](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

全部入选 RPM 的下载字节数、元数据 SHA256、RPM 头字段以及 RPM 头和 payload digest 均匹配。`rpm -Kv` 对这些 RPM 只报告摘要，未报告签名。内容可与现场获取的仓库元数据交叉核对，发布者签名真实性仍未验证。RPM 头和 metadata 的 `BUILDTIME` 均为 `0`，RPM 头 `BUILDHOST` 无值。CSV 保留原值，UTC 构建时间留空。运行 Kernel 的 banner 时间来自独立的运行态采集。 [完整 CSV](02_kernel_rpm_inventory.csv) · [校验值和证据索引](02_repository_identity.json) · [RPM 验证批次输出](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## 目标 RPM 选择

设备报告 `6.12.80-arm-rpi4-v7l`，并运行 RPi4 ARMv7l 非 RT 内核。Kernel Image 候选是 `arm-rpi4-linux-kernel-6.12.80-0.armv7l`，同一 SRPM 发布模块、开发、BTF、headers 和调试产物。没有发现目标单独的 Kernel Core RPM。全量扫描 `packages/filelists` 中目标 release 目录，找到 `arm-rpi4-linux-kernel-modules` 的 52 个模块路径与独立 SRPM 所产 `linux-tizen-modules-rpi4` 的 7 个模块路径。 [设备证据](01_runtime_kernel.md) · [机器可读 filelists 候选](02_repository_identity.json)

| 类别 | NEVRA（Epoch=0） | 来源 SRPM | RPM 字节数 | Metadata SHA256 | RPM Digest | 签名 |
| --- | --- | --- | ---: | --- | --- | --- |
| TARGET_KERNEL_IMAGE | [arm-rpi4-linux-kernel-6.12.80-0.armv7l](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | rpi4-linux-kernel-6.12.80-0.src.rpm | 17594096 | PASS | [PASS](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | NO_SIGNATURE_REPORTED |
| KERNEL_DEVELOPMENT | [arm-rpi4-linux-kernel-btf-devel-6.12.80-0.armv7l](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | rpi4-linux-kernel-6.12.80-0.src.rpm | 610660 | PASS | [PASS](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | NO_SIGNATURE_REPORTED |
| KERNEL_DEVELOPMENT | [arm-rpi4-linux-kernel-devel-6.12.80-0.armv7l](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | rpi4-linux-kernel-6.12.80-0.src.rpm | 116200896 | PASS | [PASS](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | NO_SIGNATURE_REPORTED |
| KERNEL_DEVELOPMENT | [arm-rpi4-linux-kernel-headers-6.12.80-0.armv7l](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | rpi4-linux-kernel-6.12.80-0.src.rpm | 2049380 | PASS | [PASS](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | NO_SIGNATURE_REPORTED |
| TARGET_MODULE_PAYLOAD | [arm-rpi4-linux-kernel-modules-6.12.80-0.armv7l](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | rpi4-linux-kernel-6.12.80-0.src.rpm | 728756 | PASS | [PASS](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | NO_SIGNATURE_REPORTED |
| TARGET_MODULE_PAYLOAD | [linux-tizen-modules-rpi4-11.0.0-0.armv7l](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | linux-tizen-modules-11.0.0-0.src.rpm | 92412 | PASS | [PASS](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | NO_SIGNATURE_REPORTED |
| KERNEL_DEBUGINFO | [arm-rpi4-linux-kernel-devel-debuginfo-6.12.80-0.armv7l](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | rpi4-linux-kernel-6.12.80-0.src.rpm | 75879700 | PASS | [PASS](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | NO_SIGNATURE_REPORTED |
| KERNEL_DEBUGSOURCE | [rpi4-linux-kernel-debugsource-6.12.80-0.armv7l](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | rpi4-linux-kernel-6.12.80-0.src.rpm | 18608992 | PASS | [PASS](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | NO_SIGNATURE_REPORTED |
| SOURCE_RPM | [linux-tizen-modules-11.0.0-0.src](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | 自身为 SRPM | 19542 | PASS | [PASS](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | NO_SIGNATURE_REPORTED |
| SOURCE_RPM | [rpi4-linux-kernel-6.12.80-0.src](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | 自身为 SRPM | 156385913 | PASS | [PASS](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | NO_SIGNATURE_REPORTED |

CSV 共 93 个候选，其中 10 个下载分析，83 个依据 metadata 与 filelists 排除。包括普通 ARMv7l RPM 封装的 ARM64 payload、RPi4 RT 变体、其他硬件、x86_64 软件包，以及从 Linux SRPM 生成的 userspace perf/BPF 工具。排除项保留 metadata 文件大小、校验值及选择理由，本地下载证据字段留空。 [逐项依据和下载 URL](02_kernel_rpm_inventory.csv)

| 候选排除类别 | 数量 |
| --- | ---: |
| EXCLUDED_ADJACENT_PACKAGE | 2 |
| EXCLUDED_ARM64_PAYLOAD | 11 |
| EXCLUDED_MODULE_SUPPORT_OR_OTHER_PLATFORM | 22 |
| EXCLUDED_OTHER_SOURCE_OR_PLATFORM | 19 |
| EXCLUDED_RT_VARIANT | 13 |
| EXCLUDED_USERSPACE_TOOL | 10 |
| EXCLUDED_X86_64 | 6 |

## 发布镜像与设备侧关联

同一快照的 `tizen-boot-armv7l-rpi` 与 `tizen-headed-armv7l` 分别发布 boot profile 与 headed rootfs profile。boot profile 的 `.packages` 记录当前三个相关 RPM 的 3 条 NEVRA/VCS 记录，MIC 日志保留同名 RPM 的下载/安装行。boot manifest 声明 `/boot`、`/hal`、`/lib/modules`。headed manifest 声明 rootfs 等分区，headed `.packages` 中对应 NEVRA 有 0 条。设备报告独立只读 modules 分区，设备当前 headed RPM DB 中未查到这三个包的记录。最终设备关联由 Phase 6 汇总。 [boot manifest](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [boot 安装清单](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [boot MIC 日志](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [headed manifest](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [运行态 RPM 证据](01_runtime_kernel.md)

发布 boot tar 的 SHA256 为 `de7a259811fab9d3608fa16432ce569306304a9d17fe476d77259fcd5deff5d8`，与该 profile 的 `SHA256SUMS` 一致。主机使用 mtools 从 FAT `boot.img` 读取 `zImage`，其 SHA256 为 `2b26465ef90455092cb6671bc2a6a967edfe8f5e7233894b70eaee0564b68601`，与 RPM 的文件摘要完全相同。使用只读 `debugfs` 读取 ext4 `modules.img`，目标清单的 59/59 个模块文件与对应 RPM 的 SHA256 完全相同。归档、分区和每个模块的原始文件摘要保留。本步骤没有读取设备的 boot 块设备。 [发布 SHA256SUMS](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [下载归档](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [逐文件校验记录](evidence/repository/image-profile-verification.json) · [设备端及最终二进制身份](06_repository_runtime_mapping.md)

## 复跑

在新的同结构跑次目录复制 `scripts/`，运行前两条命令获取和验证固定快照。在保留归档的目录中可用 `--replay` 复算 RPM 库结果，该命令重新读取下载产物及命令回执。

```bash
python3 scripts/record.py --timeout 1300 repository/runner python3 scripts/repository.py
python3 scripts/record.py --timeout 480 repository/image-profile-runner python3 scripts/repository_image.py
python3 scripts/record.py --timeout 90 repository/replay-runner python3 scripts/repository.py --replay
python3 scripts/report_repository.py
```

boot archive 分析依赖主机 `tar`、`debugfs`、`mcopy`。若主机无 `mcopy`，脚本可从已配置 Ubuntu 仓库下载 mtools deb 并只解包到本次 Host 工作目录。工具下载及版本回执随证据保留。 [mtools 下载回执](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [mtools 版本](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [仓库复跑回执](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [镜像分析回执](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
