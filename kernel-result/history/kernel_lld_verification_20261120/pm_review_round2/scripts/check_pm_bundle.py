#!/usr/bin/env python3
"""Validate portable evidence paths, exact counts and archive member digests."""
import argparse
from collections import Counter
import hashlib
from pathlib import Path, PurePosixPath
import re
import tarfile
from urllib.parse import unquote

from review_common import HERE, csv_rows, load, need, sha

BUNDLE = 'PM_REVIEW_EVIDENCE_BUNDLE.tar.gz'
INDEX = 'BUNDLE_SHA256SUMS'
REQUIRED = (
    '08_01_evidence_integrity_review.md','08_01_evidence_integrity_review.json',
    '08_02_historical_evidence_recovery.md','08_02_historical_evidence_recovery.json',
    '08_03_kernel_linker_selection.md','08_03_linker_variable_trace.json','08_03_linker_rule_matrix.csv',
    '08_04_in_tree_modules.md','08_04_in_tree_modules.csv','08_05_out_of_tree_modules.md','08_05_out_of_tree_modules.csv',
    '08_06_historical_linker_resolution.md','08_06_historical_linker_resolution.json',
    '08_07_build_id_postprocessing_review.md','08_08_evidence_levels.md','08_08_evidence_levels.json',
    '08_09_identity_review.md','08_09_identity_review.json','PM_REVIEW_ROUND2_REPORT.md',
    'PM_REVIEW_ROUND2_SUMMARY.json','PM_REVIEW_EVIDENCE_INDEX.md','PM_REVIEW_GATE_MATRIX.csv',
    'KERNEL_LINKER_RULE_MATRIX.csv','MODULE_LINKER_EVIDENCE_MATRIX.csv','OUT_OF_TREE_MODULES.csv','BUILD_ID_COMPARISON.json',
    'round1/KERNEL_LLD_VERIFICATION_REPORT.md','evidence/PM_TOOL_INPUTS.json'
)

def paths(root):
    for file in sorted(root.rglob('*')):
        relative=file.relative_to(root)
        if relative.parts[0]=='bundle-validation' or file.name in (BUNDLE,BUNDLE+'.sha256',INDEX):
            continue
        if relative.parts[0]=='artifacts' and file.suffix=='.rpm':
            continue
        if file.is_file():
            need(not file.is_symlink() and '__pycache__' not in file.parts,f'unexpected file {file}')
            yield relative,file

def check_semantics(root):
    need(all((root/path).is_file() and (root/path).stat().st_size>0 for path in REQUIRED),'missing requested deliverable')
    summary=load(root,'PM_REVIEW_ROUND2_SUMMARY.json')
    need(summary['overall_status']=='CONDITIONAL_PASS' and summary['engineering_acceptance']=='PASS' and
         summary['historical_evidence_status']=='HISTORICAL_EXECUTION_EVIDENCE_UNAVAILABLE' and
         summary['toolchain']['historical_execve_path'] is None and summary['closure_authority']=='PM',
         'acceptance or historical evidence does not match adjudication')
    rows=csv_rows(root,'MODULE_LINKER_EVIDENCE_MATRIX.csv')
    need(len(rows)==len({row['module_path'] for row in rows})==59 and
         Counter(row['scope'] for row in rows)=={'in-tree':52,'out-of-tree':7} and
         all(row['rpm_payload_sha256']==row['device_sha256'] and row['evidence_level']=='E3' and
             row['original_classification']=='LLD_INDICATED' and row['reason'] and
             row['final_link_argv_observed']=='False' for row in rows),
         '59-row join, digest or evidence level failed')
    for group, expect in (('repository',59),('device',59),('in-tree',52),('out-of-tree',7)):
        cov=summary['module_coverage'][group]
        need(cov['total']==cov['levels']['E3']==expect and sum(cov['levels'].values())==expect and
             cov['original_confirmed_lld']['numerator']==cov['e4_direct_execution']['numerator']==0 and
             cov['e3_plus_e4_engineering_acceptance']['numerator']==expect,f'coverage error {group}')
    gates=csv_rows(root,'PM_REVIEW_GATE_MATRIX.csv')
    need(gates==summary['gates'] and {row['gate'] for row in gates}==set('ABCDE'),'gate matrix differs from summary')
    reasons=summary['plausible_bfd_paths']
    need(len(reasons)==1 and reasons[0]['target']=='kdbus/kdbus.o' and reasons[0]['stage']=='intermediate'
         and not summary['observed_bfd_final_link'],'BFD condition mis-scoped')
    need(summary['kernel_rule_levels']=={row['target']:row['evidence_level'] for row in csv_rows(root,'KERNEL_LINKER_RULE_MATRIX.csv')},
         'kernel matrix differs from summary')
    need((root/'OUT_OF_TREE_MODULES.csv').read_bytes()==(root/'08_05_out_of_tree_modules.csv').read_bytes(),'out-of-tree exports differ')
    log_index=load(root,'evidence/ORIGINAL_BUILD_LOG_INDEX.json')
    for log in log_index:
        file=root/log['local_review_copy']
        need(sha(file)==log['full_log_sha256'] and len(file.read_text().splitlines())==log['line_count'],
             'public log bytes or count differ')
    proof=load(root,'08_01_evidence_integrity_review.json')
    need(len(proof['loaded_modules'])==11 and proof['archive_integrity_replay']['exit_status']==0 and
         load(root,'evidence/round1-offline-replay.cmd.json')['exit_status']==0,'replayed kernel evidence incomplete')
    for path in root.glob('*.md'):
        for match in re.findall(r'\]\(([^()\s]+)\)',path.read_text()):
            ref=unquote(match.split('#',1)[0])
            if not ref or ref.startswith(('https://','http://','mailto:')):
                continue
            resolved=(root/ref).resolve()
            need(resolved.is_relative_to(root) and resolved.exists(),f'stray or missing link in {path.name}: {ref}')
    print('PASS: required files, portable links, 3 complete logs, 59 distinct final .ko rows, 11 runtime IDs and strict/engineering Gates.')

def checksums(root):
    listed={}
    for line in (root/INDEX).read_text().splitlines():
        digest,name=line.split('  ',1)
        need(name not in listed and (root/name).resolve().is_relative_to(root),'invalid manifest path')
        listed[name]=digest
    return listed

def emit(root):
    selected=list(paths(root))
    with (root/INDEX).open('w') as manifest:
        for relative,file in selected:
            manifest.write(f'{sha(file)}  {relative.as_posix()}\n')
    with tarfile.open(root/BUNDLE,'w:gz',compresslevel=6) as tar:
        for relative,file in selected+[(Path(INDEX),root/INDEX)]:
            tar.add(file,arcname='pm_review_round2/'+relative.as_posix(),recursive=False)
    (root/(BUNDLE+'.sha256')).write_text(f'{sha(root/BUNDLE)}  {BUNDLE}\n')

def check_files(root):
    index=checksums(root)
    expected={relative.as_posix() for relative,_ in paths(root)}
    need(set(index)==expected,'portable manifest file set differs')
    for name,digest in index.items():
        need(sha(root/name)==digest,f'portable checksum failure {name}')
    print(f'PASS: {len(index)} portable SHA256 entries.')

def check_tar(root):
    targets=checksums(root)
    targets[INDEX]=sha(root/INDEX)
    archive=root/BUNDLE
    need(sha(archive)==(root/(BUNDLE+'.sha256')).read_text().split()[0],'tar checksum differs')
    checked=set()
    with tarfile.open(archive,'r:gz') as tar:
        for item in tar:
            path=PurePosixPath(item.name)
            need(item.isfile() and path.parts[:1]==('pm_review_round2',) and '..' not in path.parts,'unsafe tar member')
            relative=PurePosixPath(*path.parts[1:]).as_posix()
            need(relative not in checked and relative in targets,f'unexpected tar member {relative}')
            stream=tar.extractfile(item)
            with stream:
                need(hashlib.file_digest(stream,'sha256').hexdigest()==targets[relative],f'tar content mismatch {relative}')
            checked.add(relative)
    need(checked==set(targets),'tar entries missing')
    print(f'PASS: tar has {len(checked)} safe regular entries ({archive.stat().st_size:,} bytes).')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--semantic',action='store_true')
    parser.add_argument('--pack',action='store_true')
    args=parser.parse_args()
    check_semantics(HERE)
    if args.semantic:
        return
    if args.pack:
        emit(HERE)
    check_files(HERE)
    if (HERE/BUNDLE).is_file():
        check_tar(HERE)

if __name__=='__main__':
    main()
