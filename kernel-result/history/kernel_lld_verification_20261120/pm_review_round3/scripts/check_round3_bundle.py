#!/usr/bin/env python3
"""Check the Round 3 acceptance matrix, sources and portable package."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parents[1]
TAR='PM_REVIEW_ROUND3_EVIDENCE_BUNDLE.tar.gz'
MANIFEST='BUNDLE_SHA256SUMS'
REQUIRED=(
    'KERNEL_LLD_ENGINEERING_ACCEPTANCE.md','KERNEL_LLD_ENGINEERING_ACCEPTANCE.json',
    'KDBUS_LD_OVERRIDE_ROOT_CAUSE.md','KDBUS_LINKER_VARIABLE_TRACE.json',
    'KDBUS_MINIMAL_REPRODUCTION.md','KDBUS_REPRODUCTION_RESULTS.csv',
    'KDBUS_HISTORICAL_INTERMEDIATE_LINK.md','KDBUS_HISTORICAL_INTERMEDIATE_LINK.json',
    'KDBUS_LD_FIX_PROPOSAL.md','KDBUS_LD_FIX_CANDIDATE.patch',
    'KERNEL_LINKER_OVERRIDE_AUDIT.md','KERNEL_LINKER_OVERRIDE_FINDINGS.csv',
    'FUTURE_KERNEL_LINKER_E4_VERIFICATION_PLAN.md','PM_REVIEW_ROUND3_REPORT.md',
    'PM_REVIEW_ROUND3_SUMMARY.json','PM_REVIEW_ROUND3_EVIDENCE_INDEX.md',
    'reproducer/run.py','reproducer/mock_linker.py')
STATE={
    'ENGINEERING_ACCEPTANCE':'PASS', 'ENGINEERING_SCOPE':'KERNEL_AND_MODULE_FINAL_LINK',
    'STRICT_ACCEPTANCE':'CONDITIONAL_PASS','FULL_INTERMEDIATE_LINK_COVERAGE':'NOT_VERIFIED',
    'HISTORICAL_E4_EVIDENCE':'UNAVAILABLE','KDBUS_INTERMEDIATE_LINK':'OPEN'}
AUDIT_CLASSES={'CONFIRMED_BYPASS','POTENTIAL_BYPASS','SAFE_INHERITANCE','EXPECTED_HOST_TOOL','FALSE_POSITIVE'}

def require(condition,message):
    if not condition:
        raise ValueError(message)

def load(name):
    return json.loads((ROOT/name).read_text())

def read_csv(name):
    with (ROOT/name).open(newline='') as source:
        return list(csv.DictReader(source))

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def allowed_file(path):
    rel=path.relative_to(ROOT)
    return (path.is_file() and not path.is_symlink() and '__pycache__' not in rel.parts and
            rel.parts[0]!='bundle-validation' and rel.name not in (TAR,TAR+'.sha256',MANIFEST))

def verify_report():
    for name in REQUIRED:
        require((ROOT/name).is_file() and (ROOT/name).stat().st_size>0,f'missing {name}')
    a=load('KERNEL_LLD_ENGINEERING_ACCEPTANCE.json')
    summary=load('PM_REVIEW_ROUND3_SUMMARY.json')
    require(all(a[key]==value for key,value in STATE.items()) and summary['decision']==a and
            a['pm_decision']=='APPROVED_AND_CLOSED','invalid PM closure')
    require(a['accepted_primary_target_levels']=={'vmlinux.o':'E3','vmlinux':'E3','ARM Decompressor':'E3'},
            'incorrect primary levels')
    for group,total in (('repository',59),('device',59),('in-tree',52),('out-of-tree',7)):
        row=a['module_coverage'][group]
        require(row==dict(total=total,original_lld_confirmed=0,original_lld_indicated=total,
                          e3_engineering_verified=total,e4_direct_execution_verified=0,
                          e3_plus_e4_engineering_acceptance=1.0),f'invalid coverage {group}')
    for key in ('pm_instruction','prior_summary'):
        asset=a['phase9_pm_instruction'] if key=='pm_instruction' else a[key]
        require(sha(ROOT/asset)==a[key+'_sha256'],f'approval/provenance SHA mismatch {asset}')
    history=load('KDBUS_HISTORICAL_INTERMEDIATE_LINK.json')
    traces=load('KDBUS_LINKER_VARIABLE_TRACE.json')
    require(history['classification']==summary['issue']['historical_result']==traces['historical_classification']=='BFD_PATH_POSSIBLE'
            and history['historical_direct_execution'] is False and summary['issue']['state']=='OPEN','historical claim drift')
    for row in traces['source_anchors'].values():
        source=ROOT/row['file']
        require(sha(source)==row['sha256'] and '\n'.join(
                source.read_text().splitlines()[row['line_start']-1:row['line_end']])==row['original'],
                f'anchored source differs {source}')
    for asset,record in load('evidence/round2-source-bindings.json').items():
        require(sha(ROOT/asset)==record['sha256'],f'matched prior source digest mismatch {asset}')
    by_case=defaultdict(dict)
    for row in read_csv('KDBUS_REPRODUCTION_RESULTS.csv'):
        cases=by_case[row['case']]
        require(row['result']=='PASS' and row['evidence_type']=='ISOLATED_MAKE_MODEL' and row['stage'] not in cases,
                'invalid model observation')
        cases[row['stage']]=row
        argv=json.loads(row['mocked_argv'])
        if row['stage'] in ('intermediate','final'):
            require(argv and argv[0]==row['effective_ld'],'mock argv differs from Make observation')
        else:
            require(not argv,'unexpected mock command outside modeled link')
    require(len(by_case)==21 and all(len(entries)==7 for entries in by_case.values())
            and summary['minimal_reproduction']['observations']==147
            and by_case['historical_shape_control']['intermediate']['effective_ld']=='ld'
            and by_case['historical_shape_control']['final']['effective_ld']=='ld.lld'
            and by_case['remove_ld_armv7l']['intermediate']['effective_ld']=='ld.lld',
            'model result mismatch')
    patch=load('evidence/fix-proposal/patch-dry-run.json')
    require(patch['exit_status']==0 and patch['deleted_lines']==1 and patch['added_lines']==0 and
            patch['source_copy_unchanged'] and sha(ROOT/'KDBUS_LD_FIX_CANDIDATE.patch')==patch['patch_sha256']
            and summary['candidate']['applied_to_product_source'] is False,'patch evidence incorrectly bound')
    findings=read_csv('KERNEL_LINKER_OVERRIDE_FINDINGS.csv')
    counts=Counter(row['classification'] for row in findings)
    require(set(counts)<=AUDIT_CLASSES and counts['CONFIRMED_BYPASS']==0 and counts['POTENTIAL_BYPASS']==1
            and {key:counts[key] for key in AUDIT_CLASSES}==summary['audit']['classification_totals']
            and len(findings)==summary['audit']['source_hit_rows'],'audit rows drift')
    for r in findings:
        path=ROOT/r['source_file']
        require(path.is_file() and r['reason'] and 0<int(r['line_start'])<=int(r['line_end'])<=len(path.read_text().splitlines()),
                f'broken audit row {r["source_file"]}:{r["line_start"]}')
    for file in ROOT.glob('*.md'):
        for match in re.findall(r'\]\(([^()\s]+)\)',file.read_text()):
            ref=unquote(match.split('#',1)[0])
            if ref and not ref.startswith(('https://','http://')):
                chosen=(ROOT/ref).resolve()
                require(chosen.is_relative_to(ROOT) and chosen.exists(),f'broken portable link {file.name}: {ref}')
    print(f'PASS: formal closure and open historical issue, {len(by_case)} model cases, {len(findings)} classified source rows.')

def inputs():
    return [(p.relative_to(ROOT).as_posix(),p) for p in sorted(ROOT.rglob('*')) if allowed_file(p)]

def manifest():
    entries={}
    for line in (ROOT/MANIFEST).read_text().splitlines():
        digest,rel=line.split('  ',1)
        require(rel not in entries and (ROOT/rel).resolve().is_relative_to(ROOT),f'invalid manifest entry {rel}')
        entries[rel]=digest
    return entries

def emit():
    files=inputs()
    (ROOT/MANIFEST).write_text(''.join(f'{sha(p)}  {rel}\n' for rel,p in files))
    with tarfile.open(ROOT/TAR,'w:gz',compresslevel=6) as archive:
        for rel,p in files+[(MANIFEST,ROOT/MANIFEST)]:
            archive.add(p,arcname='pm_review_round3/'+rel,recursive=False)
    (ROOT/(TAR+'.sha256')).write_text(f'{sha(ROOT/TAR)}  {TAR}\n')

def verify_bundle():
    entries=manifest()
    require(set(entries)=={rel for rel,_ in inputs()},'portable file set differs')
    for rel,digest in entries.items():
        require(sha(ROOT/rel)==digest,f'portable SHA256 mismatch {rel}')
    print(f'PASS: {len(entries)} SHA256 entries.')
    if (ROOT/TAR).is_file():
        require(sha(ROOT/TAR)==(ROOT/(TAR+'.sha256')).read_text().split()[0],'archive digest mismatch')
        entries[MANIFEST]=sha(ROOT/MANIFEST)
        seen=set()
        with tarfile.open(ROOT/TAR,'r:gz') as archive:
            for member in archive:
                path=PurePosixPath(member.name)
                require(member.isfile() and path.parts[:1]==('pm_review_round3',) and '..' not in path.parts,'non-regular or unsafe tar member')
                rel=PurePosixPath(*path.parts[1:]).as_posix()
                require(rel in entries and rel not in seen,f'unexpected tar member {rel}')
                with archive.extractfile(member) as stream:
                    require(hashlib.file_digest(stream,'sha256').hexdigest()==entries[rel],f'bits differ in tar {rel}')
                seen.add(rel)
        require(set(entries)==seen,'tar member set differs')
        print(f'PASS: {len(seen)} tar members, {(ROOT/TAR).stat().st_size:,} bytes.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    flags=parser.add_mutually_exclusive_group()
    flags.add_argument('--semantic',action='store_true')
    flags.add_argument('--pack',action='store_true')
    args=parser.parse_args()
    verify_report()
    if args.semantic:
        return
    if args.pack:
        emit()
    verify_bundle()

if __name__=='__main__':
    main()
