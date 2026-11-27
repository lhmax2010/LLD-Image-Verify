#!/usr/bin/env python3
"""Build the Phase 10 submission report from authenticated Git receipts."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
E=ROOT/"evidence"
REPO="platform/kernel/linux-tizen-modules-source"
REF="refs/heads/sandbox/liushanshan/lld"
BASE="25797e8af7ed95a5783bbe84c11959560aaf7e92"
WEB="https://review.tizen.org/gerrit/gitweb?p="+REPO+".git"

def load(relative):
    return json.loads((E/relative).read_text())

def text(relative):
    return (E/relative).read_text()

def need(check,message):
    if not check:
        raise ValueError(message)

def git(*args):
    return subprocess.run(["git","-C",str(ROOT/"checkout"),*args],capture_output=True,
                          check=True,text=True).stdout

def receipt(stem,code=0):
    row=load(stem+".cmd.json")
    need(row["exit_status"]==code,f"unexpected command status {stem}")
    return row

def refs(value):
    return {ref:digest for digest,ref in (row.split("\t",1) for row in value.splitlines())
            if ref.startswith("refs/heads/")}

def main():
    for name in ("phase9-integrity","gerrit-existing-agent-auth","ref-query-authenticated","fetch-baseline",
                 "checkout-to-image-binding","patch-check","patch-apply","diff-check","diff-stat","diff",
                 "diff-status","cached-diff-check","local-commit","local-commit-status","make-validation-run",
                 "push-dry-run","remote-refs-after-push","remote-object-verification-run"):
        receipt(name)
    receipt("remote-sandbox-before-push",2)
    push=receipt("push-sandbox")
    rest=load("remote-object-verification.json")
    original, observed=(refs(text(f"{stem}.out")) for stem in ("ref-query-authenticated","remote-refs-after-push"))
    head=observed[REF]
    commit=rest["expected_commit"]
    need(rest["status"]=="PASS" and rest["remote_head_exact_commit"] and head==commit==rest["remote_head"],
         "fresh fetch and remote ref differ")
    need(REF not in original and "[new branch]" in text("push-sandbox.out"),"new branch not demonstrated")
    need(original["refs/heads/tizen"]==observed["refs/heads/tizen"]==BASE==rest["parent"],"base verification failed")
    need(push["argv"][-1]=="HEAD:"+REF,"push destination differs from PM authorization")
    message=text("local-commit-message.out").strip()
    need(message.startswith(text("commit-message-requested.txt").strip()+"\n\n"),"commit message changed")
    found=re.findall(r"^Change-Id: (I[0-9a-f]{40})$",message,re.M)
    need(len(found)==1,"missing/ambiguous Change-Id")
    change_id=found[0]
    branch_url=WEB+";a=shortlog;h="+REF
    commit_url=WEB+";a=commit;h="+commit
    pages={}
    for scope,url in (("branch",branch_url),("commit",commit_url)):
        tool=receipt(scope+"-gitweb-after")
        need(tool["argv"][-1]==url,"Gitweb URL changed")
        code,effective=text(scope+"-gitweb-after.out").strip().split("\t",1)
        pages[scope]=dict(url=url,http_status=int(code),effective_url=effective,
                          status="LOGIN_REQUIRED" if code in ("401","403") else "HTTP_RESPONSE_UNVALIDATED")
    validation=load("pre-push-validation.json")
    make=load("make-validation/summary.json")
    need(text("diff-status.out").splitlines()==[" M kernel/Makefile"] and not text("local-commit-status.out"),
         "unexpected checkout state")
    patch=text("remote-fetched-diff.out").rstrip()
    need(patch==text("diff.out").rstrip()==text("local-commit-diff.out").rstrip(),"published diff changed")
    need(len(make["cases"])==6 and all(case["status"]=="PASS" and not case["actual_linker_executed"]
                                       for case in make["cases"]),"static validation failed")
    author=git("show","-s","--format=%an <%ae>",commit).strip()
    need(message.endswith("Signed-off-by: "+author),"missing sign-off")
    output=dict(status="SANDBOX_PUSH_VERIFIED",repository=REPO,remote_url=rest["remote_url"],
        base_commit=BASE,historical_image_source_commit=BASE,base_selection="verified image revision equals authenticated tizen HEAD",
        branch_ref=REF,sandbox_branch_created=True,original_remote_head=None,new_commit_sha=commit,remote_head=head,
        remote_head_contains_commit=True,gerrit_change_id=change_id,author=author,commit_message=message,
        changed_file="kernel/Makefile",before=git("show",BASE+":kernel/Makefile").splitlines()[:5],
        after=git("show",commit+":kernel/Makefile").splitlines()[:4],changed_lines=dict(added=0,deleted=1),
        validation=validation,make_validation=make,actual_kernel_or_module_build_run=False,
        push=dict(status="PASS",warning="subject >50 characters",exact_requested_subject_preserved=True),
        remote_verification=rest,gerrit_pages=pages,product_tizen_head_before=original["refs/heads/tizen"],
        product_tizen_head_after=observed["refs/heads/tizen"],product_push_performed=False,
        commit_msg_hook_sha256=hashlib.sha256((E/"gerrit-commit-msg").read_bytes()).hexdigest(),
        remaining=["Matched targeted module build with both linker exec events","Runtime verification",
                   "Separate product merge approval","Signed-in Gitweb page rendering"])
    (ROOT/"KDBUS_LD_FIX_SUBMISSION_SUMMARY.json").write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n")
    results="\n".join(f'| {c["configuration"]} | {c["expected_family"]} | {c["intermediate_ld"]} | {c["final_ld"]} | {c["status"]} |'
                      for c in make["cases"])
    fence=chr(96)*3
    report=f"""# kdbus LD 修复 · Gerrit Sandbox 提交报告

**已创建并推送 Sandbox，远程 Git 独立验证通过。** 提交只删除 kernel/Makefile 第 2 行的 LD 覆盖，让树外模块继承顶层 Kbuild 的链接器选择。

| 字段 | 结果 |
| --- | --- |
| Repository | {REPO} |
| Base / 本次镜像源码提交 | {BASE} |
| Sandbox Ref | {REF} |
| Sandbox 新建 | 是 |
| Original Remote HEAD | 无。上传前经认证查无该 ref |
| New Commit SHA | {commit} |
| Gerrit Change-Id | {change_id} |
| Remote HEAD | {head} |

## 预检和变更

默认 SSH 身份被拒绝。复用现有 SSH agent 中唯一的 Tizen 标记身份完成认证。Gerrit 配置和认证信息未修改。经认证查询确认仓库存在，tizen HEAD 等于已验证的镜像源码。上传前再次查无 Sandbox ref。dry-run 验证了接收服务可达，实际 push 成功证明了本次分支创建和写权限。 [认证](evidence/gerrit-existing-agent-auth.out) · [原始 refs](evidence/ref-query-authenticated.out) · [上传前 ref 查询](evidence/remote-sandbox-before-push.cmd.json) · [dry-run](evidence/push-dry-run.out)

归档的 Makefile 对应 Git 仓库的 kernel/Makefile，RPM SPEC L48 将其复制到源码包根。该文件和 kdbus 子 Makefile 均与 Phase 9 封存源文件字节一致。提交前只出现预期一行删除。git diff --check、暂存区检查均通过，工作区在提交后干净。 [路径证据](evidence/repository-source-layout.out) · [字节核对](evidence/checkout-to-image-binding.out) · [diff --check](evidence/diff-check.cmd.json) · [diff --stat](evidence/diff-stat.out) · [status](evidence/diff-status.out)

{fence}diff
{patch}
{fence}

## 六组隔离验证

| 配置 | 预期链接器 | kdbus.o 中间链接 | kdbus.ko 最终链接 | 静态结果 |
| --- | --- | --- | --- | --- |
{results}

使用 {make["GNU_make"]} 和 Phase 9 的 fixture，以本次 Git 候选的实际 Makefile 字节为输入。两个阶段均由 mock 记录参数。历史 kdbus.o 的判定仍为 BFD_PATH_POSSIBLE。 [脚本](scripts/validate_make.py) · [原始执行](evidence/make-validation-run.out) · [六组 CSV](evidence/make-validation/results.csv)

{fence}ini
STATIC_VALIDATION = PASS
REAL_BUILD_VALIDATION = PENDING
RUNTIME_VALIDATION = PENDING
PRODUCT_MERGE_APPROVAL = PENDING
{fence}

## 提交、上传及独立验证

使用当前 Git Author Identity 和目标 Gerrit 提供的 commit-msg hook。服务器成功接收，并提示主题超过 50 字符。按 PM 指定文本保留主题。 [hook 下载](evidence/gerrit-commit-msg-fetch.out) · [Gerrit 回执](evidence/push-sandbox.err)

{fence}text
{message}
{fence}

上传后重新查询远程 refs，并在空 Git 仓库从 Gerrit 重新 fetch。独立比对了 HEAD、父提交、文件差异、提交正文和与隔离实验相同的 Makefile SHA256。tizen ref 在前后观察中保持 {BASE}。 [Push](evidence/push-sandbox.out) · [上传后 refs](evidence/remote-refs-after-push.out) · [独立对象验证](evidence/remote-object-verification.json)

- Gerrit 分支。匿名 HTTP 返回 {pages["branch"]["http_status"]}，要求登录。当前会话未验证登录后的网页渲染。 [Sandbox 分支]({branch_url}) · [HTTP 回执](evidence/branch-gitweb-after.out)
- Gerrit 提交。匿名 HTTP 返回 {pages["commit"]["http_status"]}，要求登录。提交已从 Gerrit 独立拉取并核验。 [提交页面]({commit_url}) · [HTTP 回执](evidence/commit-gitweb-after.out)

待用匹配的 ARMv7l/AArch64 SDK 运行定向模块构建，采集 kdbus.o 和 kdbus.ko 的实际 linker argv、工具 SHA256 及 RPM 文件关联，再验证设备运行并另行取得产品合入批准。本轮未启动真实模块或 Kernel 编译、镜像构建或设备操作。 [Phase 9 归档检查](evidence/phase9-integrity.out) · [机器可读汇总](KDBUS_LD_FIX_SUBMISSION_SUMMARY.json)
"""
    (ROOT/"KDBUS_LD_FIX_SUBMISSION_REPORT.md").write_text(report)
    print(f"PASS: {commit}, Change-Id {change_id}, verified Gerrit {REF}")

if __name__=="__main__":
    main()
