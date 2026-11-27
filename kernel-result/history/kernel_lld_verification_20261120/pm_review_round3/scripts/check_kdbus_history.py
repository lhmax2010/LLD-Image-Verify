#!/usr/bin/env python3
"""Read only sealed archives for evidence of the historical non-RT kdbus.o link."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
from time import monotonic
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent.parent
REL = '6.12.80-arm-rpi4-v7l'
MODULE_PATH = f'/lib/modules/{REL}/extra/kdbus/kdbus.ko'
PACKAGE = 'linux-tizen-modules-rpi4-11.0.0-0.armv7l.rpm'
SRC_RPM = 'linux-tizen-modules-11.0.0-0.src.rpm'
PROVIDER_RPM = 'linux-tizen-modules-source-11.0.0-0.armv7l.rpm'
HIST_LOG = 'evidence/build/linux-tizen-modules-armv7l.out'
REPO_MODULE = (f'evidence/kernel_binary/payload/{PACKAGE.removesuffix(".rpm")}'
               f'/files{MODULE_PATH}')
DEVICE_MODULE = 'evidence/runtime/installed-files/usr' + MODULE_PATH
INTERMEDIATE = re.compile(r'(?:\.?kdbus[.]o(?:[.](?:cmd|debug|xz|zst|gz))?|[.]kdbus[.]ko[.]cmd)\Z')
KO_WITH_DEBUG = re.compile(r'kdbus[.]ko(?:[.]debug|[.]dwo|[.]dwp)\Z')
LOG_LINK = re.compile(r'\]\s+LD \[M\]\s+(\S+/kdbus/kdbus[.](?:o|ko))\s*$')
REAL_COMMAND = re.compile(r'(?:^|\s)(?:[/\w.+-]*[/\s])?(?:[\w.+-]*-)?(?:ld[.]lld|ld[.]bfd|ld)\s')
TRACE = re.compile(r'\b(?:execve(?:at)?|bpftrace|strace|perf trace|LD_PROGRAM)\b|[.]kdbus[.]o[.]cmd|\bV=1\b')

def need(condition, message):
    if not condition:
        raise RuntimeError(message)

def sha(path):
    with path.open('rb') as src:
        return hashlib.file_digest(src, 'sha256').hexdigest()

def read_json(path):
    return json.loads(path.read_text())

def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')

def seal(path):
    return {name: digest for digest, name in
            (line.strip().split(None, 1) for line in path.read_text().splitlines())}

def pinned(root, manifest, rel):
    path = root / rel
    digest = sha(path)
    need(digest == manifest[rel], f'sealed archive SHA256 differs for {rel}')
    return {'archive_path': rel, 'sha256': digest, 'size': path.stat().st_size}

def copy_pinned(root, manifest, rel, path, out):
    metadata = pinned(root, manifest, rel)
    shutil.copyfile(root / rel, path)
    return dict(metadata, evidence=path.relative_to(out).as_posix())

def run(out, name, *cmd):
    base = out / name
    started = datetime.now(timezone.utc).isoformat()
    tick = monotonic()
    with base.with_suffix('.out').open('wb') as logs, base.with_suffix('.err').open('wb') as errs:
        result = subprocess.run(cmd, stdout=logs, stderr=errs, check=False)
    save_json(base.with_suffix('.cmd.json'), {
        'argv': list(map(str, cmd)), 'cwd': str(Path.cwd()), 'started_utc': started,
        'elapsed_seconds': round(monotonic()-tick, 3), 'exit_status': result.returncode})
    need(result.returncode == 0, f'command failed, see {name}.cmd.json')
    return base.with_suffix('.out').read_text()

def xml_package_index(path, module_id):
    result = []
    debuginfo_ids = (
        f'/usr/lib/debug/.build-id/{module_id[:2]}/{module_id[2:]}',
        f'/usr/lib/.build-id/{module_id[:2]}/{module_id[2:]}',
    )
    with gzip.open(path, 'rb') as stream:
        context = ET.iterparse(stream, events=('start','end'))
        _, root = next(context)
        for kind, item in context:
            if kind != 'end' or item.tag.rsplit('}',1)[-1] != 'package':
                continue
            name = item.get('name') or item.findtext('{*}name')
            arch = item.get('arch') or item.findtext('{*}arch')
            version = item.find('{*}version')
            if name is None or version is None:
                root.remove(item)
                continue
            files = [entry.text for entry in item.iter()
                     if entry.tag.rsplit('}',1)[-1] == 'file' and entry.text is not None]
            candidates = [entry for entry in files if (
                INTERMEDIATE.fullmatch(PurePosixPath(entry).name)
                or KO_WITH_DEBUG.fullmatch(PurePosixPath(entry).name)
                or entry in debuginfo_ids or entry.removesuffix('.debug') in debuginfo_ids)]
            scope = (name.startswith('linux-tizen-modules') and arch in {'armv7l','src','noarch'}
                     and (version.get('ver'),version.get('rel')) == ('11.0.0','0'))
            if scope or candidates:
                result.append({'name':name, 'arch':arch, 'version':version.attrib,
                               'files_total':len(files),
                               'kdbus_files':[file for file in files if 'kdbus' in file],
                               'intermediate_or_debug_candidates':candidates,
                               'location':item.find('{*}location').get('href')
                                          if item.find('{*}location') is not None else None})
            root.remove(item)
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-root',type=Path,default=HERE.parent)
    parser.add_argument('--output',type=Path,default=HERE)
    args=parser.parse_args()
    root=args.archive_root.resolve()
    out=args.output.resolve()
    path=out/'evidence/history'
    path.mkdir(parents=True,exist_ok=True)
    round2=root/'pm_review_round2'
    sealed=seal(root/'SHA256SUMS')
    sealed2=seal(round2/'BUNDLE_SHA256SUMS')
    original=pinned(root,sealed,HIST_LOG)
    mirror=copy_pinned(round2,sealed2,'evidence/external/external-buildlog-full.out',path/'published-buildlog.out',out)
    need(original['sha256']==mirror['sha256'],'external build logs differ')
    previous=copy_pinned(round2,sealed2,'08_02_historical_evidence_recovery.json',path/'round2-recovery.json',out)
    bfd=copy_pinned(round2,sealed2,'evidence/external/historical-binutils-resolution.json',path/'binutils-resolution.json',out)
    lld=copy_pinned(round2,sealed2,'08_06_historical_linker_resolution.json',path/'lld-resolution.json',out)
    root_make=copy_pinned(round2,sealed2,'evidence/external/source/Makefile',path/'external-top-makefile.txt',out)
    kernel_build=copy_pinned(round2,sealed2,'evidence/kernel/source/scripts/Makefile.build',path/'kbuild-object-rule.txt',out)
    log=(root/HIST_LOG).read_text().splitlines()
    need('keeping binutils-2.43-1.8' in log[436] and 'export LLVM=1' in log[564],
         'historical context lines changed')
    quiet=[]
    expanded=[]
    trace=[]
    for number,line in enumerate(log,1):
        match=LOG_LINK.search(line)
        if match:
            quiet.append({'line':number,'target':match[1], 'raw':line,
                          'variant':'non-RT' if number<664 else 'RT'})
        if 'kdbus.o' in line and REAL_COMMAND.search(line):
            expanded.append({'line':number,'raw':line})
        if TRACE.search(line):
            trace.append({'line':number,'raw':line})
    need([item['line'] for item in quiet]==[612,636,709,733], 'quiet kdbus steps changed')
    scope_lines=[2,6,437,477,485,494,509,531,534,537,555,565,566,572,574,575,576,
                 *range(603,616),635,636,637,643,645,657,658,664,667,709,733,754,755,
                 775,776,777,784,807,808,851,852,853,854,867]
    (path/'kdbus-buildlog-excerpts.txt').write_text(
        '\n'.join(f'{number:>4} {log[number-1]}' for number in scope_lines)+'\n')
    pkg_metadata=pinned(root,sealed,'evidence/repository/rpms/'+PACKAGE)
    src_metadata=pinned(root,sealed,'evidence/repository/rpms/'+SRC_RPM)
    source_provider=pinned(round2,sealed2,'evidence/external/'+PROVIDER_RPM)
    payload=run(path,'target-rpm-members','rpm','-qp','--qf',
                '[%{FILENAMES}\t%{FILEDIGESTS}\n]',root/pkg_metadata['archive_path'])
    source=run(path,'source-rpm-members','rpm','-qpl',root/src_metadata['archive_path'])
    provider=run(path,'source-provider-members','rpm','-qpl',round2/source_provider['archive_path'])
    payload_rows=dict(line.split('\t') for line in payload.splitlines() if line)
    module=pinned(root,sealed,REPO_MODULE)
    device=pinned(root,sealed,DEVICE_MODULE)
    need(module['sha256']==device['sha256']==payload_rows[MODULE_PATH], 'final .ko digests differ')
    hdr=run(path,'final-ko-readelf','readelf','-hSWn','-p','.comment','-p','.gnu_debuglink',root/REPO_MODULE)
    match=re.search(r'Build ID:\s*([0-9a-f]+)',hdr)
    need(match is not None, 'released .ko has no Build ID in readelf')
    module_id=match[1]
    comments=re.search(r"String dump of section '\.comment':\n((?:[ \t]*\[[^\n]+\n)+)",hdr)
    comment_lines=[line.split(']',1)[1].strip() for line in comments[1].splitlines()] if comments else []
    debug_sections=re.findall(r'(?m)^\s*\[\s*\d+\]\s+(\.(?:z?debug\S*|gnu_debuglink|gnu_debugaltlink))\s',hdr)
    all_member_results={}
    for area in ('packages','debug','source'):
        for layout in ('primary','filelists'):
            rel=f'evidence/repository/{area}-{layout}.out'
            all_member_results[area+'-'+layout]=dict(pinned(root,sealed,rel),
                candidates=xml_package_index(root/rel,module_id))
    member_candidates=[
      item for names in [payload_rows, source.splitlines(), provider.splitlines()]
      for item in names if INTERMEDIATE.fullmatch(PurePosixPath(item).name) or
                           KO_WITH_DEBUG.fullmatch(PurePosixPath(item).name)]
    indexed_candidates=[
        {'index': name,'package': row['name'],'arch': row['arch'],'paths':row['intermediate_or_debug_candidates']}
        for name, index in all_member_results.items() for row in index['candidates']
        if row['intermediate_or_debug_candidates']]
    manifest_candidates=[name for name in sealed if INTERMEDIATE.fullmatch(PurePosixPath(name).name)
                         or KO_WITH_DEBUG.fullmatch(PurePosixPath(name).name)]
    no_direct=not any((member_candidates,indexed_candidates,manifest_candidates,expanded,trace))
    need(no_direct, 'direct-candidate evidence surfaced; evaluate before classifying')
    bfd_data=read_json(path/'binutils-resolution.json')
    bfd_elf=bfd_data['executable_paths']
    need(bfd_elf['/usr/bin/ld']['sha256']==bfd_elf['/usr/bin/ld.bfd']['sha256']
         and bfd_elf['/usr/bin/ld']['cpio_hardlink']['inode']==bfd_elf['/usr/bin/ld.bfd']['cpio_hardlink']['inode'],
         'archived binutils candidates differ')
    proof={
        'issue_id':'LLD-KERNEL-001','classification':'BFD_PATH_POSSIBLE',
        'historical_direct_execution':False,
        'scope':{'snapshot':'tizen-unified-toolchain_20261120.082536','target':'standard/armv7l non-RT RPi4',
                 'intermediate':'kdbus/kdbus.o','build_log_line':612,'final_module_log_line':636},
        'published_build_log':{'round1':original,'round2':mirror,'lines':len(log),
                               'quiet_events':quiet,'expanded_intermediate_argv_matches':expanded,
                               'command_or_trace_matches':trace,'excerpts':'evidence/history/kdbus-buildlog-excerpts.txt'},
        'pinned_package_metadata':{'target_rpm':pkg_metadata,'source_rpm':src_metadata,'source_provider':source_provider,
                                   'indices':all_member_results,'indexed_candidates':indexed_candidates,
                                   'selected_payload_candidates':member_candidates,'sealed_paths_candidates':manifest_candidates},
        'unavailable':[
            'exact-build non-RT .kdbus.o.cmd',
            'exact-build standalone kdbus.o (including compressed or debug copy)',
            'verbose or execution log for the non-RT L612 command',
            'historical process executable path, argv and environment',
            'kernel-module kdbus.ko debug companion in archived package metadata',
        ],
        'final_module_observation':dict(module,device_archive=device,
             matched_rpm_payload_path=MODULE_PATH,build_id=module_id,comment=comment_lines,
             debug_sections=debug_sections,evidence='evidence/history/final-ko-readelf.out'),
        'reasoning':{
            'bfd_candidate':bfd,'lld_candidates':lld,'source_assignment':root_make,'kbuild_object_rule':kernel_build,
            'historical_binutils_log_line':437,'logical_linker_name_if_prefix_empty':'ld',
            'bfd_candidate_file_sha256':bfd_elf['/usr/bin/ld']['sha256'],
            'remaining_uncertainty':'No execution record establishes effective CROSS_COMPILE, exact LD, PATH, or actual executable at L612. An effective LD override to ld.lld could produce LLD, with precedence depending on its origin and make options. This remains a hypothetical alternative, not a confirmed path of this historical build.'
        },
        'previous_builder_recovery':previous,
        'rescan_policy':{'prior_failed_url_or_local_search_repeated':False,'new_network_or_rpm_download':False,
                         'historical_build_or_device_contact':False,
                         'closed_scopes_reused':['known local build roots unavailable','private worker archive unavailable',
                            'profiling report contains aggregate metadata', 'published buildinfo/buildroots/artifacts directory probes returned 404']},
    }
    save_json(out/'KDBUS_HISTORICAL_INTERMEDIATE_LINK.json',proof)
    print('PASS: targeted RPM, sealed metadata, historical output and released-module checks completed.')
    print('BFD_PATH_POSSIBLE: no direct record or standalone non-RT object for published L612.')
    print('Matched final .ko SHA256:',module['sha256'],'GNU Build ID:',module_id)
    print('Final module .comment:',comment_lines)

if __name__=='__main__':
    main()
