# Phase 14 · 产品运行验收

**RUNTIME_REGRESSION = PARTIAL_PASS_FUNCTIONAL_PENDING。** 用户更正后的地址 `private-address-03:26101` 已通过准入，目标为运行 QB `20261125.130358` 的 Raspberry Pi 4 ARMv7l 非 RT。内核正常启动，**59/59** 模块匹配发布 RPM 文件摘要，`kdbus` 的已安装及运行身份一致。功能回归等待获批准的实际用例，产品合入维持 `PENDING`。 [结构化运行结果](evidence/runtime-result.json) · [最终门槛](PRODUCT_MERGE_FINAL_GATE_MATRIX.csv)

## 设备准入和内核身份

| 项 | Phase 14 实测 |
| --- | --- |
| SDB Serial | `private-address-03:26101` |
| 型号 | Raspberry Pi 4 Model B Rev 1.5 |
| 架构、Kernel Release | `armv7l`、`6.12.80-arm-rpi4-v7l` |
| Image BUILD_ID | `tizen-unified-toolchain_20261125.130358_tizen-headed-armv7l` |
| 运行 GNU Kernel Build ID | `8d5da0f28ffc7a57a290127a26fc17cbbd103558` |
| `/proc/version` 与启动 banner | `abuild@qb-build-host-02`，Clang 22.1.8，LLD 22.1.8，Wed Nov 25 14:04:26 UTC 2026 |

运行内核的完整 84 字节 GNU/Linux notes 与 `/proc/version` 文本在已校验的发布内核 RPM `arm-rpi4-linux-kernel-6.12.80-0.armv7l.rpm` 中的 `/boot/zImage` 解压载荷里均唯一命中。运行 Build ID 与 Phase 13 读取的 SDK `vmlinux` 参考 ID 不同，本次用引导 RPM 的实际字节建立运行身份。前一阶段 `.13` 的设备观察保留在其原归档。 [设备原始身份](evidence/device-identity.out) · [SDB 回执](evidence/device-identity.cmd.json) · [发布内核身份绑定](evidence/release/kernel-identity.json)

## 启动、模块和日志

- **启动 PASS。** systemd 状态为 `running`，`sysinit.target`、`basic.target`、`multi-user.target` 和 `graphical.target` 均为 `active`，失败单元数为 0。 [启动与原始内核日志](evidence/device-boot.out)
- **模块清单 59/59 PASS。** 设备 release 目录中 52 个树内、7 个树外模块的相对路径和 SHA-256 全部匹配新 QB 已校验 RPM 的成员，无额外目标模块或模块 symlink。活动 RPM DB 对两个发布包查询均返回未安装，绑定依据为设备文件和发布 RPM 成员的直接摘要。 [逐模块 RPM 关联](evidence/module-runtime-to-rpm.csv) · [原始文件与 RPM DB 查询](evidence/device-modules.out)
- **kdbus 状态 PASS。** 已安装文件 SHA-256 为 `1f851deb321d6f9fde822d67ffa17ff0eb3b443349f3ce210c737327116fe860`，已加载 GNU Build ID 为 `9527dadadaaf6aae09ce7fb483d2878b857375f6`。两者均匹配发布。模块已加载为 `live`，引用数 98，`/proc/modules` 未列依赖，holders 为空，`kdbusfs` 已挂载在 `/sys/fs/kdbus`。可见 `control` 和现有 system、user 目录。 [模块状态原始读取](evidence/device-kdbus.out) · [已发布模块记录](../kernel_lld_verification_20261125/11F_MODULE_ABI_SUMMARY.json)
- **当前可读内核日志 PASS。** `dmesg` 从启动开头起共 548 行，包含 `[2.469537] kdbus: initialized`。未匹配到模块加载、未知符号、格式/版本或重定位错误、kdbus 错误、Oops、panic、Call Trace。日志另有 WLAN 固件及超时、SMACK 拒绝等记录，当前证据未将它们归因到此修改。内核 journal 因会话权限不足而不可读取。 [错误规则与命中](evidence/kernel-log-review.json) · [原始读取与退出信息](evidence/device-boot.out)

## 与旧 QB 的可比对照

旧 RPi4 ARMv7l QB `20261120.082536` 的同型内核 release、Clang/LLD 版本相同，运行 GNU Kernel Build ID 为 `99ba05b664f7ece7686ab5f087bf54680bb172e6`。旧、新各自对对应 RPM 的设备模块均为 59/59 匹配，跨 QB 的六个树外文件逐字节一致。旧、新 `kdbus` 均观测为 `Live`、引用数 98、`/proc/modules` 报告 98,304 Bytes，各自 Build ID 与各自发布模块匹配。旧档初始已加载模块数为 10，后续清单为 11，较当前采样多 `binfmt_misc`。这是不同采样时刻的状态。旧档主要保留 banner、模块指纹与加载快照，缺少与本轮同口径的完整启动日志。运行内存收益未测量。 [旧机身份与绑定](../kernel_lld_verification_20261120/06_repository_runtime_mapping.md) · [旧加载模块快照](../kernel_lld_verification_20261120/05_loaded_module_mapping.csv) · [本轮结构化对照](evidence/runtime-result.json)

## 功能用例与复核

**FUNCTIONAL_REGRESSION = NOT_RUN_NO_APPROVED_CASE_AVAILABLE。** 设备上核对的两个标准候选路径均无 `kdbus-test`，现有归档仅见测试 debuginfo 发布记录。执行功能回归需要可用且已批准的测试命令、测试身份和必要操作授权。应记录针对目标设备的实际用例、退出状态、行为结果和测试期间内核日志，再与可比旧 QB 结果核对。已观察的初始化、挂载和现有引用列入模块运行状态。 [测试路径读取](evidence/device-kdbus.out) · [测试包归档记录](../kernel_lld_verification_20261125/11A_PREFLIGHT.md#evidence-gaps)

在 `phase14_product_runtime_acceptance/` 内使用 `sha256sum -c --quiet SHA256SUMS` 检查本轮归档。用独立副本运行 `python3 -B scripts/review_runtime.py`，从原始输出与固定发布载荷复算。原始命令、输出、错误和退出码以 `.cmd.json`、`.out`、`.err` 成组保存。 [复核脚本](scripts/review_runtime.py) · [设备只读命令](scripts/read_device_runtime.sh)
