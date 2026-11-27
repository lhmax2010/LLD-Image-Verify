# 11H · 设备运行验收

**RUNTIME_VALIDATION = PENDING_NEW_IMAGE_DEPLOYMENT。** 使用当前已授权 SDB 会话只读识别了目标 Raspberry Pi 4。设备 IMAGE BUILD_ID 为 tizen-unified-toolchain_20261120.082536_tizen-headed-armv7l，内核为 6.12.80-arm-rpi4-v7l，运行 banner 为 Linux version 6.12.80-arm-rpi4-v7l (abuild@qb-build-host-01) (clang version 22.1.8, LLD 22.1.8) #1 SMP Fri Nov 20 09:22:45 UTC 2026。本次设备运行证据属于所观察到的镜像。 [原始读数](evidence/runtime/identity-device.out) · [SDB 清单](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

| 身份项 | 实测 |
| --- | --- |
| SDB serial | private-address-02:26101 |
| 架构和型号 | armv7l / Raspberry Pi 4 Model B Rev 1.5 |
| 运行 Kernel GNU Build ID | 99ba05b664f7ece7686ab5f087bf54680bb172e6 |
| 已安装 kdbus.ko SHA256 | 1186ce63d4c7c5f995fd0099becfe8834d52da35939d285f5c0bd9d62042a576 |
| 已加载 kdbus Build ID | b85657c98fa68ebf43a90520861cd8f461c0abad |

设备仍运行旧 QB 时，身份检查后即停止。本次旧设备文件和已加载模块仅用于确认部署状态。新 QB 的启动状态、模块加载及运行兼容性待确认。诊断中 ifconfig 不可用，SDB serial 和设备内 BUILD_ID、DT 型号及经 SHA256 核对的 notes 可用。dmesg 截取首条 banner 导致一条管道诊断，首条内容已保留。 [结构化身份](11H_RUNTIME_IDENTITY.json) · [命令及退出码](evidence/runtime/identity-device.cmd.json)
