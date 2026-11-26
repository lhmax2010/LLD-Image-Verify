# Tizen LLVM 镜像 LLD 验证

本文记录两轮 Tizen Unified Toolchain 镜像的链接器验证结果。**整镜像每轮有 6,892 / 10,875 个 ELF 或内核文件实例确认使用 LLD（63.4%）。只看 Unified RPM 来源为 6,876 / 7,055（97.5%）。** 镜像同时包含 GNU ld、MetaWare 和 Dart AOT 产物。

## 验证范围

| 轮次 | Unified Toolchain 快照 | Base Toolchain 快照 | 范围 |
| --- | --- | --- | --- |
| QB 1234653 | `20261119.012153` | `20261117.165617` | aarch64、armv7l 各一份 headed、headless、RPi boot |
| 包含 deviced 和 wrtjs Patchset 3 的后续发布 | `20261120.082536` | `20261119.042539` | 相同的六种镜像 |

[旧轮发布镜像](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261119.012153/images/standard/) · [后续轮发布镜像](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/images/standard/) · [后续轮消费的 Base](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/build.xml)

## 每轮结果

| 证据分类 | ELF 或内核文件实例 |
| --- | ---: |
| 确认使用 LLD | 6,892 |
| 确认使用 GNU ld | 140 |
| 确认使用 MetaWare | 8 |
| 确认由 Dart AOT 写出 | 2 |
| 排除 LLD 22.1.8，实际链接器待确认 | 234 |
| GNU ld 类布局 | 3,517 |
| LLD 类布局 | 24 |
| 证据不足 | 58 |
| **合计** | **10,875** |

同一文件在不同镜像或分区出现时分别计数。每轮按 SHA256 去重后有 6,014 份，另外有 12 个静态归档单列。两轮没有 x86_64 整镜像验证结果。后三种证据项和排除特定版本的项目合计 3,833 个实例，实际链接器身份仍缺确证。

- **关键目标。** 后续轮的 Base 和 Unified manifest 与 58 个预期源码 SHA 全部匹配。`deviced`、`deviced-request-shutdown`、`wrt-loader` 在两个架构共六个目标。其镜像、发布 RPM 与 debuginfo 的身份均已核对，确认 LLD 22.1.8。六个 ELF 也分别与旧轮的对应文件完整 SHA256 一致。
- **LLD 版本。** 每轮的 6,892 个确证实例包含 6,735 个 LLD 22.1.8、29 个 Chromium 工具链 LLD 20.0.0、2 个 Rust 标准库 LLD 20.1.0，以及 126 个由 Kbuild 目标日志确证的模块。模块日志未逐个记录版本。
- **GNU ld 证据。** `libdrm` 与 `nntrainer` 用具体目标链接日志和 RPM 哈希确认。Toybox 用 GNU ld.bfd 2.43 重现完整文件 SHA256。ZIP、libbz2、`sed` 和 `tzdata` 通过 BFD/LLD 对照重放确认，重放哈希比较只忽略了调试链接的四字节 CRC。
- **Base 来源。** 每轮 3,804 个实例中，126 个确认使用 GNU ld，234 个可排除 LLD 22.1.8，3,421 个是 GNU ld 类布局，23 个证据不足。另有 16 个确认 LLD 的实例无 RPM 来源归属。
- **RPM 口径。** 每轮 2,556 个 RPM 中有 1,687 个可关联本轮观察到的原生文件。同一个 RPM 可能包含来自多个链接器的文件。镜像实例比例按 ELF 或内核文件计算。

[验证方法和可复现的公开 RPM 示例](docs/verification-methods.md) · [后续验证交接](docs/handoff.md)

## 2026-11-25 补查

[补查报告](docs/follow-up-audit.md)记录了 QB 1234794 的输入、同轮编译器切换、预编译字节证据、x86_64 RPM 样本和重复验证方法。[逐 ELF、RPM 与构建日志数据](data/)和[复跑脚本](scripts/)可直接核对。补查将每轮 16 个原无归属的 LLD 实例匹配到已安装的 Unified RPM。新版 Unified 分母为 7,071，LLD 确证为 6,892。
