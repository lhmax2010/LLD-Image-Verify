#!/usr/bin/env python3
"""Render the actual Makefile-input experiment with the raw model's results."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    data=json.loads((ROOT/"11E_MAKE_VARIABLE_TRACE.json").read_text())
    tool=json.loads((ROOT/"evidence/reproduction/make-tool/selection.json").read_text())
    models={(x["case"],x["snapshot"]):x for x in data["results"]}
    old,new="20261120.082536","20261125.130358"
    rows=[]
    labels={
        "historical_shape_control":"LLVM=1、无显式 LD、空工具链前缀",
        "armv7l_cross_prefix":"ARMv7l LLVM=1",
        "aarch64_cross_prefix":"AArch64 LLVM=1",
        "gcc_armv7l_original":"ARMv7l GCC",
        "gcc_aarch64_original":"AArch64 GCC",
        "ld_lld_command_line":"显式 LD=ld.lld",
        "explicit_bfd_unprefixed":"显式 LD=ld.bfd",
        "llvm_directory_prefix":"LLVM 目录前缀",
        "llvm_suffix":"LLVM 版本后缀",
        "ld_bfd_environment_e":"环境 LD=ld.bfd 且 make -e（优先级对照）"
    }
    for case,label in labels.items():
        before,after=(models[(case,snap)] for snap in (old,new))
        rows.append(f'| {label} | {before["intermediate"]} | {after["intermediate"]} | {before["final"]} | {after["final"]} |')
    table="\n".join(rows)
    o=data["input_payloads"][old]["Makefile"]["sha256"]
    n=data["input_payloads"][new]["Makefile"]["sha256"]
    s=f'''# 11E · 旧新 QB Makefile 隔离复现

**PASS。** 从旧、新源码提供 RPM 取得各自的实际 Makefile 和 kdbus 子 Makefile，复制到临时实验目录后按原字节使用。旧 Makefile SHA256 为 {o}，新为 {n}。新文件恰好等于旧文件删除 LD 赋值后的内容。目标新 SDK 对应的 LLVM/LD、对象规则和 modfinal 规则均按实物锚点核查。 [旧新输入与锚点](11E_MAKE_VARIABLE_TRACE.json) · [补丁来源](11B_SOURCE_PROVENANCE.json)

采用 {data["gnu_make"]}。构建日志保留 make-4.4.1-1.14.armv7l，模型使用同一 Base、同一源码 revision 的 {tool["nevra"]}。主机直接从已校验的 RPM 解出工具，不安装 RPM。 [历史作业日志](evidence/build/linux-tizen-modules-armv7l.out#L314) · [模型工具来源](evidence/reproduction/make-tool/selection.json) · [版本实测](evidence/reproduction/make-tool/version.out)

复用 Round 3 的 21 组参数与环境形状，另加目录前缀和独立裸 ld.bfd 两组。Round 3 只改变赋值语法的场景在本次使用实际旧新文件，部分场景共享参数。原试验的变体名称仍保留在记录中。共 {data["runs"]} 次、{data["observations"]} 条作用域观测和 {data["modeled_calls"]} 条模拟调用。以下为关键实测对比。

| 场景 | 旧中间 | 新中间 | 旧最终 | 新最终 |
| --- | --- | --- | --- | --- |
{table}

普通 LLVM 模式下，旧对象子进程读到文件定义的 LD，新对象子进程保持从 Kbuild 继承的 LD。两个架构的 GNU 前缀、显式 LD 和 LLVM 前缀/后缀均保留。make -e 对照只说明有意选择环境优先级的后果。实验观察不是历史 argv 或实际 linker exec。真实 GCC/BFD 软件构建本轮未验证。 [全部 CSV](11E_REPRODUCTION_RESULTS.csv) · [原始运行索引](evidence/reproduction/before-after.cmd.json)

复跑命令：

    PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/reproduce_qb_make.py \\
      --old-makefile evidence/source/old/Makefile --old-kdbus evidence/source/old/kdbus/Makefile \\
      --new-makefile evidence/source/new/Makefile --new-kdbus evidence/source/new/kdbus/Makefile \\
      --new-kbuild evidence/reproduction/new-kbuild/boot/kernel/devel/kernel-devel-arm-rpi4 \\
      --make evidence/reproduction/make-tool/bin/make

该脚本重写本阶段生成的 CSV、JSON 和模型 stdout。用独立副本复跑，以保留本轮原始回执。
'''
    (ROOT/"11E_BEFORE_AFTER_REPRODUCTION.md").write_text(s)

if __name__=="__main__":
    main()
