# 后续验证交接

## 历史镜像的证据缺口

58 个证据不足实例在单轮按 SHA256 去重为 42 份，两轮合计 43 份。

| 来源 | 每轮实例 | 建议取证 |
| --- | ---: | --- |
| Base 的 `util-linux`、`libsndfile` | 4 + 4 | 用最终目标链接行和同一批对象重放 `nologin`、`libsndfile.so.1.0.37` |
| Base 的 ICU、Boost | 8 + 7 | 核对 ICU 的 `tz2icu`、`zic`，以及四个 armv7l Boost 共享库。按架构重建最小目标做 GNU ld.bfd/LLD 对照 |
| Unified 的 STT、VC | 25 + 10 | 已与 SRPM 内预编译二进制逐字节匹配。按架构、路径、SHA256 和 Build ID 向生产方取原始链接记录或匹配 debuginfo |

每轮还有 24 个 `nnfw` ELF 只有 LLD 类布局。 `libtiff`、`libelf` 和部分 `libz` 的现有证据可排除 LLD 22.1.8。`ncurses` 只有布局线索。扫描范围内未发现可归属给 `libtirpc` 的 ELF，可另验发布 RPM。

## 验证一轮新 QuickBuild

1. 记录实际发布的 Unified 和 Base 快照、预期源码 SHA、架构和镜像 profile。确认镜像归档 SHA256 及两个 build manifest。
2. 按镜像、分区和路径盘点 ELF，记录原生文件实例和按 SHA256 去重后的计数。记录实际安装 RPM、发布仓库来源及匹配 debuginfo。
3. 优先用真实链接器标记及目标日志确认用到 LLD 的文件。仍无确证的目标可做 BFD/LLD 对照重放，预编译文件先对账来源。
4. 同时报告整镜像与 Unified RPM 来源分母。实际使用 LLD、确证其他链接器、排除特定版本、结构线索和证据不足分别记录。
5. 如需验收优化或业务运行，另外核对目标的动态段、加载器、ABI 与设备结果。历史镜像的 LLD 确证只覆盖已列出的发布快照。

## ABI 后续

历史数据包含 14 对 GCC/LLVM RPM 对照，10 项 QEMU 启动依赖检查通过。 `libsolv` 有三条版本继承关系差异，四个代表性版本符号在两侧均通过 `dlvsym`。 `app-installers` 有三个由已发布开发头文件声明的构造符号在 LLVM 产物中缺失，已用 `dlsym` 复现。已扫描的现成消费者中未发现这三个导入。两侧 Base 与工具链有差异，需固定其余构建输入才能做单变量归因。整镜像实机启动、WRT 业务、安装卸载与升级尚缺验收记录。

[验证方法](verification-methods.md) · [历史统计](../README.md)
