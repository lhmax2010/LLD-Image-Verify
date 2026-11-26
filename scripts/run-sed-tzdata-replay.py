#!/usr/bin/env python3
"""Fetch the historical RPMs, replay sed/tzdata and regenerate their evidence tables."""
import argparse
import csv
import gzip
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = ROOT / 'results/2026-11-23-unresolved'
BASE = 'https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base-Toolchain/'
sys.path.insert(0, str(ROOT / 'share/tizen-lld-verify'))
from verify import fetch


def rpm_index(area, work):
    info = fetch(area + 'repodata/repomd.xml', work / 'repomd.xml')
    node = ET.parse(info).find(".//{*}data[@type='primary']")
    sha = node.find('{*}checksum')
    if sha.get('type') != 'sha256':
        raise ValueError('Unexpected repodata checksum algorithm')
    primary = fetch(urljoin(area, node.find('{*}location').get('href')),
                    work / 'primary.xml.gz', sha.text)
    with gzip.open(primary) as stream:
        return {(p.findtext('{*}name'), p.findtext('{*}arch')): (
            p.find('{*}location').get('href'), p.findtext('{*}checksum'))
            for p in ET.parse(stream).getroot().findall('{*}package')}


def main(args):
    output = Path(tempfile.mkdtemp(prefix='sed-tzdata-replay.', dir=ROOT / 'results'))
    scratch = Path(tempfile.mkdtemp(prefix='sed-tzdata-replay.'))
    print(f'Results {output}\nScratch {scratch}', flush=True)
    for round_name, snapshot, gbs, images in (
        ('latest', '20261119.042539', args.latest_gbs, args.latest_images),
        ('qb1234653', '20261117.165617', args.old_gbs, args.old_images),
    ):
        repo = f'{BASE}tizen-base-toolchain_{snapshot}/repos/standard/'
        packages = rpm_index(repo + 'packages/', scratch / round_name)
        with (PREVIOUS / f'{round_name}-remaining.tsv').open() as stream:
            candidates = list(csv.DictReader(stream, delimiter='\t'))
        for arch in ('aarch64', 'armv7l'):
            root = gbs / f'gbs-{arch}/local/BUILD-ROOTS/scratch.{arch}.0'
            image = images / f'extracted/tizen-headed-{arch}/rootfs'
            inputs = scratch / round_name / arch
            for name in ('tzdata', 'sed'):
                log = ROOT / f'evidence/2026-11-23/{round_name}/logs/base/{arch}/{name}.txt.gz'
                with gzip.open(log, 'rt') as stream:
                    source_rpm, = re.findall(r'Wrote: .*/SRPMS/(.*\.src\.rpm)', stream.read())
                srpm = fetch(repo + f'source/{source_rpm}', inputs / source_rpm)
                href, digest = packages[(name, arch)]
                runtime_url = urljoin(repo + 'packages/', href)
                rows = [r for r in candidates if r['image'] == f'tizen-headed-{arch}'
                        and r['source'].endswith('/' + name)]
                expected_urls = {r['runtime_rpm_url'] for r in rows}
                if expected_urls != {runtime_url}:
                    raise ValueError((href, expected_urls))
                runtime = fetch(runtime_url, inputs / Path(href).name, digest)
                expected_vcs, = {r['source'] + '#' + r['source_commit'] for r in rows}
                for rpm in (srpm, runtime):
                    vcs = subprocess.check_output(['rpm', '-qp', '--qf', '%{VCS}', rpm], text=True)
                    if vcs != expected_vcs:
                        raise ValueError(f'{rpm}: expected {expected_vcs}, got {vcs}')
                command = [sys.executable, ROOT / 'scripts/replay-sed-tzdata.py', name,
                           '--root', root, '--srpm', srpm, '--rpm', runtime, '--build-log', log,
                           '--image-root', image, '--work', inputs / name,
                           '--output', output / round_name / arch / name]
                if name == 'sed':
                    href, digest = packages[('compiler-rt', arch)]
                    rt = fetch(urljoin(repo + 'packages/', href), inputs / Path(href).name, digest)
                    command += ['--compiler-rt', rt]
                subprocess.run(command, check=True)
    subprocess.run([sys.executable, ROOT / 'scripts/reconcile-sed-tzdata.py',
                    '--previous', PREVIOUS, '--proofs', output], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('latest-images', 'old-images', 'latest-gbs', 'old-gbs'):
        parser.add_argument('--' + field, type=Path, required=True)
    main(parser.parse_args())
