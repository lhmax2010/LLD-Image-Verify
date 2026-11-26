#!/usr/bin/env python3
"""Prepare an isolated source checkout and a snapshot-pinned GBS configuration."""
import argparse
import gzip
from pathlib import Path
import subprocess
import sys
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'share' / 'tizen-lld-verify'))
from verify import fetch

SHA = 'd329cd15f9662c71b0a7214077edb9446d79a254'
SNAPSHOTS = ('20261119.042539', '20261117.165617')
REPO = 'ssh://liushanshan@review.tizen.org:29418/platform/upstream/toybox'


def git(repo, *args):
    subprocess.run(['git', '-C', str(repo), *args], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path, help='New working directory for the diagnostic build')
    parser.add_argument('--snapshot', choices=SNAPSHOTS, default=SNAPSHOTS[0])
    parser.add_argument('--git-url', default=REPO)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    repo = work / 'source'
    repo.mkdir()
    git(repo, 'init', '-q')
    git(repo, 'fetch', '--depth=1', args.git_url, SHA)
    git(repo, 'checkout', '--detach', SHA)
    patch = str(HERE / 'toybox-linker-verbose.patch')
    git(repo, 'apply', '--check', patch)
    git(repo, 'apply', patch)
    git(repo, 'diff', '--check')
    base = ('https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base-Toolchain/'
            f'tizen-base-toolchain_{args.snapshot}/repos/standard/packages/')
    repomd = fetch(base + 'repodata/repomd.xml', work / 'repomd.xml')
    data = ET.parse(repomd).find(".//{*}data[@type='build']")
    buildconf = fetch(urljoin(base, data.find('{*}location').get('href')),
                      work / 'build.conf.gz', data.findtext('{*}checksum'))
    (work / 'build.conf').write_bytes(gzip.decompress(buildconf.read_bytes()))
    (work / 'gbs.conf').write_text(
        '[general]\nprofile = profile.toybox\n\n[profile.toybox]\n'
        f'repos = repo.base\nbuildconf = {work / "build.conf"}\n\n'
        f'[repo.base]\nurl = {base}\n')
    print(f'Prepared {repo} at {SHA}, Base {args.snapshot}, config {work / "gbs.conf"}')


if __name__ == '__main__':
    main()
