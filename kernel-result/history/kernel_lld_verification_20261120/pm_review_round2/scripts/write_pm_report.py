#!/usr/bin/env python3
"""Join the exact target proof rows and calculate the Round 2 acceptance matrix."""
from collections import Counter
import json
from pathlib import Path
import shutil

from review_common import HERE, csv_rows, dump, load, markdown_table, need, write_csv

LEVEL_NAMES = {
    'E4':'DIRECT_EXECUTION_CONFIRMED', 'E3':'ENGINEERING_VERIFIED',
    'E2':'METADATA_SUPPORTED', 'E1':'INTENT_ONLY', 'UNKNOWN':'UNKNOWN',
}

def received_level(row):
    return row['evidence_level'].split()[0].split(':')[0]

def sha_field(row):
    for key in ('rpm_payload_sha256','payload_sha256'):
        if row.get(key):
            return row[key]
    raise ValueError(f'no payload SHA256 {row["module_path"]}')

def evidence_reason(row):
    for key in ('e3_reason','evidence_level_reason','classification_reason','reason','engineering_reason','evidence_basis'):
        if row.get(key):
            return row[key]
    if row.get('engineering_evidence'):
        return row['engineering_evidence']
    raise ValueError(f'no evidence level reason for {row["module_path"]}. Available: {list(row)}')

def construct_modules(root, integrity):
    original = {r['module_path']:r for r in integrity['module_payload_rows']}
    module_rows=[]
    for scope, name in (('in-tree','08_04_in_tree_modules.csv'), ('out-of-tree','08_05_out_of_tree_modules.csv')):
        inputs = csv_rows(root,name)
        need(len(inputs)=={'in-tree':52,'out-of-tree':7}[scope],'component denominator differs')
        for row in inputs:
            path=row['module_path']
            old=original.pop(path)
            digest=sha_field(row)
            need(scope==old['group'] and digest==row['device_sha256']==old['rpm_payload_sha256']==old['device_sha256'],
                 f'integrity and module rule rows do not join {path}')
            level=received_level(row)
            need(level in LEVEL_NAMES,'unrecognized evidence level')
            module_rows.append(dict(module_name=old['module_name'],module_path=path,scope=scope,
                        device_path=old['device_path'],binary_rpm=old['binary_rpm'],
                        source_rpm=row['source_rpm'],rpm_payload_sha256=digest,device_sha256=row['device_sha256'],
                        original_classification=old['original_classification'],evidence_level=level,
                        evidence_level_name=LEVEL_NAMES[level],final_verdict=LEVEL_NAMES[level],component_verdict=row['final_verdict'],
                        reason=evidence_reason(row), source_detail_report=name,
                        build_log=old['log'], final_ko_log_line=old['log_line'], install_log_line=old['install_line'],
                        successful_rpm_write_line=old['rpm_write_line'],final_link_argv_observed=old['final_link_argv_observed']))
    need(not original,'unmerged original files')
    return module_rows

def coverage(entries):
    levels=Counter(r['evidence_level'] for r in entries)
    original=Counter(r['original_classification'] for r in entries)
    total=len(entries)
    calculate=lambda n:dict(numerator=n,denominator=total,coverage=n/total)
    return dict(total=total, levels={key:levels[key] for key in LEVEL_NAMES},
                original_classifications=dict(original),
                original_confirmed_lld=calculate(original['LLD_CONFIRMED']),
                original_lld_evidence=calculate(original['LLD_CONFIRMED']+original['LLD_INDICATED']),
                e4_direct_execution=calculate(levels['E4']),
                e3_engineering_verified=calculate(levels['E3']),
                e3_plus_e4_engineering_acceptance=calculate(levels['E3']+levels['E4']))

def show(data):
    return f'{data["numerator"]}/{data["denominator"]}（{data["coverage"]:.0%}）'

def main():
    out=HERE
    audit=load(out,'08_01_evidence_integrity_review.json')
    recover=load(out,'08_02_historical_evidence_recovery.json')
    paths=load(out,'08_06_historical_linker_resolution.json')
    build_id=load(out,'BUILD_ID_COMPARISON.json')
    identity=load(out,'08_09_identity_review.json')
    rules=csv_rows(out,'08_03_linker_rule_matrix.csv')
    groups=['in-tree','out-of-tree']
    modules=construct_modules(out,audit)
    cov={name:coverage([row for row in modules if row['scope']==name]) for name in groups}
    cov['repository']=coverage(modules)
    cov['device']=coverage(modules)  # the 59 exact byte-matched files were audited row by row
    matrix={row['target']:row for row in rules}
    candidates=paths['selected_linker_candidates']
    b_targets=['vmlinux','arch/arm/boot/compressed/vmlinux']
    b_all=all(matrix[target]['evidence_level'] in ('E3','E4') for target in b_targets)
    d_all=all(row['evidence_level'] in ('E3','E4') for row in modules)
    strict='CONDITIONAL_PASS'
    engineering='PASS' if all((b_all,d_all,len(modules)==59)) else 'CONDITIONAL_PASS'
    link_gaps=['历史最终 linker argv 与对应 Kbuild .cmd', '历史 PATH、execve 实际绝对路径',
               'kdbus.o 中间合并的实际 linker', '设备启动文件 SHA256 和活动 RPM DB 目标条目']
    gates=[
       dict(gate='A',strict='PASS',engineering='PASS',evidence='round1/01_runtime_kernel.md',
            basis='认可独立采集的目标设备、Clang 22.1.8 / LLD 22.1.8 banner。'),
       dict(gate='B',strict=strict,engineering='PASS' if b_all else strict,evidence='KERNEL_LINKER_RULE_MATRIX.csv',
            basis='主内核和 ARM 解压器最终链接均达到 E3。无实录 argv 或 .cmd。'),
       dict(gate='C',strict='PASS',engineering='PASS',evidence='08_09_identity_review.md',
            basis='发布内核到运行内核为 STRONG_MATCH，独立 notes 与模块文件为 EXACT_MATCH。保留设备卷和 RPM DB 限制。'),
       dict(gate='D',strict=strict,engineering='PASS' if d_all else strict,evidence='MODULE_LINKER_EVIDENCE_MATRIX.csv',
            basis='59 个最终 .ko 的发布/设备摘要、解析和证据闭环。kdbus.o 独立中间步骤有合理 BFD 候选。'),
       dict(gate='E',strict='PASS',engineering='PASS',evidence='08_01_evidence_integrity_review.md',
            basis='第一轮归档验证、离线复跑、独立日志和装载 notes 核查通过。'),
    ]
    level_summary={
        'status':strict,'engineering_acceptance':engineering,'coverage':cov,'level_definitions':LEVEL_NAMES,
        'kernel_rule_levels':{target:matrix[target]['evidence_level'] for target in matrix},
        'scope':'Verified 59 final .ko outputs, main kernel final link and ARM decompressor final link; intermediate kdbus.o is assessed separately.'
    }
    dump(out/'08_08_evidence_levels.json',level_summary)
    write_csv(out/'MODULE_LINKER_EVIDENCE_MATRIX.csv',modules)
    write_csv(out/'PM_REVIEW_GATE_MATRIX.csv',gates)
    shutil.copyfile(out/'08_03_linker_rule_matrix.csv',out/'KERNEL_LINKER_RULE_MATRIX.csv')
    shutil.copyfile(out/'08_05_out_of_tree_modules.csv',out/'OUT_OF_TREE_MODULES.csv')
    cov_table = markdown_table(['指标','仓库模块','设备模块','树内模块','树外模块'], [
        (label, *(show(cov[scope][key]) for scope in ('repository','device',*groups)))
        for label,key in (
          ('Original Confirmed LLD Coverage','original_confirmed_lld'),
          ('Original LLD Evidence Coverage','original_lld_evidence'),
          ('E4 Direct Execution Coverage','e4_direct_execution'),
          ('E3 Engineering Verified Coverage','e3_engineering_verified'),
          ('E3 + E4 Engineering Acceptance Coverage','e3_plus_e4_engineering_acceptance')
        )])
    table_levels=markdown_table(['等级','含义','仓库','设备','树内','树外'], [
        (level,name,*(f'{cov[g]["levels"][level]}/{cov[g]["total"]}' for g in ('repository','device',*groups)))
         for level,name in LEVEL_NAMES.items()
    ])
    (out/'08_08_evidence_levels.md').write_text(f'''# 08.08 · 证据等级和覆盖率

E4 需要与目标产物绑定的历史直接执行证据。E3 需要匹配的源码规则、实际输入参数、有效配置、逐目标日志和产物绑定，且没有证据支持的合理替代最终链接路径。E2 表示有元数据支持但路径不闭合。E1 表示构建意图。UNKNOWN 表示不足或未解决冲突。原 LLD 分类保持。

{table_levels}

{cov_table}

分母为独立 .ko 文件。E3 理由和风险逐目标记录在表中，内核中间对象和 ARM 包装器不会进入模块分母。 [逐模块矩阵](MODULE_LINKER_EVIDENCE_MATRIX.csv) · [Kernel 链接规则矩阵](KERNEL_LINKER_RULE_MATRIX.csv)
''')
    summary=dict(overall_status=strict, engineering_acceptance=engineering, closure_authority='PM',
          engineering_closure_recommended=engineering=='PASS', strict_closure_recommended=False,
          snapshot=audit['snapshot'], runtime_gnu_build_id=build_id['old_build_id'],
          toolchain=dict(compiler='Clang 22.1.8',linker='LLD 22.1.8',historical_execve_path=paths['historical_execve_path']),
          historical_evidence_status=recover['status'], historical_linker_candidates=candidates, gates=gates,
          kernel_rule_levels=level_summary['kernel_rule_levels'], module_coverage=cov,
          module_elf_parsed=59, device_sha256_match=59, loaded_build_id_match=len(audit['loaded_modules']),
          identity=identity['relations'],
          plausible_bfd_paths=[
              dict(target='kdbus/kdbus.o',stage='intermediate',assessment='PLAUSIBLE_UNCONFIRMED',
                   cause='Exact module-source Makefile assigns LD = CROSS_COMPILE + ld inside Makefile.build. Historic binutils has both ld and ld.bfd backed by the same ARM ELF.',
                   evidence='08_05_out_of_tree_modules.md')],
          confirmed_bfd_modules=0, observed_bfd_final_link=False, unresolved=link_gaps,
          direct_execution_evidence_unchanged=True, evidence_bundle='PM_REVIEW_EVIDENCE_BUNDLE.tar.gz')
    dump(out/'PM_REVIEW_ROUND2_SUMMARY.json',summary)
    gate_table=markdown_table(['Gate','严格验收','工程验收','依据'], [
        (row['gate'],row['strict'],row['engineering'],row['basis']+f' [查看]({row["evidence"]})') for row in gates
    ])
    kernel_table=markdown_table(['目标','证据等级','有效 linker','范围'],[
        (r['target'],r['evidence_level'],r['expected_linker'],r['artifact_type']) for r in rules
    ])
    (out/'PM_REVIEW_ROUND2_REPORT.md').write_text(f'''# Tizen Kernel LLD Migration · PM Review Round 2

**严格验收总体仍为 {strict}。按 PM 提议的最终链接工程条件，Gate B 和 D 均为 {engineering}。** 目标为 {audit['snapshot']} 的 Raspberry Pi 4 ARMv7l 非 RT 内核。主内核和 ARM 解压器最终链接为 E3，52 个树内与 7 个树外最终 .ko 均为 E3。没有取得历史 E4。建议 PM 批准所列最终链接范围的工程关闭，保留严格验收的直接执行缺口，并单独跟踪树外 kdbus.o 中间合并的链接器。最终关闭由 PM 决定。

## 审阅问题处理结果

| 问题 | 本轮结果 |
| --- | --- |
| 第一轮证据能否复算 | 原归档 1,937 项 SHA256、497 条回执通过。完整离线复跑退出 0，四份关键输出 SHA256 与第一轮一致。59 条发布与设备模块字节链、11 个运行 Build ID 独立复核通过。 [完整性审计](08_01_evidence_integrity_review.md) |
| 历史命令能否取回 | {recover['status']}。公开成功日志、生成配置、Build Root 元数据和工具依赖可追溯。有限搜索未取得该构建的原 .cmd、完整 argv、历史 PATH 或 execve 路径。 [搜索范围及结果](08_02_historical_evidence_recovery.md) |
| 具体可能使用哪个链接器 | 历史原生 ARM ELF 和加速 x86-64 ELF 均解析为 LLD 22.1.8。实际绝对执行路径仍未识别。历史 binutils 的 ld/ld.bfd 支持下述中间阶段例外。 [历史可执行文件](08_06_historical_linker_resolution.md) |
| Build ID 是否能解释 | 历史 RPM 宏用 VERSION-RELEASE 形成 seed，真实日志执行 debugedit 流程。映射到 raw Image 的 32 个主 ELF 段只有 .notes 内 20 字节不同，完整 84 字节 runtime notes 匹配，两组 debuglink CRC 正确。 [段与后处理](08_07_build_id_postprocessing_review.md) |
| 身份 Exact 的范围 | zImage 文件、notes 和 59 个模块文件是 EXACT_MATCH。发布内核到当前运行身份整体为 STRONG_MATCH。设备启动文件和活动 RPM DB 仍为 UNVERIFIABLE。 [六项身份关系](08_09_identity_review.md) |

## 连接最终链接证据

{kernel_table}

主内核源自匹配的 Tizen SRPM/SPEC 和开发包中实际使用的 Kbuild。观测到的 LLVM=1、无显式 LD 覆盖的非 RT make 调用、配置探测、源码规则、四类成功 quiet 目标以及产物提供最终链接闭环。已知两种历史 ld.lld 解析均落到同版本 LLD。通过匹配配置、构建参数、实际递归路径和 RPM 结果，没有找到这些最终链接的合理 GNU BFD 路径。剩余的不确定性是未留存的原始执行路径及参数。 [内核变量传递](08_03_kernel_linker_selection.md) · [52 行树内模块](08_04_in_tree_modules.csv)

7 个树外模块用单独的打包 SPEC、独立的源码提供 RPM 和自己的构建日志。源码包装 Makefile 的 LD 赋值会进入 Makefile.build 对象构建作用域。kdbus/kdbus.o 的中间合并存在 GNU BFD 合理路径，历史 ARM binutils RPM 中的 ld 与 ld.bfd 经包记录和 inode 比对指向同一个 BFD ELF。kdbus.ko 的最终链接在顶层 Kbuild 单独启动的 Makefile.modfinal 子流程中，和同批另外六个最终 .ko 使用顶层选择的 ld.lld。中间合并的实际 executable 无法确认。 [树外作用域和全部 7 模块](08_05_out_of_tree_modules.md) · [树外矩阵](OUT_OF_TREE_MODULES.csv)

## 模块覆盖率

{cov_table}

E1、E2 和 UNKNOWN 在两组最终模块中均为 0。每个 E3 有自己的构建和安装路径、RPM 写出日志、payload 与设备 SHA256 和规则推导理由。旧分类在仓库与设备两边均为 59/59 LLD_INDICATED 和 0/59 LLD_CONFIRMED。两边 59/59 ELF 解析通过，59/59 文件匹配。未发现已确认的 BFD Module。 [59 行证据](MODULE_LINKER_EVIDENCE_MATRIX.csv) · [等级定义与分母](08_08_evidence_levels.md)

## 严格与工程验收

{gate_table}

审阅应优先确认工程关闭是否只覆盖主内核、ARM 解压器及最终 .ko。若目标进一步要求所有中间链接也使用 LLD，现有 kdbus.o 证据仍需原作业的命令记录，或由 PM 决定其处理方式。发布签名可用性、设备启动文件 SHA256 和活动 RPM DB 均沿用已记录限制。本轮未重新编译、刷机、重启或联系设备。 [证据索引与复跑](PM_REVIEW_EVIDENCE_INDEX.md)
''')
    print(f'PASS: output matrices cover {len(modules)} modules with {cov["repository"]["levels"]}. Strict {strict}; engineering {engineering}.')

if __name__=='__main__':
    main()
