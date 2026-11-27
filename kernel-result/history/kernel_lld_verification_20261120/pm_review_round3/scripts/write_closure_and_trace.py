#!/usr/bin/env python3
"""Write the PM closure record and link exact source lines to isolated Make observations."""
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'evidence/source'

def load(path):
    return json.loads((ROOT/path).read_text())

def dump(path,data):
    (ROOT/path).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')

def sha(path):
    with (ROOT/path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def check(condition,message):
    if not condition:
        raise ValueError(message)

def fragment(file,first,last=None,needle=None):
    source=(ROOT/file).read_text().splitlines()
    end=last or first
    lines=source[first-1:end]
    if needle:
        check(any(needle in line for line in lines),f'anchor drift in {file} lines {first}–{end}')
    return dict(file=file,line_start=first,line_end=end,original='\n'.join(lines),sha256=sha(file))

def write(path,text):
    (ROOT/path).write_text(text.strip()+'\n')

def evidence_paths():
    paths={
        'evidence/round2-summary.json':'PM_REVIEW_ROUND2_SUMMARY.json',
        'evidence/source/external/Makefile':'evidence/external/source/Makefile',
        'evidence/source/external/kdbus/Makefile':'evidence/external/source/kdbus/Makefile',
        'evidence/source/external/linux-tizen-modules.spec':'evidence/external/linux-tizen-modules.spec',
        'evidence/source/kbuild/Makefile':'evidence/kernel/source/Makefile',
        'evidence/source/historical-external-build.log':'evidence/external/external-buildlog-full.out',
        'evidence/source/historical-binutils-resolution.json':'evidence/external/historical-binutils-resolution.json',
        'evidence/source/source-rpm-pinned-row.json':'evidence/external/source-rpm-pinned-row.json',
        'evidence/source/target-bindings.json':'evidence/external/target-bindings.json',
    }
    for item in (SOURCE/'kbuild/scripts').glob('*'):
        paths[str(item.relative_to(ROOT))]='evidence/kernel/source/scripts/'+item.name
    old_manifest=ROOT.parent/'pm_review_round2/BUNDLE_SHA256SUMS'
    original={line.split('  ',1)[1]:line.split('  ',1)[0] for line in old_manifest.read_text().splitlines()}
    check(all(original[f]==sha(local) for local,f in paths.items()),'Round 2 selected source digest did not match')
    return {local:{'sha256':original[prior],'prior_archive':'pm_review_round2/'+prior} for local,prior in paths.items()}

def main():
    sources=evidence_paths()
    dump('evidence/round2-source-bindings.json',sources)
    prior=load('evidence/round2-summary.json')
    decision=(ROOT/'evidence/pm-decision-original.txt').read_text()
    check('PM 已完成 Round 2 报告审阅' in decision and '关闭以上最终链接范围的工程验收' in decision
          and 'Strict Acceptance 继续保持 CONDITIONAL_PASS' in decision,'PM approval evidence missing')
    check(prior['overall_status']=='CONDITIONAL_PASS' and prior['engineering_acceptance']=='PASS'
          and prior['historical_evidence_status']=='HISTORICAL_EXECUTION_EVIDENCE_UNAVAILABLE','Round 2 classification drift')
    levels=prior['kernel_rule_levels']
    kernel={'vmlinux.o':levels['vmlinux.o'],'vmlinux':levels['vmlinux'],
            'ARM Decompressor':levels['arch/arm/boot/compressed/vmlinux']}
    check(all(level=='E3' for level in kernel.values()),'kernel approved levels differ')
    scopes=prior['module_coverage']
    coverage={}
    for group,total in (('repository',59),('device',59),('in-tree',52),('out-of-tree',7)):
        row=scopes[group]
        check(row['total']==row['levels']['E3']==total and row['levels']['E4']==0
              and row['original_confirmed_lld']['numerator']==0 and row['original_lld_evidence']['numerator']==total,
              'PM coverages differ from Round 2')
        coverage[group]=dict(total=total,original_lld_confirmed=0,original_lld_indicated=total,
                             e3_engineering_verified=total,e4_direct_execution_verified=0,
                             e3_plus_e4_engineering_acceptance=1.0)
    closure=dict(
        ENGINEERING_ACCEPTANCE='PASS', ENGINEERING_SCOPE='KERNEL_AND_MODULE_FINAL_LINK',
        STRICT_ACCEPTANCE='CONDITIONAL_PASS', FULL_INTERMEDIATE_LINK_COVERAGE='NOT_VERIFIED',
        HISTORICAL_E4_EVIDENCE='UNAVAILABLE', KDBUS_INTERMEDIATE_LINK='OPEN',
        pm_decision='APPROVED_AND_CLOSED', snapshot=prior['snapshot'],
        target='6.12.80-arm-rpi4-v7l, standard/armv7l, Raspberry Pi 4 non-RT',
        accepted_primary_target_levels=kernel,
        individually_approved_intermediate='vmlinux.o (E3)',
        module_coverage=coverage, open_issue='LLD-KERNEL-001',
        phase9_pm_instruction='evidence/pm-decision-original.txt',
        pm_instruction_sha256=sha('evidence/pm-decision-original.txt'),
        prior_summary='evidence/round2-summary.json', prior_summary_sha256=sha('evidence/round2-summary.json'))
    dump('KERNEL_LLD_ENGINEERING_ACCEPTANCE.json',closure)
    fields='\n'.join(f'| {name} | {closure[name]} |' for name in (
        'ENGINEERING_ACCEPTANCE','ENGINEERING_SCOPE','STRICT_ACCEPTANCE','FULL_INTERMEDIATE_LINK_COVERAGE',
        'HISTORICAL_E4_EVIDENCE','KDBUS_INTERMEDIATE_LINK'))
    write('KERNEL_LLD_ENGINEERING_ACCEPTANCE.md',f'''
# Kernel LLD 工程验收关闭归档

PM 已批准关闭 {prior["snapshot"]} 的 RPi4 ARMv7l 非 RT 工程验收范围。该决定归档可追溯到 PM 指令与未改动的 Round 2 结果。 [PM 决定原文](evidence/pm-decision-original.txt) · [Round 2 汇总副本](evidence/round2-summary.json)

| 项目 | 状态 |
| --- | --- |
{fields}

批准范围包括主内核 vmlinux 最终链接、ARM decompressor 链接、52/52 树内和 7/7 树外模块最终链接，各为 E3。PM 另外明确逐项批准了 vmlinux.o 的 E3。这个具名批准不扩展到其他中间链接。

仓库与设备两组口径相同。原 LLD_CONFIRMED 0/59，原 LLD_INDICATED 59/59，E3 59/59，E4 0/59，工程接受覆盖率 100%。严格验收仍为 CONDITIONAL_PASS，原分类保留。

LLD-KERNEL-001 继续跟踪 kdbus.o 的中间合并。 [机器可读关闭记录](KERNEL_LLD_ENGINEERING_ACCEPTANCE.json) · [独立问题历史证据](KDBUS_HISTORICAL_INTERMEDIATE_LINK.md)
''')
    log='evidence/source/historical-external-build.log'
    wrapper='evidence/source/external/Makefile'
    spec='evidence/source/external/linux-tizen-modules.spec'
    top='evidence/source/kbuild/Makefile'
    recipe='evidence/source/kbuild/scripts/'
    source={
      'override':fragment(wrapper,2,needle='CROSS_COMPILE'),
      'external_recursive_entry':fragment(wrapper,42,49,'make -C'),
      'implementation_copy':fragment(spec,156,161,'/usr/src/linux-tizen-modules-source'),
      'spec_nonrt_toolchain':fragment(spec,245,268,'export LLVM=1'),
      'toolchain_affixes':fragment(top,423,428,'LLVM_SUFFIX'),
      'toolchain_ld_choice':fragment(top,478,496,'ld.lld'),
      'top_make_export':fragment(top,593,593,'CROSS_COMPILE LD CC'),
      'extmod_build_dir':fragment(top,1812,1816,'KBUILD_EXTMOD'),
      'final_kbuild_child':fragment(top,1881,1889,'Makefile.modfinal'),
      'kbuild_extension_select':fragment(recipe+'Kbuild.include',65,65,'Kbuild'),
      'object_scope_include':fragment(recipe+'Makefile.build',36,42,'$(kbuild-file)'),
      'object_merge_recipe':fragment(recipe+'Makefile.build',432,444,'cmd_ld_multi_m'),
      'recursive_object_scope':fragment(recipe+'Makefile.build',480,488,'$(MAKE) $(build)'),
      'kdbus_recipe_control':fragment('evidence/source/external/kdbus/Makefile',1,22,'obj-m += kdbus.o'),
      'modpost_includes_external':fragment(recipe+'Makefile.modpost',114,120,'$(kbuild-file)'),
      'final_scope_includes':fragment(recipe+'Makefile.modfinal',9,18,'include'),
      'final_link_recipe':fragment(recipe+'Makefile.modfinal',36,40,'$(LD)'),
      'historical_make':fragment(log,417,417,'make-4.4.1-1.6'),
      'historical_binutils':fragment(log,437,437,'binutils-2.43-1.8'),
      'historical_llvm_export':fragment(log,565,567,'export LLVM=1'),
      'historical_nonrt_recursive_make':fragment(log,574,577,'CFLAGS_MODULE'),
      'historical_intermediate_link':fragment(log,612,612,'kdbus/kdbus.o'),
      'historical_module_final_link':fragment(log,635,637,'kdbus/kdbus.ko'),
    }
    with (ROOT/'KDBUS_REPRODUCTION_RESULTS.csv').open(newline='') as stream:
        rows=list(csv.DictReader(stream))
    stages={s['stage']:s for s in rows if s['case']=='historical_shape_control'}
    names={s['case'] for s in rows}
    check(len(names)==21 and len(rows)==147 and all(row['result']=='PASS' for row in rows),'isolated experiment is incomplete')
    history=load('KDBUS_HISTORICAL_INTERMEDIATE_LINK.json')
    check(history['classification']=='BFD_PATH_POSSIBLE','historical classification changed')
    bind=load('evidence/source/source-rpm-pinned-row.json')
    binutils=load('evidence/source/historical-binutils-resolution.json')
    version=(ROOT/'evidence/reproducer/make-version.out').read_text().splitlines()[0]
    raw=source['override']['original']
    dump('KDBUS_LINKER_VARIABLE_TRACE.json',dict(
        issue='LLD-KERNEL-001', issue_state='OPEN', historical_classification=history['classification'],
        package='linux-tizen-modules-rpi4-11.0.0-0.armv7l.rpm',
        wrapper_source_rpm='linux-tizen-modules-11.0.0-0.src.rpm',
        implementation_source_package=bind['name']+'-'+bind['version']+'-'+bind['release']+'.'+bind['architecture'],
        implementation_source_rpm=bind['source_rpm'],
        implementation_revision='25797e8af7ed95a5783bbe84c11959560aaf7e92',
        wrapper_assignment=dict(operator='=',flavor='recursive',origin_when_assignment_wins='file',
                                explicit_override=False,explicit_export=False),
        historical_scope_trace={
            'ordinary_make_precedence':'command line > ordinary file assignment > environment; -e and override are exceptions',
            'external_entry':'Wrapper recipe does not use LD and forwards no LD argument in observed argv.',
            'top_kbuild_static_resolution':'LLVM=1 => ld.lld with plain assignment and explicit export for recipe children',
            'build_object_process':'inherits exported LD; external include replaces effective value and environment LD stays exportable',
            'kdbus_intermediate':'inherits exported resolved external LD; expands CROSS_COMPILE plus ld; effective historical prefix and PATH not preserved',
            'modpost':'Reads external Kbuild in its process. Recipe calls MODPOST.',
            'final_module':'Direct child of Kbuild top level sees top-level LD; external file is not included.',
            'command_values':'Full LD origin, flavor, PATH and resolution at historical exec unavailable. Trace origins below come from isolated model.',
        },
        prior_historical_binutils=binutils['ld_resolution'],
        source_anchors=source, make_model=dict(case_count=len(names),observation_count=len(rows),mocked_linker_argv_count=2*len(names),
                  make_version=version, intermediate=stages['intermediate'], final=stages['final'], full_baseline=stages),
        supporting_receipts=['evidence/reproducer-first.cmd.json','KDBUS_REPRODUCTION_RESULTS.csv','KDBUS_HISTORICAL_INTERMEDIATE_LINK.json']))
    stage_label={
        'kbuild_top_selected':'顶层 Kbuild 选定 LD',
        'build_before_include':'Makefile.build include 前',
        'build_after_include':'Makefile.build include 后',
        'intermediate':'kdbus 子进程的中间归并',
        'modpost':'独立 modpost',
        'final':'顶层直接启动的 modfinal',
    }
    baseline='\n'.join(f'| {label} | {stages[key]["origin"]} | {stages[key]["flavor"]} | {stages[key]["raw_ld"]} | {stages[key]["effective_ld"]} |'
                        for key,label in stage_label.items())
    write('KDBUS_LD_OVERRIDE_ROOT_CAUSE.md',f'''
# LLD-KERNEL-001 · kdbus 中间链接根因

**准确来源为 platform/kernel/linux-tizen-modules-source @ 25797e8af7ed95a5783bbe84c11959560aaf7e92 的顶层 Makefile 第 2 行。** 源码提供 RPM 将它安装到 /usr/src/linux-tizen-modules-source/Makefile。包装 SRPM 的 SPEC L159 将其复制到 ./kernel/Makefile，日志 L509 记录了该复制。SPEC L262 只移除特定 Clang 警告选项，保留第 2 行的 LD 赋值。 [真实 Makefile](evidence/source/external/Makefile#L2) · [包装 SPEC](evidence/source/external/linux-tizen-modules.spec#L159) · [源 RPM 记录](evidence/source/source-rpm-pinned-row.json)

    {raw}

该行采用普通递归赋值 =，命中时 origin 为 file，flavor 为 recursive，展开取引用时的 CROSS_COMPILE 值。该行没有 export 或 override。顶层外部 wrapper 的 L42–49 只调用子 make，不在本层执行 LD，历史子 make argv L576 无显式 LD。它引入风险的入口是同一个文件在 **Kbuild Makefile.build 子进程中再次被 include**。 [外层配方](evidence/source/external/Makefile#L42) · [历史递归命令](evidence/source/historical-external-build.log#L576)

## 作用域与优先级

1. 日志 L565–566 记录 LLVM=1。SDK 的 Makefile L423–428 处理可选前后缀，L478–496 据此选取 ld.lld，L593 显式 export LD 和 CROSS_COMPILE。整个 historical PATH、原始环境变量及 make override 状态没有留存。 [目标 SDK](evidence/source/kbuild/Makefile#L478) · [历史日志](evidence/source/historical-external-build.log#L565)
2. Makefile.build L41 include 外部 Makefile 前，LD 来自父进程的环境。普通文件赋值优先于默认环境优先级，使本作用域的变量变为递归表达式。原来从环境导入的 LD 默认继续导出，递归子 make 接收父作用域展开后的字符串。Makefile.build L484–488 进入 kdbus 子目录，L432–443 用 LD 运行组合对象链接。确切 kdbus Makefile 的 19 个对象和历史日志 L612 绑定此阶段。 [include](evidence/source/kbuild/scripts/Makefile.build#L41) · [归并规则](evidence/source/kbuild/scripts/Makefile.build#L432) · [复合对象组](evidence/source/external/kdbus/Makefile) · [GNU Make 优先级和递归](https://www.gnu.org/software/make/manual/make.html)
3. 顶层 modules 依赖 modpost，再独立启动 Makefile.modfinal（L1886–1888）。modpost 即使读取外部 Makefile，其子进程中的 LD 赋值也不回流到顶层。modfinal L9–18 读取配置、公共规则和 MODORDER，L36–40 使用继承自顶层的 LD。它没有 include 外部 Makefile，且对象构建子进程与它不是父子关系。历史 L636 绑定最终 kdbus.ko。 [两个子流程的边界](evidence/source/kbuild/Makefile#L1886) · [modpost include](evidence/source/kbuild/scripts/Makefile.modpost#L118) · [最终规则](evidence/source/kbuild/scripts/Makefile.modfinal#L36) · [历史 .ko 记录](evidence/source/historical-external-build.log#L636)

| 赋值或输入 | 对本案的影响 |
| --- | --- |
| LD = … | 本案实际源码。默认优先级高于环境，低于命令行赋值 |
| LD := … | 立即展开且仍是普通文件赋值。仅把 = 改为 := 不消除覆盖 |
| LD ?= … | 只在 LD 未定义时赋值。对象子进程继承已有 LD，本模型中保留 ld.lld。GNU Make 内建的默认 LD 也可算作已定义 |
| override LD = … | 显式提高本地优先级。不是本案源码，亦不能从本地取值推断所有递归子进程的 argv |
| export LD | 规定对子进程的环境传递，不单独改变赋值优先级。顶层 SDK 有实际 export |
| 命令行 LD | 通常由 MAKEFLAGS/MAKEOVERRIDES 传播并压过普通赋值。单纯环境 LD 默认不能阻止覆盖。-e 是另一个优先级分支 |

## 隔离实验中的基准观测

| 作用域 | origin | flavor | value | 展开 |
| --- | --- | --- | --- | --- |
{baseline}

历史作业保留 Make 4.4.1。独立实验使用 {version}，模拟 LLVM=1，取空的 CROSS_COMPILE 且没有命令行 LD。源规则、GNU Make 语义和实验相互支持，表中 origin 和展开值属于实验。 [实测输出](evidence/reproducer/historical_shape_control.out) · [完整 trace](KDBUS_LINKER_VARIABLE_TRACE.json)

历史 ARMv7l binutils 2.43-1.8 保留在作业环境，原 RPM 文件和 newc inode 验证表明 /usr/bin/ld 和 /usr/bin/ld.bfd 是同一 BFD ELF 的硬链接。若中间命令为裸 ld 且解析到该文件，GNU BFD 路径成立。带 CROSS_COMPILE 时，规则会请求对应前缀工具。实际历史前缀、PATH 和执行记录缺失，判定为 BFD_PATH_POSSIBLE。 [历史作业依赖](evidence/source/historical-external-build.log#L437) · [历史 ld/ld.bfd](evidence/source/historical-binutils-resolution.json) · [目标证据结果](KDBUS_HISTORICAL_INTERMEDIATE_LINK.md)

覆盖来自树外源码顶层 Makefile，因此模式可影响同一 include 作用域内任何使用 LD 的组合目标。该批其余六个目标只在此阶段编译单一对象，匹配 SDK 未启用触发单对象额外链接的 Clang LTO。本次已观测的中间归并风险定位到 kdbus.o。 [目标构建绑定](evidence/source/target-bindings.json) · [同类检查](KERNEL_LINKER_OVERRIDE_AUDIT.md)
''')
    simpl=[]
    for n in dict.fromkeys(row['case'] for row in rows):
        chosen={r['stage']:r for r in rows if r['case']==n}
        fields=[n,chosen['build_after_include']['effective_ld'],chosen['intermediate']['effective_ld'],chosen['final']['effective_ld']]
        simpl.append('| '+' | '.join(fields)+' |')
    simple='\n'.join(simpl)
    write('KDBUS_MINIMAL_REPRODUCTION.md',f'''
# GNU Make 最小作用域实验

**通过 {len(names)} 个场景、{len(rows)} 条变量观测和 {2*len(names)} 条 mock argv 断言。** 直接复制封存的外部 Makefile 及 kdbus 子 Makefile 到临时目录，用简化 Kbuild 复现父进程、对象子进程、子目录递归、modpost 和 modfinal 的边界。外部入口执行复制件中的递归配方。mock 只打印参数，不运行编译器、链接器或生成 .o/.ko。 [原始 GNU Make 版本](evidence/reproducer/make-version.out) · [运行回执](evidence/reproducer-first.cmd.json) · [全部原始命令与退出状态](evidence/reproducer/cases.json)

| 场景 | Makefile.build include 后 | 中间 kdbus.o | 最终 kdbus.ko |
| --- | --- | --- | --- |
{simple}

每条 CSV 保留 $(origin LD)、$(flavor LD)、$(value LD)、$(LD)、LLVM origin/value、CROSS_COMPILE、MAKEFLAGS、MAKEOVERRIDES、MAKELEVEL，以及适用时的模拟 argv。override_with_cli 在对象父进程观测到 origin override，但其子进程仍通过 MAKEFLAGS 接收命令行 ld.lld，说明应分别查看各作用域。LLVM=0 在当前条件中仍是非空字符串。 [完整 CSV](KDBUS_REPRODUCTION_RESULTS.csv) · [override 原始输出](evidence/reproducer/override_with_cli.out)

删除 LD 赋值后，两个架构的 LLVM 模型统一继承 ld.lld，GCC 模型保留各自前缀的 ld，显式 Clang+BFD 命令行仍生效。这是变量选择的回归矩阵，尚无真实编译、链接或 ABI 回归结论。历史作业使用 Make 4.4.1，本次运行使用 {version}。 [历史 Make 行](evidence/source/historical-external-build.log#L417) · [候选方案兼容性](KDBUS_LD_FIX_PROPOSAL.md)

在本目录复跑：

    python3 -B reproducer/run.py --output /path/to/new-experiment

脚本清洗影响 Make 变量的继承环境，通过场景定义显式传入设置。历史中间链接仍为 BFD_PATH_POSSIBLE。 [脚本](reproducer/run.py) · [历史证据](KDBUS_HISTORICAL_INTERMEDIATE_LINK.md)
''')
    print('PASS: formal PM closure, exact source/line trace, and audited 21-case experiment report.')

if __name__=='__main__':
    main()
