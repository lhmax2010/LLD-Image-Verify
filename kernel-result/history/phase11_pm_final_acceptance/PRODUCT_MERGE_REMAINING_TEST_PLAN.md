# LLD-KERNEL-001 · 产品合入剩余测试计划

产品合入准备状态为 **PENDING**。本计划保留 PM 指定的三项工作。Phase 11 工程验收为 **PASS**，工程问题已 **CLOSED**。本轮执行范围仅为归档。刷机、新构建及合入正式产品分支均需另行授权。 [PM 决策](PM_PHASE11_FINAL_ACCEPTANCE.md)

## 1. 新 QB Runtime Regression

**当前状态 `PENDING_NEW_IMAGE_DEPLOYMENT`。** 上次只读核对识别到的设备运行 `20261120.082536`。待已授权部署的设备可用后，在匹配的 Raspberry Pi 4 ARMv7l 非 RT 配置上执行。 [已归档设备身份](../kernel_lld_verification_20261125/11H_RUNTIME_VERIFICATION.md)

1. 记录设备型号、镜像 BUILD_ID、内核 release、Build ID 和启动日志。用新 QB 发布记录和设备身份确认实际运行 `20261125.130358`。新旧 QB 的 kernel release 相同，使用镜像身份与模块摘要作区分。
2. 核对部署的 `kdbus.ko` 与已验证的新 QB RPM 成员。预期 SHA-256 为 `1f851deb321d6f9fde822d67ffa17ff0eb3b443349f3ce210c737327116fe860`。确认正常启动、模块加载情况和内核日志，检查模块加载失败、版本不符、未知符号或重定位错误。按产品的已授权流程覆盖正常 kdbus 使用路径，保留执行结果。
3. 归档设备身份、发布包映射、模块状态、测试步骤和日志。以新镜像身份确认、部署模块匹配、正常使用路径通过且无相关错误为通过条件。若设备仍为旧 QB 或模块使用路径尚未覆盖，继续记为待验证并注明缺口。 [新模块身份与摘要](../kernel_lld_verification_20261125/11D_LINKER_VARIABLE_TRACE.json)

## 2. 真实 GCC/BFD Build Regression

**当前状态 `PENDING`。** Phase 11 已验证 GNU Make 模拟。收到另行授权后，利用正常产品构建流程验证真实路径。 [模拟矩阵](../kernel_lld_verification_20261125/11E_REPRODUCTION_RESULTS.csv)

1. 固定 RPi4 ARMv7l 非 RT 产品配置、候选提交、匹配 SDK、GCC/BFD 工具链版本和构建参数。按实际产品流程选用 GCC/BFD，记录配置与解析到的工具身份。
2. 在该配置下完成外部模块构建，核实 `kdbus.o` 中间链接和 `kdbus.ko` 最终链接均尊重产品配置选定的 GNU BFD。记录实际命令、模块产物和包摘要。
3. 核对模块 ELF、`vermagic`、导入符号与版本 CRC 对其匹配 SDK 的兼容性，并记录意外链接错误、符号差异和重定位差异。以构建完成、GNU BFD 选择正确且无未解释的关键 ABI 回归为通过条件。 [静态对照方法](../kernel_lld_verification_20261125/11F_MODULE_BINARY_COMPARISON.md)

## 3. 后续正常构建的 E4 Evidence Collection

**当前状态待后续正常构建。** Phase 11 的两个链接步骤均保留 E3。历史 QB 的严格验收维持 `CONDITIONAL_PASS`。 [历史直接证据缺口](../kernel_lld_verification_20261125/11C_INTERMEDIATE_DIRECT_EVIDENCE.md)

1. 在后续正常 LLVM/LLD 作业中记录源码提交、作业 ID、SDK、工具链包、构建参数和环境中的实际 PATH。保存 `kdbus.o` 与 `kdbus.ko` 对应的详细 Kbuild 命令、完整 argv、响应文件及构建目录上下文。
2. 由构建执行记录确认每步实际运行的链接器绝对路径、版本和 SHA-256，并保留执行成功或退出码。将记录分别关联到中间对象、最终模块和交付 RPM 的摘要。
3. 保留原始证据与作业信息。实际成功执行证据及完整产物链齐备时，按该次作业评定 E4。下一次作业的证据只支持该次作业，历史 QB 的 E4 缺口继续独立跟踪。 [E3 链路与证据边界](../kernel_lld_verification_20261125/11D_INTERMEDIATE_LINKER_CAUSAL_ANALYSIS.md)
