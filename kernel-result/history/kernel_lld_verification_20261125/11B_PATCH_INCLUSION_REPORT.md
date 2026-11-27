# 11B 修复纳入新 QB 的验证

**PATCH_INCLUDED。** 新 QB `tizen-unified-toolchain_20261125.130358` 的 Raspberry Pi 4 ARMv7l 非 RT 外部模块构建使用含本次修复的源码。旧、新 QB 的源码提供 RPM 各有 53 个 `/usr/src/linux-tizen-modules-source/` 文件，全部与各自 RPM 成员 SHA256 匹配。逐文件对比只有顶层 `Makefile` 不同，差异仅一行。 [来源与摘要](11B_SOURCE_PROVENANCE.json) · [逐行差异](11B_SOURCE_DIFF.patch)

```diff
-LD = ${CROSS_COMPILE}ld
```

| 链路 | 核验结果 |
|---|---|
| Phase 10 提交 | 已归档的认证 Git 验证记录确认 Sandbox 分支包含修复 `1c26a4781d7813abd9ab2fb4c3fad35c52ec8fc8`。本地 Git 对象的父提交为历史实现 `25797e8af7ed95a5783bbe84c11959560aaf7e92`，Change-Id 为 `Ic0b9efb5c514bb6e18dbc270aa269211ec514375`，Git 差异只有 `kernel/Makefile`。 |
| 新 QB 发布源版本 | 新 QB 发布 manifest 第 488 行和新源码提供 SPEC 第 2 行、源码提供二进制 RPM VCS 字段均确认包含修复的实现提交。旧 QB 的 manifest 和源码提供 RPM VCS 确认历史实现。 |
| 实际发布的源码提供包 | 新 `linux-tizen-modules-source-11.0.0-0.src.rpm` 和 ARMv7l 源码提供 RPM 由对应新 QB repodata 校验。新 Source0 tarball 内 53 个对应文件逐字节匹配已展开的二进制 RPM 负载。旧、新顶层和子目录 Makefile 逐字节匹配各自 Git 对象。 |
| 实际构建源码准备 | 源码提供 SPEC 第 48–51 行和该 job 日志第 634 行等记录把源码装入 `/usr/src/linux-tizen-modules-source`。模块打包 SPEC 第 156–159 行执行 `%setup` 后复制该目录到 `./kernel`，新模块 job 第 370 行记录安装该依赖，第 396–402 行记录解包与复制。第 460 行的 Makefile 修改仅移除指定编译告警选项。 |
| 回引和旁路检查 | 新 QB 的两份 SPEC 和 Source0 归档的 Makefile、Kbuild、SPEC、构建脚本和补丁文件清单均已扫描。模块打包 Source0 内没有预置 `kernel/` 源文件。未发现重新引入 `LD`、显式 `ld` 或 `ld.bfd`、SPEC 的 `LD` 覆盖、补丁应用或替代链接命令。 |

模块打包仓库仍为 `platform/kernel/linux-tizen-modules` 的 `458baad02d812098938663971d1b8560a4813375`。该包装 SRPM 的 SHA256 与旧 QB 归档完全相同，按新 QB 元数据重验后复用。实现源码变化来自独立仓库 `platform/kernel/linux-tizen-modules-source`。 [新发布 manifest](evidence/repository/manifest.out) · [源码提供 SPEC](evidence/source/new/provider-srpm/linux-tizen-modules-source.spec) · [模块打包 SPEC](../kernel_lld_verification_20261120/pm_review_round3/evidence/source/external/linux-tizen-modules.spec) · [实际模块构建日志](evidence/build/linux-tizen-modules-armv7l.out)

本轮重查 Gerrit Sandbox 分支时，当前 SSH 环境返回 `Permission denied (publickey)`。Phase 10 的认证查验可复核，当前分支 HEAD 未复验。新 QB 的固定源码结论以其发布 manifest、SRPM、源码提供 RPM 实际成员和构建流程交叉确认。历史 job 的实时构建目录不可访问，源码准备通过发布负载和成功构建日志复核。 [Phase 10 归档](../phase10_kdbus_sandbox/KDBUS_LD_FIX_SUBMISSION_SUMMARY.json) · [本轮 SSH 读取回执](evidence/source/phase10-git-sandbox-head.cmd.json) · [错误输出](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

```sh
python3 scripts/qb_build_support.py source
```
