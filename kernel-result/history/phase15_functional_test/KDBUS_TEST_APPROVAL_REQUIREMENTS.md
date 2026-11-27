# Phase 15 · kdbus 功能测试审批要求

本轮只读可行性调查完成。同版本原生用例已发现，等待设备、Kernel Owner 及产品验收范围的确认。`FUNCTIONAL_REGRESSION = NOT_RUN_PENDING_APPROVAL`，`PRODUCT_KDBUS_TRANSPORT_COVERAGE = UNCONFIRMED`，`KERNEL_OWNER_APPROVAL = PENDING`，`PRODUCT_MERGE_READINESS = PENDING`。

| 审批方 | 需要确认的内容 | 批准后允许的操作与影响 |
| --- | --- | --- |
| Kernel Owner / Kernel QA | 确认目标 VCS `1c26a4781d7813abd9ab2fb4c3fad35c52ec8fc8` 的发布 RPM 与测试 ELF 摘要；复核 `hello`、`message-basic`、`sync-reply`、`name-basics`、`byebye` 五项命令、断言及预期负向返回；确认是否有优先的既有获批入口 | 使用同源用例创建临时 kdbus 连接、发送合成消息、登记测试名，并释放测试对象 |
| 设备 Owner / 实验室 | 通过内部记录绑定目标 SDB Serial、目标 QB、预约窗口、普通 SDB 测试账号及允许执行的临时目录；确认设备独占，接受 test bus 的 world-accessible 模式；批准具体监管入口、进程组范围、限时和超时清理 | 个别测试会创建进程、线程及 eventfd。允许在指定临时目录写入一个经校验的 ELF、改为 `0700`、运行并删除。只读采集测试窗口的 `dmesg`，只处置归属本次测试的进程组 |
| PM / 产品 QA | 确认原生 ioctl 五项通过是否足以满足本次产品功能门禁。若必须验证实际产品链路，给出用例 ID、服务、精确调用、账号、可能激活或修改的状态、恢复方式及获批取证工具 | 额外用例和 transport 取证仅按单独批准的范围执行。trace/日志只在内部留存必要的 FD、端点及结果，公开报告使用脱敏摘要 |
| Kernel Owner / PM 合入评审 | Kernel Owner 另行记录已量测构建代价的接受意见，并确认现有 GCC/BFD 验证覆盖目标产品范围。PM 在有效功能结果、运行证据和 Owner 意见齐备后评估产品合入 | 本次可行性归档完成后提交评审，产品合入仍待决策 |

## 变更边界和停测条件

- 默认方案从发布 RPM 在主机提取单个 ELF。RPM 安装、额外工具入机、权限提升、改变安全策略或新挂载均需独立授权。获批执行时使用普通账号，单次运行指定用例。
- 已有 system/user bus、模块、设备启动状态和产品服务配置保持原状。批准的 IPC 仅涉及独立临时 bus；同一挂载中可见的临时节点是已列明的测试副作用。若实验室无法提供独占环境，转交 Owner 评估另行隔离的实验环境。
- 任一设备身份或文件摘要不匹配、用例超时、权限失败、清理不完整、错误触及现有服务或检测到新内核异常时，停止启动后续用例，保留关键日志和当前状态并交回 Owner。无法确认进程组归属时，保持现场。
- 有合规的五项用例和日志证据后，可提交 `DIRECT_KDBUS_FUNCTIONAL` 的结论供审核。产品 transport 的覆盖由产品 QA 审核相应证据；当 PM 明确接受直接内核 IPC 的功能覆盖范围时，将该批准连同结论归档。Owner 通过功能或构建评审的审批记录应分别留存。

需随审批记录归档目标镜像、允许的命令、时间窗、值守方、监管入口、实验设备范围、原始记录存放位置，以及批准的产品覆盖范围。拟执行命令和可预期副作用见 [最小测试方案](KDBUS_FUNCTIONAL_TEST_PLAN.md)。
