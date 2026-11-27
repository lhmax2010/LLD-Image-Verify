#!/usr/bin/env python3
"""Verify hashes, file references, coverage denominators and identity claims."""
import argparse
from collections import Counter
import csv
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote

from analyze_artifacts import CATEGORIES, ROOT, sha

SELF = {'SHA256SUMS','COMMANDS.jsonl','evidence/preflight/self-check.out',
        'evidence/preflight/self-check.err','evidence/preflight/self-check.cmd.json'}
DELIVERABLES = (
    '00_preflight.md','00_preflight.json','01_runtime_kernel.md','01_runtime_kernel.json',
    '02_repository_inventory.md','02_kernel_rpm_inventory.csv','02_repository_identity.json',
    '03_kernel_binary_analysis.md','03_kernel_binary_inventory.csv','03_kernel_linker_evidence.json',
    '04_kernel_config_analysis.md','04_build_command_analysis.md','04_build_evidence.json',
    '05_kernel_module_analysis.md','05_kernel_module_inventory.csv','05_kernel_module_coverage.json',
    '05_loaded_module_mapping.csv','06_repository_runtime_mapping.md','06_identity_verification.json',
    'KERNEL_LLD_VERIFICATION_REPORT.md','KERNEL_LLD_VERIFICATION_REPORT.html','KERNEL_LLD_VERIFICATION_SUMMARY.json',
    'VERIFICATION_METHOD.md','COMMANDS.jsonl','SHA256SUMS',
)

def require(condition, message):
    if not condition:
        raise ValueError(message)

def files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink()
                  and '__pycache__' not in p.parts)

def from_root(path):
    return path.relative_to(ROOT).as_posix()

def load(path):
    return json.loads((ROOT/path).read_text())

def entries(path):
    with (ROOT/path).open(newline='') as data:
        return list(csv.DictReader(data))

def create_catalog():
    count = 0
    with (ROOT/'COMMANDS.jsonl').open('w') as result:
        for receipt in files():
            rel = from_root(receipt)
            if not rel.endswith('.cmd.json') or rel in SELF:
                continue
            details = load(rel)
            sibling = rel.removesuffix('.cmd.json')
            details['record'] = rel
            details['stdout'] = sibling+'.out'
            details['stderr'] = sibling+'.err'
            result.write(json.dumps(details, ensure_ascii=False)+'\n')
            count += 1
    with (ROOT/'SHA256SUMS').open('w') as result:
        for file in files():
            rel = from_root(file)
            if rel not in SELF-{'COMMANDS.jsonl'}:
                result.write(f'{sha(file)}  {rel}\n')
    return count

def check_files(recompute=True):
    index = {}
    for line in (ROOT/'SHA256SUMS').read_text().splitlines():
        expected, path = line.split('  ',1)
        absolute = ROOT/path
        require(path not in index and absolute.is_file() and not absolute.is_symlink() and absolute.resolve().is_relative_to(ROOT),
                f'invalid or duplicated SHA256 manifest path {path}')
        require(re.fullmatch(r'[0-9a-f]{64}',expected), f'not a SHA256 entry for {path}')
        if recompute:
            require(sha(absolute)==expected, f'SHA256 mismatch for {path}')
        index[path] = expected
    uncovered = {from_root(p) for p in files()}-index.keys()-SELF
    require(not uncovered, f'unhashed regular files: {sorted(uncovered)}')
    for path in DELIVERABLES:
        require((ROOT/path).is_file() and (ROOT/path).stat().st_size > 0, f'missing or empty deliverable: {path}')
    count = 0
    for line in (ROOT/'COMMANDS.jsonl').read_text().splitlines():
        row = json.loads(line)
        for key in ('record','stdout','stderr'):
            require(row[key] in index, f'command receipt file missing: {row[key]}')
        require(isinstance(row['exit_status'],int), f'bad exit status: {row["record"]}')
        argv = row.get('argv', [])
        if argv[:1]==['sdb'] and row['record'].startswith('evidence/runtime/'):
            require(len(argv)==5 and argv[1:4]==['-s','private-address-02:26101','shell'],
                    f'non-audited runtime transport {row["record"]}')
            require(not re.search(r'(^|[;&|\n])\s*(?:mount|umount|reboot|insmod|rmmod|modprobe|rpm\s+-(?:i|U|e)|dd)(?:\s|$)', argv[4]),
                    f'unexpected runtime state-changing command {row["record"]}')
        count += 1
    return len(index), count

class Hrefs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.paths.extend(v for k,v in attrs if k=='href')

def check_ref(raw, source):
    if not raw or raw.startswith(('http://','https://','mailto:','#')):
        return
    for value in raw.split(' | '):
        target = unquote(value.split('#',1)[0])
        target = re.sub(r':\d+(?:[-–]\d+)?$', '', target)
        section = re.split(r'\s+\.(?:comment|modinfo)(?:\+.*)?$', target)[0]
        if section.startswith('evidence/') or re.fullmatch(r'(?:0[0-6]_[^/]+|KERNEL_[^/]+|COMMANDS|VERIFICATION_METHOD)\.(?:md|csv|json|jsonl|html)|SHA256SUMS|scripts/\S+',section):
            require((ROOT/section).exists() or section=='evidence/preflight/self-check.out',
                    f'{source}: missing evidence {section}')

def json_refs(data, source):
    if isinstance(data,str):
        check_ref(data,source)
    elif isinstance(data,dict):
        for value in data.values():
            json_refs(value,source)
    elif isinstance(data,list):
        for value in data:
            json_refs(value,source)

def check_formats():
    paths = list(ROOT.glob('*.json'))
    for path in paths:
        json_refs(json.loads(path.read_text()),path.name)
    for path in ROOT.glob('*.md'):
        for ref in re.findall(r'\]\(([^()\s]+)\)',path.read_text()):
            check_ref(ref,path.name)
    html = Hrefs()
    html.feed((ROOT/'KERNEL_LLD_VERIFICATION_REPORT.html').read_text())
    require(len(html.paths) >= 20, 'HTML report failed to render links/table content')
    for ref in html.paths:
        check_ref(ref,'HTML')
    phase_flags = load('00_preflight.json')['checks']
    require(all({key for key in ('status','evidence','limitation','next_action')} <= set(i) for i in phase_flags),
            'preflight check fields incomplete')
    return len(paths)

def check_coverage():
    counts = load('05_kernel_module_coverage.json')
    sources = entries('05_kernel_module_inventory.csv')
    per_source = {}
    for source in ('repository','device'):
        part = [row for row in sources if row['scope']==source]
        per_source[source] = part
        summary = counts[source]
        total = len(part)
        classes = Counter(row['classification'] for row in part)
        parsed = sum(row['parsed']=='True' for row in part)
        require(total and total==sum(classes.values())==summary['total_module_files'], f'{source}: denominator mismatch')
        require(set(classes)<=set(CATEGORIES) and all(classes[key]==summary['counts'][key] for key in CATEGORIES),
                f'{source}: classification totals differ')
        require(all(row['reason'] for row in part),f'{source}: missing classification reason')
        require(all(row['evidence_type'] and row['evidence_location'] and row['raw_evidence'] and
                    row['proves_final_link']=='False' for row in part if row['classification']=='LLD_INDICATED'),
                f'{source}: weak indication trace')
        require(parsed==summary['successfully_parsed'] and parsed/total==summary['elf_parsing_coverage'] and
                classes['LLD_CONFIRMED']/total==summary['confirmed_lld_coverage'] and
                (classes['LLD_CONFIRMED']+classes['LLD_INDICATED'])/total==summary['lld_evidence_coverage'],
                f'{source}: coverage arithmetic failed')
        for row in part:
            require(sha(ROOT/row['file'])==row['raw_sha256'] and sha(ROOT/row['representative_elf'])==row['elf_sha256'],
                    f'{source}: per-module recorded hash mismatch {row["path"]}')
            check_ref(row['evidence_location'],row['path'])
    mod_report = (ROOT/'05_kernel_module_analysis.md').read_text()
    for key in CATEGORIES:
        expected_line = f'| {key} | {counts["repository"]["counts"][key]} | {counts["device"]["counts"][key]} |'
        require(expected_line in mod_report, f'Markdown class count diverges for {key}')
    repo = {(row['path'],row['rpm']): row for row in per_source['repository']}
    equal = 0
    for row in per_source['device']:
        if row['repository_identity']=='EXACT_PATH_AND_SHA256':
            equal += 1
            base = repo[row['repository_path'],row['repository_rpm']]
            require(row['raw_sha256']==base['raw_sha256'], f'module SHA256 differs for {row["path"]}')
    require(equal==counts['device_repo_mapping_counts']['EXACT_PATH_AND_SHA256'], 'module identity count mismatch')
    loaded = entries('05_loaded_module_mapping.csv')
    require(len(loaded)==counts['runtime_loaded'] and
            dict(Counter(r['live_installed_build_id_comparison'] for r in loaded))==counts['live_module_build_id_counts'],
            'runtime module map count mismatch')
    return f'{len(repo)} repository, {len(per_source["device"])} installed, {len(loaded)} loaded'

def check_identity():
    repo = load('02_repository_identity.json')
    inv = entries('02_kernel_rpm_inventory.csv')
    selected = [row for row in inv if row['selected']=='True']
    require(len(selected)==len(repo['selected_rpms']) and len(inv)==repo['candidate_rpm_count'],
            'RPM CSV and JSON mismatch')
    for row in selected:
        require(sha(ROOT/row['rpm_path'])==row['sha256']==row['metadata_checksum'] and
                row['rpm_digest_verification']=='PASS',f'RPM integrity failure {row["name"]}')
    ident = load('06_identity_verification.json')
    static = load('03_kernel_linker_evidence.json')
    z = next(x for x in static['binaries'] if x['path']=='/boot/zImage')
    public = load('evidence/repository/image-profile-verification.json')['boot']['boot_archive_verification']
    require(sha(ROOT/z['file'])==ident['repository_zimage_sha256']==sha(ROOT/public['kernel']['extracted_path']),
            'zImage byte identity mismatch')
    payload = (ROOT/ident['repo_raw_kernel_payload']).read_bytes()
    note = (ROOT/ident['runtime_notes']['evidence']).read_bytes()
    offset = ident['runtime_notes']['raw_offset']
    require(ident['status']=='EXACT_MATCH' and offset>=0 and payload[offset:offset+len(note)]==note,
            'runtime note does not exactly match zImage payload')
    require(bytes.fromhex(ident['runtime_build_id']) in note,'build ID missing from runtime notes')
    summary = load('KERNEL_LLD_VERIFICATION_SUMMARY.json')
    require(summary['modules']==load('05_kernel_module_coverage.json') and summary['identity']==ident and
            summary['overall_status']=='CONDITIONAL_PASS' and not summary['acceptance_close_ready'] and
            not summary['kernel']['independent_final_link_evidence'] and
            all(summary['gates'][key]['status']=='CONDITIONAL_PASS' for key in ('B','D')),
            'final summary or Gate B/D verdict diverges from evidence')
    return len(selected), len(inv), ident['runtime_build_id']

def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('--seal', action='store_true', help='Refresh command index and SHA256 manifest before verification')
    opt = args.parse_args()
    if opt.seal:
        create_catalog()
    hashed, commands = check_files(recompute=not opt.seal)
    structured = check_formats()
    modules = check_coverage()
    selected, candidates, build_id = check_identity()
    print(f'PASS: {hashed} SHA256 entries, {commands} command receipts, {structured} root JSON files.')
    print(f'PASS: {selected} selected RPMs from {candidates} candidates. Module denominators: {modules}.')
    print(f'PASS: {build_id} exact runtime note match. Gate B/D preserve the historical final-link gap.')

if __name__=='__main__':
    main()
