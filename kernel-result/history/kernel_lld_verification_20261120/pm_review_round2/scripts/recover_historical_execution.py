#!/usr/bin/env python3
"""Bounded historical Ker­nel command recovery from sealed inputs and the exact public snapshot."""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import urljoin

from inspect_historical_linker import OUT, LOGS, ROOT, check_originals, digest, manifest_hashes, run, write_data

SNAPSHOT = ('https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/'
            'tizen-unified-toolchain_20261120.082536/')
CATALOG = (
    'evidence/repository/publication-build.out',
    'evidence/repository/manifest.out',
    'evidence/build/builddata-index.out',
    'evidence/build/buildlogs-armv7l-index.out',
    'evidence/build/profiling-default-index.out',
    'evidence/build/rejected-local-gbs-candidate.out',
)
ENDPOINTS = {
    'profiling-result-meta': 'builddata/profiling_reports/standard/armv7l/sample_data/datasets/default/result_meta.json',
    'buildinfo-index-probe': 'builddata/buildinfo/',
    'buildroot-index-probe': 'builddata/buildroots/',
    'artifact-index-probe': 'builddata/artifacts/',
}
MEMBER = re.compile(r'(?:(?:^|/)\.vmlinux(?:\.unstripped|\.o)?\.cmd$|'
                    r'\.ko\.cmd$|/include/generated/compile\.h$|/include/config/auto\.conf$|/\.config$)')
DIRECT = re.compile(r'(?:^|\s)(?:/\S+/)?(?:ld\.lld|ld\.bfd|\S*-linux-\S*ld|ld)\s+[^A-Z\[]'
                    r'|(?:^|[^_.A-Za-z])(?:PATH|LD|LD_LIBRARY_PATH)\s*=')

def refs(relative, line_nums):
    return [f'round1/{relative}#L{n}' for n in line_nums]

def selected_rpms(base):
    meta = json.loads((base/'02_repository_identity.json').read_text())
    return [row['rpm_path'] for row in meta['selected_rpms'] if row['name'] in (
        'arm-rpi4-linux-kernel', 'arm-rpi4-linux-kernel-devel',
        'arm-rpi4-linux-kernel-modules', 'arm-rpi4-linux-kernel-devel-debuginfo',
        'linux-tizen-modules-rpi4',
    )]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--round1', required=True, type=Path)
    parser.add_argument('--probe-public', action='store_true')
    ns = parser.parse_args()
    base = ns.round1.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    originals = CATALOG + LOGS
    check_originals(base, manifest_hashes(base), originals)
    direct_hits = {}
    roots = []
    retained = {}
    for tag, rel in zip(('kernel','external'), LOGS):
        lines = (base/rel).read_text(errors='replace').splitlines()
        root_line = next((i,line) for i,line in enumerate(lines,1) if 'Using BUILD_ROOT=' in line)
        roots.append(root_line[1].split('Using BUILD_ROOT=',1)[1])
        direct_hits[tag] = [{'line':i,'raw':line} for i,line in enumerate(lines,1) if DIRECT.search(line)]
        packages = r'(?:keeping|cumulate|installing)\s+(?:gcc-|binutils-|llvm-|clang-|libllvm-|qemu-linux-user-|rpm-build-)'
        wanted = [i for i,line in enumerate(lines,1) if re.search(packages,line) or (
            i <= 20 or re.search(r'binfmt|.*\bexport LLVM=1$|.*\bexport .*MAKEFLAGS',line))]
        (OUT/f'{tag}-buildroot-excerpts.txt').write_text(
            f'Full original file round1/{rel}\nSHA256 {digest(base/rel)}\n\n' +
            '\n'.join(f'{i:05d}\t{lines[i-1]}' for i in wanted)+'\n')
        retained[tag] = {'source': 'round1/'+rel, 'sha256': digest(base/rel), 'lines': len(lines),
                         'command_mentions_candidate_review': direct_hits[tag],
                         'build_root': refs(rel,[root_line[0]]),
                         'build_dependency_excerpt': f'evidence/recovery/{tag}-buildroot-excerpts.txt'}
    build_paths = run('exact-local-build-roots',['stat','--',*roots,'/home/abuild/rpmbuild'],allowed=(0,1))
    built = selected_rpms(base)
    if len(built) != 5:
        raise ValueError(f'Unexpected set of selected binary, devel, debug and module packages: {built}')
    dep = []
    for rpm in built:
        label = 'rpm-command-record-members-'+Path(rpm).name.removesuffix('.rpm')
        listing = run(label,['bash','-o','pipefail','-c',
            'rpm -qpl "$1" | grep -E "(^.*/)([.]vmlinux([.]unstripped|[.]o)?[.]cmd|[^/]+[.]ko[.]cmd|include/generated/compile[.]h|include/config/auto[.]conf|[.]config)$" || [[ ${PIPESTATUS[0]} -eq 0 ]]',
            '--',base/rpm]).splitlines()
        if any(not MEMBER.search(p) for p in listing):
            raise ValueError(f'Unexpected RPM listing match: {rpm}')
        dep.append({'round1_rpm_path':rpm,'matching_members':listing,
                    'sha256':manifest_hashes(base)[rpm],
                    'evidence':f'evidence/recovery/{label}.out'})
    queries = []
    for label,path in ENDPOINTS.items():
        url = urljoin(SNAPSHOT,path)
        if ns.probe_public:
            run(label,['curl','-fLsS','--max-time','16','-D',OUT/(label+'.headers'),url],allowed=(0,22,28))
        receipt_path = OUT/(label+'.cmd.json')
        header_path = OUT/(label+'.headers')
        if receipt_path.exists():
            hdr = header_path.read_text(errors='replace') if header_path.exists() else ''
            status = re.findall(r'^HTTP/\S+\s+(\d+)',hdr,re.M)
            queries.append({'url':url,'http_status':int(status[-1]) if status else None,
                            'receipt':f'evidence/recovery/{label}.cmd.json',
                            'headers':f'evidence/recovery/{label}.headers',
                            'data':f'evidence/recovery/{label}.out'})
    outcome = dict(
        status='HISTORICAL_EXECUTION_EVIDENCE_UNAVAILABLE',
        scope='Search confined to recorded published job roots, pinned snapshot publication/catalog, five relevant RPMs, and sealed prior local candidate comparison.',
        snapshot='tizen-unified-toolchain_20261120.082536',
        target='standard/armv7l non-RT RPi4, 6.12.80-arm-rpi4-v7l',
        retrieved=dict(
            generated_headers_and_config=[e for r in dep for e in r['matching_members'] if not e.endswith('.cmd')],
            exact_public_success_logs=retained,
            rbs_build_metadata='round1/evidence/repository/publication-build.out',
            rbs_project_manifest='round1/evidence/repository/manifest.out',
            toolchain_package_provenance='evidence/recovery/base-selected-packages.json',
            original_build_root_paths=roots,
        ),
        unresolved=['verbatim linker argv / full verbose log','historical PATH or process environment dump',
                    '.vmlinux.cmd','.vmlinux.o.cmd','.vmlinux.unstripped.cmd',
                    'arch/arm/boot/compressed/.vmlinux.cmd','*.ko.cmd',
                    'historical process executable and QEMU dispatch','matching private worker archive'],
        local_scope={'exact_paths': roots + ['/home/abuild/rpmbuild'],
                     'receipt':'evidence/recovery/exact-local-build-roots.cmd.json',
                     'stdout':build_paths,'prior_candidate':'round1/evidence/build/rejected-local-gbs-candidate.out'},
        archive_membership=dep, public_probes=queries,
        catalog=[{'path':'round1/'+ref,'sha256':digest(base/ref)} for ref in CATALOG],
        continuation='Causal analysis may use shipped rules and matched observations. Do not turn a reconstruction into direct execution evidence.',
    )
    cmd = [m for r in dep for m in r['matching_members'] if m.endswith('.cmd')]
    if cmd:
        raise ValueError(f'Historical recovered command recording must be evaluated, found: {cmd}')
    write_data(ROOT/'08_02_historical_evidence_recovery.json',outcome)
    print(outcome['status'])

if __name__=='__main__':
    main()
