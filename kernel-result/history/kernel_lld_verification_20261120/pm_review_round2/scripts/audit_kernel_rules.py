#!/usr/bin/env python3
"""Trace the pinned ARM kernel rules and verify the 52 in-tree final paths."""
from collections import Counter
import argparse
import json
from pathlib import Path, PurePosixPath
import re

from review_common import csv_rows, dump, need, sha, write_csv

LOG = 'evidence/build/linux-rpi-armv7l.out'
SRC = 'evidence/kernel/source/'
BINARY_RPM = 'arm-rpi4-linux-kernel-modules-6.12.80-0.armv7l.rpm'
REVISION = '42aeefac58edeb081aff440f0b60be71cbe49755'
SHARED_GAP = 'No historical process argv, resolved executable path or target .cmd.'
ENGINEERING = (
    'Published SPEC and historical LLVM=1/target argv select ld.lld. Generated Kconfig probes LLD 22.1.8. '
    'The matched ARM recipe inherits LD and runs for this exact target. '
    'Neither verified retained RPM provider of ld.lld dispatches to GNU BFD. '
    'Quiet target and release packaging evidence link the rule and artifact.'
)
ASSIGNMENT = re.compile(r'(^|[:\s])(?:override\s+|export\s+|private\s+)*(LD|LLVM|LLVM_IAS|CC|PATH|MAKEFLAGS|MAKEOVERRIDES|GNUMAKEFLAGS|CROSS_COMPILE|LLVM_PREFIX|LLVM_SUFFIX)\s*(?::+|\?|[+!])?=')
DEPENDENCY = re.compile(r'(^|\s)((?:[^\s/]+/)*[^\s]+\.(?:o_shipped|a_shipped|ko_shipped|obj|so|a))(?=\s|$)')
DIRECT_ALT = re.compile(r'(^|[;\s])(?:[^/\s]+/)*(?:[\w.-]+-)?ld(?:\.bfd|\.gold)?(?:\s|$)|\$\((?:CROSS_COMPILE)\)ld\b')

def source(out, file, *ranges):
    lines = (out/SRC/file).read_text().splitlines()
    records = []
    for start, end in ranges:
        need(start <= end <= len(lines), f'Invalid source interval {file}:{start}-{end}')
        records.append({'file':SRC+file,'start_line':start,'end_line':end,
                        'code':[{'line':i,'raw':lines[i-1]} for i in range(start,end+1)]})
    return records

def event(log, line):
    return {'file':LOG,'line':line,'raw':log[line-1]}

def select_log(log, pattern, first, last):
    return [event(log,i) for i in range(first,last+1) if re.search(pattern,log[i-1])]

def one(items, label):
    need(len(items)==1, f'{label}: expected one record, saw {len(items)}')
    return items[0]

def module_rows(base, out, log, scoped):
    recorded = json.loads((base/'evidence/build/module-final-commands.json').read_text())
    expected = {o['build_output']:o for o in recorded['quiet_link_observations'] if o['package_rpm']==BINARY_RPM}
    final_events = select_log(log, r'\sLD \[M\]\s+\S+\.ko$',3371,8156)
    outputs = {e['raw'].split()[-1]:e for e in final_events}
    need(len(final_events)==len(outputs)==len(expected)==52 and outputs.keys()==expected.keys(),
         'Pinned in-tree compile span and archived final module records disagree')
    nonrt = '/lib/modules/6.12.80-arm-rpi4-v7l/kernel/'
    installs = select_log(log, r'\sINSTALL\s+\S+'+re.escape(nonrt)+r'\S+\.ko$',14124,14235)
    strips = select_log(log, r'\sSTRIP\s+\S+'+re.escape(nonrt)+r'\S+\.ko$',14124,14235)
    installmap = {e['raw'].split()[3].split(nonrt)[1]:e for e in installs}
    stripmap = {e['raw'].split()[3].split(nonrt)[1]:e for e in strips}
    need(len(installs)==len(strips)==len(installmap)==len(stripmap)==52 and
         installmap.keys()==stripmap.keys()==outputs.keys(), 'Non-RT install and strip scopes not identical to final paths')
    otrecords = csv_rows(base,'05_kernel_module_inventory.csv')
    repo = {row['path']:row for row in otrecords if row['scope']=='repository' and row['path'].startswith(nonrt)}
    device = {row['repository_path']:row for row in otrecords if row['scope']=='device' and row['repository_path'].startswith(nonrt)}
    need(set(repo)==set(device)=={nonrt+x for x in outputs}, 'Artifact paths do not match both inventories')
    quoted = {3371,3372,7939,7940,7941,7945,7947,7951,7958,7962,7966,7967,7969,8141,8143,8145,8146,
              8150,8151,8156,8162,14011,14124,14125,14127,14235,14237,15249,15251,15253,15255,15262,15275,
              84,123,155,1672,1673,1675,1676,1677,1678,1679,1680,2682,2687,2699}
    rows = []
    suspicious = []
    for directory in scoped['directory_scope']:
        if directory == '.':
            continue  # Top-level selection is traced as the common parent separately.
        for child in ('Kbuild','Makefile'):
            path = out/SRC/directory/child
            if not path.is_file():
                continue
            for i,line in enumerate(path.read_text(errors='replace').splitlines(),1):
                uncommented = line.split('#',1)[0]
                if ASSIGNMENT.search(uncommented) or DIRECT_ALT.search(uncommented) or DEPENDENCY.search(uncommented):
                    suspicious.append(dict(path=str(path.relative_to(out)),line=i,raw=line))
    for target, final in outputs.items():
        rel = PurePosixPath(target)
        payload = nonrt+target
        orig = expected[target]
        install, strip = installmap[target], stripmap[target]
        need(orig['event']['line']==final['line'] and orig['event']['raw']==final['raw'] and
             orig['install_event']['line']==install['line'] and orig['install_event']['raw']==install['raw'] and
             orig['payload_path']==payload and orig['rpm_write']['line']==15253 and
             orig['build_completion']['line']==15275 and orig['observed_successful_install_and_packaging'],
             f'Target event identity mismatch: {target}')
        pattern = r'\s(?:CC|LD) \[M\]\s+'+re.escape(rel.with_suffix('.o').as_posix())+'$'
        obj = one(select_log(log,pattern,3371,7940),f'{target} input .o')
        mod_obj = one(select_log(log,r'\sCC \[M\]\s+'+re.escape(rel.with_suffix('.mod.o').as_posix())+'$',
                                 7946,final['line']),f'{target} .mod.o')
        btf = one(select_log(log,r'\sBTF \[M\]\s+'+re.escape(target)+'$',
                             final['line'],8156),f'{target} BTF')
        quoted.update((final['line'],install['line'],strip['line'],obj['line'],mod_obj['line'],btf['line']))
        configs = {}
        selects = []
        pos = tuple(rel.parents)
        for folder in pos:
            for srcfile in ('Kbuild','Makefile'):
                path = (out/SRC/folder/srcfile)
                if path.is_file():
                    for number,line in enumerate(path.read_text().splitlines(),1):
                        if re.match(r'\s*obj-(?:m|\$\(CONFIG_[A-Za-z0-9_]+\))\s*[+:]?=',line) and re.search(r'(?<!\S)'+re.escape(rel.stem+'.o')+r'(?=\s|$)',line):
                            selects.append(f'{path.relative_to(out)}#L{number} {line.strip()}')
                            for symbol in re.findall(r'\bCONFIG_[A-Za-z0-9_]+\b',line):
                                conf_path = out/SRC/'.config'
                                match = [n for n,x in enumerate(conf_path.read_text().splitlines(),1)
                                         if x.startswith(symbol+'=') or x=='# '+symbol+' is not set']
                                if match:
                                    line_config=conf_path.read_text().splitlines()[match[0]-1]
                                    configs[symbol]=f'{line_config} ({SRC}.config#L{match[0]})'
        need(selects and (any('=m (' in c for c in configs.values()) or any('obj-m ' in x for x in selects)),
             f'No active kbuild source rule for {target}')
        r,d = repo[payload],device[payload]
        val = r['raw_sha256']
        need(r['parsed']==d['parsed']=='True' and r['classification']==d['classification']=='LLD_INDICATED' and
             d['repository_identity']=='EXACT_PATH_AND_SHA256' and
             sha(base/r['file'])==val==d['raw_sha256']==sha(base/d['file']),
             f'Payload or installed file mismatch for {target}')
        nearby = [x for x in suspicious if PurePosixPath(x['path'].removeprefix(SRC)).parent in pos]
        prebuilt = [p for p in scoped['srpm']['prebuilt_scoped'] if PurePosixPath(p).parent in pos]
        prebuilt += [p for patch in scoped['srpm']['patches'] for p in patch['potentially_prebuilt_scoped'] if PurePosixPath(p).parent in pos]
        rows.append(dict(
            module_name=r['name'],module_path=payload,device_path=d['path'],build_output=target,
            binary_rpm=BINARY_RPM,source_rpm='rpi4-linux-kernel-6.12.80-0.src.rpm',source_revision=REVISION,
            source_selection=' | '.join(selects),effective_module_config=' | '.join(configs.values()) or 'obj-m in selected subdirectory',
            build_invocation=f'{LOG}:3371',
            effective_llvm_setting='LLVM=1 (historical shell trace 1677–1678)',
            effective_ld_setting='ld.lld (matched source inference; LLD 22.1.8 detected and both retained provider RPMs identified)',
            final_link_rule=f'{SRC}scripts/Makefile.modfinal#L36-L61',
            intermediate_object_log_line=obj['line'],intermediate_object_raw=obj['raw'],
            modinfo_object_log_line=mod_obj['line'],modinfo_object_raw=mod_obj['raw'],
            module_final_log_line=final['line'],module_final_raw=final['raw'],
            btf_log_line=btf['line'],btf_raw=btf['raw'],
            install_log_line=install['line'],install_raw=install['raw'],strip_log_line=strip['line'],strip_raw=strip['raw'],
            rpm_write_log_line=15253,build_completion_log_line=15275,
            prebuilt_object_presence='NONE_IN_SCOPED_SRPM_MEMBERS_OR_PATCH_PATHS' if not prebuilt else json.dumps(prebuilt),
            linker_override_risk='NONE_IN_SCOPED_TARGET_DECLARATIONS; original resolved process path unavailable' if not nearby else json.dumps(nearby,ensure_ascii=False),
            rpm_payload_sha256=val,device_sha256=val,
            original_classification=r['classification'],evidence_level='E3',final_verdict='ENGINEERING_VERIFIED',
            e3_reason=ENGINEERING+' Historical .o, .mod.o, final .ko, BTF, install, strip and RPM write are paired by full non-RT paths.',
            still_unobserved=SHARED_GAP))
    need(not suspicious, f'Unclassified scoped build declarations: {suspicious}')
    need(all(row['prebuilt_object_presence'].startswith('NONE') for row in rows), 'Unreviewed prebuilt evidence')
    return rows, sorted(quoted), suspicious

def rule_matrix(out, log):
    cases = [
        ('vmlinux.o','relocatable kernel object','ELF intermediate, package stripping excludes *.o; binds via vmlinux build sequence',
         '$(LD) … -r -o vmlinux.o …',[7940,7941,7942,7945],
         [('Makefile',(1156,1165)),('scripts/Makefile.vmlinux_o',(48,67))]),
        ('vmlinux','kernel final ELF','vmlinux to arm/boot/Image. Runtime notes and packaged zImage/+devel debuglink checked independently in Task 7',
         'scripts/link-vmlinux.sh "$(LD)" … ; ARM executes the passed LD … -o vmlinux',[7941,7945,7947,7951,7958,7962,7966,7967,8145,14011,15251,15255],
         [('Makefile',(1178,1181)),('scripts/Makefile.vmlinux',(25,34)),('scripts/link-vmlinux.sh',(28,36),(57,103),(270,280)),('arch/arm/boot/Makefile',(53,60))]),
        ('arch/arm/boot/compressed/vmlinux','ARM decompressor final ELF','compressed/vmlinux to arm/boot/zImage via OBJCOPY, then install and non-RT kernel RPM',
         '$(LD) $(ld_flags) $(real-prereqs) -o $@',[8141,8143,8145,14011,15251,15255],
         [('arch/arm/Makefile',(252,258),(295,302)),('arch/arm/boot/Makefile',(53,60)),('arch/arm/boot/compressed/Makefile',(103,124),(146,158)),('scripts/Makefile.lib',(330,335))]),
        ('52 in-tree .ko','module final relocatables','52/52 target paths -> INSTALL/STRIP -> modules RPM -> identical installed SHA256',
         '$(LD) -r … -T scripts/module.lds -o $@ …',[3371,7945,7969,8038,8142,14124,14130,14232,15253,15275],
         [('Makefile',(1881,1889)),('scripts/Makefile.modfinal',(15,18),(36,40),(59,64)),('scripts/Makefile.modinst',(43,72),(76,89))]),
    ]
    rows, trace = [], {}
    for target, kind, binding, effective, log_lines, ranges in cases:
        sources = [x for filename,*sub in ranges for x in source(out,filename,*sub)]
        events = [event(log,i) for i in log_lines]
        locations = ' | '.join(f'{item["file"]}:{item["start_line"]}-{item["end_line"]}' for item in sources)
        rows.append(dict(target=target,artifact_type=kind,source_file_and_lines=locations,
                         original_code=' | '.join(x['raw'] for y in sources for x in y['code']
                                                  if re.search(r'\$\(LD\)|\$\{LD\}|cmd_ld_|if_changed(?:_except)?,ld|vmlinux_link vmlinux|cmd_link_vmlinux',x['raw'])),
                         effective_make_variable='LLVM=1 observed. LD=ld.lld inferred. '+effective,
                         expected_linker='LLD 22.1.8',linker_override='NONE_IN_SCOPED_RULES',
                         build_log_evidence=' | '.join(f'{x["file"]}:{x["line"]} {x["raw"]}' for x in events),
                         artifact_binding=binding,evidence_strength='E3',evidence_level='E3',final_verdict='ENGINEERING_VERIFIED',
                         reason=ENGINEERING,remaining_uncertainty=SHARED_GAP+
                         (' Standalone historical vmlinux.o bytes not retained.' if target=='vmlinux.o' else '')))
        trace[target]={'sources':sources,'log_events':events,'verdict':rows[-1]}
    return rows,trace

def main():
    arg=argparse.ArgumentParser(description=__doc__)
    arg.add_argument('base',type=Path)
    arg.add_argument('out',type=Path)
    a=arg.parse_args()
    base,out=a.base.resolve(),a.out.resolve()
    log=(base/LOG).read_text().splitlines()
    scoped=json.loads((out/'evidence/kernel/kernel-source-binding.json').read_text())
    for entry in scoped['devel']['members']:
        need(sha(out/'evidence/kernel'/entry['file'])==entry['sha256'],
             f"Devel extracted file hash failed: {entry['file']}")
    need(not scoped['devel']['arm_postlink'], 'Unexpected arch/arm Makefile.postlink')
    need('export LLVM=1' in log[1676] and 'make O=build/arm-rpi4 -j8' in log[3370] and log[3370].rstrip().endswith('-j8'),
         'Observed build settings changed')
    modules,quoted,suspicious=module_rows(base,out,log,scoped)
    rules,trace=rule_matrix(out,log)
    for t in trace.values():
        quoted=sorted(set(quoted)|{e['line'] for e in t['log_events']})
    v={
       'LLVM':('export LLVM=1 observed at log 1677–1678. Nonempty triggers LLVM branch. LLVM=0 is also nonempty in this tree and would not select GNU tools here.',
               [('spec/linux-rpi.spec',(190,198)),('Makefile',(423,434),(476,496))],[1677,1678]),
       'LD':('Predicted make value is ld.lld with default empty prefix/suffix. Kconfig checked $LD --version, distinguishing BFD and LLD. Generated LLD_VERSION=220108. No same-build absolute executable path recovered.',
             [('Makefile',(423,428),(476,496),(591,604)),('scripts/Kconfig.include',(39,59)),('scripts/ld-version.sh',(22,57)),('init/Kconfig',(47,61)),('.config',(5,13))],[1677,2687,3371]),
       'CC':('RPM preamble exported target clang names. Ordinary GNU make precedence selects Makefile CC=clang in this LLVM branch unless -e/override. Effective compiler family/version independently observed. Kernel direct linker recipes do not use CC as LD.',
             [('Makefile',(476,496),(661,664)),('scripts/link-vmlinux.sh',(77,89)),('.config',(5,13))],[1672,1673]),
       'CROSS_COMPILE':('No literal historical value recovered for this invocation. The non-LLVM branch uses it to form ld. The observed LLVM branch does not. Clang target triple and integrated assembler flow are separate.',
                       [('Makefile',(476,496)),('scripts/Makefile.clang',(1,4),(15,29))],[3371]),
       'LLVM_IAS':('Banner/config show integrated assembler from the matching config. Exact historical environment value unobserved. Source uses LLVM_IAS=0 only for clang assembler selection.',
                   [('scripts/Makefile.clang',(20,29)),('.config',(9,10))],[2687,3371]),
       'PATH':('Exact historical PATH unresolved. Both retained package ld.lld ELF candidates implement LLD 22.1.8. Present binutils names ld and ld.bfd do not resolve ld.lld. A path insertion or replacement not evidenced by this build would be needed.',
               [('Makefile',(423,428),(476,489)),('scripts/Kconfig.include',(39,59))],[84,123,155]),
       'MAKEFLAGS':('RPM preamble records addition of -k, not the complete preexisting value. Top make adds -rR. Observed default target argv has O and -j8 only. A different target-specific override, -e with an inherited LD plus target-scoped change, injected MAKEFLAGS/MAKEFILES, or a post-config replacement would need additional unsupported assumptions.',
                    [('Makefile',(41,58),(76,101),(179,196),(208,225))],[1675,1676,3371]),
       'recursive_make':('O places child make in build/arm-rpi4 via -C and explicit source Makefile. Top exports LD. Child -f vmlinux_o/vmlinux/modfinal uses exported LD. ARM uses scripts/Makefile.build separately. The observed command line contains no LD/CC/LLVM override, and child recipes do not set one.',
                         [('Makefile',(179,196),(208,225),(591,604),(1156,1181),(1881,1889)),('scripts/Kbuild.include',(109,119)),('scripts/Makefile.build',(36,43))],[3371,3372,8150]),
       'architecture':('ARM make changes flags and zImage routing only. No ARM Makefile.postlink exists in exact devel payload. link-vmlinux.sh ARM route uses LD directly. The CC-based special branch is UML, outside this ARMv7 path.',
                       [('arch/arm/Makefile',(13,17),(44,52),(252,258),(295,302)),('scripts/link-vmlinux.sh',(77,103))],[8141,8143,8145]),
    }
    variable_trace={key:{'evaluation': val[0],
                         'source': [entry for file,*spans in val[1] for entry in source(out,file,*spans)],
                         'historical_log_events':[event(log,i) for i in val[2]]} for key,val in v.items()}
    dump(out/'08_03_linker_variable_trace.json',dict(
         release='6.12.80-arm-rpi4-v7l',vcs_revision=REVISION,target='arm-rpi4 non-RT',
         package_source_binding='evidence/kernel/kernel-source-binding.json',
         historical_log=dict(file=LOG,sha256=sha(base/LOG)),
         variable_trace=variable_trace,target_rules=trace,
         historical_path_evidence='08_06_historical_linker_resolution.md',
         static_alternative_assessment='NO_REASONABLE_BFD_ROUTE_IN_MATCHED_BUILD_SCOPE',
         remaining_uncertainty=SHARED_GAP,
         original_classification_preserved=True))
    dump(out/'evidence/kernel/in-tree-event-audit.json',dict(
         full_log_path=LOG,full_log_sha256=sha(base/LOG),nonrt_argv_and_build_span=[3371,8156],
         nonrt_install_span=[14124,14235],rpm_write_line=15253,build_completion_line=15275,
         source_ancestor_directory_count=len(scoped['directory_scope']),
         scoped_makefile_count=sum(m['file'].split('/')[-1] in ('Kbuild','Makefile') for m in scoped['devel']['members']),
         alternative_assignment_hits=suspicious,prebuilt_scope_regular_members=scoped['srpm']['scope_regular_members'],
         records=modules))
    (out/'evidence/kernel/linux-rpi-armv7l-excerpts.txt').write_text(
        f'Original archive member: {LOG}\nSHA256: {sha(base/LOG)}\n'+
        ''.join(f'{i:5d}\t{log[i-1]}\n' for i in quoted))
    write_csv(out/'08_03_linker_rule_matrix.csv',rules)
    write_csv(out/'08_04_in_tree_modules.csv',modules)
    print(f'Kernel variable routes: {len(rules)} E3. In-tree signatures: {dict(Counter(r["evidence_level"] for r in modules))}.')
    print(f'52/52 raw build paths, final .ko, BTF, install, strip, and RPM-to-device SHA256 validated.')
    print(f'Observed bounded source overrides: {len(suspicious)}. Historical argv unavailable.')

if __name__=='__main__':
    main()
