# 11D 新 QB 中间链接器工程验证

**E3_ENGINEERING_VERIFIED。** 对新 QB Raspberry Pi 4 ARMv7l 非 RT 的真实构建，`kdbus/kdbus.o` 中间链接和 `kdbus/kdbus.ko` 最终链接分别推导为 `ld.lld`，匹配工具链的链接器为 LLVM LLD 22.1.8。旧外部 Makefile 的 BFD 旁路已删除，已验证构建链中未发现另一条合理的 GNU BFD 执行路径。旧 QB 中间链接器保持 `BFD_PATH_POSSIBLE`。 [机器可读变量追踪](11D_LINKER_VARIABLE_TRACE.json) · [源码和日志规则矩阵](11D_LINKER_RULE_MATRIX.csv)

## 构建参数和 Make 变量

新 job 的包装 SPEC 对 ARM RPi4 导出 `BUILD_kdbus=m`，仅在 Clang 配置导出 `LLVM=1`，然后为非 RT SDK 执行外部模块递归 Make。日志第 427–431 行记录 RPM shell 的 `CC=armv7l-tizen-linux-gnueabi-clang` 和 `MAKEFLAGS += -k`，第 448、458–469 行确认进入上述配置和两级 `make` 命令。组成目标的实际调用无 `LD` 命令行覆盖。完整历史 `MAKEFLAGS`、`CROSS_COMPILE` 和 `PATH` 未打印。 [包装 SPEC](../kernel_lld_verification_20261120/pm_review_round3/evidence/source/external/linux-tizen-modules.spec) · [保留行号的日志摘录](evidence/build/new-wrapper-observed-excerpt.out)

匹配 SDK 的顶层 Makefile 第 425–437 行解析 LLVM 前后缀，`LLVM=1` 无前后缀。第 477–496 行在非空 `LLVM` 分支选择 `CC=clang` 和 `LD=ld.lld`，第 593 行导出 `LD` 给递归 Make。该分支的 `LD` 不依赖 `CROSS_COMPILE`。SDK `.config` 另记录 `CONFIG_LD_IS_LLD=y`、`CONFIG_LLD_VERSION=220108` 和 Clang 版本 22.1.8，它提供同批 SDK 的配置佐证。 [顶层 Makefile](../kernel_lld_verification_20261120/pm_review_round2/evidence/kernel/source/Makefile) · [SDK 配置证据](evidence/build/new-sdk-linker-configuration.out)

## 两次链接分别追踪

| 步骤 | 规则及实际构建结果 |
|---|---|
| 外部 Makefile | `M=<外部源码>` 选择 `KBUILD_EXTMOD`。顶层以 `scripts/Makefile.build` 进入目标目录，对目录内 Kbuild 或 Makefile 进行包含。`BUILD_kdbus=m` 进入 `kdbus/`，经验证的顶层和子目录都没有 `LD` 赋值。 |
| `kdbus.o` 中间链接 | 新 SDK `Makefile.build` 第 432–444 行的 `cmd_ld_multi_m` 调用 `$(LD) $(ld_flags) -r -o $@ @$< $(cmd_objtool)`，输入对象来自 `kdbus-y` 对应的 `.mod` 响应文件。日志第 505 行记录确切组合对象目标，前面独立编译组成对象。 |
| `kdbus.ko` 最终链接 | 顶层 Makefile 第 1886–1889 行单独启动 `Makefile.modfinal`。该文件第 36–40、60–64 行使用所继承的 `$(LD)`、`-r`、`-T scripts/module.lds` 和 `.o` 输入。日志依次记录第 511 行 MODPOST、第 528 行模块元数据对象编译、第 529 行最终链接和第 530 行 BTF。 |
| 发布物 | 非 RT 构建第 550–551 行安装及 strip，同 job 第 746 行写入已发布 RPM。对应已校验 RPM 内 `/lib/modules/6.12.80-arm-rpi4-v7l/extra/kdbus/kdbus.ko` 为 161292 字节，文件 SHA256 `1f851deb321d6f9fde822d67ffa17ff0eb3b443349f3ce210c737327116fe860` 与 RPM 成员摘要一致。 |

上表中的规则文本为匹配 SDK 源码，其展开结果是工程推导。历史 job 在每次链接时解析到的确切路径、argv 和可执行文件哈希仍未恢复。已发布 `.ko` 的存在用于构建链关联，两个链接器身份分别检查。 [中间规则](../kernel_lld_verification_20261120/pm_review_round2/evidence/kernel/source/scripts/Makefile.build) · [最终规则](../kernel_lld_verification_20261120/pm_review_round2/evidence/kernel/source/scripts/Makefile.modfinal) · [11C 原始执行记录查验](11C_INTERMEDIATE_DIRECT_EVIDENCE.md)

## 匹配构建 job 的工具链

新 job 使用 `tizen-base-toolchain_20261030.120529`。实际 job 保留的 `llvm-22.1.8-4.1.armv7l` 和 `clang-accel-x86_64-armv7l-0.4-2.3.armv7l` 均已按此 Base 的 repodata 校验并提取。 [准确版本与候选包](evidence/build/base/toolchain-primary-package-candidates.json) · [链接器负载身份](evidence/build/base/linker-payload-identities.json)

| 候选 | 版本核验 | ELF SHA256 |
|---|---|---|
| ARM 原生 `/usr/bin/ld.lld → /usr/bin/lld` | ARM ELF 内嵌精确字符串 `LLD 22.1.8` | `14141d7469471bc653b6f5521071c038af59a348beb0066c28eaca9ab65715f4` |
| 加速 `/emul/usr/bin/ld.lld` | x86-64 ELF 动态符号确认 LLVM ELF 链接器函数，从版本函数写入的立即数字节恢复 `LLD 22.1.8` | `232f8cee392bbe63ff94d7bb58beb580de080f8e6f8c6263d1ddccb81a540ca3` |

已安装的 GNU `binutils` 和 `qemu-accel` 包提供 `ld` 或 `ld.bfd`，其文件列表没有 `ld.lld`。Unified 的 Rust 和 bootstrap 文件列表虽有额外同名路径，但位于 Rust 内部或镜像 bootstrap 专用目录，日志记录删除 Rust，未选择该 bootstrap 包，也未选择另一个 ARM 原生加速包。源码、已观察的 SPEC 和 Make 入口以及匹配的 SDK 未增加绕过 `LD` 的命令。若要证明某个非归档的 shell 环境覆盖、PATH 重定向或文件替换曾发生，需要实际 job 的补充记录。 [校验后的同名路径范围](evidence/build/base/repository-filelists-linker-paths.json) · [加速链接器版本函数](evidence/build/base/clang-accel-x86_64-armv7l.version-disassembly.out)

```sh
python3 scripts/qb_build_support.py source
python3 scripts/qb_build_support.py linkers
python3 scripts/qb_build_support.py build
```
