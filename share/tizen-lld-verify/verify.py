#!/usr/bin/env python3
"""Verify linker evidence for Tizen QB 1234653 using public artifacts."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from urllib.parse import urljoin
import xml.etree.ElementTree as ET
import zlib

import config
import match_debug
import scan_images
import summarize

SAMPLES = (
    ('deviced', '/usr/bin/deviced'),
    ('wrtjs', '/usr/bin/wrt-loader'),
    ('libtiff', '/usr/{lib}/libtiff.so.6.1.0'),
)
LOGS = ('linux-rpi', 'mesa', 'glib-networking', 'pulseaudio', 'systemd', 'chromium-efl')


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fetch(url, path, expected=None, resume=False):
    if path.is_file():
        if expected is None or sha256(path) == expected:
            return path
        raise ValueError(f'Cached file checksum mismatch: {path}. Remove that file and retry.')
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + '.part')
    command = ['curl', '-fsSL', '--retry', '2', '--connect-timeout', '15', '--max-time', '1800']
    if resume:
        command += ['--continue-at', '-']
    subprocess.run([*command, '-o', str(partial), url], check=True)
    if expected and sha256(partial) != expected:
        raise ValueError(f'Download checksum mismatch: {partial}. Remove that file and retry.')
    partial.rename(path)
    return path


def fetch_image(profile, with_archive):
    folder = config.WORK / 'images' / profile
    root = config.UNIFIED + f'images/standard/{profile}/'
    index = fetch(root + 'SHA256SUMS', folder / 'SHA256SUMS')
    stem = f'{config.BUILD}_{profile}'
    files = {stem + '.packages'}
    if with_archive:
        files.update(('manifest.json', stem + '.tar.gz'))
        if '-boot-' not in profile:
            files.add(stem + '.files')
    discovered = set()
    for record in index.read_text().splitlines():
        digest, name = record.split(maxsplit=1)
        name = name.lstrip('*')
        if name in files:
            print(f'{profile}: verifying {name}', flush=True)
            fetch(root + name, folder / name, digest, resume=name.endswith('.tar.gz'))
            discovered.add(name)
    if missing := files - discovered:
        raise ValueError(f'No SHA256 entry for {profile}: {", ".join(sorted(missing))}')
    return folder


def fetch_metadata(repo, area, types):
    tag = repo if area == 'packages' else f'{repo}-debug'
    root = config.SOURCES[repo] + f'repos/standard/{area}/'
    raw = config.WORK / 'raw'
    repomd = fetch(root + 'repodata/repomd.xml', raw / f'{tag}-repomd.xml')
    tree = ET.parse(repomd)
    for name in types:
        record = tree.find(f".//{{*}}data[@type='{name}']")
        if record is None:
            raise ValueError(f'{repomd}: missing {name} metadata')
        checksum = record.find('{*}checksum')
        if checksum.get('type') != 'sha256':
            raise ValueError(f'{repomd}: unexpected checksum algorithm')
        href = record.find('{*}location').get('href')
        fetch(urljoin(root, href), raw / f'{tag}-{name}.xml.gz', checksum.text)


def fetch_logs(arch):
    folder = config.WORK / 'buildlogs'
    for name in LOGS:
        url = config.UNIFIED + f'builddata/buildlogs/standard/{arch}/succeeded/{name}.buildlog.txt'
        fetch(url, folder / arch / f'{name}.txt')
    url = config.BASE + f'builddata/buildlogs/standard/{arch}/succeeded/glibc.buildlog.txt'
    fetch(url, folder / 'base' / arch / 'glibc.buildlog.txt')


def require_tools(names):
    if missing := [name for name in names if shutil.which(name) is None]:
        raise ValueError('Missing tools: ' + ', '.join(missing) + '. See README.md.')


def inspect_elf(path):
    with path.open('rb') as stream:
        values = scan_images.scan_elf(stream)
    if values is None:
        raise ValueError(f'{path}: expected a native ELF file')
    row = dict(zip(scan_images.FIELDS[3:15], values))
    row.update(path=str(path), partition='rootfs', repository='', source='')
    return row


def crc32_of(path):
    result = 0
    with path.open('rb') as stream:
        while block := stream.read(1 << 20):
            result = zlib.crc32(block, result)
    return f'{result:08x}'


def check_debug(runtime, debug_path):
    debug = inspect_elf(debug_path)
    checksum = crc32_of(debug_path)
    crc = runtime['debug_crc']
    build_id = runtime['build_id']
    check_crc = bool(crc) and crc == checksum
    check_id = bool(build_id) and build_id == debug['build_id']
    if ((crc and not check_crc) or (build_id and debug['build_id'] and not check_id)
            or not (check_crc or check_id) or runtime['machine'] != debug['machine']):
        raise ValueError(f'{debug_path}: debuginfo does not match the runtime ELF CRC or Build ID')
    return {
        'rpm': '', 'debug_path': str(debug_path), 'crc': checksum,
        'linker': debug['linker'], 'evidence': debug['evidence'], 'comments': debug['comments'],
    }


def elf_command(args):
    row = inspect_elf(args.file)
    proof = [check_debug(row, args.debug)] if args.debug else []
    summarize.classify(row, proof, set(), '')
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


def installed_rpms(manifest, arch):
    packages = {}
    for line in manifest.read_text().splitlines():
        fields = line.split(maxsplit=2)
        if len(fields) == 3 and fields[0].endswith('.' + arch):
            name = fields[0].rsplit('.', 1)[0]
            packages[name] = (fields[1], fields[2])
    return packages


def find_runtime_rpm(name, arch, version, vcs):
    for repo, root in config.SOURCES.items():
        metadata = config.WORK / 'raw' / f'{repo}-primary.xml.gz'
        with gzip.open(metadata) as stream:
            tree = ET.parse(stream)
        for p in tree.getroot():
            if p.findtext('{*}name') != name or p.findtext('{*}arch') != arch:
                continue
            attrs = p.find('{*}version').attrib
            if f"{attrs['ver']}-{attrs['rel']}" != version or attrs.get('vcs') != vcs:
                continue
            href = p.find('{*}location').get('href')
            checksum = p.find('{*}checksum')
            if checksum.get('type') != 'sha256':
                raise ValueError(f'Unexpected checksum in {metadata}')
            return repo, urljoin(root + 'repos/standard/packages/', href), checksum.text
    raise ValueError(f'Exact RPM for {name} {arch} {version} {vcs} missing from public repositories')


def extract_one(rpm, path, dest):
    with dest.open('wb') as out, subprocess.Popen(['rpm2cpio', rpm], stdout=subprocess.PIPE) as reader:
        subprocess.run(['cpio', '--quiet', '-i', '--to-stdout', '.' + path, path.lstrip('/')],
                       stdin=reader.stdout, stdout=out, check=True)
        if reader.wait() != 0:
            raise ValueError(f'Could not read the RPM payload: {rpm}')
    if not dest.stat().st_size:
        raise ValueError(f'{path} missing in {rpm}')


def sample_command(args):
    require_tools(('curl', 'rpm2cpio', 'cpio'))
    profile = f'tizen-headed-{args.arch}'
    folder = fetch_image(profile, with_archive=False)
    for repo in config.SOURCES:
        fetch_metadata(repo, 'packages', ('primary',))
        fetch_metadata(repo, 'debug', ('primary', 'filelists'))
    packages = installed_rpms(next(folder.glob('*.packages')), args.arch)
    rows = []
    sample_dir = config.WORK / 'samples' / args.arch
    sample_dir.mkdir(parents=True, exist_ok=True)
    for name, path in SAMPLES:
        path = path.format(lib='lib64' if args.arch == 'aarch64' else 'lib')
        version, vcs = packages[name]
        repo, url, checksum = find_runtime_rpm(name, args.arch, version, vcs)
        rpm = fetch(url, sample_dir / PurePosixPath(url).name, checksum)
        copy = sample_dir / PurePosixPath(path).name
        extract_one(rpm, path, copy)
        row = inspect_elf(copy)
        identity = 'manifest-rpm'
        if args.image_root:
            image_file = args.image_root / path.lstrip('/')
            if sha256(image_file) != row['sha256']:
                raise ValueError(f'Image file differs from selected RPM: {image_file}')
            identity = 'image-file-sha256-matched'
        row.update(path=path, repository=repo, source=vcs.split('#')[0],
                   rpm=f'{name}.{args.arch} {version}', source_commit=vcs.partition('#')[2],
                   runtime_rpm_url=url, image_identity=identity)
        rows.append(row)
    debug = {row['sha256']: [] for row in rows}
    tasks = match_debug.plan(rows)
    for pkg, candidates in tasks.items():
        for key, entry in match_debug.run(pkg, candidates):
            debug[key].append(entry)
    for row in rows:
        summarize.classify(row, debug[row['sha256']], set(), '')
        print(f"{row['path']}\t{row['classification']}\t{row['evidence']}", flush=True)
    out = config.WORK / f'sample-{args.arch}.tsv'
    summarize.write_tsv(out, rows)
    print(f'Saved {out}')
    return 0


def image_command(args):
    names = args.profile or ['tizen-headed-aarch64']
    profiles = config.PROFILES if args.all else tuple(dict.fromkeys(names))
    if args.all and args.profile:
        raise ValueError('Choose --all or --profile, one at a time')
    required = {'curl', 'debugfs'}
    if any('-boot-' in profile for profile in profiles):
        required.add('mcopy')
    if any('-boot-' not in profile for profile in profiles):
        required.update(('unmkinitramfs', 'cpio'))
    if not args.no_debuginfo:
        required.add('rpm2cpio')
    require_tools(sorted(required))
    if sys.version_info < (3, 12):
        raise ValueError('The image command requires Python 3.12 or newer')
    for profile in profiles:
        folder = fetch_image(profile, with_archive=True)
        scan_images.scan_image(folder)
    for repo in config.SOURCES:
        fetch_metadata(repo, 'packages', ('primary', 'filelists'))
        if not args.no_debuginfo:
            fetch_metadata(repo, 'debug', ('primary', 'filelists'))
    arches = [arch for arch in config.ARCHES if any(arch in profile for profile in profiles)]
    debug_results = []
    failures = 0
    for arch in arches:
        fetch_logs(arch)
        if not args.no_debuginfo:
            result, errors = match_debug.match_arch(arch, profiles, args.jobs)
            debug_results.append(result)
            failures += errors
    stats = summarize.run(profiles, debug_results)
    for profile, data in stats['images'].items():
        print(f'{profile}\t' + ', '.join(f'{k}={v}' for k, v in sorted(data['elf'].items())))
    print(f"Saved elf-linker-audit.tsv, rpm-linker-audit.tsv and summary.json in {config.WORK}")
    if failures:
        print(f'{failures} debuginfo RPMs could not be read. See debug-errors-*.jsonl.', file=sys.stderr)
        return 2
    return 0


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, default=config.WORK, help='Cache and result directory')
    commands = parser.add_subparsers(dest='command', required=True)
    elf = commands.add_parser('elf', help='Inspect a local ELF, optionally with a matching .debug file')
    elf.add_argument('file', type=Path)
    elf.add_argument('--debug', type=Path)
    elf.set_defaults(run=elf_command)
    sample = commands.add_parser('sample', help='Check three RPM artifacts selected by the headed image manifest')
    sample.add_argument('--arch', choices=config.ARCHES, default='aarch64')
    sample.add_argument('--image-root', type=Path, help='Compare actual rootfs files with the selected RPMs')
    sample.set_defaults(run=sample_command)
    image = commands.add_parser('image', help='Download and audit published image archives')
    image.add_argument('--profile', choices=config.PROFILES, action='append')
    image.add_argument('--all', action='store_true', help='Scan all six images')
    image.add_argument('--jobs', type=int, choices=range(1, 9), default=2, metavar='1-8',
                       help='Concurrent debuginfo download workers (default 2)')
    image.add_argument('--no-debuginfo', action='store_true', help='Use only image ELF and build log evidence')
    image.set_defaults(run=image_command)
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    config.WORK = args.work_dir.expanduser().resolve()
    for module in (scan_images, match_debug, summarize):
        module.WORK = config.WORK
    try:
        sys.exit(args.run(args))
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError, ET.ParseError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(1)
