# Phase 13 · 新 QB 运行回归

**RUNTIME_REGRESSION = PENDING_NEW_IMAGE_DEPLOYMENT。** 已授权的 `private-address-02:26101` 在此次只读检查中响应为 Raspberry Pi 5 AArch64，镜像为 `20261118.083201`。它与目标 RPi4 ARMv7l 新 QB 的型号、架构、release、镜像及模块身份均不匹配。Phase 11 同一地址的归档曾识别到 RPi4 ARMv7l `20261120.082536`，本轮以新采样为准。 [当前原始读取](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [读取回执](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [历史设备记录](../kernel_lld_verification_20261125/11H_RUNTIME_IDENTITY.json)

| 项 | 当前实测 | 新 QB 目标 |
| --- | --- | --- |
| Image BUILD_ID | `tizen-unified-toolchain_20261118.083201_tizen-headed-aarch64` | `tizen-unified-toolchain_20261125.130358` 对应 ARMv7l 镜像 |
| 型号 / 架构 | Raspberry Pi 5 Model B Rev 1.1 / `aarch64` | Raspberry Pi 4 / `armv7l` |
| 内核 release | `6.12.80-arm64-rpi4-v8` | `6.12.80-arm-rpi4-v7l` |
| GNU Kernel Build ID | `5515a1af6c753eea904eb053e361100dc94aa518` | 匹配已发布 SDK 的 `vmlinux` 参考为 `b0449fe7b89ffc0f19584f789e3c73c6240fba28` |
| 已安装 `kdbus.ko` SHA-256 | `88858c0534df8ef339eae94dbc8b60c83b423b1e6b83a6a18791907c3eb6b647` | `1f851deb321d6f9fde822d67ffa17ff0eb3b443349f3ce210c737327116fe860` |
| 已加载 `kdbus` GNU Build ID | `c722ae31605b60b9e2258fea78a800e47c75486c` | 发布 `kdbus.ko` 为 `9527dadadaaf6aae09ce7fb483d2878b857375f6` |

`/proc/version` 和首条 boot banner 均显示 `6.12.80-arm64-rpi4-v8`、`abuild@qb-build-host-03`、Clang 22.1.8、LLD 22.1.8、`Wed Nov 18 09:57:28 UTC 2026`。GNU note 先用设备给出的 SHA-256 校验字节，再解码 Build ID。SDK Build ID 是已归档 SDK 工件的参考，目标启动身份还需部署记录确证。 [结构化身份](evidence/runtime/identity.json) · [SDK Build ID 读取](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [新 QB 模块发布清单](../kernel_lld_verification_20261125/11G_MODULE_INVENTORY_DIFF.csv)

| 阶段 | 本轮结果 |
| --- | --- |
| D1 · 新 QB 启动 | 待部署 |
| D2 · 59 个模块与发布绑定 | 待部署 |
| D3 · 模块运行状态 | 待部署 |
| D4 · 错误与旧基线对照 | 待部署 |
| D5 · 功能回归 | 未执行 |

身份不匹配后结束设备侧检查，未执行设备变更。离线归档只发现用户态 `kdbus-test.debug` 的打包记录，未找到本次设备上已批准且取得结果的功能测试。取得正确部署后，先绑定镜像、内核及 59 个模块，再按获准范围读取启动状态、加载、依赖、引用计数和相关错误。涉及设备状态变更或业务触发的功能测试需要单独授权。新 QB 的持续内存和功能收益仍未测量。 [功能用例离线查找](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [原运行测试计划](../phase11_pm_final_acceptance/PRODUCT_MERGE_REMAINING_TEST_PLAN.md)
