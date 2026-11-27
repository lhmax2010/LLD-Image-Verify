#!/usr/bin/env python3
"""Verify published boot-profile package membership and compare image payload bytes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import tarfile

from record import ROOT, run
from repository import REPO, RELEASE, SNAPSHOT, SNAPSHOT_URL, command_ok, digest, fetch, rel

IMAGE = REPO / 'images'
BOOT_RPMS = ('arm-rpi4-linux-kernel', 'arm-rpi4-linux-kernel-modules', 'linux-tizen-modules-rpi4')
PROFILES = {'boot': 'tizen-boot-armv7l-rpi', 'headed': 'tizen-headed-armv7l'}
MTOOLS_PACKAGE = 'mtools_4.0.43-1build1_amd64.deb'

def ensure_raw(stem, url, refresh):
    path = REPO / f'{stem}.out'
    if refresh or not path.is_file() or not command_ok(stem):
        if fetch(stem, url):
            raise OSError(f'Could not retrieve {url}; see {stem}.err')
    return path

def profile_inputs(name, profile, refresh):
    base_url = f'{SNAPSHOT_URL}images/standard/{profile}/'
    prefix = f'{SNAPSHOT}_{profile}'
    index = ensure_raw(f'{name}-image-profile', base_url, refresh)
    sums = ensure_raw(f'{name}-SHA256SUMS', base_url+'SHA256SUMS', refresh)
    expected = {f.strip('*'): sha for sha, f in
                (line.split(maxsplit=1) for line in sums.read_text().splitlines() if line.strip())}
    urls = {'manifest': 'manifest.json', 'packages': f'{prefix}.packages',
            'ks': f'{prefix}.ks', 'log': f'{prefix}.log'}
    collected = {
        key: ensure_raw(f'{name}-{key}', base_url+filename, refresh) for key, filename in urls.items()
    }
    receipts = {}
    for key, path in collected.items():
        checksum = digest(path)
        published = expected.get(urls[key])
        receipts[key] = {
            'url': base_url+urls[key], 'path': rel(path), 'sha256': checksum,
            'published_sha256': published,
            'checksum_result': ('PASS' if checksum == published else 'MISMATCH') if published else 'NOT_PUBLISHED',
        }
        if published and checksum != published:
            raise ValueError(f'{path} has invalid SHA256')
    packages = [
        {'line': number, 'text': line} for number, line in
        enumerate(collected['packages'].read_text().splitlines(), 1)
        if line.split() and line.split()[0] in {f'{rpm}.armv7l' for rpm in BOOT_RPMS}
    ]
    return {
        'profile': profile, 'index': rel(index), 'checksum_evidence': rel(sums),
        'published_inputs': receipts, 'partitions': json.loads(collected['manifest'].read_text())['loop']['partitions'],
        'target_package_lines': packages,
    }, base_url, expected, prefix

def read_payload_digests(row):
    rpm = row['rpm_path']
    qf = '%{FILEDIGESTALGO}\n[%{FILENAMES}\t%{FILEDIGESTS}\n]'
    rc, out = run('repository/image-rpm-payload-'+row['name'],
                  ['rpm', '-qp', '--qf', qf, rpm])
    if rc:
        raise OSError(f'Could not read RPM file digest headers: {rpm}')
    algorithm, *lines = out.read_text().splitlines()
    if algorithm != '8':
        raise ValueError(f'Unexpected RPM file digest algorithm {algorithm}')
    return dict(line.split('\t') for line in lines if '\t' in line), rel(out)

def obtain_mcopy():
    installed = shutil.which('mcopy')
    if installed:
        return installed, None
    package = IMAGE / MTOOLS_PACKAGE
    if not package.is_file():
        rc, _ = run('repository/boot-apt-mtools', [
            'bash', '-c', 'cd evidence/repository/images && apt-get download mtools=4.0.43-1build1',
        ])
        if rc:
            return None, None
    extracted = IMAGE / 'mtools'
    rc, _ = run('repository/boot-mtools-unpack', ['dpkg-deb', '-x', rel(package), rel(extracted)])
    cmd = extracted / 'usr/bin/mcopy'
    if rc or not cmd.is_file():
        return None, None
    run('repository/boot-mtools-version', [rel(cmd), '-V'])
    return rel(cmd), {'path': rel(package), 'sha256': digest(package)}

def extract_boot(archive, names):
    """Copy only fixed regular files out of the published tarball."""
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        for name in names:
            matches = [member for member in members if member.name == name and member.isfile()]
            if len(matches) != 1:
                raise ValueError(f'Expected one regular published image member {name}')
            with tar.extractfile(matches[0]) as source, (IMAGE / name).open('wb') as target:
                shutil.copyfileobj(source, target)

def compare_boot_image(published, boot_url, checksums, prefix, refresh):
    file = f'{prefix}.tar.gz'
    archive = IMAGE / file
    if refresh or not archive.is_file() or digest(archive) != checksums[file]:
        if fetch('boot-archive', boot_url+file, archive, seconds=240):
            raise OSError('Boot archive download failed')
    sha = digest(archive)
    if sha != checksums[file]:
        raise ValueError('Boot archive checksum mismatch')
    run('repository/boot-archive-members', ['tar', '-tvf', rel(archive)])
    extract_boot(archive, ['boot.img', 'modules.img'])
    scope = json.loads((ROOT / '02_repository_identity.json').read_text())
    entries = {row['name']: row for row in scope['selected_rpms']}
    boot_digests, boot_digest_evidence = read_payload_digests(entries[BOOT_RPMS[0]])
    kernel = '/boot/zImage'
    mcopy, tool = obtain_mcopy()
    zpath = IMAGE / 'published-zImage'
    mcopy_exit = 127
    if mcopy:
        mcopy_exit, _ = run('repository/boot-mcopy-zimage', [
            mcopy, '-o', '-i', rel(IMAGE / 'boot.img'), '::/zImage', rel(zpath)])
    zsha = digest(zpath) if mcopy_exit == 0 else None
    reports = {
        'archive': {'url': boot_url+file, 'path': rel(archive), 'sha256': sha,
                    'published_sha256': checksums[file], 'checksum_result': 'PASS',
                    'members_evidence': 'evidence/repository/boot-archive-members.out'},
        'partition_images': {name: {'path': rel(IMAGE / name), 'sha256': digest(IMAGE / name)}
                             for name in ('boot.img', 'modules.img')},
        'kernel': {
            'rpm_name': BOOT_RPMS[0], 'rpm_file': kernel,
            'rpm_file_sha256': boot_digests[kernel], 'rpm_digest_evidence': boot_digest_evidence,
            'image_file': '::/zImage', 'extracted_path': rel(zpath) if zsha else None,
            'image_file_sha256': zsha, 'local_tool_source': tool,
            'tool_exit_status': mcopy_exit,
            'comparison': ('EXACT_SHA256' if zsha == boot_digests[kernel] else 'MISMATCH') if zsha else 'UNVERIFIABLE',
        },
    }
    inputs = []
    for name in BOOT_RPMS[1:]:
        digests, evidence = read_payload_digests(entries[name])
        for path, sha in digests.items():
            if f'/modules/{RELEASE}/' in path and any(path.endswith(ext) for ext in ('.ko', '.ko.gz', '.ko.xz', '.ko.zst')):
                inputs.append((name, path, sha, evidence))
    inputs.sort(key=lambda item: item[1])
    image = rel(IMAGE / 'modules.img')
    def compare(entry):
        item, parts = entry
        name, path, sha, evidence = parts
        in_image = path.split('/modules', 1)[1]
        rc, out = run(f'repository/image-module-{item:03d}',
                      ['debugfs', '-R', 'cat '+in_image, image])
        observed = digest(out) if not rc else None
        return {
            'rpm_name': name, 'rpm_path': path, 'rpm_digest_evidence': evidence,
            'rpm_sha256': sha, 'image_path': in_image, 'image_file_sha256': observed,
            'image_extracted_evidence': rel(out), 'exit_status': rc,
            'comparison': ('EXACT_SHA256' if sha == observed else 'MISMATCH') if not rc else 'UNVERIFIABLE',
        }
    with ThreadPoolExecutor(max_workers=6) as threads:
        files = list(threads.map(compare, enumerate(inputs, 1)))
    reports['modules'] = {
        'total': len(files),
        'exact_sha256': sum(file['comparison'] == 'EXACT_SHA256' for file in files),
        'files': files,
    }
    published['boot_archive_verification'] = reports
    return published

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles-only', action='store_true', help='Do not download or inspect the boot archive.')
    parser.add_argument('--refresh', action='store_true', help='Refetch the exact published indexes and boot archive.')
    args = parser.parse_args()
    result = {}
    for name, profile in PROFILES.items():
        details, url, checksums, prefix = profile_inputs(name, profile, args.refresh)
        if name == 'boot' and not args.profiles_only:
            details = compare_boot_image(details, url, checksums, prefix, args.refresh)
        result[name] = details
    result['limitation'] = 'The published profile and filesystem image are host evidence. This comparison does not read the device boot volume or prove on-device RPM database ownership.'
    (REPO / 'image-profile-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    if args.profiles_only:
        return 0
    boot = result['boot']['boot_archive_verification']
    print(boot['kernel']['comparison'], boot['modules']['exact_sha256'], boot['modules']['total'])
    return int(boot['kernel']['comparison'] != 'EXACT_SHA256' or not boot['modules']['total']
               or boot['modules']['exact_sha256'] != boot['modules']['total'])

if __name__ == '__main__':
    raise SystemExit(main())
