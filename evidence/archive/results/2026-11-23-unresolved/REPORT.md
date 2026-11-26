# 原 100 个证据不足实例的补查

后续验证已确认 sed 和 tzdata 的 12 个实例。最新待确认数是每轮 58 个。 [后续报告](../2026-11-23-sed-tzdata/REPORT.md)

QB 1234653 和新版 Unified `20261120.082536` 已复核。每轮原有 100 个待确认实例，按 SHA256 去重是 62 份 ELF。两轮合计 67 份。**本轮每轮解决 30 个实例，剩余 70 个，对应单轮 48 份、两轮合计 50 份 ELF。** [两轮计数及镜像分组](updated-counts.json)

## 新确认的结果

| 目标 | 每轮实例 | 每轮不同 SHA256 | 确认结果 |
| --- | ---: | ---: | --- |
| `zip`、`zipcloak`、`zipnote`、`zipsplit` | 16 | 8 | GNU ld.bfd 2.43 |
| `libbz2.so.1.0.8` | 8 | 2 | GNU ld.bfd 2.43 |
| `/usr/sbin/glibc_post_upgrade` | 4 | 2 | GNU ld.bfd 2.43 |
| Homescreen 的 `lib/libapp.so` | 2 | 2 | Dart AOT 自带 ELF writer |
| **合计** | **30** | **14** | **28 个 GNU ld，2 个 Dart AOT** |

- **ZIP 和 libbz2。** 两轮、两个架构，合计 20 次目标对比。用各自发布的 SRPM 和构建日志重建相同目标，使用 GNU ld.bfd 2.43 和 LLD 22.1.8 分别链接。每次只有 BFD 产物与镜像 ELF 匹配。对比将两边 `.gnu_debuglink` 尾部的四字节调试文件 CRC 清零，其余 ELF 字节完全一致。完整文件 SHA256 有差异，归档保留了完整 SHA 和只忽略 CRC 的 SHA。归档环境中 libbz2 的默认 Clang 调用实际选用 LLD，公开日志里原始命令只写了 Clang，因此仅看驱动名或重跑默认命令都不足以归类原始 ELF。 [ZIP 日志与哈希](zip/) · [libbz2 日志与哈希](bzip2/)
- **glibc 升级工具。** 四份原始日志都有具体目标的 GCC 静态链接、安装和打包记录。用对应 Base 环境重放同一驱动参数，通过 `-Wl,--version` 实际得到 GNU ld 2.43。下载的对应 glibc RPM 里的目标与镜像 ELF 四次完整 SHA256 一致。 [原始日志、驱动探测和 RPM 校验](glibc/)
- **Homescreen。** 新版镜像两个架构的 `libapp.so` 与发布 TPK 中对应成员字节一致，旧版镜像与新版的两份 ELF 分别完全一致。按 Dart 源码将两份指令镜像的三个已应用重定位字段恢复为写入前的占位值，对四块 snapshot 数据重算 Build ID。aarch64 得到 `7a3ef9308559ffc2d645996eaaf3112e`，armv7l 得到 `1414365c27fcad0ab81de21e361d0d57`，均与 ELF 精确匹配。两份 ELF 均导出 Dart 的 Build ID note 符号和四个 snapshot 符号。按直接 ELF writer 归类，原始 Flutter 构建命令仍未取得。 [aarch64 结果](dart-aarch64.json) · [armv7l 结果](dart-armv7l.json) · [Dart ELF writer 的 Build ID 实现](https://github.com/dart-lang/sdk/blob/3.12.0/runtime/vm/elf.cc#L1714-L1780) · [Dart 字节哈希实现](https://github.com/dart-lang/sdk/blob/3.12.0/runtime/platform/utils.cc) · [Dart 占位字段和重定位实现](https://github.com/dart-lang/sdk/blob/3.12.0/runtime/vm/image_snapshot.cc) · [gen_snapshot 的 ELF 生成入口](https://github.com/dart-lang/sdk/blob/3.12.0/runtime/bin/gen_snapshot.cc)

## 剩余 70 个如何取证

| 对象 | 每轮实例 / 不同 SHA256 | 下一步 |
| --- | ---: | --- |
| `sed` | 8 / 2 | 优先重放。用发布 SRPM、原始 configure flags、gnulib/gettext 生成文件和最终 `sed/sed` 链接行，在同一批目标文件上做 BFD/LLD 对照。日志中的 GNU ld 来自 configure 探测，最终命令由 Clang 驱动。checksum 匹配后即可按两个 ELF 回填八个镜像实例。 |
| `tzdata` | 4 / 4 | 优先重放。原日志分别有 `zic`、`zdump` 的链接命令，用各自目标文件和同架构 CRT 重放。按发布 RPM 核对两个程序，并与 ICU 自己打包的同名 `zic` 区分。 |
| ICU | 8 / 4 | 分别捕获 `tz2icu` 与 ICU 构建的 `zic`。优先重放这两个工具目标，保存 make 展开后的最终驱动参数，并核对它们最终进入的 RPM 路径。 |
| Boost | 7 / 4 | 只追 armv7l 的四个共享库。用归档的 `b2` 配置与 `-d+2` 输出最终命令，从历史对象重链接或在同一个构建根重建对应库。 |
| `libsndfile` | 4 / 2 | 用 `make V=1` 收集 libtool 展开的最终共享库链接行，为 `libsndfile.so.1.0.37` 进行 A/B 对照。 |
| `util-linux` | 4 / 2 | 原日志有 `nologin` 目标，截取 libtool 实际执行的驱动命令。用相同依赖重放，核对安装进 RPM 的 `nologin`。 |
| `stt-engine-default` | 25 / 25 | 25 份均与 SRPM 中预编译文件字节一致。按逐文件清单向原始 gRPC/STT 构建方索取包含实际 linker 路径或版本的目标日志、匹配的未 strip ELF 或 debuginfo。 |
| `vc-engine-default` | 10 / 5 | 5 份均来自 SRPM 预编译文件，包括主程序、`libfst.so.8` 和 `libondeviceasr.so`。按 Build ID 或 SHA256 追溯到语音引擎生产方。 |
| **合计** | **70 / 48** | **35 个 Base 实例可按原目标复建，35 个 Unified 实例需要预编译产物来源方提供链接证据。** |

语音组共 30 份去重后的 ELF，与 SRPM 中的原始文件逐字节匹配，原始文件同样没有 `.comment` 字符串。当前 Unified 构建日志只记录安装和打包过程。拿到生产方提供的调试文件后，优先校验 ELF 的 GNU Build ID 或 debuglink CRC，再核对链接器标记。若生产方只提供链接日志，需同时拿到同产物的哈希或原始制品记录，以建立日志和镜像之间的对应关系。只用相同源码重新生成一个可运行的语音库，还无法确定历史二进制的来源。 [30 份预编译来源核对](voice-source-provenance.tsv) · [统一发布的 SRPM](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/repos/standard/source/)

## 汇总及原始文件

每轮 10,875 个实例中，6,892 个确认 LLD，128 个确认 GNU ld，8 个确认 MetaWare，2 个确认 Dart AOT，70 个证据不足。另外有 234 个可排除本轮 LLD 22.1.8，3,517 个为 GNU ld 类布局，24 个为 LLD 类布局。分类之和等于每轮总数。Unified 仍有 6,876 / 7,055（97.5%）个 LLD 确证实例。 [新版逐实例复核](latest-follow-up.tsv) · [新版剩余目标](latest-remaining.tsv) · [旧版逐实例复核](qb1234653-follow-up.tsv) · [旧版剩余目标](qb1234653-remaining.tsv)

可从相同快照取回 SRPM 和 RPM，使用已保留的原始日志、GBS 构建根和镜像解包目录复跑。 [复跑方法和命令](../../METHODS.md#7-复核缺少链接器标记的原始目标)
