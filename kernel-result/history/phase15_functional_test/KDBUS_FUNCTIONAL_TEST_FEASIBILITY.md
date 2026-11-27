# Phase 15 · kdbus 功能测试可行性

**发现同版本原生测试。** 新 QB 发布了 `kdbus-test` 的 ARMv7l 可执行 RPM、对应 debuginfo 和 SRPM。测试与设备上的 kdbus 模块同源，可以作为受控实验设备上的功能回归候选。设备当前未安装该测试，本轮仅执行了只读检查。`FUNCTIONAL_REGRESSION = NOT_RUN_PENDING_APPROVAL`，`PRODUCT_KDBUS_TRANSPORT_COVERAGE = UNCONFIRMED`，`PRODUCT_MERGE_READINESS = PENDING`。

## 目标设备复核

| 项目 | 本轮只读结果 |
| --- | --- |
| 设备及镜像 | 通过已授权的 SDB 端点，核对 Raspberry Pi 4 Model B Rev 1.5、`armv7l`、Non-RT、`BUILD_ID=tizen-unified-toolchain_20261125.130358_tizen-headed-armv7l` |
| 内核 | `6.12.80-arm-rpi4-v7l`，`/proc/version` 及启动日志报告 Clang/LLD 22.1.8；运行中 Build ID `8d5da0f28ffc7a57a290127a26fc17cbbd103558` 与 Phase 14 发布内核绑定一致 |
| kdbus | `/proc/modules` 状态 `Live`，运行中 Build ID `9527dadadaaf6aae09ce7fb483d2878b857375f6`，安装文件 SHA-256 `1f851deb321d6f9fde822d67ffa17ff0eb3b443349f3ce210c737327116fe860`，均与 Phase 14 一致 |
| kdbusfs | `/sys/fs/kdbus` 已挂载，并有现有系统和用户 bus；`control` 节点权限位为 `0666`。SDB shell 为非 root，`CapEff=0`。实际 bus 创建是否受运行策略拦截，留待获批执行确认 |
| 工具与依赖 | 测试包、debuginfo 及两个常见 `kdbus-test` 可执行路径均未发现；已核对测试所需的 ELF 解释器及共享库文件可见。`dmesg` 可读。`strace`、`timeout` 和 Toybox 的 `timeout` applet 不可用 |

设备身份绑定沿用 Phase 14 已审核的发布证据。此次重新核对内核和 kdbus 身份，59 个模块的逐文件核对见原归档。 [Phase 14 运行报告](../phase14_product_runtime_acceptance/PHASE14_RUNTIME_REGRESSION_REPORT.md)

## 发行物及目标 UAPI

从 QB `standard` 的 `packages`、`debug`、`source` 仓库 `primary` 与 `filelists` 解析候选，先用各自 `repomd.xml` 校验压缩和解压后的元数据摘要，再核对下面的实际 RPM 字节。测试、debuginfo、headers 的 VCS 均指向 `platform/kernel/linux-tizen-modules-source#1c26a4781d7813abd9ab2fb4c3fad35c52ec8fc8`，三个二进制包的 Source RPM 均是下表所列 SRPM。

| 发布制品 | RPM SHA-256 |
| --- | --- |
| [linux-tizen-modules-tests-11.0.0-0.armv7l.rpm](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261125.130358/repos/standard/packages/armv7l/linux-tizen-modules-tests-11.0.0-0.armv7l.rpm) | `1c607b3d98d1cdfd811612d8ea634ec9deed32259c01570a1011b0973db28882` |
| [linux-tizen-modules-tests-debuginfo-11.0.0-0.armv7l.rpm](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261125.130358/repos/standard/debug/linux-tizen-modules-tests-debuginfo-11.0.0-0.armv7l.rpm) | `1aa1af307ae3a3072bf98b49685ba3d1beac08e8670c21f31ead1540562bd589` |
| [linux-tizen-modules-source-11.0.0-0.src.rpm](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261125.130358/repos/standard/source/linux-tizen-modules-source-11.0.0-0.src.rpm) | `16149cc7e6ee1f790f82cc0697694c8ec89cd960149fd705494cc01d2a59dc88` |
| [linux-tizen-modules-headers-11.0.0-0.armv7l.rpm](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261125.130358/repos/standard/packages/armv7l/linux-tizen-modules-headers-11.0.0-0.armv7l.rpm) | `a00355fc660479fc7165971a13a0f64bba298db405d3cc83d01545be6f09f3a8` |

- **测试入口。** SRPM 内 `tests/kdbus/` 的 28 个 Git 路径与目标提交逐字节相同。RPM 提供 `linux-kernel-kdbus-tests`，入口是 `/usr/libexec/linux-tizen-modules-source/tests/kdbus-test`。发布日志及 `tests/kdbus/Makefile` 显示其使用同一源码树的 `include/uapi`，按 ARMv7l 编译并链接。测试入口可用 `-l` 列出用例，`-f -t CASE` 执行单个用例。包构建日志记录了编译与打包，未提供设备功能执行结果。尚未取得 Kernel Team 对此入口和五项用例的内部批准记录或其他内部测试清单。 [目标 QB 测试构建日志](../kernel_lld_verification_20261125/evidence/build/linux-tizen-modules-source-armv7l.out#L465)
- **头文件绑定。** SRPM、同版本 headers RPM、Phase 11 已绑定的模块 provider RPM，以及目标 Git 提交中的 `linux/kdbus.h` 逐字节一致，SHA-256 为 `7774b1f57127a36b1f537117eab4ca5061eb4b7ac290003f2acf77091722e9db`。同发行源、头文件和真实构建命令共同支持测试 UAPI 匹配。
- **二进制与调试符号。** 可执行文件为 ELF32 ARM，解释器 `/lib/ld-linux.so.3`，文件 SHA-256 为 `c9df48f29c59562b3bc6b755c5ed89d90ab879334e0c032eeb6ed5fd6ea751fe`。`kdbus-test` 和 `kdbus-test.debug` 均无 GNU Build ID。可执行文件的 `.gnu_debuglink` 指向 `kdbus-test.debug`，其中 CRC32 `d8bdb394` 与 debuginfo RPM 实际成员一致。

## D-Bus、GLib 与产品覆盖

| 候选 | 核对结果 | 本轮判定 |
| --- | --- | --- |
| `dbus-tests-1.12.20-3.armv7l` | QB 发布 `/usr/lib/dbus-tests/runner/dbus-tests`，包内有 daemon、monitor、FD passing 等用例。匹配 SRPM 的 spec 单独构建 kdbus 扩展；常规构建打包测试。Tizen 的用户会话配置存在可依次尝试 `kernel:` 与 `unix:` 的设置。设备未安装该测试包 | 未建立具体用例的实际 kdbus 路径 |
| `glib2-tests-2.80.5-0.armv7l` | QB 发布 `/usr/lib/dbus-tests/runner/glib-tests`，包括 `gdbus-peer`、`gdbus-message` 等。设备有匹配版本的 `libgio-extension-kdbus`，测试包未安装 | 未建立具体用例的实际 kdbus 路径 |
| `libdbuspolicy-tests-1.2.0-0.armv7l` | QB 发布 `/usr/lib/dbus-tests/runner/libdbuspolicy-tests`，包含 method call、ownership 与 signal 测试。随包 `system.conf` 指向已存在的 system kdbus 端点及 Unix socket 备选，目标机未安装该测试包 | 涉及系统 bus 路径，超出临时测试 bus 方案；目前没有证明单次测试调用经过 kdbus |
| 已装客户端工具及产品测试 | 发现 `dbus-send`、`dbus-monitor`、`dbus-run-session` 和 `busctl`。对已知测试目录、常见 system D-Bus Unix 监听路径及可见的 D-Bus daemon 线索做了限定范围的只读查询，未取得端到端连接或 ioctl 证据 | 产品用例、服务、调用身份和实际 transport 仍待产品 QA 确认 |

D-Bus SRPM 提到了 `dbus-integration-tests` 依赖场景。目标 QB 的 `standard` 仓库元数据未列出该名称的独立 RPM。`dbus-tools` 发布包还包含策略检查器。它可以检查策略文件，无法替代一次真实 IPC 往返。项目归档和可检查的公开发布制品提供了原生及中间件测试入口，当前证据不足以确认已有产品功能测试实际覆盖 kdbus。 [D-Bus SRPM](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261125.130358/repos/standard/source/dbus-1.12.20-3.src.rpm) · [D-Bus 测试包](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261125.130358/repos/standard/packages/armv7l/dbus-tests-1.12.20-3.armv7l.rpm) · [策略测试包](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261125.130358/repos/standard/packages/armv7l/libdbuspolicy-tests-1.2.0-0.armv7l.rpm) · [GLib 测试包](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261125.130358/repos/standard/packages/armv7l/glib2-tests-2.80.5-0.armv7l.rpm)

首选已发布的同源原生测试。它用测试自己创建的 bus 执行 kdbus ioctl，能直接覆盖内核 IPC。若产品验收要求覆盖特定服务，需要为同一次已批准的产品调用单独绑定请求、应答和实际 kdbus transport。执行方案和权限见 [最小测试方案](KDBUS_FUNCTIONAL_TEST_PLAN.md) 及 [审批要求](KDBUS_TEST_APPROVAL_REQUIREMENTS.md)。
