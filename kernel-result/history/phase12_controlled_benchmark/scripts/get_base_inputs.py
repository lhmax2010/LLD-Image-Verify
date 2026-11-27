#!/usr/bin/env python3
"""Resolve exact packages from the archived QB Base repository and verify each payload."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent / 'kernel_lld_verification_20261125/evidence/build/base'
CACHE = ROOT / 'work/rpms'
EVIDENCE = ROOT / 'evidence/toolchain'


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('packages', nargs='+', metavar='NAME:ARCH')
    cli.add_argument('--receipt', default='base-inputs')
    cli.add_argument('--unified', action='store_true', help='use the pinned Unified QB packages area')
    options = cli.parse_args()
    requested = [tuple(x.rsplit(':', 1)) for x in options.packages]
    base_url = 'https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base-Toolchain/tizen-base-toolchain_20261030.120529/repos/standard/packages/'
    meta, manifest = BASE / 'primary.xml.gz', BASE / 'repomd.out'
    if options.unified:
        repo = BASE.parent.parent / 'repository'
        meta, manifest = repo / 'packages-primary.out', repo / 'packages-repomd.out'
        base_url = 'https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261125.130358/repos/standard/packages/'
    repomd = ET.parse(manifest).find(".//{*}data[@type='primary']")
    assert sha(meta) == repomd.findtext('{*}checksum')
    plain = gzip.decompress(meta.read_bytes())
    assert hashlib.sha256(plain).hexdigest() == repomd.findtext('{*}open-checksum')
    index = {}
    for pkg in ET.fromstring(plain).findall('{*}package'):
        key = (pkg.findtext('{*}name'), pkg.findtext('{*}arch'))
        if key in requested:
            assert key not in index
            index[key] = pkg
    CACHE.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    def acquire(key):
        if key not in index:
            return {'requested': key, 'status': 'NOT_IN_BASE_PRIMARY'}
        pkg = index[key]
        href = pkg.find('{*}location').get('href')
        path = CACHE / Path(href).name
        exact = BASE / 'rpms' / path.name
        expected = pkg.findtext('{*}checksum')
        url = base_url + href
        command = ['curl','-fLsS','--retry','2','--max-time','180','-o', str(path),url]
        if exact.is_file() and not path.exists():
            shutil.copyfile(exact, path)
        code = 0
        if not path.is_file() or sha(path) != expected:
            code = subprocess.run(command, cwd=ROOT, check=False).returncode
        actual = sha(path) if path.is_file() else None
        return {'requested': key, 'path': str(path.relative_to(ROOT)), 'url': url,
                'version': pkg.find('{*}version').attrib, 'expected_sha256': expected,
                'actual_sha256': actual, 'fetch_argv': command, 'fetch_exit': code,
                'status': 'PASS' if not code and actual == expected else 'FAIL'}
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(acquire, requested))
    (EVIDENCE / (options.receipt + '.json')).write_text(json.dumps(results, indent=2) + '\n')
    for row in results:
        print(row['requested'], row['status'], row.get('path', ''))
    if any(r['status'] != 'PASS' for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
