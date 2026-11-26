"""Match the inspected image ELFs to public debug RPMs using debuglink CRCs."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from csv import DictReader
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zlib

import scan_images as scanner
from config import SOURCES, WORK

ROOTS = {name: root + 'repos/standard/debug/' for name, root in SOURCES.items()}


def repo_index(repo):
    primary = {}
    raw = WORK / 'raw'
    with gzip.open(raw / f'{repo}-debug-primary.xml.gz') as f:
        for p in ET.parse(f).getroot():
            href = p.find('{*}location').get('href')
            sha = p.findtext('{*}checksum')
            primary[sha] = (repo, href, sha, int(p.find('{*}size').get('package')))
    with gzip.open(raw / f'{repo}-debug-filelists.xml.gz') as f:
        for p in ET.parse(f).getroot():
            pkg = primary.get(p.get('pkgid'))
            if not pkg or p.get('arch') not in {'aarch64', 'armv7l'}:
                continue
            for item in p.findall('{*}file'):
                if item.get('type') != 'dir' and item.text.endswith('.debug'):
                    yield (p.get('arch'), item.text), pkg


def plan(rows):
    by_path = defaultdict(set)
    for repo in ROOTS:
        for key, pkg in repo_index(repo):
            by_path[key].add(pkg)
    requests = defaultdict(lambda: defaultdict(set))
    for row in rows:
        path = PurePosixPath(row['path'])
        arch = {'aarch64': 'aarch64', 'arm': 'armv7l'}.get(row['machine'])
        if not arch:
            continue
        name, crc, build_id = row.get('debuglink',''), row.get('debug_crc',''), row['build_id']
        if not name and not build_id:
            continue
        candidates = set()
        if name:
            parents = {str(path.parent)}
            parent = str(path.parent)
            parents.add(parent.removeprefix('/usr') if parent.startswith('/usr/') else '/usr' + parent)
            if row['partition'] in {'ramdisk', 'ramdisk-recovery'}:
                parent = parent.removeprefix('/mnt/initrd-recovery').removeprefix('/mnt/initrd')
                parents.update({parent, parent.removeprefix('/usr') if parent.startswith('/usr/') else '/usr'+parent})
            for parent in parents:
                candidates.add(f'/usr/lib/debug{parent.rstrip("/")}/{name}')
        if build_id:
            candidates.add(f'/usr/lib/debug/.build-id/{build_id[:2]}/{build_id[2:]}.debug')
        for key in candidates:
            for pkg in by_path[(arch, key)]:
                requests[pkg][key].add((row['sha256'], crc, build_id))
    return requests


def skip(stream, size):
    while size:
        data = stream.read(min(size, 256 * 1024))
        if not data:
            raise EOFError('Truncated cpio')
        size -= len(data)


def inspect_rpm(path, candidates):
    with subprocess.Popen(['rpm2cpio', path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
        f = proc.stdout
        while True:
            h = f.read(110)
            if not h:
                break
            if len(h) != 110 or h[:6] not in (b'070701', b'070702'):
                raise ValueError('Invalid cpio header')
            mode = int(h[14:22], 16)
            size = int(h[54:62], 16)
            length = int(h[94:102], 16)
            name = f.read(length)[:-1].decode(errors='replace')
            skip(f, -(110 + length) % 4)
            if name == 'TRAILER!!!':
                break
            name = '/' + name.removeprefix('./').lstrip('/')
            if mode & 0xf000 == 0x8000 and size and name.endswith('.debug'):
                think = candidates.get(name, set())
                # Matching IDs can name symlinks, so inspect the real debug entries as well.
                if not think:
                    think = {x for values in candidates.values() for x in values if x[2]}
                if think:
                    with tempfile.SpooledTemporaryFile(max_size=2**20) as data:
                        check = 0
                        remaining = size
                        while remaining:
                            block = f.read(min(remaining, 256 * 1024))
                            if not block:
                                raise EOFError('Truncated debug file')
                            remaining -= len(block)
                            data.write(block)
                            check = zlib.crc32(block, check)
                        guesses = [x for x in think if not x[1] or x[1] == f'{check:08x}']
                        if guesses:
                            data.seek(0)
                            item = scanner.scan_elf(data)
                            if item:
                                for file_hash, crc, build_id in guesses:
                                    if build_id and build_id != item[5]:
                                        continue
                                    yield file_hash, {
                                        'debug_path': name, 'crc': f'{check:08x}', 'build_id': item[5],
                                        'linker': item[2], 'evidence': item[3], 'comments': item[4],
                                    }
                else:
                    skip(f, size)
            else:
                skip(f, size)
            skip(f, -size % 4)
        if proc.wait() != 0:
            raise RuntimeError(f'rpm2cpio failed on {path}')


def run(pkg, candidates):
    repo, href, digest, size = pkg
    folder = WORK / 'debug-cache' / repo
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / PurePosixPath(href).name
    if not path.is_file():
        temp = path.with_suffix('.part')
        subprocess.run(['curl', '-fsSL', '--connect-timeout', '12', '-m', '300',
                        '--retry', '2', ROOTS[repo] + href, '-o', temp],
                       check=True, capture_output=True)
        temp.rename(path)
    with path.open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != digest:
            raise ValueError(f'{path} sha256 mismatch')
    return [(key, entry | {'rpm': ROOTS[repo] + href, 'repo': repo})
            for key, entry in inspect_rpm(path, candidates)]


def match_arch(arch, profiles, jobs):
    rows = []
    for profile in profiles:
        if arch in profile:
            with (WORK / 'observed' / f'{profile}.tsv').open() as source:
                rows.extend(DictReader(source, delimiter='\t'))
    tasks = plan(rows)
    print(f'{arch}: {len(tasks)} candidate debug RPMs ({sum(p[3] for p in tasks) / 10**6:.1f} MB)',
          flush=True)
    results = WORK / f'debug-matches-{arch}.jsonl'
    errors = WORK / f'debug-errors-{arch}.jsonl'
    failures = 0
    with results.open('w') as out, errors.open('w') as err, ThreadPoolExecutor(jobs) as pool:
        futures = {pool.submit(run, pkg, files): pkg
                   for pkg, files in sorted(tasks.items(), key=lambda item: item[0][3])}
        for number, future in enumerate(as_completed(futures), start=1):
            try:
                for key, entry in dict(future.result()).items():
                    out.write(json.dumps({'sha256': key, **entry}) + '\n')
            except (OSError, ValueError, EOFError, RuntimeError, subprocess.SubprocessError) as exc:
                pkg = futures[future]
                message = exc.stderr.decode(errors='replace').strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
                err.write(json.dumps({'rpm': ROOTS[pkg[0]] + pkg[1], 'error': message}) + '\n')
                failures += 1
            if number % 100 == 0 or number == len(futures):
                print(f'{arch}: {number}/{len(futures)} debug RPMs processed', flush=True)
    return results, failures
