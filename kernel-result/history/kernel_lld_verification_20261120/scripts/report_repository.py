#!/usr/bin/env python3
"""Render the Phase 2 report from the verified repository data."""
from collections import Counter
import csv
import json

from record import ROOT

def main():
    repo = json.loads((ROOT / '02_repository_identity.json').read_text())
    rows = repo['selected_rpms']
    with (ROOT / '02_kernel_rpm_inventory.csv').open(newline='') as f:
        excluded = Counter(row['category'] for row in csv.DictReader(f) if row['selected'] == 'False')
    boots = json.loads((ROOT / repo['publication_profile_evidence']).read_text())
    exact = boots['boot']['boot_archive_verification']
    modules = exact['modules']
    profiles = '`' + boots['boot']['profile'] + '` 与 `' + boots['headed']['profile'] + '`'
    table = [
        '| 类别 | NEVRA（Epoch=0） | 来源 SRPM | RPM 字节数 | Metadata SHA256 | RPM Digest | 签名 |',
        '| --- | --- | --- | ---: | --- | --- | --- |',
    ]
    for row in rows:
        package = f"{row['name']}-{row['version']}-{row['release']}.{row['architecture']}"
        table.append(
            f"| {row['category']} | [{package}]({row['rpm_path']}) | {row['source_rpm'] or '自身为 SRPM'} | "
            f"{row['actual_file_size_bytes'] or '未取得'} | {row['metadata_checksum_verification']} | "
            f"[{row['rpm_digest_verification']}]({row['rpm_verify_evidence']}) | {row['rpm_signature_verification']} |"
        )
    scope = [
        '| 候选排除类别 | 数量 |', '| --- | ---: |',
        *(f'| {label} | {count} |' for label, count in sorted(excluded.items())),
    ]
    counts = {
        item['name']: len(item['module_paths'])
        for item in repo['binary_filelists_release_matches'].values()
    }
    shape = '\n'.join(
        f"- `{area}` 的 `repomd.xml` 返回 HTTP {metadata['repomd_http_status']}。"
        f" Primary 和 filelists 的压缩及解压后校验值全部匹配。分离签名及密钥探测分别为 HTTP "
        f"{metadata['repomd_signature_http_status']} 和 {metadata['repomd_key_http_status']}。"
        f" [repomd.xml]({metadata['repomd_path']})"
        for area, metadata in repo['metadata'].items()
    )
    table_text = '\n'.join(table)
    scope_text = '\n'.join(scope)
    boot_path = exact['archive']['path']
    kernel_sha = exact['kernel']['image_file_sha256']
    archive_sha = exact['archive']['sha256']
    package_count = len(boots['boot']['target_package_lines'])
    head_count = len(boots['headed']['target_package_lines'])
    report = f'''
# Phase 2 · Repository 与 Kernel RPM 定位

**采集与校验结果 {repo['status']}**。固定快照 `{repo['snapshot']}` 可通过主机访问。RPM 库发布 `packages/`、`debug/` 和 `source/` 三个子库。包索引包含 `armv7l`、`aarch64`、`x86_64`、`riscv64` 与 `noarch`。发布文件记录了 Base 快照 `tizen-base-toolchain_20261119.042539`。此次定位只使用指定 Unified 快照的 RPM。 [HTTPS 发布目录]({repo['snapshot_url']}) · [主机 HTTP 证据](evidence/repository/http-root.out) · [标准仓库目录](evidence/repository/standard.out) · [发布 build.xml]({repo['publication_build_evidence']})

## 元数据和校验边界

{shape}

全部入选 RPM 的下载字节数、元数据 SHA256、RPM 头字段以及 RPM 头和 payload digest 均匹配。`rpm -Kv` 对这些 RPM 只报告摘要，未报告签名。内容可与现场获取的仓库元数据交叉核对，发布者签名真实性仍未验证。RPM 头和 metadata 的 `BUILDTIME` 均为 `0`，RPM 头 `BUILDHOST` 无值。CSV 保留原值，UTC 构建时间留空。运行 Kernel 的 banner 时间来自独立的运行态采集。 [完整 CSV](02_kernel_rpm_inventory.csv) · [校验值和证据索引](02_repository_identity.json) · [RPM 验证批次输出](evidence/repository/runner.out)

## 目标 RPM 选择

设备报告 `{repo['runtime_release']}`，并运行 RPi4 ARMv7l 非 RT 内核。Kernel Image 候选是 `arm-rpi4-linux-kernel-6.12.80-0.armv7l`，同一 SRPM 发布模块、开发、BTF、headers 和调试产物。没有发现目标单独的 Kernel Core RPM。全量扫描 `packages/filelists` 中目标 release 目录，找到 `arm-rpi4-linux-kernel-modules` 的 {counts['arm-rpi4-linux-kernel-modules']} 个模块路径与独立 SRPM 所产 `linux-tizen-modules-rpi4` 的 {counts['linux-tizen-modules-rpi4']} 个模块路径。 [设备证据](01_runtime_kernel.md) · [机器可读 filelists 候选](02_repository_identity.json)

{table_text}

CSV 共 {repo['candidate_rpm_count']} 个候选，其中 {len(rows)} 个下载分析，{repo['excluded_candidate_rpm_count']} 个依据 metadata 与 filelists 排除。包括普通 ARMv7l RPM 封装的 ARM64 payload、RPi4 RT 变体、其他硬件、x86_64 软件包，以及从 Linux SRPM 生成的 userspace perf/BPF 工具。排除项保留 metadata 文件大小、校验值及选择理由，本地下载证据字段留空。 [逐项依据和下载 URL](02_kernel_rpm_inventory.csv)

{scope_text}

## 发布镜像与设备侧关联

同一快照的 {profiles} 分别发布 boot profile 与 headed rootfs profile。boot profile 的 `.packages` 记录当前三个相关 RPM 的 {package_count} 条 NEVRA/VCS 记录，MIC 日志保留同名 RPM 的下载/安装行。boot manifest 声明 `/boot`、`/hal`、`/lib/modules`。headed manifest 声明 rootfs 等分区，headed `.packages` 中对应 NEVRA 有 {head_count} 条。设备报告独立只读 modules 分区，设备当前 headed RPM DB 中未查到这三个包的记录。最终设备关联由 Phase 6 汇总。 [boot manifest](evidence/repository/boot-manifest.out) · [boot 安装清单](evidence/repository/boot-packages.out) · [boot MIC 日志](evidence/repository/boot-log.out) · [headed manifest](evidence/repository/headed-manifest.out) · [运行态 RPM 证据](01_runtime_kernel.md)

发布 boot tar 的 SHA256 为 `{archive_sha}`，与该 profile 的 `SHA256SUMS` 一致。主机使用 mtools 从 FAT `boot.img` 读取 `zImage`，其 SHA256 为 `{kernel_sha}`，与 RPM 的文件摘要完全相同。使用只读 `debugfs` 读取 ext4 `modules.img`，目标清单的 {modules['exact_sha256']}/{modules['total']} 个模块文件与对应 RPM 的 SHA256 完全相同。归档、分区和每个模块的原始文件摘要保留。本步骤没有读取设备的 boot 块设备。 [发布 SHA256SUMS](evidence/repository/boot-SHA256SUMS.out) · [下载归档]({boot_path}) · [逐文件校验记录]({repo['publication_profile_evidence']}) · [设备端及最终二进制身份](06_repository_runtime_mapping.md)

## 复跑

在新的同结构跑次目录复制 `scripts/`，运行前两条命令获取和验证固定快照。在保留归档的目录中可用 `--replay` 复算 RPM 库结果，该命令重新读取下载产物及命令回执。

```bash
python3 scripts/record.py --timeout 1300 repository/runner python3 scripts/repository.py
python3 scripts/record.py --timeout 480 repository/image-profile-runner python3 scripts/repository_image.py
python3 scripts/record.py --timeout 90 repository/replay-runner python3 scripts/repository.py --replay
python3 scripts/report_repository.py
```

boot archive 分析依赖主机 `tar`、`debugfs`、`mcopy`。若主机无 `mcopy`，脚本可从已配置 Ubuntu 仓库下载 mtools deb 并只解包到本次 Host 工作目录。工具下载及版本回执随证据保留。 [mtools 下载回执](evidence/repository/boot-apt-mtools.out) · [mtools 版本](evidence/repository/boot-mtools-version.out) · [仓库复跑回执](evidence/repository/replay-runner.cmd.json) · [镜像分析回执](evidence/repository/image-profile-runner.cmd.json)
'''
    (ROOT / '02_repository_inventory.md').write_text(report.strip()+'\n')

if __name__ == '__main__':
    main()
