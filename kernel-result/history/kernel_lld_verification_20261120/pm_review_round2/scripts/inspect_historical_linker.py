#!/usr/bin/env python3
"""Inspect pinned Tizen linker RPM payloads without executing them."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

BASE_URL = ('https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Base-Toolchain/'
            'tizen-base-toolchain_20261119.042539/repos/standard/packages/')
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'evidence/recovery'
PRIMARY = (
    ('Base', 'evidence/build/historical-base-index.out', 'evidence/build/historical-base-primary.out'),
    ('Unified', 'evidence/repository/packages-repomd.out', 'evidence/repository/packages-primary.out'),
)
LOGS = (
    'evidence/build/linux-rpi-armv7l.out',
    'evidence/build/linux-tizen-modules-armv7l.out',
)

def digest(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()

def manifest_hashes(baseline):
    pairs = (line.split('  ', 1) for line in (baseline / 'SHA256SUMS').read_text().splitlines())
    return {name: sha for sha, name in pairs}

def check_originals(baseline, hashes, names):
    for name in names:
        if digest(baseline / name) != hashes[name]:
            raise ValueError(f'Sealed original evidence SHA256 mismatch for {name}')

def write_data(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')

def write_evidence(name, data):
    write_data(OUT / name, data)

def run(label, args, allowed=(0,)):
    args = [str(arg) for arg in args]
    started = datetime.now(timezone.utc).isoformat()
    tick = time.monotonic()
    env = {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}
    res = subprocess.run(args, capture_output=True, env=env)
    (OUT / f'{label}.out').write_bytes(res.stdout)
    (OUT / f'{label}.err').write_bytes(res.stderr)
    write_evidence(f'{label}.cmd.json', dict(
        argv=args, cwd=str(Path.cwd()), started_utc=started,
        elapsed_seconds=round(time.monotonic()-tick, 3), exit_status=res.returncode,
    ))
    if res.returncode not in allowed:
        raise ValueError(f'Command {label} failed: {res.returncode}')
    return res.stdout.decode(errors='replace')

def observed(lines, pattern):
    return [dict(line=i, raw=line) for i, line in enumerate(lines, 1) if re.search(pattern, line)]

def records(source, repomd, data):
    root = ET.parse(repomd)
    stanza = root.find("./{*}data[@type='primary']")
    packed = data.read_bytes()
    plain = gzip.decompress(packed)
    hash_packed = hashlib.sha256(packed).hexdigest()
    hash_plain = hashlib.sha256(plain).hexdigest()
    if (stanza.findtext('{*}checksum'), stanza.findtext('{*}open-checksum')) != (hash_packed, hash_plain):
        raise ValueError(f'{source} primary repomd checksum mismatch')
    cursor = ET.fromstring(plain)
    output = []
    for package in cursor.findall('{*}package'):
        arch = package.findtext('{*}arch')
        if arch not in ('armv7l','noarch'):
            continue
        name = package.findtext('{*}name')
        attrs = package.find('{*}version').attrib
        files = [f.text for f in package.findall('./{*}format/{*}file') if f.text]
        names = [f for f in files if Path(f).name in ('ld', 'ld.bfd', 'ld.lld', 'lld')]
        if not names and name not in ('binutils-devel', 'clang', 'libllvm', 'qemu-linux-user-x86_64-cross'):
            continue
        output.append(dict(
            primary=source, name=name, arch=arch, version=attrs['ver'], release=attrs['rel'],
            vcs=attrs.get('vcs'), paths=names, location=package.find('{*}location').get('href'),
            sha256=package.findtext('{*}checksum'), size=int(package.find('{*}size').get('package')),
        ))
    return {'packed_sha256': hash_packed, 'expanded_sha256': hash_plain, 'records': output}

def identify(label, rpm, scratch, package, paths):
    rpm_sha = digest(rpm)
    if rpm.stat().st_size != package['size'] or rpm_sha != package['sha256']:
        raise ValueError(f'Pinned RPM payload SHA256/size mismatch: {rpm}')
    run(label+'-rpm-digest', ['rpm', '-Kv', rpm])
    hdr = run(label+'-rpm-header', ['rpm','-qp','--qf',
        '%{NAME}\t%{ARCH}\t%{VERSION}\t%{RELEASE}\t%{SOURCERPM}\n',rpm]).strip().split('\t')
    if hdr[:4] != [package[key] for key in ('name','arch','version','release')]:
        raise ValueError(f'Package header identity mismatch: {rpm}')
    run(label+'-rpm-scripts', ['rpm','-qp','--scripts',rpm])
    qf = '%{FILEDIGESTALGO}\n[%{FILENAMES}\t%{FILEDIGESTS}\t%{FILELINKTOS}\t%{FILEINODES}\n]'
    pattern = '^(8$|' + '|'.join(re.escape(path) + r'\s' for path in paths) + ')'
    listing = run(label+'-rpm-file-headers', ['bash','-o','pipefail','-c',
        'rpm -qp --qf "$1" "$2" | grep -E "$3"', '--', qf, rpm, pattern]).splitlines()
    payload_hashes = {line.split('\t')[0]:line.split('\t')[1:] for line in listing if '\t' in line}
    if listing[0] != '8' or set(payload_hashes) != set(paths):
        raise ValueError('Unexpected RPM file digest metadata')
    scratch.mkdir(parents=True, exist_ok=True)
    run(label+'-rpm-extract', ['bash','-o','pipefail','-c',
        'rpm2cpio "$1" | cpio -idmu -D "$2" --no-absolute-filenames "$3" "$4"',
        '--', rpm, scratch, *['.'+p for p in paths]])
    location, target = (scratch / p.removeprefix('/') for p in paths)
    if location.is_symlink():
        link = location.readlink().as_posix()
        if location.parent / link != target or payload_hashes[paths[0]][1] != link:
            raise ValueError(f'Unexpected {location} target')
    else:
        link = None
        if target.is_symlink():
            raise ValueError(f'Unexpected {target} symlink')
    binary = {
        'path': paths[0], 'symlink_target': link, 'regular_path': paths[1] if link else paths[0],
        'target_file_sha256': digest(location), 'companion_lld_path': paths[1],
        'companion_lld_sha256': digest(target), 'binary_bytes': location.stat().st_size,
        'same_target_inode_as_companion': location.stat().st_ino == target.stat().st_ino,
        'rpm_file_inodes': [payload_hashes[p][2] for p in paths],
    }
    for path, key in ((paths[1], 'companion_lld_sha256'),(paths[0], 'target_file_sha256')):
        if path != paths[0] or not link:
            if binary[key] != payload_hashes[path][0]:
                raise ValueError(f'Header vs extracted file SHA256 mismatch: {path}')
    binary['file_output'] = run(label+'-file', ['file', '-L', location]).strip()
    elf = run(label+'-readelf', ['readelf','-hWlnd',location])
    binary['elf_class'] = re.search(r'Class:\s+(\S+)', elf)[1]
    binary['machine'] = re.search(r'Machine:\s+([^\n]+)', elf)[1]
    binary['interpreter'] = re.search(r'Requesting program interpreter: ([^\]]+)', elf)[1]
    binary['lib_dependencies'] = re.findall(r'Shared library: \[([^\]]+)\]', elf)
    ver = run(label+'-strings-version', ['bash','-o','pipefail','-c',
        'strings -a "$1" | grep -E "^LLD [0-9]+[.][0-9]+[.][0-9]+$"', '--', location]).splitlines()
    if sorted(set(ver)) != ['LLD 22.1.8']:
        raise ValueError(f'Unexpected linker version markers for {location}: {ver}')
    binary['embedded_version_identification'] = ver
    binary['is_wrapper'] = False
    binary['rpm'] = package | {'source_rpm': hdr[4], 'actual_sha256': rpm_sha}
    binary['receipts_dir'] = 'evidence/recovery'
    binary['receipt_prefix'] = label
    return binary

def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('--round1', required=True, type=Path)
    args.add_argument('--scratch', required=True, type=Path)
    args.add_argument('--fetch-accelerator', action='store_true', help='Retrieve the missing pinned accelerator RPM only')
    ns = args.parse_args()
    b = ns.round1.resolve()
    scratch = ns.scratch.resolve()
    if scratch == b or b in scratch.parents:
        raise ValueError('Use temporary extraction space outside the sealed Round 1 tree')
    OUT.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    hashes = manifest_hashes(b)
    all_originals = [p for _, *paths in PRIMARY for p in paths] + list(LOGS)
    llvm_path = 'evidence/build/historical-base/llvm-22.1.8-1.6.armv7l.rpm'
    check_originals(b, hashes, all_originals + [llvm_path])
    meta = {group:records(group,b/repomd,b/data) for group,repomd,data in PRIMARY}
    logs = {ref:(b/ref).read_text(errors='replace').splitlines() for ref in LOGS}
    for row in [item for entry in meta.values() for item in entry['records']]:
        nevr = f'{row["name"]}-{row["version"]}-{row["release"]}'
        needle = r'(?:keeping|cumulate|installing|replacing|downgrading)\s+' + re.escape(nevr) + r'(?:\s|$)'
        row['observed_jobs'] = {filename: events for filename, lines in logs.items()
                                if (events := observed(lines, needle))}
    write_evidence('base-selected-packages.json', meta)
    selected = {row['name']:row for row in meta['Base']['records'] if row['observed_jobs']}
    lib_names = ('binutils','llvm','clang-accel-x86_64-armv7l','qemu-linux-user-x86_64-cross')
    if set(lib_names) - selected.keys():
        raise ValueError(f'Historical job package retention missing: {set(lib_names) - selected.keys()}')
    x = selected['clang-accel-x86_64-armv7l']
    accel = scratch / Path(x['location']).name
    if not accel.exists() and ns.fetch_accelerator:
        run('accelerator-fetch', ['curl','-fLsS','--max-time','150','--retry','1',
                                  '-o',accel,urljoin(BASE_URL,x['location'])])
    nat = identify('native', b/llvm_path, scratch/'native', selected['llvm'],
                   ('/usr/bin/ld.lld','/usr/bin/lld'))
    acc = identify('accelerated', accel, scratch/'accelerated', x,
                   ('/emul/usr/bin/ld.lld','/emul/usr/bin/lld'))
    for record in (nat, acc):
        record['rpm']['snapshot_url'] = urljoin(BASE_URL, record['rpm']['location'])
    write_data(ROOT/'08_06_historical_linker_resolution.json', dict(
        status='FAMILY_AND_VERSION_VERIFIED_PATH_UNRESOLVED',
        family='LLD', linker_version='22.1.8', selected_linker_candidates=[nat,acc],
        historical_path=None, historical_execve_path=None,
        observed_qemu_binfmt=True, binutils=selected['binutils'],
        candidate_namespace='Base/Unified primary metadata and positive package retention in the two archived ARMv7l jobs',
        historical_execution_evidence='HISTORICAL_EXECUTION_EVIDENCE_UNAVAILABLE',
        proven_behavior='Both named package payloads are LLVM LLD 22.1.8 executable artifacts. No documented branch between them selects GNU BFD.',
        limitation='The shell PATH, QEMU runtime dispatch, process argv and executable actually chosen by the historical link have not been recovered.',
        source_assets=all_originals,
    ))
    print('Native and accelerated historical-package candidates are LLD 22.1.8; exact execution path unresolved.')

if __name__=='__main__':
    main()
