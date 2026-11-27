#!/usr/bin/env python3
"""Reconcile Phase 12 measurements and seal a compact, checkable evidence archive."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT/'PHASE12_EVIDENCE_BUNDLE.tar.gz'
BUNDLE_SHA = ROOT/(BUNDLE.name+'.sha256')
MANIFEST = ROOT/'PHASE12_BUNDLE_CONTENTS.csv'
SUMMARY = ROOT/'PHASE12_LLD_BENEFIT_SUMMARY.json'
MATRIX = ROOT/'CONTROLLED_BUILD_MATRIX.csv'
REQUIRED = (
    'PHASE12_LLD_BENEFIT_REPORT.md', 'PHASE12_LLD_BENEFIT_SUMMARY.json',
    'CONTROLLED_BUILD_MATRIX.csv', 'LINKER_BENCHMARK_RAW.csv', 'LINKER_BENCHMARK_SUMMARY.csv',
    'ELF_SIZE_COMPARISON.csv', 'ARM_MAPPING_SYMBOL_ANALYSIS.md', 'GCC_COMPATIBILITY_REPORT.md',
    'RUNTIME_MEMORY_FEASIBILITY.md', 'KERNEL_OWNER_BENEFIT_SUMMARY.md', 'REPRODUCE.md',
)


def require(value, message):
    if not value:
        raise ValueError(message)


def data(path):
    return json.loads((ROOT/path).read_text())


def read_rows(path):
    with (ROOT/path).open(newline='') as file:
        return list(csv.DictReader(file))


def digest(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def write_csv(path, rows):
    with path.open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def measured_record(path, expected):
    file = ROOT/path
    require(digest(file) == expected, f'SHA256 mismatch for {path}')
    return file.stat().st_size


def verify_links():
    reports = [ROOT/f for f in REQUIRED if f.endswith('.md')]
    reports.append(ROOT/'evidence/runtime/generalization.md')
    for report in reports:
        for target in re.findall(r'\]\(([^()]+)\)',report.read_text()):
            path = target.split('#', 1)[0].strip('<>')
            if path and not re.match(r'^[a-z][a-z+.-]+://',path):
                require((report.parent/path).exists(), f'Missing {report.name} link {target}')


def audit():
    build = data('evidence/build/controlled-builds.json')
    groups = build['groups']
    replay = data('evidence/replay/link-replay.json')
    elf = data('evidence/elf/status.json')
    gcc = data('evidence/gcc/status.json')
    runtime = data('evidence/runtime/status.json')
    packaging = data('evidence/packaging/compression.json')
    historical = data('../kernel_lld_verification_20261125/KDBUS_LLD_FIX_QB_VERIFICATION_SUMMARY.json')
    tools = data('evidence/replay/frozen-inputs.json')
    require(build['source_delta'] == ['kernel/Makefile'] and build['response_and_ordered_inputs_byte_identical'],
            'Control source or inputs differ unexpectedly')
    require(len(groups['A']['ordered_inputs'])==19 and len(tools['ordered_response_and_objects'])==22,
            'Frozen ordered input count')
    for obj in tools['ordered_response_and_objects'] + tools['sdk_resources']:
        require(measured_record(obj['path'], obj['sha256'])==obj['size'], 'Frozen input identity')
    require(replay['status']=='PASS' and elf['status']=='MEASURED', 'Intermediate replay or ELF check incomplete')
    require(gcc['gcc_real_build']==gcc['gcc_compatibility']=='PASS', 'GCC status mismatch')
    require(runtime['runtime_memory_benefit']=='NOT_MEASURED' and not runtime['runtime_device_operations'],
            'Unexpected runtime evidence')
    matrix = []
    for group, result in groups.items():
        inter, final = result['intermediate'], result['final']
        stages = (result['intermediate_object'], result['unstripped_module'], result['strip_debug_module'])
        require(inter['exit_status']==final['exit_status']==0, f'{group} link exits')
        versions = ('GNU BFD 2.43' if group=='A' else 'LLVM LLD 22.1.8', 'LLVM LLD 22.1.8')
        require((inter['version'],final['version'])==versions, f'{group} linkers')
        require(all(measured_record(s['path'],s['sha256'])==s['size'] for s in stages), f'{group} target artifact')
        for stage in (inter, final):
            tool = 'work/tool-overlays/' + stage['executable'].lstrip('/')
            measured_record(tool, stage['executable_sha256'])
            trace = stage['exec_trace']
            measured_record(trace['path'], trace['sha256'])
            require('exit_group(0)' in (ROOT/trace['path']).read_text(), 'Actual successful link missing')
        require(stages[-1]['sha256']==historical['kdbus']['old_sha256' if group=='A' else 'new_sha256'],
                f'{group} does not match the released comparator')
        matrix.append(dict(group=group, configuration='LLVM=1, matched Unified Toolchain SDK',
            makefile='Original LD override' if group=='A' else 'Override removed',
            result='PASS', intermediate_linker=inter['version'], intermediate_executable=inter['executable'],
            intermediate_executable_sha256=inter['executable_sha256'], final_linker=final['version'],
            final_executable=final['executable'], final_executable_sha256=final['executable_sha256'],
            execution_evidence='E4 (Phase 12 only)', kdbus_o_sha256=stages[0]['sha256'],
            kdbus_unstripped_sha256=stages[1]['sha256'], kdbus_stripped_sha256=stages[2]['sha256'],
            kdbus_o_bytes=stages[0]['size'], kdbus_unstripped_bytes=stages[1]['size'],
            kdbus_stripped_bytes=stages[2]['size'], record='evidence/build/controlled-builds.json'))

    gcc_lane=gcc['runs']['exact_publication_acceleration']
    require(gcc_lane['module_count']==7 and gcc_lane['module_import_crcs_each']==345, 'GCC ABI scope')
    for group in ('C', 'D'):
        directory = Path(f'evidence/gcc/builds/{group}-accel')
        receipt = directory/'linker-execution.json'
        links = data(receipt)
        inter, final = links['kdbus.o'], links['kdbus.ko']
        digests = [gcc_lane[k] for k in ('kdbus_intermediate_sha256','kdbus_unstripped_sha256','kdbus_installed_sha256')]
        files = ['kdbus.o', 'kdbus.ko', 'kdbus.installed.ko']
        sizes = [measured_record(directory/k, h) for k,h in zip(files,digests,strict=True)]
        require(inter['exit_status']==final['exit_status']==0 and inter['output_sha256']==digests[0]
                and final['output_sha256']==digests[1], f'{group} direct GCC evidence mismatch')
        matrix.append(dict(group=group, configuration='Real GCC/BFD, exact Tizen Unified Dev SDK',
            makefile='Original LD override' if group=='C' else 'Override removed',
            result='PASS', intermediate_linker=gcc_lane['both_linkers'], intermediate_executable=inter['executable'],
            intermediate_executable_sha256=inter['tool']['sha256'], final_linker=gcc_lane['both_linkers'],
            final_executable=final['executable'], final_executable_sha256=final['tool']['sha256'],
            execution_evidence='E4 (Phase 12 only)', kdbus_o_sha256=digests[0],
            kdbus_unstripped_sha256=digests[1], kdbus_stripped_sha256=digests[2],
            kdbus_o_bytes=sizes[0], kdbus_unstripped_bytes=sizes[1], kdbus_stripped_bytes=sizes[2], record=str(receipt)))

    measured = read_rows('LINKER_BENCHMARK_RAW.csv')
    require(len(measured)==160 and all(row['status']=='0' for row in measured), 'Invalid benchmark samples')
    require(set(Counter((r['profile'],r['linker']) for r in measured).values())=={40}, 'Unbalanced timing sample')
    metrics = read_rows('LINKER_BENCHMARK_SUMMARY.csv')
    reports = {}
    for profile in ('default_threads','one_cpu_one_thread'):
        report = {}
        for metric in ('wall_ms','peak_rss_kib'):
            pair = [line for line in metrics if line['profile']==profile and line['metric']==metric]
            by_tool={line['linker']:float(line['median']) for line in pair}
            change = pair[0]
            require(set(by_tool)=={'lld','bfd'} and change['classification']=='REGRESSION' and
                    float(change['ci95_upper'])<0, 'Unexpected measured performance classification')
            report[metric]={'classification':change['classification'], 'median':by_tool,
                'improvement_pct_bfd_relative':float(change['improvement_pct']),
                'ci95_improvement_pct':[float(change[k]) for k in ('ci95_lower','ci95_upper')]}
        reports[profile]=report

    expected_sizes={'intermediate': (2505192,1998564), 'unstripped': (2071276,2069984), 'stripped': (162584,161292)}
    for kind,sizes in expected_sizes.items():
        pair = [replay['products'][label][kind] for label in ('bfd','lld')]
        require(tuple(p['size'] for p in pair)==sizes, f'{kind} replay sizes')
        for entity in pair:
            measured_record(entity['path'],entity['sha256'])
    cases = {case['id']:case for case in elf['experiments']}
    mapping = cases['frozen-stripped']['mapping_counts']
    require(mapping['left']['d'] - mapping['right']['d']==81 and
            cases['frozen-intermediate']['mapping_counts']['left']['d']-cases['frozen-intermediate']['mapping_counts']['right']['d']==101,
            'Mapping-sym count mismatch')
    require(cases['frozen-intermediate']['mapping_origin_status']=={'LINK_MAP_UNIQUE':101} and
            cases['frozen-stripped']['mapping_origin_status']=={'LINK_MAP_UNIQUE':75,'LINK_MAP_MULTIPLE':6} and
            all(not case['mapping_executable_span_differences'] for case in cases.values()),
            'Mapping symbol lineage or executable span compatibility mismatch')
    require(packaging['A']['bytes_removed_by_strip']==packaging['B']['bytes_removed_by_strip']==1908692,
            'Unexpected packaging effect')
    xz = {k:packaging[k]['single_file_xz']['size'] for k in packaging}
    require(xz=={'A':48312,'B':48000}, 'Unexpected single-file compression')
    measures = {
        'CONTROLLED_LLVM_AB_BUILD':'PASS',
        'ACTUAL_BFD_LINK':'CONFIRMED_A_INTERMEDIATE_GNU_BFD_2.43',
        'ACTUAL_LLD_LINK':'CONFIRMED_B_INTERMEDIATE_AND_A_B_FINAL_LLVM_LLD_22.1.8',
        'NEW_EXECUTION_EVIDENCE_LEVEL':'E4_PHASE12_LOCAL_CONTROLLED_BUILDS',
        'PATCH_CAUSALITY':'MEASURED_AND_ATTRIBUTED',
        'MAPPING_SYMBOL_OPTIMIZATION':'MEASURED_AND_ATTRIBUTED',
        'INTERMEDIATE_SIZE_CHANGE': 'MEASURED_AND_ATTRIBUTED',
        'FINAL_MODULE_SIZE_CHANGE': 'MEASURED_AND_ATTRIBUTED',
        'LINK_TIME_IMPROVEMENT': 'REGRESSION',
        'PEAK_RSS_IMPROVEMENT': 'REGRESSION',
        'BENCHMARK_CONFIDENCE':'95_PERCENT_PAIRED_CI_BOTH_PROFILES_LOCAL_HOST',
        'STATIC_ABI_REGRESSION':'NONE_OBSERVED_IN_CHECKED_ARTIFACTS',
        'GCC_REAL_BUILD':gcc['gcc_real_build'],
        'GCC_COMPATIBILITY':gcc['gcc_compatibility'],
        'RUNTIME_MEMORY_BENEFIT':runtime['runtime_memory_benefit'],
        'RUNTIME_REGRESSION':runtime['runtime_regression'],
        'GENERALIZATION_POTENTIAL':runtime['generalization_potential'],
        'PRODUCT_MERGE_READINESS':'PENDING',
        'PM_REVIEW_REQUIRED':'YES',
    }
    details={'historical_qb_direct_execution':'HISTORICAL_EXECUTION_EVIDENCE_UNAVAILABLE',
        'scope':'RPi4 ARMv7l non-RT external modules; host-native BFD/LLD frozen relocatable linking',
        'historical_engineering_status':'CLOSED',
        'fixed_commit':historical['NEW_QB_SOURCE_COMMIT'],
        'size_bytes':{k:{'bfd':v[0], 'lld':v[1], 'delta':v[1]-v[0]} for k,v in expected_sizes.items()},
        'mapping_symbols':{'synthetic_extra_bfd_intermediate':101,'extra_bfd_final':81,
                           'final_d_count_bfd':183,'final_d_count_lld':102},
        'controlled_stripped_matches_historical_files':True,
        'controlled_gcc_sdk':gcc['qb'],
        'real_gcc_all_other_installed_modules_byte_identical':True,
        'benchmark': reports, 'benchmark_valid_samples':len(measured),
        'packaging':{'xz_single_file_test':{'classification':'MEASURED_AND_ATTRIBUTED',
                                          'old_bytes':xz['A'],'new_bytes':xz['B'],'delta_bytes':-312},
                     'historical_rpm_xz_payload':{'classification':'OBSERVED_NOT_ATTRIBUTED',
                                                  'old_bytes':82852,'new_bytes':82420,'delta_bytes':-432},
                     'controlled_binary_rpm_packaging':'NOT_MEASURED'},
        'limits':['Fixed LLVM Base RPM server returns 404 for some dependencies. Read-only recovered Tizen ARM user space and older BFD accelerator are common to both A/B.',
                  'Benchmark measures specific native linker payloads and a single small composite workload on a shared x86-64 host.',
                  'Neither runtime memory nor new QB runtime regression was measured.'],
        'references':{'build':'evidence/build/controlled-builds.json','replay':'evidence/replay/link-replay.json',
                      'elf':'evidence/elf/status.json','gcc':'evidence/gcc/status.json','runtime':'evidence/runtime/status.json',
                      'raw_benchmark':'LINKER_BENCHMARK_RAW.csv','summary_benchmark':'LINKER_BENCHMARK_SUMMARY.csv'}}
    return measures | details, matrix


def eligible():
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file() or path.is_symlink() or '__pycache__' in path.parts:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel in (BUNDLE.name,BUNDLE_SHA.name,MANIFEST.name,BUNDLE.name+'.tmp'):
            continue
        if path.suffix in ('.rpm','.deb','.xz') and not rel.startswith('evidence/packaging/'):
            continue
        if rel.startswith(('scripts/','evidence/')) or '/' not in rel:
            if rel.startswith('evidence/elf/tools/gnu/') or rel=='evidence/elf/raw-comparison.json':
                continue
            if rel.startswith('evidence/elf/tools/') and (path.name.endswith('.out') or path.name.endswith('.err')):
                continue
            yield path
        elif rel.startswith(('work/A/home/','work/B/home/','work/replay/home/')):
            if path.suffix in ('.o','.ko','.mod','.map') or path.name in ('Makefile','kdbus.mod.c'):
                yield path


def seal():
    result,matrix = audit()
    SUMMARY.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    write_csv(MATRIX,matrix)
    for req in REQUIRED:
        require((ROOT/req).stat().st_size>0,f'Incomplete deliverable {req}')
    files = list(eligible())
    records, canonical = [],{}
    for p in files:
        name = p.relative_to(ROOT).as_posix()
        sha = digest(p)
        identity = (sha, p.stat().st_mode&0o777)
        records.append(dict(path=name,sha256=sha,bytes=p.stat().st_size,archive_alias=canonical.get(identity,'')))
        canonical.setdefault(identity,name)
    write_csv(MANIFEST,records)
    verify_links()
    tmp = BUNDLE.with_name(BUNDLE.name+'.tmp')
    with tarfile.open(tmp,'w:gz',compresslevel=5) as archive:
        for record in records:
            name = record['path']
            if alias := record['archive_alias']:
                entry=archive.gettarinfo(str(ROOT/name),arcname=name)
                entry.type,entry.linkname,entry.size=tarfile.LNKTYPE,alias,0
                archive.addfile(entry)
            else:
                archive.add(ROOT/name,arcname=name,recursive=False)
        archive.add(MANIFEST,arcname=MANIFEST.name,recursive=False)
    tmp.replace(BUNDLE)
    BUNDLE_SHA.write_text(f'{digest(BUNDLE)}  {BUNDLE.name}\n')
    verify()


def verify():
    result,matrix = audit()
    require(data(SUMMARY)==result,'Summary does not match preserved measurements')
    require(read_rows(MATRIX)==[{k:str(v) for k,v in row.items()} for row in matrix],'Build matrix mismatch')
    verify_links()
    require(BUNDLE_SHA.read_text()==f'{digest(BUNDLE)}  {BUNDLE.name}\n','Bundle SHA256 mismatch')
    expected={r['path']:r for r in read_rows(MANIFEST)}
    verified={}
    with tarfile.open(BUNDLE,'r|gz') as archive:
        for member in archive:
            if member.name==MANIFEST.name:
                require(archive.extractfile(member).read()==MANIFEST.read_bytes(),'Archive manifest mismatch')
                continue
            require(member.name in expected, f'Archive has undeclared member {member.name}')
            match=expected.pop(member.name)
            require(digest(ROOT/member.name)==match['sha256'],f'Workspace evidence hash mismatch {member.name}')
            if member.islnk():
                require(member.linkname==match['archive_alias'] and verified.get(member.linkname)==match['sha256'],
                        f'Archive alias mismatch {member.name}')
            else:
                require(member.isreg() and member.size==int(match['bytes']) and
                        hashlib.file_digest(archive.extractfile(member),'sha256').hexdigest()==match['sha256'],
                        f'Archive file mismatch {member.name}')
            verified[member.name]=match['sha256']
    require(not expected,'Missing archive evidence')


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('stage', choices=('seal','verify'))
    args=cli.parse_args()
    (seal if args.stage=='seal' else verify)()
    print('PASS: Phase 12 measurements, A/B/C/D matrix, Markdown links and evidence bundle')


if __name__=='__main__':
    main()
