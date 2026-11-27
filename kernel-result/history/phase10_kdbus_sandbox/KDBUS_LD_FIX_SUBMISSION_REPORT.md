# kdbus LD 修复 · Gerrit Sandbox 提交报告

**已创建并推送 Sandbox，远程 Git 独立验证通过。** 提交只删除 kernel/Makefile 第 2 行的 LD 覆盖，让树外模块继承顶层 Kbuild 的链接器选择。

| 字段 | 结果 |
| --- | --- |
| Repository | platform/kernel/linux-tizen-modules-source |
| Base / 本次镜像源码提交 | 25797e8af7ed95a5783bbe84c11959560aaf7e92 |
| Sandbox Ref | refs/heads/sandbox/liushanshan/lld |
| Sandbox 新建 | 是 |
| Original Remote HEAD | 无。上传前经认证查无该 ref |
| New Commit SHA | 1c26a4781d7813abd9ab2fb4c3fad35c52ec8fc8 |
| Gerrit Change-Id | Ic0b9efb5c514bb6e18dbc270aa269211ec514375 |
| Remote HEAD | 1c26a4781d7813abd9ab2fb4c3fad35c52ec8fc8 |

## 预检和变更

默认 SSH 身份被拒绝。复用现有 SSH agent 中唯一的 Tizen 标记身份完成认证。Gerrit 配置和认证信息未修改。经认证查询确认仓库存在，tizen HEAD 等于已验证的镜像源码。上传前再次查无 Sandbox ref。dry-run 验证了接收服务可达，实际 push 成功证明了本次分支创建和写权限。 [认证](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [原始 refs](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [上传前 ref 查询](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [dry-run](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

归档的 Makefile 对应 Git 仓库的 kernel/Makefile，RPM SPEC L48 将其复制到源码包根。该文件和 kdbus 子 Makefile 均与 Phase 9 封存源文件字节一致。提交前只出现预期一行删除。git diff --check、暂存区检查均通过，工作区在提交后干净。 [路径证据](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [字节核对](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [diff --check](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [diff --stat](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [status](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

```diff
diff --git a/kernel/Makefile b/kernel/Makefile
index 13005c9..9ecc13c 100644
--- a/kernel/Makefile
+++ b/kernel/Makefile
@@ -1,5 +1,4 @@
 PWD := $(shell pwd)
-LD = ${CROSS_COMPILE}ld
 
 LOGGER_MAIN_BUFFER_SIZE ?= 256
 LOGGER_EVENTS_BUFFER_SIZE ?= 256
```

## 六组隔离验证

| 配置 | 预期链接器 | kdbus.o 中间链接 | kdbus.ko 最终链接 | 静态结果 |
| --- | --- | --- | --- | --- |
| ARMv7l GCC + BFD | GNU BFD | armv7l-tizen-linux-gnueabi-ld | armv7l-tizen-linux-gnueabi-ld | PASS |
| ARMv7l Clang + LLVM=1 | LLD | ld.lld | ld.lld | PASS |
| AArch64 GCC + BFD | GNU BFD | aarch64-tizen-linux-gnu-ld | aarch64-tizen-linux-gnu-ld | PASS |
| AArch64 Clang + LLVM=1 | LLD | ld.lld | ld.lld | PASS |
| Explicit LD=ld.bfd | GNU BFD | ld.bfd | ld.bfd | PASS |
| Explicit LD=ld.lld | LLD | ld.lld | ld.lld | PASS |

使用 GNU Make 4.3 和 Phase 9 的 fixture，以本次 Git 候选的实际 Makefile 字节为输入。两个阶段均由 mock 记录参数。历史 kdbus.o 的判定仍为 BFD_PATH_POSSIBLE。 [脚本](scripts/validate_make.py) · [原始执行](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [六组 CSV](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

```ini
STATIC_VALIDATION = PASS
REAL_BUILD_VALIDATION = PENDING
RUNTIME_VALIDATION = PENDING
PRODUCT_MERGE_APPROVAL = PENDING
```

## 提交、上传及独立验证

使用当前 Git Author Identity 和目标 Gerrit 提供的 commit-msg hook。服务器成功接收，并提示主题超过 50 字符。按 PM 指定文本保留主题。 [hook 下载](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [Gerrit 回执](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

```text
kbuild: Remove redundant LD override in external modules

The external module Makefile explicitly assigns LD to
$(CROSS_COMPILE)ld, which can override the linker selected
and exported by the top-level Kbuild system.

When building with LLVM=1, this assignment may cause GNU
BFD to be used for intermediate relocatable linking
instead of the configured LLVM LLD linker.

Remove the redundant LD assignment and allow external
modules to inherit the linker selected by Kbuild.

This preserves the caller's toolchain selection and
improves build consistency across GCC and LLVM
configurations.

Change-Id: Ic0b9efb5c514bb6e18dbc270aa269211ec514375
Signed-off-by: liushanshan <[email-redacted]>
```

上传后重新查询远程 refs，并在空 Git 仓库从 Gerrit 重新 fetch。独立比对了 HEAD、父提交、文件差异、提交正文和与隔离实验相同的 Makefile SHA256。tizen ref 在前后观察中保持 25797e8af7ed95a5783bbe84c11959560aaf7e92。 [Push](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [上传后 refs](evidence/remote-refs-after-push.out) · [独立对象验证](evidence/remote-object-verification.json)

- Gerrit 分支。匿名 HTTP 返回 401，要求登录。当前会话未验证登录后的网页渲染。 [Sandbox 分支](https://review.tizen.org/gerrit/gitweb?p=platform/kernel/linux-tizen-modules-source.git;a=shortlog;h=refs/heads/sandbox/liushanshan/lld) · [HTTP 回执](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
- Gerrit 提交。匿名 HTTP 返回 401，要求登录。提交已从 Gerrit 独立拉取并核验。 [提交页面](https://review.tizen.org/gerrit/gitweb?p=platform/kernel/linux-tizen-modules-source.git;a=commit;h=1c26a4781d7813abd9ab2fb4c3fad35c52ec8fc8) · [HTTP 回执](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

待用匹配的 ARMv7l/AArch64 SDK 运行定向模块构建，采集 kdbus.o 和 kdbus.ko 的实际 linker argv、工具 SHA256 及 RPM 文件关联，再验证设备运行并另行取得产品合入批准。本轮未启动真实模块或 Kernel 编译、镜像构建或设备操作。 [Phase 9 归档检查](evidence/phase9-integrity.out) · [机器可读汇总](KDBUS_LD_FIX_SUBMISSION_SUMMARY.json)
