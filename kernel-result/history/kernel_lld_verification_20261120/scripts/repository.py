#!/usr/bin/env python3
"""Acquire and verify metadata and kernel RPMs in the pinned Tizen snapshot."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

from record import ROOT, run

SNAPSHOT = 'tizen-unified-toolchain_20261120.082536'
SNAPSHOT_URL = f'https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/{SNAPSHOT}/'
BASE = SNAPSHOT_URL + 'repos/standard/'
REPO = ROOT / 'evidence/repository'
RELEASE = '6.12.80-arm-rpi4-v7l'
TARGET_SRPM = 'rpi4-linux-kernel-6.12.80-0.src.rpm'
MODULE_SRPM = 'linux-tizen-modules-11.0.0-0.src.rpm'
AREAS = ('packages', 'debug', 'source')
ITEMS = ('primary', 'filelists')
MODULE_FILE = re.compile(r'\.ko(?:\.(?:gz|xz|zst))?$')
ROOT_PROBES = {
    'http-root': SNAPSHOT_URL.replace('https://', 'http://', 1),
    'https-root': SNAPSHOT_URL,
    'repos': SNAPSHOT_URL + 'repos/',
    'standard': BASE,
    'publication-build': SNAPSHOT_URL + 'build.xml',
    'builddata-index': SNAPSHOT_URL + 'builddata/',
    'image-builddata': SNAPSHOT_URL + 'builddata/images/',
    'images-index': SNAPSHOT_URL + 'images/',
    'images-standard': SNAPSHOT_URL + 'images/standard/',
    'manifest': SNAPSHOT_URL + f'builddata/manifest/{SNAPSHOT}_standard.xml',
    **{f'packages-{arch}': BASE + f'packages/{arch}/' for arch in ('armv7l', 'aarch64', 'x86_64')},
}
PROBES = ROOT_PROBES | {
    f'{area}-{name}': BASE + area + '/' + route
    for area in AREAS
    for name, route in (('index', ''), ('repomd', 'repodata/repomd.xml'),
                        ('signature', 'repodata/repomd.xml.asc'), ('key', 'repodata/repomd.xml.key'))
}

def rel(path):
    return str(path.relative_to(ROOT))

def fetch(stem, url, output=None, seconds=90):
    command = [
        'curl', '-fsSL', '--proto', '=http,https', '--proto-redir', '=https',
        '--connect-timeout', '12', '--max-time', str(seconds), '--retry', '2',
        '--retry-delay', '1', '-D', f'evidence/repository/{stem}.headers',
    ]
    if output:
        command += ['-o', rel(output)]
    return run(f'repository/{stem}', command+[url], seconds * 3 + 5)[0]

def digest(path, algorithm='sha256', opener=Path.open):
    with opener(path, 'rb') as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()

def receipt(stem):
    path = REPO / f'{stem}.cmd.json'
    return json.loads(path.read_text()) if path.exists() else {}

def command_ok(stem):
    return receipt(stem).get('exit_status') == 0

def saved_command(stem, argv, replay):
    if replay:
        return receipt(stem).get('exit_status', 127), REPO / f'{stem}.out'
    return run(f'repository/{stem}', argv)

def http_status(stem):
    path = REPO / f'{stem}.headers'
    if path.exists():
        matches = re.findall(r'^HTTP/\S+\s+(\d{3})', path.read_text(), flags=re.M)
        return int(matches[-1]) if matches else None
    return None

def load_area(area, refresh):
    root = ET.parse(REPO / f'{area}-repomd.out')
    entries = {}
    for datatype in ITEMS:
        data = root.find(f".//{{*}}data[@type='{datatype}']")
        stem = f'{area}-{datatype}'
        path = REPO / f'{stem}.out'
        href = data.find('{*}location').get('href')
        url = urljoin(BASE + f'{area}/', href)
        if refresh or not command_ok(stem) or not path.is_file():
            fetch(stem, url)
        checksum = data.find('{*}checksum')
        open_checksum = data.find('{*}open-checksum')
        compressed_actual = digest(path, checksum.get('type'))
        decompressed_actual = digest(path, open_checksum.get('type'), opener=gzip.open)
        expected_bytes = int(data.findtext('{*}size'))
        verified = (compressed_actual == checksum.text and decompressed_actual == open_checksum.text
                    and path.stat().st_size == expected_bytes)
        entries[datatype] = {
            'url': url, 'path': rel(path), 'size': path.stat().st_size,
            'expected_size': expected_bytes, 'algorithm': checksum.get('type'),
            'metadata_checksum': checksum.text, 'actual_checksum': compressed_actual,
            'open_checksum_algorithm': open_checksum.get('type'),
            'metadata_open_checksum': open_checksum.text, 'actual_open_checksum': decompressed_actual,
            'sha256': digest(path), 'verified': verified,
        }
        if not verified:
            raise ValueError(f'{area}/{datatype} checksum or size mismatch')
    return {
        'repomd_url': PROBES[f'{area}-repomd'],
        'repomd_path': f'evidence/repository/{area}-repomd.out',
        'repomd_sha256': digest(REPO / f'{area}-repomd.out'),
        'repomd_http_status': http_status(f'{area}-repomd'),
        'repomd_signature_http_status': http_status(f'{area}-signature'),
        'repomd_key_http_status': http_status(f'{area}-key'),
        'repomd_signature_verified': False,
        **entries,
    }

def target_payloads():
    # Search the entire binary filelists, independent of package names.
    filelists = gzip.open(REPO / 'packages-filelists.out', 'rb')
    results = {}
    with filelists:
        for _, package in ET.iterparse(filelists, events=('end',)):
            if package.tag.rsplit('}', 1)[-1] != 'package':
                continue
            paths = [f.text for f in package.findall('{*}file') if f.text]
            scoped = [name for name in paths if f'/modules/{RELEASE}/' in name]
            if scoped:
                results[package.get('pkgid')] = {
                    'name': package.get('name'),
                    'arch': package.get('arch'),
                    'matching_paths': len(scoped),
                    'module_paths': [p for p in scoped if MODULE_FILE.search(p)],
                }
            package.clear()
    return results

def choose(name, arch, source_rpm, area, modules, summary):
    if modules:
        return 'TARGET_MODULE_PAYLOAD', True, 'Filelists paths match the observed runtime release.'
    if area == 'source' and (name in {'rpi4-linux-kernel', 'linux-tizen-modules'}):
        return 'SOURCE_RPM', True, 'Source package of a selected target RPM. Build intent and source evidence.'
    if (name.startswith('arm-rpi4-linux-kernel') or name == 'rpi4-linux-kernel-debugsource') and arch == 'armv7l':
        if name == 'arm-rpi4-linux-kernel':
            return 'TARGET_KERNEL_IMAGE', True, 'ARMv7l non-RT RPi4 image. Runtime identity pending ELF/build-ID comparison.'
        if name.endswith('debuginfo'):
            return 'KERNEL_DEBUGINFO', True, 'Debuginfo for ARMv7l non-RT RPi4 kernel development RPM.'
        if name.endswith('debugsource'):
            return 'KERNEL_DEBUGSOURCE', True, 'ARMv7l RPi4 debug sources.'
        if 'devel' in name or name.endswith('headers'):
            return 'KERNEL_DEVELOPMENT', True, 'ARMv7l non-RT RPi4 development artifact.'
        return 'KERNEL_RELATED', True, 'ARMv7l non-RT RPi4 artifact.'
    if 'rpi4' in name and ('rt-linux-kernel' in name or '-rpi4-rt' in name):
        return 'EXCLUDED_RT_VARIANT', False, 'RT variant does not match the observed non-RT release.'
    if 'rpi4' in name and (name.startswith('arm64-') or arch == 'aarch64' or name.endswith('-aarch64')):
        return 'EXCLUDED_ARM64_PAYLOAD', False, 'ARM64 variant, including ARM64 payloads wrapped in an armv7l RPM.'
    if name.startswith(('linux-kernel-bpftool', 'linux-kernel-perf')):
        return 'EXCLUDED_USERSPACE_TOOL', False, 'Userspace BPF/perf tool from the kernel SRPM.'
    if name.startswith('linux-tizen-modules-') and 'rpi4' not in name:
        return 'EXCLUDED_MODULE_SUPPORT_OR_OTHER_PLATFORM', False, 'Other board or supporting source/tool/test. No matching module path in binary filelists.'
    if arch == 'x86_64':
        return 'EXCLUDED_X86_64', False, 'RPM is for x86_64. No matching module path in binary filelists.'
    if source_rpm and source_rpm not in {TARGET_SRPM, MODULE_SRPM}:
        return 'EXCLUDED_OTHER_SOURCE_OR_PLATFORM', False, 'Different source package or hardware flavor. No matching module path in binary filelists.'
    return 'EXCLUDED_ADJACENT_PACKAGE', False, summary

def candidates(payloads):
    rows = []
    for area in AREAS:
        with gzip.open(REPO / f'{area}-primary.out', 'rb') as stream:
            tree = ET.parse(stream)
            for package in tree.findall('{*}package'):
                name = package.findtext('{*}name')
                arch = package.findtext('{*}arch')
                source_rpm = package.findtext('{*}format/{*}sourcerpm') or ''
                checksum = package.find('{*}checksum')
                modules = payloads.get(checksum.text, {}).get('module_paths', [])
                # Preserve candidate decisions for same-source RPMs, alternative kernels
                # across architectures, and external Tizen module package variants.
                relevant = (
                    bool(modules) or source_rpm in {TARGET_SRPM, MODULE_SRPM}
                    or name.startswith('linux-tizen-modules')
                    or 'linux-kernel' in name
                    or re.match(r'^(kernel(?:-|$)|emulator-kernel)', name)
                )
                if not relevant:
                    continue
                version = package.find('{*}version')
                stamp = int(package.find('{*}time').get('build'))
                size = int(package.find('{*}size').get('package'))
                href = package.find('{*}location').get('href')
                category, selected, reason = choose(name, arch, source_rpm, area, modules, package.findtext('{*}summary'))
                rows.append({
                    'category': category, 'selected': selected, 'selection_reason': reason,
                    'name': name, 'epoch': version.get('epoch'), 'version': version.get('ver'),
                    'release': version.get('rel'), 'architecture': arch, 'source_rpm': source_rpm,
                    'build_time_epoch': stamp,
                    'build_time_utc': datetime.fromtimestamp(stamp, timezone.utc).isoformat() if stamp else None,
                    'repository_area': area, 'repository_url': BASE+f'{area}/',
                    'download_url': urljoin(BASE+f'{area}/', href), 'metadata_file_size_bytes': size,
                    'metadata_checksum_algorithm': checksum.get('type'), 'metadata_checksum': checksum.text,
                    'metadata_module_file_count': len(modules),
                    'runtime_match': ('RELEASE_PATH_MATCH' if modules else 'CANDIDATE_PENDING_RUNTIME_IDENTITY') if selected else 'EXCLUDED',
                    'actual_file_size_bytes': None, 'sha256': None, 'metadata_checksum_verification': 'NOT_DOWNLOADED',
                    'rpm_digest_verification': 'NOT_RUN', 'rpm_signature_verification': 'NOT_RUN',
                    'rpm_path': None, 'rpm_header_evidence': None, 'rpm_filelist_evidence': None,
                    'rpm_verify_evidence': None,
                })
    return rows

def download(row, refresh, replay):
    name = Path(row['download_url']).name
    base = f'rpm-{name}'
    path = REPO / 'rpms' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    row['rpm_path'] = rel(path)
    ok = path.is_file() and (
        path.stat().st_size == row['metadata_file_size_bytes']
        and digest(path, row['metadata_checksum_algorithm']) == row['metadata_checksum']
    )
    if replay and not ok:
        row['metadata_checksum_verification'] = 'MISSING_OR_MISMATCH'
        return row
    if refresh or not ok:
        temporary = path.with_suffix('.rpm.part')
        if fetch(base, row['download_url'], temporary, seconds=360):
            row['metadata_checksum_verification'] = 'DOWNLOAD_FAILED'
            row['rpm_path'] = None
            return row
        temporary.replace(path)
    row['actual_file_size_bytes'] = path.stat().st_size
    row['sha256'] = digest(path)
    valid = (row['actual_file_size_bytes'] == row['metadata_file_size_bytes']
             and digest(path, row['metadata_checksum_algorithm']) == row['metadata_checksum'])
    row['metadata_checksum_verification'] = 'PASS' if valid else 'MISMATCH'
    if not valid:
        return row
    qformat = '%{NAME}\t%{EPOCH}\t%{VERSION}\t%{RELEASE}\t%{ARCH}\t%{SOURCERPM}\t%{BUILDTIME}\t%{BUILDHOST}\t%{VCS}\n'
    query_rc, query = saved_command(f'{base}-header', ['rpm', '-qp', '--qf', qformat, rel(path)], replay)
    row['rpm_header_evidence'] = rel(query)
    if not query_rc:
        actual = query.read_text().strip().split('\t')
        expected = [row['name'], row['epoch'], row['version'], row['release'],
                    row['architecture'], row['source_rpm'], str(row['build_time_epoch'])]
        if actual[1] == '(none)':
            actual[1] = '0'
        if actual[5] == '(none)':
            actual[5] = ''
        if row['repository_area'] == 'source' and actual[4] != 'src':
            # Source RPMs can retain the build architecture in RPMTAG_ARCH.
            source_rc, source_header = saved_command(f'{base}-sourcepkg', [
                'rpm', '-qp', '--qf', '%{SOURCEPACKAGE}\n', rel(path)], replay)
            if source_rc == 0 and source_header.read_text().strip() == '1':
                row['rpm_source_build_arch'] = actual[4]
                actual[4] = 'src'
        row['rpm_header_vs_metadata'] = 'PASS' if actual[:7] == expected else 'MISMATCH'
    else:
        row['rpm_header_vs_metadata'] = 'QUERY_FAILED'
    _, listing = saved_command(f'{base}-filelist', ['rpm', '-qpl', rel(path)], replay)
    row['rpm_filelist_evidence'] = rel(listing)
    check_rc, check = saved_command(f'{base}-verify', ['rpm', '-Kv', rel(path)], replay)
    row['rpm_verify_evidence'] = rel(check)
    detail = check.read_text() + check.with_suffix('.err').read_text()
    digests = [line for line in detail.splitlines() if re.search(r'digest:', line, re.I)]
    signature = [line for line in detail.splitlines() if re.search(r'signature', line, re.I)]
    if digests:
        row['rpm_digest_verification'] = 'PASS' if all(line.strip().endswith(': OK') for line in digests) else 'FAILED'
    else:
        row['rpm_digest_verification'] = 'UNAVAILABLE'
    if signature:
        if any(re.search(r'\b(?:NOKEY|NOTTRUSTED)\b', line) for line in signature):
            row['rpm_signature_verification'] = 'UNTRUSTED_OR_KEY_UNAVAILABLE'
        elif all(line.strip().endswith(': OK') for line in signature):
            row['rpm_signature_verification'] = 'PASS_WITH_HOST_KEYS'
        else:
            row['rpm_signature_verification'] = 'FAILED'
    else:
        row['rpm_signature_verification'] = 'NO_SIGNATURE_REPORTED' if not check_rc and digests else 'UNVERIFIABLE'
    return row

def write_results(rows, metadata, payloads):
    selected = [row for row in rows if row['selected']]
    with (ROOT / '02_kernel_rpm_inventory.csv').open('w', newline='') as stream:
        fields = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    manifest = REPO / 'manifest.out'
    manifest_digest = digest(manifest) if command_ok('manifest') else None
    image_evidence = REPO / 'image-profile-verification.json'
    publication_build = REPO / 'publication-build.out'
    details = {
        'snapshot': SNAPSHOT, 'snapshot_url': SNAPSHOT_URL,
        'runtime_release': RELEASE, 'status': 'PASS' if all(
            row['metadata_checksum_verification'] == 'PASS' and row['rpm_digest_verification'] == 'PASS'
            and row.get('rpm_header_vs_metadata') == 'PASS' for row in selected
        ) else 'INCONCLUSIVE',
        'runtime_package_and_binary_identity': 'Repository candidates and release-path selection are recorded here. See 06_identity_verification.json for the final binary identity and runtime RPM limitations.',
        'directory_probes': {
            name: {'url': url, 'http_status': http_status(name),
                   'exit_status': receipt(name).get('exit_status'),
                   'raw_output': f'evidence/repository/{name}.out'}
            for name, url in PROBES.items()
        },
        'manifest_sha256': manifest_digest, 'metadata': metadata,
        'publication_build_evidence': rel(publication_build) if publication_build.is_file() else None,
        'publication_profile_evidence': rel(image_evidence) if image_evidence.is_file() else None,
        'candidate_rpm_count': len(rows), 'excluded_candidate_rpm_count': len(rows)-len(selected),
        'selected_rpms': selected, 'binary_filelists_release_matches': payloads,
        'filelists_scope': f"All binary package filelists. Paths containing '/modules/{RELEASE}/'.",
        'signature_limitation': 'RPM digests and repodata checksums verify consistency. Detached repomd signature and key URLs returned 404. RPM signature verdicts are per selected package.',
        'rpm_build_time_limitation': 'A zero build-time tag is retained as epoch 0 and described as unavailable. It does not establish the historical kernel build time.',
    }
    (ROOT / '02_repository_identity.json').write_text(json.dumps(details, ensure_ascii=False, indent=2)+'\n')
    return details

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--refresh', action='store_true', help='Refetch indexes, metadata and RPMs.')
    mode.add_argument('--replay', action='store_true', help='Recompute inventory with local files and saved RPM command receipts.')
    args = parser.parse_args()
    if args.replay:
        missing = [stem for area in AREAS for stem in
                   (f'{area}-repomd', *(f'{area}-{item}' for item in ITEMS))
                   if not command_ok(stem) or not (REPO / f'{stem}.out').is_file()]
        if missing:
            raise ValueError(f'Missing saved metadata receipts: {missing}')
    with ThreadPoolExecutor(max_workers=6) as threads:
        list(threads.map(lambda item: fetch(*item), [
            (lab, url) for lab, url in PROBES.items()
            if not args.replay and (args.refresh or not (REPO / f'{lab}.cmd.json').exists())
        ]))
        meta = dict(zip(AREAS, threads.map(lambda area: load_area(area, args.refresh), AREAS)))
        payloads = target_payloads()
        rows = candidates(payloads)
        selected = sorted((row for row in rows if row['selected']), key=lambda row: (
            {'TARGET_KERNEL_IMAGE': 0, 'TARGET_MODULE_PAYLOAD': 1, 'SOURCE_RPM': 2,
             'KERNEL_DEBUGINFO': 3, 'KERNEL_DEVELOPMENT': 4}.get(row['category'], 5),
            row['metadata_file_size_bytes']))
        if not selected:
            raise ValueError('Pinned repo selection returned zero RPMs')
        list(threads.map(lambda row: download(row, args.refresh, args.replay), selected))
    details = write_results(rows, meta, payloads)
    for row in selected:
        print(row['metadata_checksum_verification'], row['rpm_digest_verification'],
              row['rpm_signature_verification'], row['category'], row['rpm_path'], flush=True)
    return int(details['status'] != 'PASS')

if __name__ == '__main__':
    raise SystemExit(main())
