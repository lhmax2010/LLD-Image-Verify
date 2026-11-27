# Phase 11A — Preflight 与 QB 身份验证

**结论 `PASS`。** 新 QB `tizen-unified-toolchain_20261125.130358` 发布了 RPi4 ARMv7l 非 RT 的外部模块构建。目标 RPM 与旧 QB `tizen-unified-toolchain_20261120.082536` 同名、同 NEVRA，SHA-256 已变化。两次独立的成功构建日志均列出该 RPM。新旧 Kernel Release、开发包 `.config`、生成的 Clang/LLD 版本均相同，基础 QB 和构建工具 RPM release 有变化。[机器可读身份记录](11A_QB_IDENTITY.json) · [RPM 清单](11A_RPM_INVENTORY.csv)

## 发布仓库与平台匹配

- HTTP GET 使用 Tizen 官方发布站点的 HTTPS 固定版本路径。根目录、`build.xml`、`builddata/`、`repos/standard/` 可访问。`build.xml` 报告新 QB ID 和 ARMv7l 架构。`packages`、`debug`、`source` 三个区域的 `repomd.xml` 和六份 `primary` / `filelists` 已归档。六份文件的压缩 SHA-256、解压 SHA-256 和压缩大小与各自 `repomd.xml` 匹配。三个元数据分离签名路径都返回 HTTP 404，验证依据为 HTTPS 发布来源和摘要匹配。[发布仓库](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261125.130358/) · [发布身份](evidence/repository/build-identity.out) · [标准仓库目录](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
- 按包架构、名称和 filelists 中的 `/lib/modules/6.12.80-arm-rpi4-v7l/` 锁定目标。树内模块 RPM 列出 52 个模块，树外模块 RPM 列出 7 个，包括 `extra/kdbus/kdbus.ko`。RT、原生 AArch64 和通过 ARMv7l RPM 封装的 AArch64 命中项保留在清单中供排除核对。[RPM 清单](11A_RPM_INVENTORY.csv)
- 从新发布下载 5 个所需 RPM，包括 Kernel SDK、树内与树外模块包、实现源码载体、实现 SRPM。Kernel SRPM 与模块包装 SRPM 复用旧归档中字节相同的文件，均按新发布清单重新校验。七个输入的 SHA-256、`rpm -Kv` 摘要、RPM header 身份和 VCS 比对通过。[获取与校验回执](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## 新旧 QB 对比

| 项目 | 旧 QB | 新 QB |
| --- | --- | --- |
| 基础 QB | `tizen-base-toolchain_20261119.042539` | `tizen-base-toolchain_20261030.120529` |
| Kernel Release | `6.12.80-arm-rpi4-v7l` | `6.12.80-arm-rpi4-v7l` |
| `linux-rpi` manifest / RPM VCS | `42aeefac58edeb081aff440f0b60be71cbe49755` | `42aeefac58edeb081aff440f0b60be71cbe49755` |
| `linux-tizen-modules` 包装 manifest / RPM VCS | `458baad02d812098938663971d1b8560a4813375` | `458baad02d812098938663971d1b8560a4813375` |
| `linux-tizen-modules-source` 实现 manifest / RPM VCS | `25797e8af7ed95a5783bbe84c11959560aaf7e92` | `1c26a4781d7813abd9ab2fb4c3fad35c52ec8fc8` |
| SDK `compile.h` | Clang `22.1.8`，LLD `22.1.8` | Clang `22.1.8`，LLD `22.1.8` |
| `clang` / `llvm` 构建依赖 | `22.1.8-1.6` | `22.1.8-4.1` |
| `clang-accel` / `qemu-accel` 构建依赖 | `0.4-1.1` | `0.4-2.3` |
| GNU binutils / make | `2.43-1.8` / `4.4.1-1.6` | `2.43-1.16` / `4.4.1-1.14` |
| `gcc` / `glibc` / `rpm` 构建依赖 | `14.2.0-1.7` / `2.40-1.8` / `4.14.1.1-1.8` | `14.2.0-1.14` / `2.40-2.5` / `4.14.1.1-1.9` |
| 目标 `linux-tizen-modules-rpi4-11.0.0-0.armv7l.rpm` SHA-256 | `ee434f5a9545811fa060f3dfc3b45be7bd4e3e0a09cb5d9b9c2e810d32dd87aa` | `92a3a372dd9ead740720f209918c27a88f04329c3a2a45d62c4196762954a2de` |

- 开发包 `.config` 全文件按字节一致，SHA-256 为 `688e66c3d0c2e31c09fb563d9905420475319787c4d6764cd7b7e210a4f6d33c`。其中 `CONFIG_ARM=y`、`CONFIG_PREEMPT_RT` 未启用、`CONFIG_LD_IS_LLD=y`、`CONFIG_LLD_VERSION=220108`、`CONFIG_MODVERSIONS=y`、`CONFIG_LTO_NONE=y`。`include/generated/utsrelease.h` 字节一致。`compile.h` 的构建主机标识发生变化。[新 SDK `.config`](../kernel_lld_verification_20261120/pm_review_round2/evidence/kernel/source/.config) · [新编译器记录](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [SDK 提取清单](evidence/repository/sdk-selection.out)
- 新 manifest 中的实现源码版本与 Phase 10 已验证的 Sandbox 修复提交一致。具体打包源码、SPEC 和 `%prep` 的核验见 11B。[新 manifest](evidence/repository/manifest.out) · [Phase 10 提交摘要](../phase10_kdbus_sandbox/KDBUS_LD_FIX_SUBMISSION_SUMMARY.json)
- 新旧外部模块日志中可见的非 RT 配置参数相同，包括 `LLVM=1`、`BUILD_kdbus=m`、`MAKEFLAGS+= -k`、ARMv7l Clang 包装器、`CFLAGS_MODULE`、`KERNELDIR` 和选取的构建入口命令。基础 QB、依赖 RPM release、构建主机、时间和 scratch 路径变化均影响新旧对比的归因。日志工具版本针对构建依赖，完整的每个目标参数和历史实际可执行文件需要 11C 的直接记录。[新外部模块日志](evidence/build/linux-tizen-modules-armv7l.out) · [旧外部模块日志](../kernel_lld_verification_20261120/evidence/build/linux-tizen-modules-armv7l.out) · [基础 QB 工具元数据](evidence/build/base/matched-metadata.json)

## 构建日志与 RPM 的关联

三个日志来自新 QB 的 `standard/armv7l/succeeded`。每条 RPM 清单行保存 NEVRA、SRPM、VCS、发布 URL、发布与本地 SHA-256、校验状态及可匹配的日志行。RPM `Build Time` 表头与 Primary 的值为 `0`，`metadata_file_time_utc` 是仓库文件时间。以下起止时间来自 job 日志。

| 构建包 | 2026-11-25 UTC | job `BUILD_ROOT` 末尾 | 对应 `Wrote` 日志行 |
| --- | --- | --- | --- |
| `linux-tizen-modules-source` | 13:08:26–13:13:01 | `scratch.armv7l.4` | 766–767 实现 SRPM 与源载体 RPM |
| `linux-rpi` | 13:34:46–14:44:39 | `scratch.armv7l.24` | 15234、15236、15238、15240、15246 分别为 Kernel SRPM、镜像、树内模块、SDK 及核心 debuginfo |
| `linux-tizen-modules` | 14:44:43–14:46:56 | `scratch.armv7l.0` | 744 包装 SRPM、746 目标非 RT ARMv7l 模块 RPM |

仓库 Primary 的 VCS 和 `Wrote` 的精确包名相符，下载的目标模块与新仓库摘要相符。旧日志自身也在第 853 行生成同名目标包，起止时间为 2026-11-20 10:42:48–10:45:07 UTC，旧发布摘要与新摘要不同。这些记录支持目标模块已随新 QB 重新构建。SRPM 的 `Wrote` 仅提供名称和同仓库 VCS 的关联，成功日志未公布每个输出文件的摘要。[实现日志](evidence/build/linux-tizen-modules-source-armv7l.out) · [Kernel 日志](evidence/build/linux-rpi-armv7l.out) · [包装日志](evidence/build/linux-tizen-modules-armv7l.out)

## Evidence Gaps

- 新镜像 `arm-rpi4-linux-kernel-6.12.80-0.armv7l.rpm`（17,596,028 字节）与核心 `arm-rpi4-linux-kernel-devel-debuginfo-6.12.80-0.armv7l.rpm`（75,868,128 字节）的发布 URL、SHA-256、VCS 与日志关联已确认，包体未下载。11A 的版本和配置比对使用匹配的 SDK，11H 另行记录设备身份。[RPM 清单](11A_RPM_INVENTORY.csv) · [核心 debuginfo filelist](evidence/repository/filelists/arm-rpi4-linux-kernel-devel-debuginfo-6.12.80-0.armv7l.rpm.txt) · [设备身份](11H_RUNTIME_VERIFICATION.md)
- 三个区域的发布 filelists 均无目标 `kdbus.ko.debug`、中间 `kdbus.o` 或 `.kdbus.o.cmd` 条目。`linux-tizen-modules-debugsource` 的发布记录未列出文件。`linux-tizen-modules-source-debugsource` 列出源码文件，`linux-tizen-modules-tests-debuginfo` 包含用户态 `kdbus-test.debug`。未获取历史 Build Root 的内部文件，实际执行链接器的证明由 11C 单独评级。[实现 debugsource filelist](evidence/repository/filelists/linux-tizen-modules-source-debugsource-11.0.0-0.armv7l.rpm.txt) · [用户态测试 debuginfo filelist](evidence/repository/filelists/linux-tizen-modules-tests-debuginfo-11.0.0-0.armv7l.rpm.txt)

## 本地复核

在 Phase 11 目录执行以下命令。步骤复用保存在本目录的仓库元数据、日志和 RPM，并读取旁边的 Phase 10 与旧 QB 归档。第一条命令可补取缺失的目标 RPM，下载使用固定 QB 的 HTTPS GET。命令参数、退出状态、原始标准输出及错误见同名 `.cmd.json`、`.out` 和 `.err`。第三条命令输出新旧 `.config`、编译标记、可见构建参数、日志关联与工具包的比较数据。

```bash
python3 -B scripts/record_review.py evidence/repository/repository-acquisition python3 -B scripts/qb_repo.py
python3 -B scripts/record_review.py evidence/repository/sdk-selection bash scripts/extract_qb_sdk.sh
python3 -B scripts/record_review.py evidence/repository/identity-comparison python3 -B scripts/complete_qb_identity.py
```
